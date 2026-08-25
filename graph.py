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
    get_active_cooldowns_from_db
)
from prompts import analyze_crypto_news, formulate_trade_strategy
from telegram_bot import send_telegram_trade_approval

# -----------------------------------------
# DÜĞÜM (NODE) TANIMLARI
# -----------------------------------------

from news_service import fetch_live_global_crypto_news
from surge_detector import detect_early_volume_breakouts

def node_fetch_data(state: CryptoAgentState) -> Dict[str, Any]:
    print("\n--- [1. NODE: DİNAMİK BORSA VE ANLIK FİYAT MOTORU DEVREDE] ---")
    tenant_config = state.get("tenant_config")
    portfolio = fetch_portfolio_balance(tenant_config)
    return {"news_data": "Fast Scalper Active", "portfolio_state": portfolio}

def node_analyze_news(state: CryptoAgentState) -> Dict[str, Any]:
    return {"sentiment_score": 8.5}

def node_formulate_strategy(state: CryptoAgentState) -> Dict[str, Any]:
    print("\n--- [3. NODE: STRATEJİ VE OTONOM KÂR ALMA MOTORU DEVREDE] ---")
    portfolio_state = state.get("portfolio_state") or {}
    tenant_config = state.get("tenant_config") or {}
    tenant_id = str(tenant_config.get("id") or tenant_config.get("telegram_chat_id") or "default_tenant")
    user_tp = float(tenant_config.get("take_profit_percent") or 1.5)
    user_sl = float(tenant_config.get("stop_loss_percent") or 1.5)
    exch_id = str(tenant_config.get("exchange_id", "")).lower()
    is_tr_user = bool(exch_id in ["binancetr", "binance.tr", "trbinance"])
    live_fx = get_live_usd_try_rate()
    
    # -------------------------------------------------------------
    # 1. KISIM: AÇIK POZİSYONLARIN KÂR ALMA / STOP-LOSS DENETİMİ (SUPABASE LEDGER)
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
        # DB Ledger üzerinden açık pozisyonları oku
        saved_positions = get_active_positions_from_db(tenant_id=tenant_id, exchange_id=exch_name)
        
        if isinstance(holdings_map, dict):
            for coin_asset, details in holdings_map.items():
                asset_upper = str(coin_asset).upper()
                if asset_upper in ["TRY", "USDT", "BUSD", "USDC"]:
                    continue
                    
                coin_amount = details.get("amount", 0.0) if isinstance(details, dict) else float(details or 0.0)
                val_fiat = details.get("val_try" if is_tr_silo else "val_usd", 0.0) if isinstance(details, dict) else 0.0
                
                # Asgari borsa işlem limitinin altındaki tozları satışa sokma ($5.00 USD / ₺10.00 TL)
                min_thresh = 10.0 if is_tr_silo else 5.0
                if coin_amount > 0.0001 and val_fiat >= min_thresh:
                    target_symbol = f"{asset_upper}/{pair_quote}"
                    ticker = fetch_ticker_price(target_symbol)
                    curr_p = float(ticker.get("last_price", 0.0))
                    if curr_p <= 0:
                        continue
                        
                    recorded_buy_p = 0.0
                    pos_sl_price = 0.0
                    pos_tp_price = 0.0
                    entry_info = saved_positions.get(asset_upper)
                    if isinstance(entry_info, dict):
                        recorded_buy_p = float(entry_info.get("buy_price", 0.0))
                        pos_sl_price = float(entry_info.get("stop_loss_price") or 0.0)
                        pos_tp_price = float(entry_info.get("take_profit_price") or 0.0)
                        
                    if recorded_buy_p <= 0.0:
                        print(f"   ⚠️ [Bilinmeyen Maliyet]: {asset_upper} için DB'de kayıtlı alış fiyatı bulunamadı. Hatalı stop tetiklememek için pozisyon bekletiliyor.")
                        continue
                            
                    gross_change_pct = ((curr_p - recorded_buy_p) / recorded_buy_p * 100) if recorded_buy_p > 0 else 0.0
                    BINANCE_COMMISSION_PCT = 0.20
                    # Komisyon hem kârda hem zararda düşülür (Gerçek Net P&L)
                    net_profit_pct = gross_change_pct - BINANCE_COMMISSION_PCT
                    
                    # 🚀 CLAUDE İZ SÜREN STOP & KONTROL MERKEZİ ENTEGRASYONU
                    from db import get_system_setting
                    trailing_enabled = bool(get_system_setting("trailing_stop_enabled", True))
                    stage = str(entry_info.get("stage") or "INITIAL")
                    highest_p = float(entry_info.get("highest_price") or recorded_buy_p)
                    
                    # Zirve fiyatı anlık güncelle
                    if curr_p > highest_p:
                        highest_p = curr_p
                        save_position_to_db(
                            tenant_id=tenant_id,
                            exchange_id=exch_name,
                            symbol=target_symbol,
                            base_asset=asset_upper,
                            quote_asset=pair_quote,
                            amount=coin_amount,
                            buy_price=recorded_buy_p,
                            stop_loss_price=pos_sl_price,
                            take_profit_price=pos_tp_price,
                            highest_price=curr_p,
                            stage=stage
                        )
                    
                    is_stop_loss = False
                    is_take_profit = False
                    reason_type_str = "exit"
                    reason_desc = ""
                    sell_fraction = 1.0 # Varsayılan %100 satış
                    
                    if trailing_enabled:
                        if stage == "INITIAL":
                            # 🛡️ ERKEN MALİYET VE KÂR KORUMA SİGORTASI (Early Breakeven & Peak Profit Lock)
                            # 1. Kural: Coin en az +%2.0 görmüşse ve maliyete inerse asla zarara izin vermez, 0 zararla kapatır!
                            if highest_p >= recorded_buy_p * 1.020 and curr_p <= recorded_buy_p * 1.002:
                                is_stop_loss = True
                                reason_type_str = "breakeven_exit"
                                reason_desc = f"🛡️ Erken Maliyet Sigortası (0 Zararla Kapatıldı @ ${recorded_buy_p:,.4f})"
                                sell_fraction = 1.0
                            # 2. Kural: Coin en az +%3.0 görmüş ve zirveden %1.8 geri çekilmişse, kârı cebe kilitler!
                            elif highest_p >= recorded_buy_p * 1.030 and curr_p <= highest_p * 0.982:
                                is_take_profit = True
                                reason_type_str = "peak_profit_lock"
                                reason_desc = f"🏆 Zirve Kâr Koruma Satışı (+%{net_profit_pct:.2f} Net Cebe Kilitlendi)"
                                sell_fraction = 1.0
                            # 3. Kural: Standart Stop-Loss veya %50 Kısmi Kâr Alma
                            elif (pos_sl_price > 0 and curr_p <= pos_sl_price) or (net_profit_pct <= -user_sl):
                                is_stop_loss = True
                                reason_type_str = "stop-loss"
                                reason_desc = f"Stop-Loss (%{net_profit_pct:.2f} Net)"
                                sell_fraction = 1.0
                            elif (pos_tp_price > 0 and curr_p >= pos_tp_price) or (net_profit_pct >= user_tp):
                                is_take_profit = True
                                # Küçük bakiye koruması: Pozisyon $15 / ₺500 altındaysa %100 tek seferde satılır (asgari $5 limiti takılmaz)
                                if (not is_tr_silo and val_fiat < 15.0) or (is_tr_silo and val_fiat < 500.0):
                                    reason_type_str = "take-profit"
                                    reason_desc = f"🏆 Tam Kâr Alma (%100 Satıldı @ +%{net_profit_pct:.2f} Net)"
                                    sell_fraction = 1.0
                                else:
                                    reason_type_str = "partial_take_profit"
                                    reason_desc = f"1. Aşama Kademeli Kâr (%50 Satıldı @ +%{net_profit_pct:.2f} Net)"
                                    sell_fraction = 0.5 # Yarısı satılır, kalan %50 Breakeven + Trailing'e geçer
                        else: # STAGE_1_TP_TAKEN (Koşucu / Runner Modu)
                            trail_sl_price = highest_p * (1 - 0.025) # Zirveden %2.5 geri çekilme
                            if curr_p <= recorded_buy_p: # Maliyet (Breakeven) Stop
                                is_stop_loss = True
                                reason_type_str = "breakeven_exit"
                                reason_desc = f"Maliyet Koruma (Breakeven @ ${recorded_buy_p:,.4f})"
                                sell_fraction = 1.0
                            elif curr_p <= trail_sl_price: # İz Süren Stop Zirve Çıkışı
                                is_take_profit = True
                                reason_type_str = "trailing_stop_exit"
                                reason_desc = f"İz Süren Stop Zirve Çıkışı (Zirve: ${highest_p:,.4f} -> Çıkış: ${curr_p:,.4f} | Net: +%{net_profit_pct:.2f})"
                                sell_fraction = 1.0
                    else:
                        # KLASİK MOD: Sabit TP ve SL ile %100 tek seferde çıkış
                        if (pos_sl_price > 0 and curr_p <= pos_sl_price) or (net_profit_pct <= -user_sl):
                            is_stop_loss = True
                            reason_type_str = "stop-loss"
                            reason_desc = f"Stop-Loss (%{net_profit_pct:.2f} Net)"
                            sell_fraction = 1.0
                        elif (pos_tp_price > 0 and curr_p >= pos_tp_price) or (net_profit_pct >= user_tp):
                            is_take_profit = True
                            reason_type_str = "take-profit"
                            reason_desc = f"Kâr Alma (+%{net_profit_pct:.2f} Net)"
                            sell_fraction = 1.0
                        
                    if is_stop_loss or is_take_profit:
                        sell_coin_amt = coin_amount * sell_fraction
                        sell_val_fiat = val_fiat * sell_fraction
                        
                        sell_proposal = {
                            "should_trade": True,
                            "symbol": target_symbol,
                            "direction": "SELL",
                            "is_stop_loss": is_stop_loss,
                            "reason_type": reason_type_str,
                            "amount_usd": round(sell_val_fiat / live_fx if is_tr_silo else sell_val_fiat, 2),
                            "amount_coin": sell_coin_amt,
                            "remaining_coin": coin_amount - sell_coin_amt,
                            "entry_price": recorded_buy_p,
                            "highest_price": highest_p,
                            "stage": stage,
                            "sell_fraction": sell_fraction,
                            "net_profit_pct": round(net_profit_pct, 2),
                            "gross_change_pct": round(gross_change_pct, 2),
                            "stop_loss_percent": user_sl,
                            "stop_loss_price": pos_sl_price or round(recorded_buy_p * (1 - (user_sl/100.0)), 8 if recorded_buy_p < 1 else 2),
                            "take_profit_price": pos_tp_price or curr_p,
                            "risk_justification": f"Otomatik Kâr/Zarar Kapatma: {asset_upper}/{pair_quote} ({reason_desc})"
                        }
                        print(f"   [Seçilen İşlem Teklifi]: SATIM ({sell_proposal['symbol']}) - {reason_desc} | Alış: ${sell_proposal['entry_price']} -> Güncel: ${curr_p}")
                        return {"trade_proposal": sell_proposal, "human_approval": "Approved"}
                    else:
                        # 🧩 3 KADEMELİ AKILLI GİRİŞ (DCA 2. KADEME DİP EKLEME):
                        # Pozisyon INITIAL aşamasında ise, zırh aktifse ve -%1.0 ile -%2.2 arası sağlıklı geri çekilme yaptıysa:
                        from db import get_system_setting
                        shield_active = bool(get_system_setting("v21_security_shield_enabled", True))
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
                                    "risk_justification": f"🧩 3 Kademeli Akıllı Giriş (DCA 2. Kademe): {asset_upper} -%{abs(net_profit_pct):.2f} geri çekilme desteğinde ortalama maliyeti düşürmek için ${dca_budget:.1f} eklendi."
                                }
                                print(f"   [Seçilen İşlem Teklifi]: 🧩 DCA 2. KADEME ALIM ({target_symbol}) - Fiyat: ${curr_p} | Maliyet Düşürme Bütçesi: ${dca_budget}")
                                return {"trade_proposal": dca_proposal, "human_approval": "Approved"}

                        trail_info_str = f" | Zirve: ${highest_p:,.4f}, İz Süren SL: ${highest_p*0.975:,.4f}" if (trailing_enabled and stage != "INITIAL") else ""
                        print(f"   ⏳ [Pozisyon Bekletiliyor (HOLD)]: {asset_upper} (Aşama: {stage}, Birim: {pair_quote}, Net: %{net_profit_pct:+.2f}{trail_info_str} | SL: ${pos_sl_price:,.4f}, TP: ${pos_tp_price:,.4f}).")
                elif asset_upper in saved_positions:
                    # Kalan bakiye borsa asgari işlem sınırının ($5 / ₺10) altında kalmış mikro toz ise DB'den temizle
                    remove_position_from_db(tenant_id=tenant_id, exchange_id=exch_name, symbol=f"{asset_upper}/{pair_quote}")

    # Serbest nakit kontrolü (Çift Borsa ve Tekil Borsa Tam Uyumlu)
    live_fx = get_live_usd_try_rate()
    if live_fx <= 0:
        print("   ❌ [Canlı Kur Hatası]: USDT/TRY kuru okunamadı. Güvenlik amacıyla piyasa taraması durduruldu (Fail-Closed).")
        return {"trade_proposal": None, "human_approval": "Rejected"}

    holdings = portfolio_state.get("holdings_details") or portfolio_state.get("crypto_holdings") or {}
    free_try = float(portfolio_state.get("free_try") or portfolio_state.get("binance_tr", {}).get("free_try") or 0.0)
    free_usdt = float(portfolio_state.get("free_usdt") or portfolio_state.get("binance_global", {}).get("free_usdt") or 0.0)
    if isinstance(holdings, dict):
        if free_try <= 0:
            free_try = float(holdings.get("TRY", {}).get("amount", 0.0) if isinstance(holdings.get("TRY"), dict) else holdings.get("TRY", 0.0))
        if free_usdt <= 0:
            free_usdt = float(holdings.get("USDT", {}).get("amount", 0.0) if isinstance(holdings.get("USDT"), dict) else holdings.get("USDT", 0.0))
            
    is_dual = (exch_id == "dual")
    total_avail_usd = (free_try / live_fx) + free_usdt
    if total_avail_usd < 5.0 and free_try < 50.0:
        print(f"   ⏳ [Nakit Bakiye Yetersiz]: Serbest nakit (Global: ${free_usdt:.2f} / TR: ₺{free_try:.2f}) yeni alım için yetersiz. Bekletiliyor.")
        return {"trade_proposal": None, "human_approval": "Rejected"}

    # KATI PORTFÖY ÇEŞİTLİLİK ENGELİ: Yalnızca ($6.50 USD / ₺250 TL üzeri) GERÇEK pozisyonları sayar (Tozlar elenir!)
    current_assets = []
    if isinstance(holdings, dict):
        for k, v in holdings.items():
            if str(k).upper() in ["TRY", "USDT", "USDC", "BNB"]:
                continue
            amt = v.get("amount", 0.0) if isinstance(v, dict) else float(v or 0.0)
            val = v.get("val_usd", 0.0) if isinstance(v, dict) else 0.0
            val_tl = v.get("val_try", 0.0) if isinstance(v, dict) else 0.0
            if amt > 0.0001 and (val >= 6.50 or val_tl >= 250.0):
                current_assets.append(str(k).upper())

    # 🛡️ 1. DEVRE KESİCİ & DİNAMİK POZİSYON SINIRI KONTROLÜ (Adaptive Slot Management)
    from circuit_breaker import check_circuit_breaker, get_adaptive_max_slots
    tot_val_usd = float(portfolio_state.get("total_usdt", 0.0))
    adaptive_max_slots = get_adaptive_max_slots(tot_val_usd)
    cb_check = check_circuit_breaker(tenant_id=tenant_id, open_positions_count=len(current_assets), max_concurrent_positions=adaptive_max_slots)
    if not cb_check.get("allowed", True):
        print(f"   🛑 [Devre Kesici Engeli]: {cb_check.get('reason')}")
        return {"trade_proposal": None, "human_approval": "Rejected"}

    # 🌐 2. PİYASA REJİMİ KONTROLÜ (BTC EMA200 Ayı Rejimi Koruması)
    from market_regime import check_market_regime
    regime = check_market_regime()
    if not regime.get("is_bullish", True):
        print(f"   ⚠️ [Piyasa Rejimi Uyarısı]: {regime.get('reason')}. Yeni altcoin alımları donduruldu (Sermaye Koruma).")
        return {"trade_proposal": None, "human_approval": "Rejected"}

    from surge_detector import get_active_trading_symbols
    active_syms = get_active_trading_symbols()

    # DOĞRUDAN VE KESİNTİSİZ ERKEN BALİNA VE HACİM PATLAMASI TARAYICI (Çift Borsa Eşzamanlı)
    dynamic_candidates = []
    seen_symbols = set()
    try:
        # Eğer çift borsa kullanıcısıysa hem TRY hem USDT tahtalarını tara
        quotes_to_scan = []
        if is_dual:
            if free_try >= 50.0: quotes_to_scan.append("TRY")
            if free_usdt >= 5.0: quotes_to_scan.append("USDT")
        elif is_tr_user or (free_usdt < 5.0 and free_try >= 50.0):
            quotes_to_scan.append("TRY")
        else:
            quotes_to_scan.append("USDT")
            
        for q_sym in quotes_to_scan:
            early_surges = detect_early_volume_breakouts(quote=q_sym)
            for es in early_surges:
                sym_c = es.get("symbol", "") if isinstance(es, dict) else str(es)
                if sym_c and sym_c not in seen_symbols:
                    seen_symbols.add(sym_c)
                    dynamic_candidates.append(es)
    except Exception:
        pass
        
    try:
        top_g = fetch_top_volume_gainers(limit=15)
        for tg in top_g:
            sym_c = tg.get("symbol", "") if isinstance(tg, dict) else str(tg)
            if sym_c and sym_c not in seen_symbols:
                seen_symbols.add(sym_c)
                dynamic_candidates.append(tg)
    except Exception:
        pass
    
    # 🛑 3. KURAL İÇİN SUPABASE ATOMİK SOĞUMA / GEÇMİŞ ÇIKIŞ HAFIZASI:
    active_db_cooldowns = get_active_cooldowns_from_db(tenant_id=tenant_id)
    if active_db_cooldowns is None:
        print("   ❌ [Veritabanı Uyarısı]: Supabase soğuma listesi okunamadı. Güvenlik amacıyla alım bekletiliyor (Fail-Closed).")
        return {"trade_proposal": None, "human_approval": "Rejected"}

    fresh_coin = None
    selected_proposal = None
    
    for c in dynamic_candidates:
        c_sym = c.get("symbol", "") if isinstance(c, dict) else str(c)
        c_base = c_sym.split("/")[0].split("_")[0].upper()
        target_pair_clean = f"{c_base}{pair_quote}"
        if c_base in current_assets or c_base in ["TRY", "USDT", "USDC", "FDUSD", "BUSD"]:
            continue
        if active_syms and target_pair_clean not in active_syms:
            continue
            
        best_candidate_meta = c if isinstance(c, dict) else {}
        base_score = float(best_candidate_meta.get("momentum_score", 7.0))
        price_change_5m = float(best_candidate_meta.get("price_change_5m", 2.0))
        vol_spike = float(best_candidate_meta.get("volume_spike_ratio", 2.0))

        # -------------------------------------------------------------
        # 1. KURAL: DİP GİRİŞ KONTROLÜ (Pre-Pump Ground-Floor Filter)
        # -------------------------------------------------------------
        # 24 saatte %+15.0 ve 5 dakikada %+7.0'yi aşmamış taze hareketler yakalanır.
        cand_24h_change = float(best_candidate_meta.get("price_change_24h", 0.0))
        if cand_24h_change > 15.0 or price_change_5m > 7.0:
            print(f"   🛑 [1. Kural Reddi]: {c_base} aşırı primli (24s: %{cand_24h_change:+.1f}, 5dk: %{price_change_5m:+.1f}). FOMO engellendi.")
            continue

        # -------------------------------------------------------------
        # 2. KURAL: DOYUM NOKTASI VE DERİNLİK ANALİZİ (Saturation Engine)
        # -------------------------------------------------------------
        try:
            depth_res = requests.get(f"https://api.binance.com/api/v3/depth?symbol={target_pair_clean}&limit=10", timeout=2).json()
            bids_vol = sum(float(b[1]) for b in depth_res.get("bids", []))
            asks_vol = sum(float(a[1]) for a in depth_res.get("asks", []))
            if asks_vol <= 0:
                print(f"   🛑 [2. Kural Reddi]: {c_base} tahtasında satış derinliği bulunamadı. Alım iptal.")
                continue
            orderbook_ratio = bids_vol / asks_vol
        except Exception as e_depth:
            print(f"   🛑 [2. Kural Reddi]: {c_base} tahta derinliği okunamadı ({e_depth}). Fail-Closed gereği alım iptal.")
            continue

        # Satış baskısı alışın 1.5 katından fazlaysa (Alış/Satış < 0.65): Doyum noktasına ulaşılmıştır!
        if asks_vol > (bids_vol * 1.5) or orderbook_ratio < 0.65:
            print(f"   🛑 [2. Kural Reddi]: {c_base} tahtasında ağır satış baskısı (Alış/Satış: {orderbook_ratio:.2f}). Alım iptal.")
            continue

        orderbook_boost = 1.0 if orderbook_ratio >= 1.2 else (0.0 if orderbook_ratio >= 0.8 else -0.5)
        ai_conviction_score = min(10.0, max(1.0, round(base_score + orderbook_boost, 1)))

        # -------------------------------------------------------------
        # 3. KURAL: KÂR VE ZARAR SONRASI DİNLENME SOĞUMASI (Cooldown Filter)
        # -------------------------------------------------------------
        is_recently_sold = (c_base in active_db_cooldowns)
        if is_recently_sold:
            print(f"   ⏳ [3. Kural - Soğuma Kilidi]: {c_base} yakın zamanda satıldığı için dinlenmede.")
            continue

        if ai_conviction_score < 5.0:
            continue
            
        # 🎯 KURUMSAL BORSACI KASA YÖNETİMİ & v2.1 GÜVENLİK ZIRHI KONTROLÜ:
        from db import get_system_setting
        shield_active = bool(get_system_setting("v21_security_shield_enabled", True))
        
        user_max_budget_pct = float(tenant_config.get("max_budget_percent") or 15.0)
        cand_quote = "TRY" if (c_sym.upper().endswith("TRY") or c_sym.upper().endswith("_TRY")) else "USDT"
        is_quote_try = (cand_quote == "TRY")
        target_slots = max(4, adaptive_max_slots) if shield_active else max(1, adaptive_max_slots)
        
        if is_quote_try:
            tot_tr_try = float(portfolio_state.get("binance_tr", {}).get("total_try", 0.0)) or (tot_val_usd * live_fx)
            max_cap_tl = round(tot_tr_try * (user_max_budget_pct / 100.0), 2)
            slot_budget_tl = min(round(tot_tr_try / target_slots, 2), max_cap_tl, 1200.0) if shield_active else round(tot_tr_try / target_slots, 2)
            trade_budget_tl = min(slot_budget_tl, free_try * 0.95)
            safe_budget_usd = round(trade_budget_tl / live_fx, 2)
            if free_try < 100.0 or trade_budget_tl < 100.0:
                user_label = (tenant_config or {}).get("tenant_name", "Kullanıcı")
                print(f"   ⏳ [Bütçe Yetersiz ({user_label})]: Serbest TL (₺{free_try:.2f}) slot bütçesi (₺{slot_budget_tl:.2f}) için yetersiz.")
                continue
        else:
            tot_gl_usd = float(portfolio_state.get("binance_global", {}).get("total_usdt", 0.0)) or tot_val_usd
            max_cap_usd = min(round(tot_gl_usd * (user_max_budget_pct / 100.0), 2), 30.0) # Maksimum $30 / %15 katı tavan
            slot_budget_usd = min(round(tot_gl_usd / target_slots, 2), max_cap_usd) if shield_active else round(tot_gl_usd / target_slots, 2)
            safe_budget_usd = round(min(slot_budget_usd, free_usdt * 0.95), 2)
            if free_usdt < 10.0 or safe_budget_usd < 10.0:
                user_label = (tenant_config or {}).get("tenant_name", "Kullanıcı")
                print(f"   ⏳ [Bütçe Yetersiz ({user_label})]: Serbest USDT (${free_usdt:.2f}) slot bütçesi (${slot_budget_usd:.2f}) için yetersiz.")
                continue
            
        fresh_coin = f"{c_base}/{cand_quote}"
        real_ticker = fetch_ticker_price(fresh_coin)
        real_entry_price = float(real_ticker.get("last_price") or 1.0)
        if real_entry_price <= 0:
            continue
            
        # 🎯 ATR(14) Tabanlı Dinamik Stop-Loss ve R:R >= 1:2 Take-Profit
        from atr_calculator import calculate_atr_sl_tp
        tp_price, sl_price, dynamic_tp_pct, dynamic_sl_pct = calculate_atr_sl_tp(
            symbol=fresh_coin,
            entry_price=real_entry_price,
            user_tp_override=user_tp,
            user_sl_override=user_sl
        )
            
        reentry_tag = " (2. Kademe Heyet Onaylı Giriş)" if is_recently_sold else ""
        from db import get_coin_historical_performance
        tenant_id = tenant_config.get("id") or str(tenant_config.get("telegram_chat_id", ""))
        coin_perf = get_coin_historical_performance(tenant_id, c_base)
        perf_insight = coin_perf.get("insight_summary", "Geçmiş veri yok.")
        
        dynamic_budget_pct = round(100.0 / target_slots, 1)
        selected_proposal = {
            "should_trade": True,
            "symbol": fresh_coin,
            "direction": "BUY",
            "amount_usd": safe_budget_usd,
            "entry_price": real_entry_price,
            "sentiment_score": ai_conviction_score,
            "take_profit_price": tp_price,
            "stop_loss_price": sl_price,
            "take_profit_percent": dynamic_tp_pct,
            "stop_loss_percent": dynamic_sl_pct,
            "coin_historical_insight": perf_insight,
            "risk_justification": f"Yapay Zeka Analiz Skoru: {ai_conviction_score}/10{reentry_tag} -> Tahta Oranı: {orderbook_ratio:.2f} | ATR TP: +%{dynamic_tp_pct:.1f} (${tp_price}) | ATR SL: -%{dynamic_sl_pct:.1f} (${sl_price}) (R:R 1:2) | Bütçe: Serbest kasanın %{dynamic_budget_pct:.1f}'i (${safe_budget_usd:.2f} USD) tahsis edildi. | 📊 [Geçmiş Hafıza]: {perf_insight}"
        }
        break
        
    if not selected_proposal:
        print("   ⏳ [Piyasa Beklemede (HOLD)]: Şu anda anlık balina şartını sağlayan onaylı yeni coin bulunamadı.")
        return {"trade_proposal": None, "human_approval": "Rejected"}

    print(f"   [Seçilen İşlem Teklifi]: {selected_proposal['direction']} {selected_proposal['symbol']} - Fiyat: ${selected_proposal['entry_price']} | TP: ${selected_proposal['take_profit_price']} | SL: ${selected_proposal['stop_loss_price']} | Bütçe: ${selected_proposal['amount_usd']} USD ({pair_quote})")
    return {"trade_proposal": selected_proposal, "human_approval": "Approved"}

