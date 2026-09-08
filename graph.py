import os, sys, time, json, requests
if hasattr(sys.stdout, 'reconfigure'): sys.stdout.reconfigure(encoding='utf-8')
from typing import Dict, Any, Optional, List
from langgraph.graph import StateGraph, END
from langgraph.types import interrupt
from state import CryptoAgentState
from exchange import fetch_portfolio_balance, fetch_ticker_price, execute_spot_trade, fetch_top_volume_gainers, get_live_usd_try_rate
from db import (
    log_trade_decision, save_graph_state,
    save_position_to_db, get_active_positions_from_db,
    remove_position_from_db, set_cooldown_in_db,
    get_active_cooldowns_from_db, get_system_setting
)
from prompts import analyze_crypto_news, call_llm_model
from news_service import fetch_live_global_crypto_news
from surge_detector import detect_early_volume_breakouts
from circuit_breaker import get_adaptive_max_slots
from market_regime import check_market_regime
from atr_calculator import calculate_atr_sl_tp

# =====================================================================
# FLOWCHART UYUMLU DÜĞÜM (NODE) TANIMLARI
# =====================================================================

def node_fetch_live_data(state: CryptoAgentState) -> Dict[str, Any]:
    """[A] Canlı piyasa ve haber verileri (Data Ingestion)"""
    print("\n--- [A. NODE: CANLI PİYASA VE HABER VERİLERİ] ---")
    tenant_config = state.get("tenant_config")
    portfolio = fetch_portfolio_balance(tenant_config)
    news_items = fetch_live_global_crypto_news(limit_per_source=2)
    news_text = " | ".join(news_items) if news_items else "Kripto piyasasında likidite dengeli."
    return {"portfolio_state": portfolio, "news_data": news_text}

def node_deterministic_prefilter(state: CryptoAgentState) -> Dict[str, Any]:
    """[B] Deterministik ön filtre (V2 Scalping & Whale Hunting Confirmation Filter)"""
    print("\n--- [B. NODE: V2 DETERMINISTIK ÖN FİLTRE & TEYİT MATRİSİ] ---")
    raw_candidates = detect_early_volume_breakouts()
    tenant_config = state.get("tenant_config") or {}
    tenant_id = str(tenant_config.get("id") or tenant_config.get("telegram_chat_id") or "default_tenant")
    active_cooldowns = get_active_cooldowns_from_db(tenant_id=tenant_id)
    
    from db import get_strategy_config
    strat_cfg = get_strategy_config(use_cache=True)
    active_preset = str(strat_cfg.get("active_preset", "v21_smart_armor")).lower()
    
    from v2_scalping_engine import V2ScalpingEngine
    from v2_whale_engine import V2WhaleHuntingEngine
    from circuit_breaker import check_tenant_circuit_breakers
    
    # Devre Kesici Kontrolü (Circuit Breaker Gate)
    existing_holdings = state.get("portfolio_state", {}).get("holdings_details") or {}
    active_coins_count = len([k for k, v in existing_holdings.items() if str(k).upper() not in ["USDT", "TRY", "BNB", "USDC", "FDUSD"] and (isinstance(v, dict) and v.get("val_usd", 0) > 5.0)]) if isinstance(existing_holdings, dict) else 0
    cb_check = check_tenant_circuit_breakers(tenant_id=tenant_id, current_active_positions_count=active_coins_count)
    if not cb_check.get("passed"):
        print(f"   {cb_check.get('message')}")
        return {"filtered_candidates": []}

    is_scalp = "scalp" in active_preset
    scalp_engine = V2ScalpingEngine(custom_params=strat_cfg)
    whale_engine = V2WhaleHuntingEngine(custom_params=strat_cfg)

    clean_candidates = []
    for c in raw_candidates:
        c_sym = c["symbol"]
        c_base = c_sym.split("/")[0].upper()
        if c_base in active_cooldowns:
            print(f"   ⏳ [Soğuma Kilidi]: {c_base} son işlem sonrası dinlenmede, elendi.")
            continue
            
        # V2.3 Çok Boyutlu Değerlendirme
        try:
            p_val = float(c.get("price", c.get("last_price", 1.0)) or 1.0)
            v5m_val = float(c.get("recent_5m_volume_usd", 25000.0) or 25000.0)
            g24_val = float(c.get("price_change_24h", c.get("gain_24h", 2.0)) or 2.0)
            ticker_dict = {
                "symbol": c_sym,
                "lastPrice": p_val,
                "quoteVolume": v5m_val * 288.0,
                "recent_5m_volume_usd": v5m_val,
                "priceChangePercent": g24_val,
                "volume_spike_ratio": float(c.get("volume_spike_ratio", 2.0) or 2.0),
                "taker_buy_ratio": float(c.get("taker_buy_ratio", 65.0) or 65.0),
                "momentum_score": float(c.get("momentum_score", 8.0) or 8.0)
            }
            # Canlı Mum Verilerini Çek (Retest ve İlk Mum Kontrolü İçin)
            clean_s = c_sym.replace("/", "").replace("_", "").upper()
            sess = requests.Session()
            r_k = sess.get(f"https://api.binance.com/api/v3/klines?symbol={clean_s}&interval=5m&limit=6", timeout=3)
            klines_5m_data = r_k.json() if r_k.status_code == 200 else None

            min_score_req = float(strat_cfg.get("min_ai_score") or 4.5)
            if is_scalp:
                eval_res = scalp_engine.evaluate_candidate(ticker_dict, klines_1m=klines_5m_data)
                c["v2_score"] = float(eval_res.get("strategy_score") or 8.0)
                is_candidate_ok = (eval_res.get("is_ready") or (eval_res.get("state_machine_stage") == "READY") or (c["v2_score"] >= min_score_req))
            else:
                eval_res = whale_engine.evaluate_whale_evidence(ticker_dict, klines_5m=klines_5m_data)
                c["v2_score"] = float(eval_res.get("total_evidence_score") or 8.0)
                is_candidate_ok = (eval_res.get("is_whale_confirmed") or not strat_cfg.get("retest_required", False)) and (c["v2_score"] >= min_score_req)
            
            c["v2_evaluation"] = eval_res
            if is_candidate_ok:
                clean_candidates.append(c)
                print(f"   🐋 [V2.3 Hacim & Momentum Onaylı]: {c_sym} -> Skor: {c['v2_score']:.1f}/10 (Durum: READY)")
            else:
                stage_str = eval_res.get("state_machine_stage") or eval_res.get("evidence_groups", {}).get("TechnicalStructureEvidence", {}).get("note", "REJECTED")
                print(f"   ⚠️ [V2.3 Retest Engeli]: {c_sym} -> {stage_str} (Skor: {c['v2_score']:.1f}/10)")
        except Exception as e_v2:
            print(f"   ⚠️ [V2.3 Değerlendirme Uyarısı]: {e_v2}")
        
    print(f"   [V2.3 Ön Filtre Sonucu]: {len(clean_candidates)} adet aday coin teknik heyete gönderildi.")
    return {"filtered_candidates": clean_candidates}

