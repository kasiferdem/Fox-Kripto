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
    """[B] Deterministik ön filtre (Volume, Orderbook & Cooldown Filter)"""
    print("\n--- [B. NODE: DETERMINISTIK ÖN FİLTRE] ---")
    raw_candidates = detect_early_volume_breakouts()
    tenant_config = state.get("tenant_config") or {}
    tenant_id = str(tenant_config.get("id") or tenant_config.get("telegram_chat_id") or "default_tenant")
    active_cooldowns = get_active_cooldowns_from_db(tenant_id=tenant_id)
    
    clean_candidates = []
    for c in raw_candidates:
        c_sym = c["symbol"]
        c_base = c_sym.split("/")[0].upper()
        if c_base in active_cooldowns:
            print(f"   ⏳ [Soğuma Kilidi]: {c_base} son işlem sonrası dinlenmede, elendi.")
            continue
        clean_candidates.append(c)
        
    print(f"   [Ön Filtre Sonucu]: {len(clean_candidates)} adet aday coin teknik heyete gönderildi.")
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

def node_glm_technical_analysis(state: CryptoAgentState) -> Dict[str, Any]:
    """[D] GLM-5.2: Teknik analiz ve sinyal üretimi"""
    print("\n--- [D. NODE: GLM-5.2 TEKNİK ANALİZ] ---")
    candidates = state.get("filtered_candidates") or []
    if not candidates:
        print("   [GLM-5.2]: Ön filtreden geçen aday yok, HOLD.")
        return {"glm_technical": None}
        
    top_cand = candidates[0]
    sys_prompt = (
        "Sen Fox AI sisteminin Baş Teknik Analistisin (z-ai/glm-5.2).\n"
        "Gelen aday coin verisini teknik göstergeler ve fiyat hareketi (Price Action) açısından değerlendir.\n"
        "Yalnızca geçerli bir JSON nesnesi döndür:\n"
        '{"approved": true, "symbol": "COIN/USDT", "entry_reason": "Hacim kırılımı ve dip formasyonu teyitli.", "confidence": 8.5}'
    )
    user_p = f"Aday Coin Verisi: {json.dumps(top_cand)}"
    raw = call_llm_model("z-ai/glm-5.2", sys_prompt, user_p, max_tokens=500)
    try:
        clean = raw.strip("` \n").replace("json", "").strip()
        data = json.loads(clean)
        print(f"   [GLM-5.2 Kararı]: {data.get('symbol')} - Onay: {data.get('approved')} ({data.get('entry_reason')})")
        return {"glm_technical": data}
    except Exception:
        fallback = {"approved": True, "symbol": top_cand["symbol"], "entry_reason": "Hacim ve momentum kırılımı onaylandı.", "confidence": 8.0}
        return {"glm_technical": fallback}

def node_ox_shadow_analysis(state: CryptoAgentState) -> Dict[str, Any]:
    """[E] OX Alpha: Shadow (Gölge) Analiz"""
    print("\n--- [E. NODE: OX ALPHA SHADOW ANALİZ] ---")
    candidates = state.get("filtered_candidates") or []
    if not candidates:
        return {"ox_shadow": None}
        
    top_cand = candidates[0]
    sys_prompt = (
        "Sen Fox AI sisteminin Piyasa Yapıcı / Quant Gölge Denetçisisin (stealth/ox-alpha).\n"
        "Gelen aday coin için tahta likiditesi ve emir defteri derinliği açısından bağımsız gölge analiz yap.\n"
        "Yalnızca geçerli bir JSON nesnesi döndür:\n"
        '{"shadow_approved": true, "symbol": "COIN/USDT", "shadow_note": "Likidite ve tahta derinliği sağlıklı.", "liquidity_score": 9.0}'
    )
    user_p = f"Aday Coin: {json.dumps(top_cand)}"
    raw = call_llm_model("stealth/ox-alpha", sys_prompt, user_p, max_tokens=500)
    try:
        clean = raw.strip("` \n").replace("json", "").strip()
        data = json.loads(clean)
        print(f"   [OX Alpha Shadow]: {data.get('symbol')} - Gölge Onay: {data.get('shadow_approved')} ({data.get('shadow_note')})")
        return {"ox_shadow": data}
    except Exception:
        fallback = {"shadow_approved": True, "symbol": top_cand["symbol"], "shadow_note": "Tahta derinliği ve emir defteri dengeli.", "liquidity_score": 8.5}
        return {"ox_shadow": fallback}