def node_human_approval(state: CryptoAgentState) -> Dict[str, Any]:
    print("\n--- [4. NODE: TAM OTONOM MOD ONAYI DEVREDE] ---")
    proposal = state.get("trade_proposal")
    if not proposal:
        return {"human_approval": "Rejected"}
        
    # Tam Otonom Mod (Butonsuz Otomatik): Doğrudan onay ver ve borsada icra et
    print("   [Tam Otonom Mod]: İzin verildi. Borsada otomatik işlem başlatılıyor...")
    return {"human_approval": "Approved"}

def node_execute_trade(state: CryptoAgentState) -> Dict[str, Any]:
    print("\n--- [5. NODE: UYGULAYICI & SUPABASE LOGLAMA DEVREDE] ---")
    approval = state.get("human_approval")
    proposal = state.get("trade_proposal")
    tenant_config = state.get("tenant_config")
    
    if approval == "Approved" and proposal:
        result = execute_spot_trade(
            symbol=proposal["symbol"],
            side=proposal["direction"],
            amount_usd=proposal["amount_usd"],
            stop_loss_price=proposal["stop_loss_price"],
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
                            tenant_id=tenant_id,
                            exchange_id=exch_name,
                            symbol=proposal["symbol"],
                            base_asset=base_sym,
                            quote_asset=quote_c,
                            amount=tot_amt,
                            buy_price=avg_p,
                            stop_loss_price=round(avg_p * 0.975, 8 if avg_p < 1 else 2),
                            take_profit_price=proposal.get("take_profit_price"),
                            is_simulated=is_simulated,
                            stage=next_stage
                        )
                        print(f"🧩 [DCA Kademe Tamamlandı]: {base_sym} yeni ortalama maliyet: ${avg_p:.4f} (Toplam {tot_amt:.4f} adet | Aşama: {next_stage})")
                    else:
                        save_position_to_db(
                            tenant_id=tenant_id,
                            exchange_id=exch_name,
                            symbol=proposal["symbol"],
                            base_asset=base_sym,
                            quote_asset=quote_c,
                            amount=new_coin_amt,
                            buy_price=exec_p,
                            stop_loss_price=proposal.get("stop_loss_price"),
                            take_profit_price=proposal.get("take_profit_price"),
                            is_simulated=is_simulated,
                            stage="INITIAL"
                        )
                else: # SELL
                    r_type = str(proposal.get("reason_type", "")).lower()
                    if r_type == "partial_take_profit":
                        rem_amt = float(proposal.get("remaining_coin") or 0.0)
                        entry_p = float(proposal.get("entry_price") or 0.0)
                        high_p = float(proposal.get("highest_price") or entry_p)
                        # Breakeven Stop kurulur, stage = STAGE_1_TP_TAKEN
                        save_position_to_db(
                            tenant_id=tenant_id,
                            exchange_id=exch_name,
                            symbol=proposal["symbol"],
                            base_asset=base_sym,
                            quote_asset=quote_c,
                            amount=rem_amt,
                            buy_price=entry_p,
                            stop_loss_price=entry_p, # Maliyet (Breakeven) Stop
                            take_profit_price=None, # Sabit TP kalkar, trailing iz sürer
                            is_simulated=is_simulated,
                            highest_price=high_p,
                            stage="STAGE_1_TP_TAKEN",
                            partial_amount_sold=float(proposal.get("amount_coin") or 0.0)
                        )
                        print(f"🎯 [Kademeli Kâr Alındı]: {base_sym} %50 satıldı. Kalan {rem_amt} adet Breakeven (${entry_p}) + İz Süren Moda alındı!")
                    else:
                        remove_position_from_db(tenant_id=tenant_id, exchange_id=exch_name, symbol=proposal["symbol"])
                        # Satılan coin için 60 dakika soğuma başlat
                        set_cooldown_in_db(tenant_id=tenant_id, symbol=proposal["symbol"], base_asset=base_sym, duration_seconds=3600)
            else:
                # Satış emri bakiye yetersizliği (-2010) veya borsa mikro bakiye engeli (-1013 MIN_NOTIONAL) yüzünden başarısız olduysa,
                # bu coin gerçek borsada zaten satılmış veya sıfırlanmıştır. DB ledger'dan temizle ki sonsuz döngüye girmesin!
                if proposal["direction"].upper() not in ["BUY", "ALIM"]:
                    err_msg = str(result.get("error", "")).upper()
                    if "-1013" in err_msg or "MIN_NOTIONAL" in err_msg or "-2010" in err_msg or "INSUFFICIENT" in err_msg:
                        print(f"🧹 [Otomatik Temizleme]: {proposal['symbol']} borsada bulunamadığı veya mikro bakiye olduğu için veritabanı pozisyon listesinden düşürüldü.")
                        remove_position_from_db(tenant_id=tenant_id, exchange_id=exch_name, symbol=proposal["symbol"])
        except Exception as pe:
            print(f"⚠️ [DB Ledger Güncelleme Uyarısı]: {pe}")
            
        t_id = str((tenant_config or {}).get("id") or (tenant_config or {}).get("telegram_chat_id") or "default_tenant")
        t_name = str((tenant_config or {}).get("tenant_name") or "S")
        t_chat = (tenant_config or {}).get("telegram_chat_id")
        log_details = {
            **(result if isinstance(result, dict) else {}),
            "tenant_id": t_id,
            "tenant_name": t_name,
            "telegram_chat_id": t_chat,
            "reason_type": proposal.get("reason_type", "momentum_entry" if proposal.get("direction") == "BUY" else "exit"),
            "net_profit_pct": proposal.get("net_profit_pct", 0.0),
            "gross_change_pct": proposal.get("gross_change_pct", 0.0),
            "stop_loss_price": proposal.get("stop_loss_price"),
            "take_profit_price": proposal.get("take_profit_price")
        }
        log_payload = {
            **proposal,
            "sentiment_score": state.get("sentiment_score"),
            "human_approval": approval,
            "status": result.get("status", "EXECUTED"),
            "order_id": result.get("order_id"),
            "execution_details": log_details
        }
        t_id = str((tenant_config or {}).get("id") or (tenant_config or {}).get("telegram_chat_id") or "default_tenant")
        log_trade_decision(log_payload, tenant_id=t_id)
        save_graph_state("session_langgraph_hitl", state)
        return {"execution_result": result}
    else:
        print("❌ İşlem reddedildi veya onaylanmadı.")
        return {"execution_result": {"status": "CANCELLED"}}