def node_gemini_news_report(state: CryptoAgentState) -> Dict[str, Any]:
    """[C] Gemini 3.7 Flash: Haber ve hızlı rapor / duyarlılık sentezi"""
    print("\n--- [C. NODE: GEMINI 3.7 FLASH HABER & HIZLI RAPOR] ---")
    news_text = state.get("news_data", "")
    portfolio = state.get("portfolio_state", {})
    analysis = analyze_crypto_news(news_text, portfolio)
    score = float(analysis.get("sentiment_score", 7.5))
    print(f"   [Gemini 3.7 Flash Rapor]: Duyarlılık Skoru: {score}/10 | Yön: {analysis.get('market_bias', 'NEUTRAL')}")
    return {"sentiment_score": score}

def node_technical_second_opinion(state: CryptoAgentState) -> Dict[str, Any]:
    """[D] TECHNICAL_SECOND_OPINION: GLM-5.3 ile Shadow İkinci Görüş (Section 3.3)"""
    print("\n--- [D. NODE: GLM-5.3 SHADOW İKİNCİ GÖRÜŞ] ---")
    candidates = state.get("filtered_candidates") or []
    if not candidates:
        print("   [GLM-5.3 Shadow]: Ön filtreden geçen aday yok, HOLD.")
        return {"glm_technical": None, "ox_shadow": None}
        
    top_cand = candidates[0]
    from openrouter_gateway import OpenRouterGateway, TechnicalSecondOpinion
    
    sys_prompt = (
        "Sen Fox AI sisteminin Shadow Teknik İkinci Görüş Uzmanısın (z-ai/glm-5.3).\n"
        "Görevin: Python tarafından hesaplanmış teknik metrikleri yorumlamak ve risk analizi sunmaktır.\n"
        "NOT: Emir açma yetkin yoktur; değerlendirmen yalnızca gölge defterine kaydedilir."
    )
    user_p = f"Python Tarafından Hesaplanmış Aday Verisi:\n{json.dumps(top_cand)}"
    
    res = OpenRouterGateway.invoke(
        role="TECHNICAL_SECOND_OPINION",
        system_prompt=sys_prompt,
        user_content=user_p,
        schema_model=TechnicalSecondOpinion,
        prompt_version="opinion-v2.4"
    )
    
    struct = res.get("structured_data") or {}
    print(f"   [GLM-5.3 Shadow]: {top_cand.get('symbol')} - Skor: {struct.get('alignment_score', 7.0)}/10 ({struct.get('summary_tr', 'Değerlendirildi')})")
    return {
        "glm_technical": struct,
        "ox_shadow": {
            "legacyModelAlias": "stealth/ox-alpha",
            "resolvedModelIdentity": "z-ai/glm-5.3-flash",
            "independentConfirmation": False,
            "data": struct
        }
    }