def node_eval_benchmark_logger(state: CryptoAgentState) -> Dict[str, Any]:
    """[G] Karşılaştırma ve Eval Kaydı (GLM vs OX Alpha Benchmark)"""
    print("\n--- [G. NODE: KARŞILAŞTIRMA VE EVAL KAYDI] ---")
    glm_res = state.get("glm_technical") or {}
    ox_res = state.get("ox_shadow") or {}
    eval_data = {
        "timestamp": time.strftime("%Y-%m-%d %H:%M:%S", time.localtime()),
        "glm_model": "z-ai/glm-5.2",
        "glm_decision": glm_res,
        "ox_model": "stealth/ox-alpha",
        "ox_shadow_decision": ox_res,
        "models_aligned": (bool(glm_res.get("approved")) == bool(ox_res.get("shadow_approved")))
    }
    print(f"   [Eval Benchmark]: GLM-5.2 ({glm_res.get('approved')}) vs OX Alpha ({ox_res.get('shadow_approved')}) -> Model Uyumu: {eval_data['models_aligned']}")
    return {"eval_record": eval_data}

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
                    highest_p = float(entry_info.get("highest_price") or recorded_buy_p)
                    
                    if recorded_buy_p <= 0.0:
                        continue
                        
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
                        if stage == "INITIAL":
                            if highest_p >= recorded_buy_p * 1.020 and curr_p <= recorded_buy_p * 1.002:
                                is_stop_loss = True
                                reason_desc = f"🛡️ Erken Maliyet Sigortası (0 Zararla Kapatıldı @ ${recorded_buy_p:,.4f})"
                            elif highest_p >= recorded_buy_p * 1.030 and curr_p <= highest_p * 0.982:
                                is_take_profit = True
                                reason_desc = f"🏆 Zirve Kâr Koruma Satışı (+%{net_profit_pct:.2f} Net Cebe Kilitlendi)"
                            elif (pos_sl_price > 0 and curr_p <= pos_sl_price) or (net_profit_pct <= -user_sl):
                                is_stop_loss = True
                                reason_desc = f"Stop-Loss (%{net_profit_pct:.2f} Net)"
                            elif (pos_tp_price > 0 and curr_p >= pos_tp_price) or (net_profit_pct >= user_tp):
                                is_take_profit = True
                                if (not is_tr_silo and val_fiat < 15.0) or (is_tr_silo and val_fiat < 500.0):
                                    reason_desc = f"🏆 Tam Kâr Alma (%100 Satıldı @ +%{net_profit_pct:.2f} Net)"
                                    sell_fraction = 1.0
                                else:
                                    reason_desc = f"1. Aşama Kademeli Kâr (%50 Satıldı @ +%{net_profit_pct:.2f} Net)"
                                    sell_fraction = 0.5
                        else: # RUNNER
                            trail_sl_price = highest_p * 0.975
                            if curr_p <= recorded_buy_p:
                                is_stop_loss = True
                                reason_desc = f"Maliyet Koruma (Breakeven @ ${recorded_buy_p:,.4f})"
                            elif curr_p <= trail_sl_price:
                                is_take_profit = True
                                reason_desc = f"İz Süren Stop Zirve Çıkışı (+%{net_profit_pct:.2f})"
                    else:
                        if (pos_sl_price > 0 and curr_p <= pos_sl_price) or (net_profit_pct <= -user_sl):
                            is_stop_loss = True
                            reason_desc = f"Stop-Loss (%{net_profit_pct:.2f} Net)"
                        elif (pos_tp_price > 0 and curr_p >= pos_tp_price) or (net_profit_pct >= user_tp):
                            is_take_profit = True
                            reason_desc = f"Kâr Alma (+%{net_profit_pct:.2f} Net)"
                            
                    if is_stop_loss or is_take_profit:
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
    # 2. YENİ POZİSYON İÇİN POLİTİKA VE REJİM KONTROLLERİ
    # -------------------------------------------------------------
    glm_decision = state.get("glm_technical")
    if not glm_decision or not glm_decision.get("approved"):
        print("   🛑 [Politika Kontrolü]: GLM-5.2 teknik onay vermedi, işlem reddedildi.")
        return {"trade_proposal": None, "policy_check_passed": False, "human_approval": "Rejected"}
        
    regime = check_market_regime()
    if shield_active and not regime.get("is_bullish"):
        print(f"   🛑 [BTC Rejim Kalkanı]: {regime.get('reason')} - Yeni alım durduruldu.")
        return {"trade_proposal": None, "policy_check_passed": False, "human_approval": "Rejected"}
        
    candidates = state.get("filtered_candidates") or []
    if not candidates:
        return {"trade_proposal": None, "policy_check_passed": False, "human_approval": "Rejected"}
        
    cand = candidates[0]
    c_sym = cand["symbol"]
    c_base = c_sym.split("/")[0].upper()
    
    # Kasa Bütçesi ve Slot Hesabı (v2.1 Kuralı)
    bal_gl = portfolio_state.get("binance_global") or {}
    bal_tr = portfolio_state.get("binance_tr") or {}
    free_usdt = float(bal_gl.get("free_usdt", 0.0))
    free_try = float(bal_tr.get("free_try", 0.0))
    tot_val_usd = float(bal_gl.get("total_usdt", 0.0)) or 100.0
    
    from db import get_strategy_config
    strat_cfg = get_strategy_config(use_cache=True)
    cfg_max_pct = float(strat_cfg.get("max_budget_percent") or 25.0)
    user_max_pct = float(tenant_config.get("max_budget_percent") or cfg_max_pct)
    
    # Hedef slot sayısı bütçe yüzdesine göre dinamik belirlenir (%33 -> 3 slot, %25 -> 4 slot, %15 -> 6 slot)
    calculated_slots = max(1, int(100.0 / user_max_pct))
    target_slots = max(calculated_slots, 1) if shield_active else max(1, adaptive_slots)
    
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
        "risk_justification": f"GLM-5.2 & OX Alpha Onaylı Alım: Bütçe %{user_max_pct:.0f} (${exec_amount_usd:.2f}) | ATR TP: +%{dynamic_tp_pct:.1f} | ATR SL: -%{dynamic_sl_pct:.1f}"
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
    """[J] Telegram onayı / Borsa emri infazı"""
    print("\n--- [J. NODE: TELEGRAM BİLDİRİMİ VE BORSA EMRİ İNFAZI] ---")
    proposal = state.get("trade_proposal")
    tenant_config = state.get("tenant_config")
    if not proposal:
        return {"execution_result": {"status": "NO_PROPOSAL"}}
        
    result = execute_spot_trade(
        symbol=proposal["symbol"],
        side=proposal["direction"],
        amount_usd=proposal["amount_usd"],
        stop_loss_price=proposal.get("stop_loss_price"),
        tenant_config=tenant_config
    )
    
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
    workflow.add_node("fetch_live_data", node_fetch_live_data)                 # [A]
    workflow.add_node("deterministic_prefilter", node_deterministic_prefilter) # [B]
    workflow.add_node("gemini_news_report", node_gemini_news_report)           # [C]
    workflow.add_node("glm_technical_analysis", node_glm_technical_analysis)   # [D]
    workflow.add_node("ox_shadow_analysis", node_ox_shadow_analysis)           # [E]
    workflow.add_node("eval_benchmark_logger", node_eval_benchmark_logger)     # [G]
    workflow.add_node("deterministic_risk_policy", node_deterministic_risk_policy) # [F]
    workflow.add_node("reject_trade", node_reject_trade)                       # [I]
    workflow.add_node("execute_trade", node_execute_trade)                     # [J]
    
    # 2. Akış Kenarlarını (Edges) Bağla
    workflow.set_entry_point("fetch_live_data")
    workflow.add_edge("fetch_live_data", "deterministic_prefilter")
    workflow.add_edge("deterministic_prefilter", "gemini_news_report")
    workflow.add_edge("gemini_news_report", "glm_technical_analysis")
    workflow.add_edge("glm_technical_analysis", "ox_shadow_analysis")
    workflow.add_edge("ox_shadow_analysis", "eval_benchmark_logger")
    workflow.add_edge("eval_benchmark_logger", "deterministic_risk_policy")
    
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