# -----------------------------------------
# LANGGRAPH STATEGRAPH KURULUMU
# -----------------------------------------
def create_crypto_graph():
    workflow = StateGraph(CryptoAgentState)
    
    workflow.add_node("fetch_data", node_fetch_data)
    workflow.add_node("analyze_news", node_analyze_news)
    workflow.add_node("formulate_strategy", node_formulate_strategy)
    workflow.add_node("human_approval", node_human_approval)
    workflow.add_node("execute_trade", node_execute_trade)
    
    workflow.set_entry_point("fetch_data")
    workflow.add_edge("fetch_data", "analyze_news")
    workflow.add_edge("analyze_news", "formulate_strategy")
    workflow.add_edge("formulate_strategy", "human_approval")
    workflow.add_edge("human_approval", "execute_trade")
    workflow.add_edge("execute_trade", END)
    
    return workflow.compile()

if __name__ == "__main__":
    print("🚀 LangGraph StateGraph Akışı Çalıştırılıyor...")
    app_graph = create_crypto_graph()
    initial_state = {
        "news_data": "",
        "portfolio_state": {},
        "sentiment_score": 0.0,
        "trade_proposal": None,
        "human_approval": "Pending",
        "execution_result": None
    }
    final_output = app_graph.invoke(initial_state)
    print("\n✅ LangGraph Akışı Tamamlandı. Sonuç:", final_output.get("execution_result"))