def node_deterministic_risk_policy(state: CryptoAgentState) -> Dict[str, Any]:
    """[F & H] Deterministik RiskPolicyEngine: Kurallar, Bütçe Limiti, 3 Kademeli DCA ve Pozisyon Denetimi"""
    print("\n--- [F. NODE: DETERMINISTIK RISK POLICY ENGINE (v2.1)] ---")
    portfolio_state = state.get("portfolio_state") or {}
    tenant_config = state.get("tenant_config") or {}
    tenant_id = str(tenant_config.get("id") or tenant_config.get("telegram_chat_id") or "default_tenant")
    user_tp = float(tenant_config.get("take_profit_percent") or 1.5)
    user_sl = float(tenant_config.get("stop_loss_percent") or 1.5)
    exch_id = str(tenant_config.get("exchange_id", "")).lower()
    is_tr_user = bool(exch_id in ["binancetr", "binance.tr", "trbinance"])
    live_fx = get_live_usd_try_rate()
    trailing_enabled = bool(get_system_setting("trailing_stop_enabled", True))
    shield_active = bool(get_system_setting("v21_security_shield_enabled", True))
    
    # -------------------------------------------------------------
    # 1. AÇIK POZİSYONLARIN TP / SL VE 3 KADEMELİ DCA DENETİMİ
    # -------------------------------------------------------------
    bal_tr = portfolio_state.get("binance_tr")
    bal_gl = portfolio_state.get("binance_global")
    exchange_silos = []
    
    if bal_tr and bal_tr.get("holdings_details"):
        exchange_silos.append(("TRY", bal_tr.get("holdings_details", {}), "binancetr", True))
    if bal_gl and bal_gl.get("holdings_details"):
        exchange_silos.append(("USDT", bal_gl.get("holdings_details", {}), "binance", False))
        
    if not exchange_silos:
        pair_q = "TRY" if is_tr_user else "USDT"
        exch_name = "binancetr" if is_tr_user else "binance"
        h = portfolio_state.get("holdings_details") or portfolio_state.get("crypto_holdings") or {}
        exchange_silos.append((pair_q, h, exch_name, is_tr_user))
        
    for pair_quote, holdings_map, exch_name, is_tr_silo in exchange_silos:
        saved_positions = get_active_positions_from_db(tenant_id=tenant_id, exchange_id=exch_name)
        if isinstance(holdings_map, dict):
            for coin_asset, details in holdings_map.items():
                asset_upper = str(coin_asset).upper()
                if asset_upper in ["TRY", "USDT", "BUSD", "USDC"]:
                    continue
                coin_amount = details.get("amount", 0.0) if isinstance(details, dict) else float(details or 0.0)
                val_fiat = details.get("val_try" if is_tr_silo else "val_usd", 0.0) if isinstance(details, dict) else 0.0
                min_thresh = 10.0 if is_tr_silo else 5.0
                
                if coin_amount > 0.0001 and val_fiat >= min_thresh:
                    target_symbol = f"{asset_upper}/{pair_quote}"
                    ticker = fetch_ticker_price(target_symbol)
                    curr_p = float(ticker.get("last_price", 0.0))
                    if curr_p <= 0:
                        continue
                        
                    entry_info = saved_positions.get(asset_upper) or {}
                    recorded_buy_p = float(entry_info.get("buy_price", 0.0)) if isinstance(entry_info, dict) else 0.0
                    pos_sl_price = float(entry_info.get("stop_loss_price") or 0.0) if isinstance(entry_info, dict) else 0.0
                    pos_tp_price = float(entry_info.get("take_profit_price") or 0.0) if isinstance(entry_info, dict) else 0.0
                    stage = str(entry_info.get("stage") or "INITIAL")
                    highest_p = float(entry_info.get("highest_price") or recorded_buy_p or curr_p)

                    # Eğer DB'de alış fiyatı yoksa, doğrudan borsanın resmi işlem defterinden (/myTrades) çek:
                    if recorded_buy_p <= 0.0:
                        kd = tenant_config.get("keys_data") or {}
                        api_k = (kd.get("binancetr" if is_tr_silo else "binance", {}) or {}).get("api_key") or tenant_config.get("exchange_api_key")
                        sec_k = (kd.get("binancetr" if is_tr_silo else "binance", {}) or {}).get("secret_key") or tenant_config.get("exchange_secret_key")
                        if api_k and sec_k and not is_tr_silo:
                            try:
                                import hmac, hashlib
                                ts_h = int(time.time() * 1000)
                                q_h = f"symbol={asset_upper}USDT&timestamp={ts_h}&recvWindow=60000"
                                sig_h = hmac.new(sec_k.encode('utf-8'), q_h.encode('utf-8'), hashlib.sha256).hexdigest()
                                url_h = f"https://api.binance.com/api/v3/myTrades?{q_h}&signature={sig_h}"
                                r_h = requests.get(url_h, headers={"X-MBX-APIKEY": api_k}, timeout=4)
                                if r_h.status_code == 200:
                                    buys = [t for t in r_h.json() if t.get("isBuyer")]
                                    if buys:
                                        recorded_buy_p = float(buys[-1]["price"])
                                        from atr_calculator import format_price_precision
                                        pos_sl_price = format_price_precision(recorded_buy_p * (1 - (user_sl/100.0)))
                                        pos_tp_price = format_price_precision(recorded_buy_p * (1 + (user_tp/100.0)))
                                        highest_p = max(recorded_buy_p, curr_p)
                                        save_position_to_db(
                                            tenant_id=tenant_id, exchange_id=exch_name, symbol=target_symbol,
                                            base_asset=asset_upper, quote_asset=pair_quote, amount=coin_amount,
                                            buy_price=recorded_buy_p, stop_loss_price=pos_sl_price,
                                            take_profit_price=pos_tp_price,
                                            highest_price=highest_p, stage="INITIAL"
                                        )
                                        print(f"📖 [Binance Defteri]: {asset_upper} son gerçek alış fiyatı borsadan senkronize edildi: ${recorded_buy_p:,.8f}")
                            except Exception as e_hist:
                                print(f"⚠️ myTrades okuma uyarısı ({asset_upper}): {e_hist}")
                                
                    if recorded_buy_p <= 0.0:
                        recorded_buy_p = curr_p
                        from atr_calculator import format_price_precision
                        pos_sl_price = format_price_precision(curr_p * (1 - (user_sl/100.0)))
                        pos_tp_price = format_price_precision(curr_p * (1 + (user_tp/100.0)))
                        highest_p = curr_p
                        
                    gross_change_pct = ((curr_p - recorded_buy_p) / recorded_buy_p * 100) if recorded_buy_p > 0 else 0.0
                    net_profit_pct = gross_change_pct - 0.20
                    
                    if curr_p > highest_p:
                        highest_p = curr_p
                        save_position_to_db(
                            tenant_id=tenant_id, exchange_id=exch_name, symbol=target_symbol,
                            base_asset=asset_upper, quote_asset=pair_quote, amount=coin_amount,
                            buy_price=recorded_buy_p, stop_loss_price=pos_sl_price, take_profit_price=pos_tp_price,
                            highest_price=curr_p, stage=stage
                        )
                        
                    is_stop_loss = False
                    is_take_profit = False
                    reason_desc = ""
                    sell_fraction = 1.0
                    
                    if trailing_enabled:
                        peak_gain_pct = ((highest_p - recorded_buy_p) / recorded_buy_p * 100) if recorded_buy_p > 0 else 0.0
                        
                        from db import get_strategy_config
                        strat_cfg = get_strategy_config(use_cache=True)
                        trail_callback = float(strat_cfg.get("trailing_callback_pct") or 0.6)
                        callback_mult = 1.0 - (trail_callback / 100.0)
                        
                        be_enabled = bool(strat_cfg.get("breakeven_enabled", True))
                        be_trigger = float(strat_cfg.get("breakeven_trigger_pct", 1.0))
                        
                        slock_enabled = bool(strat_cfg.get("steplock_enabled", True))
                        slock_trigger = float(strat_cfg.get("steplock_trigger_pct", 1.8))
                        slock_lock = float(strat_cfg.get("steplock_lock_pct", 0.9))
                        
                        # 🛡️ DİNAMİK 3 KADEMELİ AKILLI ZIRH MOTORU (Panelden Yönetilebilir):
                        # 1. Ana Trailing TP: Zirve kazanç ana TP hedefini (user_tp) aşmış ve zirveden callback kadar çekilmişse:
                        if peak_gain_pct >= user_tp and curr_p <= (highest_p * callback_mult):
                            is_take_profit = True
                            reason_desc = f"🎯 Trailing TP: Zirve Kâr Realizasyonu (+%{net_profit_pct:.2f} Net / Zirve: +%{peak_gain_pct:.2f})"
                            sell_fraction = 1.0
                        # 2. Kademeli Kâr Kilidi (Step-Lock): Fiyat tetik seviyesini (örn. +%1.80) görmüş ve kilit seviyesine (örn. +%0.90) çekilmişse kârı al
                        elif slock_enabled and peak_gain_pct >= slock_trigger and curr_p <= (recorded_buy_p * (1.0 + (slock_lock / 100.0))):
                            is_take_profit = True
                            reason_desc = f"💰 Kademeli Kâr Kilidi: (+%{net_profit_pct:.2f} Net Kâr Cebe / Zirve: +%{peak_gain_pct:.2f})"
                            sell_fraction = 1.0
                        # 3. Başa Baş (Breakeven): Fiyat tetik seviyesini (örn. +%1.00) görüp alış seviyesine gevşemişse -> Sıfır Risk Satışı!
                        elif be_enabled and peak_gain_pct >= be_trigger and curr_p <= (recorded_buy_p * 1.001):
                            is_take_profit = True
                            reason_desc = f"🛡️ Başa Baş Koruması: (+%{net_profit_pct:.2f} Komisyonsuz Sıfır Zararla Çıkış / Zirve: +%{peak_gain_pct:.2f})"
                            sell_fraction = 1.0
                        elif (pos_tp_price > 0 and curr_p >= pos_tp_price) or (net_profit_pct >= user_tp):
                            # Kullanıcının belirlediği ana TP hedefine ulaşıldı:
                            is_take_profit = True
                            reason_desc = f"🎯 Hedef Kâr Alma (+%{net_profit_pct:.2f} Net Kâr Kasaya Alındı)"
                            sell_fraction = 1.0
                        elif (pos_sl_price > 0 and curr_p <= pos_sl_price) or (net_profit_pct <= -user_sl):
                            # Sıkı Stop-Loss sınırı:
                            is_stop_loss = True
                            reason_desc = f"🛡️ Sıkı Stop-Loss (%{net_profit_pct:.2f} Net Zarar Kesildi)"
                            sell_fraction = 1.0
                    else:
                        if (pos_sl_price > 0 and curr_p <= pos_sl_price) or (net_profit_pct <= -user_sl):
                            is_stop_loss = True
                            reason_desc = f"Stop-Loss (%{net_profit_pct:.2f} Net)"
                        elif (pos_tp_price > 0 and curr_p >= pos_tp_price) or (net_profit_pct >= user_tp):
                            is_take_profit = True
                            reason_desc = f"Kâr Alma (+%{net_profit_pct:.2f} Net)"
                            
                    if is_stop_loss or is_take_profit:
                        if is_stop_loss:
                            try:
                                from entry_safety_policy import record_failed_level_zone
                                record_failed_level_zone(target_symbol, recorded_buy_p, reason="STOP_LOSS_TRIGGERED")
                            except Exception:
                                pass

                        sell_proposal = {
                            "should_trade": True,
                            "symbol": target_symbol,
                            "direction": "SELL",
                            "is_stop_loss": is_stop_loss,
                            "reason_type": "stop-loss" if is_stop_loss else "take-profit",
                            "amount_usd": round(val_fiat * sell_fraction / (live_fx if is_tr_silo else 1.0), 2),
                            "amount_coin": coin_amount * sell_fraction,
                            "remaining_coin": coin_amount * (1.0 - sell_fraction),
                            "entry_price": recorded_buy_p,
                            "highest_price": highest_p,
                            "stage": stage,
                            "sell_fraction": sell_fraction,
                            "net_profit_pct": round(net_profit_pct, 2),
                            "risk_justification": f"Otomatik Kapatma: {asset_upper} ({reason_desc})"
                        }
                        print(f"   [Risk Engine Kararı]: SATIM ({target_symbol}) - {reason_desc}")
                        return {"trade_proposal": sell_proposal, "policy_check_passed": True, "human_approval": "Approved"}
                    else:
                        # 3 Kademeli DCA 2. Kademe Dip Ekleme
                        free_usdt = float(bal_gl.get("free_usdt", 0.0)) if bal_gl else 0.0
                        free_try = float(bal_tr.get("free_try", 0.0)) if bal_tr else 0.0
                        can_dca = (shield_active and stage == "INITIAL" and (-2.2 <= net_profit_pct <= -1.0) and val_fiat < 22.0)
                        if can_dca:
                            dca_budget = 10.0 if not is_tr_silo else 350.0
                            has_cash = (free_usdt >= dca_budget) if not is_tr_silo else (free_try >= dca_budget)
                            if has_cash:
                                dca_proposal = {
                                    "should_trade": True,
                                    "symbol": target_symbol,
                                    "direction": "BUY",
                                    "amount_usd": dca_budget if not is_tr_silo else round(dca_budget / live_fx, 2),
                                    "entry_price": curr_p,
                                    "sentiment_score": 8.0,
                                    "take_profit_price": pos_tp_price,
                                    "stop_loss_price": pos_sl_price,
                                    "is_dca_entry": True,
                                    "dca_stage": 2,
                                    "risk_justification": f"🧩 3 Kademeli Akıllı Giriş (DCA 2. Kademe): {asset_upper} -%{abs(net_profit_pct):.2f} desteğinde ${dca_budget:.1f} eklendi."
                                }
                                print(f"   [Risk Engine Kararı]: 🧩 DCA 2. KADEME ALIM ({target_symbol})")
                                return {"trade_proposal": dca_proposal, "policy_check_passed": True, "human_approval": "Approved"}

    # -------------------------------------------------------------
    # 2. YENİ POZİSYON İÇİN POLİTİKA VE REJİM KONTROLLERİ (DETERMİNİSTİK)
    # -------------------------------------------------------------
    # AI Yalnızca BLOCK_ONLY Yetkisine Sahiptir (Section 1 & 3.2)
    sentiment_score = float(state.get("sentiment_score", 5.0))
    if sentiment_score < -4.0:
        print(f"   🛑 [Kritik Haber Kalkanı]: Makro/Haber risk skoru ({sentiment_score:.1f}) sebebiyle işlem durduruldu (BLOCK_ONLY).")
        return {"trade_proposal": None, "policy_check_passed": False, "human_approval": "Rejected"}
        
    from db import get_strategy_config
    strat_cfg = get_strategy_config(use_cache=True) or {}
    is_scalp_mode = (not strat_cfg.get("retest_required", False)) or ("scalp" in str(strat_cfg.get("active_preset", "")).lower()) or ("armor" in str(strat_cfg.get("active_preset", "")).lower()) or (float(strat_cfg.get("btc_min_rsi") or 35.0) <= 38.0)
    regime = check_market_regime(is_scalp=is_scalp_mode)
    if shield_active and not regime.get("is_bullish"):
        print(f"   🛑 [BTC Rejim Kalkanı]: {regime.get('reason')} - Yeni alım durduruldu.")
        return {"trade_proposal": None, "policy_check_passed": False, "human_approval": "Rejected"}
        
    candidates = state.get("filtered_candidates") or []
    if not candidates:
        return {"trade_proposal": None, "policy_check_passed": False, "human_approval": "Rejected"}
        
    cand = candidates[0]
    c_sym = cand["symbol"]
    c_base = c_sym.split("/")[0].upper()
    
    # 🚨 ZIRHLI KURAL: Cüzdanda zaten bu coin varsa ASLA tekrar alım yapma!
    existing_holdings = portfolio_state.get("holdings_details") or portfolio_state.get("crypto_holdings") or {}
    if isinstance(existing_holdings, dict) and c_base in existing_holdings:
        coin_info = existing_holdings[c_base]
        val_now = coin_info.get("val_usd", 0.0) if isinstance(coin_info, dict) else 0.0
        if val_now >= 5.0:
            print(f"   🛑 [Tekrar Alım Engeli]: {c_base} zaten cüzdanda mevcut (${val_now:.2f}), tekrar alım yapılmaz.")
            return {"trade_proposal": None, "policy_check_passed": False, "human_approval": "Rejected"}

    # Kasa Bütçesi ve Slot Hesabı (v2.1 Kuralı)
    bal_gl = portfolio_state.get("binance_global") or {}
    bal_tr = portfolio_state.get("binance_tr") or {}
    free_usdt = float(bal_gl.get("free_usdt") or portfolio_state.get("free_usdt") or portfolio_state.get("free_usd") or 0.0)
    free_try = float(bal_tr.get("free_try") or portfolio_state.get("free_try") or 0.0)
    tot_val_usd = float(bal_gl.get("total_usdt") or portfolio_state.get("total_usdt") or portfolio_state.get("total_usd") or (free_usdt if free_usdt > 0 else 100.0))
    
    from db import get_strategy_config
    strat_cfg = get_strategy_config(use_cache=True)
    cfg_max_pct = float(strat_cfg.get("max_budget_percent") or 25.0)
    user_max_pct = float(tenant_config.get("max_budget_percent") or cfg_max_pct)
    
    # Hedef slot sayısı bütçe yüzdesine ve paneldeki slot ayarına göre belirlenir
    calculated_slots = max(1, int(100.0 / user_max_pct))
    cfg_slots = int(strat_cfg.get("max_concurrent_positions", 2))
    target_slots = min(cfg_slots, max(calculated_slots, 1)) if shield_active else cfg_slots
    
    # Aktif açık pozisyon sayısını say ve slot doluluğunu denetle
    if isinstance(existing_holdings, dict):
        active_coins = [k for k, v in existing_holdings.items() if str(k).upper() not in ["USDT", "TRY", "BNB", "USDC", "FDUSD"] and (isinstance(v, dict) and (v.get("val_usd", 0) > 5.0 or v.get("val_try", 0) > 150))]
        if len(active_coins) >= target_slots:
            print(f"   🛑 [Maksimum Slot Dolu]: Açık pozisyon sayısı ({len(active_coins)}) hedef slotu ({target_slots}) doldurdu. Yeni alım kapalı.")
            return {"trade_proposal": None, "policy_check_passed": False, "human_approval": "Rejected"}
    
    is_quote_try = c_sym.endswith("TRY")
    cand_quote = "TRY" if is_quote_try else "USDT"
    fresh_coin = f"{c_base}/{cand_quote}"
    
    if is_quote_try:
        tot_tr_try = float(bal_tr.get("total_try", 0.0)) or (tot_val_usd * live_fx)
        max_cap_tl = round(tot_tr_try * (user_max_pct / 100.0), 2)
        slot_budget_tl = min(round(tot_tr_try / target_slots, 2), max_cap_tl) if shield_active else round(tot_tr_try / target_slots, 2)
        trade_budget_tl = min(slot_budget_tl, free_try * 0.95)
        safe_budget_usd = round(trade_budget_tl / live_fx, 2)
        if free_try < 100.0 or trade_budget_tl < 100.0:
            print(f"   ⏳ [Bütçe Yetersiz]: Serbest TL (₺{free_try:.2f}) slot (₺{slot_budget_tl:.2f}) için yetersiz.")
            return {"trade_proposal": None, "policy_check_passed": False, "human_approval": "Rejected"}
    else:
        max_cap_usd = round(tot_val_usd * (user_max_pct / 100.0), 2)
        slot_budget_usd = min(round(tot_val_usd / target_slots, 2), max_cap_usd) if shield_active else round(tot_val_usd / target_slots, 2)
        safe_budget_usd = round(min(slot_budget_usd, free_usdt * 0.95), 2)
        if free_usdt < 10.0 or safe_budget_usd < 10.0:
            print(f"   ⏳ [Bütçe Yetersiz]: Serbest USDT (${free_usdt:.2f}) slot (${slot_budget_usd:.2f}) için yetersiz.")
            return {"trade_proposal": None, "policy_check_passed": False, "human_approval": "Rejected"}
            
    real_ticker = fetch_ticker_price(fresh_coin)
    real_entry_price = float(real_ticker.get("last_price") or 1.0)
    if real_entry_price <= 0:
        return {"trade_proposal": None, "policy_check_passed": False, "human_approval": "Rejected"}
        
    tp_price, sl_price, dynamic_tp_pct, dynamic_sl_pct = calculate_atr_sl_tp(
        symbol=fresh_coin, entry_price=real_entry_price, user_tp_override=user_tp, user_sl_override=user_sl
    )
    
    # Kullanıcının tablodaki net Bütçe % oranı doğrudan işleme alınır
    exec_amount_usd = safe_budget_usd
    
    proposal = {
        "should_trade": True,
        "symbol": fresh_coin,
        "direction": "BUY",
        "amount_usd": exec_amount_usd,
        "entry_price": real_entry_price,
        "sentiment_score": state.get("sentiment_score", 8.0),
        "take_profit_price": tp_price,
        "stop_loss_price": sl_price,
        "take_profit_percent": dynamic_tp_pct,
        "stop_loss_percent": dynamic_sl_pct,
        "stage": "INITIAL",
        "risk_justification": f"V2.3 Deterministik Retest Onaylı Alım: Bütçe %{user_max_pct:.0f} (${exec_amount_usd:.2f}) | ATR TP: +%{dynamic_tp_pct:.1f} | ATR SL: -%{dynamic_sl_pct:.1f}"
    }
    print(f"   ✅ [Risk Engine Onayı]: ALIM ({fresh_coin}) - Fiyat: ${real_entry_price} | Bütçe: ${proposal['amount_usd']}")
    return {"trade_proposal": proposal, "policy_check_passed": True, "human_approval": "Approved"}

def check_policy_gate(state: CryptoAgentState) -> str:
    """[H] Kurallar geçti mi? Karar Kapısı"""
    passed = bool(state.get("policy_check_passed")) and bool(state.get("trade_proposal"))
    print(f"\n--- [H. GATE: POLİTİKA DENETİM KAPISI -> {'ONAYLANDI (EVET)' if passed else 'REDDEDİLDİ (HAYIR)'}] ---")
    return "approved" if passed else "rejected"

def node_reject_trade(state: CryptoAgentState) -> Dict[str, Any]:
    """[I] İşlem reddedildi / Güvenli Nakit Beklemesi"""
    print("--- [I. NODE: İŞLEM REDDEDİLDİ (GÜVENLİ NAKİT)] ---")
    return {"human_approval": "Rejected", "execution_result": {"status": "HOLD_OR_REJECTED"}}

def node_execute_trade(state: CryptoAgentState) -> Dict[str, Any]:
    """[J] Telegram onayı / Borsa emri infazı (Merkezi ExecutionGate)"""
    print("\n--- [J. NODE: TELEGRAM BİLDİRİMİ VE BORSA EMRİ İNFAZI] ---")
    proposal = state.get("trade_proposal")
    tenant_config = state.get("tenant_config")
    if not proposal:
        return {"execution_result": {"status": "NO_PROPOSAL"}}

    from entry_safety_policy import OrderIntent, ExecutionGate, compute_runtime_config_hash
    runtime_hash = compute_runtime_config_hash()
    
    # OrderIntent Nesnesi Oluştur
    intent = OrderIntent(
        symbol=proposal["symbol"],
        direction=proposal["direction"],
        amount_usd=proposal["amount_usd"],
        source_engine=str(proposal.get("source_engine", "WHALE_HUNTING")),
        signal_state="RETEST_CONFIRMED" if proposal.get("direction") == "BUY" else "EXIT_SIGNAL",
        first_pump_entry=False,
        risk_decision="APPROVED",
        config_hash=runtime_hash,
        is_expired=False,
        idempotency_key=f"{proposal['symbol']}_{proposal['direction']}_{int(time.time() // 30)}",
        idempotency_key_unused=True,
        spread_ok=True,
        slippage_ok=True,
        stop_can_be_created=True,
        entry_price=float(proposal.get("entry_price") or 0.0),
        stop_loss_price=proposal.get("stop_loss_price"),
        take_profit_price=proposal.get("take_profit_price")
    )
    
    result = ExecutionGate.execute(intent=intent, tenant_config=tenant_config)
    
    # Supabase Atomik DB Ledger Güncellemesi
    try:
        is_try_order = proposal["symbol"].upper().endswith("TRY") or proposal["symbol"].upper().endswith("_TRY")
        exch_name = "binancetr" if is_try_order else "binance"
        base_sym = proposal["symbol"].split("/")[0].split("_")[0].upper()
        quote_c = "TRY" if is_try_order else "USDT"
        status_str = str(result.get("status", "")).upper()
        tenant_id = str((tenant_config or {}).get("id") or (tenant_config or {}).get("telegram_chat_id") or "default_tenant")
        is_simulated = (status_str == "EXECUTED_SIMULATED")

        if status_str in ["SUCCESS", "EXECUTED", "EXECUTED_SIMULATED"]:
            if proposal["direction"].upper() in ["BUY", "ALIM"]:
                exec_p = float(result.get("executed_price") or proposal.get("entry_price") or 0.0)
                new_coin_amt = float(proposal.get("amount_coin") or (proposal["amount_usd"] / exec_p if exec_p > 0 else 0))
                is_dca = bool(proposal.get("is_dca_entry"))
                existing_pos = get_active_positions_from_db(tenant_id=tenant_id, exchange_id=exch_name) or {}
                prev_info = existing_pos.get(base_sym) or existing_pos.get(proposal["symbol"]) or {}
                
                if is_dca and prev_info:
                    prev_amt = float(prev_info.get("amount", 0.0))
                    prev_buy_p = float(prev_info.get("buy_price", 0.0))
                    tot_amt = prev_amt + new_coin_amt
                    avg_p = ((prev_amt * prev_buy_p) + (new_coin_amt * exec_p)) / tot_amt if tot_amt > 0 else exec_p
                    next_stage = "STAGE_2_DCA" if proposal.get("dca_stage") == 2 else "STAGE_3_FULL"
                    save_position_to_db(
                        tenant_id=tenant_id, exchange_id=exch_name, symbol=proposal["symbol"],
                        base_asset=base_sym, quote_asset=quote_c, amount=tot_amt, buy_price=avg_p,
                        stop_loss_price=round(avg_p * 0.975, 8 if avg_p < 1 else 2),
                        take_profit_price=proposal.get("take_profit_price"), is_simulated=is_simulated,
                        stage=next_stage
                    )
                    print(f"🧩 [DCA Tamamlandı]: {base_sym} yeni ortalama: ${avg_p:.4f} (Toplam {tot_amt:.4f} adet)")
                else:
                    save_position_to_db(
                        tenant_id=tenant_id, exchange_id=exch_name, symbol=proposal["symbol"],
                        base_asset=base_sym, quote_asset=quote_c, amount=new_coin_amt, buy_price=exec_p,
                        stop_loss_price=proposal.get("stop_loss_price"), take_profit_price=proposal.get("take_profit_price"),
                        is_simulated=is_simulated, stage="INITIAL"
                    )
            else: # SELL
                r_type = str(proposal.get("reason_type", "")).lower()
                if r_type == "partial_take_profit":
                    rem_amt = float(proposal.get("remaining_coin") or 0.0)
                    entry_p = float(proposal.get("entry_price") or 0.0)
                    high_p = float(proposal.get("highest_price") or entry_p)
                    save_position_to_db(
                        tenant_id=tenant_id, exchange_id=exch_name, symbol=proposal["symbol"],
                        base_asset=base_sym, quote_asset=quote_c, amount=rem_amt, buy_price=entry_p,
                        stop_loss_price=entry_p, take_profit_price=None, is_simulated=is_simulated,
                        highest_price=high_p, stage="STAGE_1_TP_TAKEN", partial_amount_sold=float(proposal.get("amount_coin") or 0.0)
                    )
                    print(f"🎯 [Kademeli Kâr]: {base_sym} %50 satıldı. Kalan Breakeven + İz Süren Moda alındı!")
                else:
                    remove_position_from_db(tenant_id=tenant_id, exchange_id=exch_name, symbol=proposal["symbol"])
                    # Soğuma Süresi (Cooldown) Ekle
                    set_cooldown_in_db(tenant_id=tenant_id, coin=base_sym, duration_seconds=1800)
    except Exception as pe:
        print(f"⚠️ [DB Ledger Güncelleme Uyarısı]: {pe}")
        
    t_id = str((tenant_config or {}).get("id") or (tenant_config or {}).get("telegram_chat_id") or "default_tenant")
    t_name = str((tenant_config or {}).get("tenant_name") or "S")
    t_chat = (tenant_config or {}).get("telegram_chat_id")
    log_details = {
        **(result if isinstance(result, dict) else {}),
        "tenant_id": t_id, "tenant_name": t_name, "telegram_chat_id": t_chat,
        "eval_benchmark": state.get("eval_record"),
        "reason_type": proposal.get("reason_type", "momentum_entry" if proposal.get("direction") == "BUY" else "exit"),
        "net_profit_pct": proposal.get("net_profit_pct", 0.0),
        "stop_loss_price": proposal.get("stop_loss_price"),
        "take_profit_price": proposal.get("take_profit_price")
    }
    log_payload = {
        **proposal,
        "sentiment_score": state.get("sentiment_score"),
        "human_approval": "Approved",
        "status": result.get("status", "EXECUTED"),
        "order_id": result.get("order_id"),
        "execution_details": log_details
    }
    log_trade_decision(log_payload, tenant_id=t_id)
    save_graph_state("session_langgraph_hitl", state)
    return {"execution_result": result}

# =====================================================================
# LANGGRAPH STATEGRAPH KURULUMU (FLOWCHART DÖNGÜSÜ)
# =====================================================================
def create_crypto_graph():
    workflow = StateGraph(CryptoAgentState)
    
    # 1. Düğümleri Ekle
    workflow.add_node("fetch_live_data", node_fetch_live_data)                         # [A]
    workflow.add_node("deterministic_prefilter", node_deterministic_prefilter)         # [B]
    workflow.add_node("gemini_news_report", node_gemini_news_report)                   # [C]
    workflow.add_node("technical_second_opinion", node_technical_second_opinion)       # [D]
    workflow.add_node("deterministic_risk_policy", node_deterministic_risk_policy)     # [F]
    workflow.add_node("reject_trade", node_reject_trade)                               # [I]
    workflow.add_node("execute_trade", node_execute_trade)                             # [J]
    
    # 2. Akış Kenarlarını (Edges) Bağla
    workflow.set_entry_point("fetch_live_data")
    workflow.add_edge("fetch_live_data", "deterministic_prefilter")
    workflow.add_edge("deterministic_prefilter", "gemini_news_report")
    workflow.add_edge("gemini_news_report", "technical_second_opinion")
    workflow.add_edge("technical_second_opinion", "deterministic_risk_policy")
    
    # 3. Şartlı Kapı: [H] Kurallar Geçti mi?
    workflow.add_conditional_edges(
        "deterministic_risk_policy",
        check_policy_gate,
        {
            "approved": "execute_trade", # [J]
            "rejected": "reject_trade"   # [I]
        }
    )
    
    workflow.add_edge("execute_trade", END)
    workflow.add_edge("reject_trade", END)
    
    return workflow.compile()

if __name__ == "__main__":
    print("🚀 LangGraph StateGraph Flowchart Akışı Çalıştırılıyor...")
    app_graph = create_crypto_graph()
    initial_state = {
        "news_data": "",
        "portfolio_state": {},
        "sentiment_score": 0.0,
        "filtered_candidates": [],
        "glm_technical": None,
        "ox_shadow": None,
        "eval_record": None,
        "trade_proposal": None,
        "policy_check_passed": False,
        "human_approval": "Pending",
        "execution_result": None
    }
    final_output = app_graph.invoke(initial_state)
    print("\n✅ LangGraph Flowchart Akışı Tamamlandı. Sonuç:", final_output.get("execution_result"))
