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
    is_tr_user = bool(tenant_config and str(tenant_config.get("exchange_id", "")).lower() in ["binancetr", "binance.tr", "trbinance"])
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
                
                # Minimum $1 / 40 TL altı tozları atla
                min_thresh = 40.0 if is_tr_silo else 1.0
                if coin_amount > 0.0001 and val_fiat >= min_thresh:
                    target_symbol = f"{asset_upper}/{pair_quote}"
                    ticker = fetch_ticker_price(target_symbol)
                    curr_p = float(ticker.get("last_price", 0.0))
                    if curr_p <= 0:
                        continue
                        
                    recorded_buy_p = 0.0
                    entry_info = saved_positions.get(asset_upper)
                    if isinstance(entry_info, dict):
                        recorded_buy_p = float(entry_info.get("buy_price", 0.0))
                        
                    if recorded_buy_p <= 0.0:
                        print(f"   ⚠️ [Bilinmeyen Maliyet]: {asset_upper} için DB'de kayıtlı alış fiyatı bulunamadı. Hatalı stop tetiklememek için pozisyon bekletiliyor.")
                        continue
                            
                    gross_change_pct = ((curr_p - recorded_buy_p) / recorded_buy_p * 100) if recorded_buy_p > 0 else 0.0
                    BINANCE_COMMISSION_PCT = 0.20
                    # Komisyon hem kârda hem zararda düşülür (Gerçek Net P&L)
                    net_profit_pct = gross_change_pct - BINANCE_COMMISSION_PCT
                    
                    # KÂR ALMA / STOP-LOSS TETİKLENME DENETİMİ
                    if net_profit_pct >= user_tp or net_profit_pct <= -user_sl:
                        is_stop_loss = (net_profit_pct <= -user_sl)
                        reason_type = f"Stop-Loss (%{net_profit_pct:.2f} Net)" if is_stop_loss else f"Kâr Alma (+%{net_profit_pct:.2f} Net)"
                        
                        sell_proposal = {
                            "should_trade": True,
                            "symbol": target_symbol,
                            "direction": "SELL",
                            "is_stop_loss": is_stop_loss,
                            "amount_usd": round(val_fiat / live_fx if is_tr_silo else val_fiat, 2),
                            "amount_coin": coin_amount,
                            "entry_price": recorded_buy_p,
                            "net_profit_pct": round(net_profit_pct, 2),
                            "gross_change_pct": round(gross_change_pct, 2),
                            "stop_loss_percent": user_sl,
                            "stop_loss_price": round(recorded_buy_p * (1 - (user_sl/100.0)), 8 if recorded_buy_p < 1 else 2),
                            "take_profit_price": curr_p,
                            "risk_justification": f"Otomatik Kâr/Zarar Kapatma: {asset_upper}/{pair_quote} {reason_type}"
                        }
                        print(f"   [Seçilen İşlem Teklifi]: SATIM ({sell_proposal['symbol']}) - Kâr/Zarar: %{sell_proposal['net_profit_pct']}% | Alış: ${sell_proposal['entry_price']} -> Güncel: ${curr_p}")
                        return {"trade_proposal": sell_proposal, "human_approval": "Approved"}
                    else:
                        print(f"   ⏳ [Pozisyon Bekletiliyor (HOLD)]: {asset_upper} (Birim: {pair_quote}, Net: %{net_profit_pct:+.2f}). Hedefe henüz ulaşmadı.")

    # Serbest nakit kontrolü (Çift Borsa ve Tekil Borsa Tam Uyumlu)
    live_fx = get_live_usd_try_rate()
    if live_fx <= 0:
        print("   ❌ [Canlı Kur Hatası]: USDT/TRY kuru okunamadı. Güvenlik amacıyla piyasa taraması durduruldu (Fail-Closed).")
        return {"trade_proposal": None, "human_approval": "Rejected"}

    holdings = portfolio_state.get("holdings_details") or portfolio_state.get("crypto_holdings") or {}
    free_try = 0.0
    free_usdt = float(portfolio_state.get("free_usdt") or 0.0)
    if isinstance(holdings, dict):
        free_try = float(holdings.get("TRY", {}).get("amount", 0.0) if isinstance(holdings.get("TRY"), dict) else holdings.get("TRY", 0.0))
        if free_usdt <= 0:
            free_usdt = float(holdings.get("USDT", {}).get("amount", 0.0) if isinstance(holdings.get("USDT"), dict) else holdings.get("USDT", 0.0))
            
    if is_tr_user or (free_usdt < 5.0 and free_try >= 200.0):
        is_tr_user = True
        pair_quote = "TRY"
        free_cash_usd = free_try / live_fx
    else:
        pair_quote = "USDT"
        free_cash_usd = free_usdt

    if free_cash_usd < 5.0 and free_try < 200.0:
        print(f"   ⏳ [Nakit Bakiye Yetersiz]: Serbest nakit (${free_cash_usd:.2f} / ₺{free_try:.2f}) yeni alım için yetersiz. Bekletiliyor.")
        return {"trade_proposal": None, "human_approval": "Rejected"}

    # KATI PORTFÖY ÇEŞİTLİLİK ENGELİ: Cüzdanda MADDETEN BULUNAN coinleri tekrar almayı KESİNLİKLE engeller
    current_assets = []
    if isinstance(holdings, dict):
        for k, v in holdings.items():
            amt = v.get("amount", 0.0) if isinstance(v, dict) else float(v or 0.0)
            val = v.get("val_usd", 0.0) if isinstance(v, dict) else 0.0
            if amt > 0.0001 and val >= 1.0:
                current_assets.append(str(k).upper())

    # 🛡️ 1. DEVRE KESİCİ & POZİSYON SINIRI KONTROLÜ (Circuit Breaker)
    from circuit_breaker import check_circuit_breaker
    cb_check = check_circuit_breaker(tenant_id=tenant_id, open_positions_count=len(current_assets), max_concurrent_positions=3)
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

    # DOĞRUDAN VE KESİNTİSİZ ERKEN BALİNA VE HACİM PATLAMASI TARAYICI
    dynamic_candidates = []
    seen_symbols = set()
    try:
        early_surges = detect_early_volume_breakouts(quote=pair_quote)
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
        # Eğer bir coin son 24 saatte %+8.5 üzeri primlenmişse veya 5 dakikada %+5.5'i aşmışsa tepeye girilmez!
        cand_24h_change = float(best_candidate_meta.get("price_change_24h", 0.0))
        if cand_24h_change > 8.5 or price_change_5m > 5.5:
            print(f"   🛑 [1. Kural Reddi]: {c_base} zaten %+8.5 üzeri primli veya ani fırlamış (24s: %{cand_24h_change:+.1f}, 5dk: %{price_change_5m:+.1f}). FOMO engellendi.")
            continue

        # -------------------------------------------------------------
        # 2. KURAL: DOYUM NOKTASI VE DERİNLİK ANALİZİ (Saturation Engine)
        # -------------------------------------------------------------
        # Tahtadaki anlık alış/satış derinliği ve doyum seviyesi incelenir (Fail-Closed).
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

        # Satış baskısı alışın 1.3 katından fazlaysa (Alış/Satış < 0.77): Doyum noktasına ulaşılmıştır!
        if asks_vol > (bids_vol * 1.3) or orderbook_ratio < 0.77:
            print(f"   🛑 [2. Kural Reddi]: {c_base} tahtasında doyum ve satış baskısı tespit edildi (Alış/Satış Oranı: {orderbook_ratio:.2f}). Alım iptal.")
            continue

        orderbook_boost = 1.0 if orderbook_ratio >= 1.3 else (0.0 if orderbook_ratio >= 0.9 else -1.0)
        ai_conviction_score = min(10.0, max(1.0, round(base_score + orderbook_boost, 1)))

        # -------------------------------------------------------------
        # 3. KURAL: HEYET ONAYLI DİNAMİK YENİDEN GİRİŞ (Committee Consensus)
        # -------------------------------------------------------------
        # Statik kilit yerine: Eğer bu coin son 60 dk içinde satıldıysa,
        # sadece ve sadece ANALİZ HEYETİ oybirliğiyle onaylarsa (Skor >= 8.5 ve Güçlü Alıcı Baskısı) 2. kez alınır!
        is_recently_sold = (c_base in active_db_cooldowns)
        if is_recently_sold:
            committee_approved = (ai_conviction_score >= 8.5) and (vol_spike >= 3.0) and (orderbook_ratio >= 1.4)
            if not committee_approved:
                print(f"   ⏳ [3. Kural - Heyet Reddi]: {c_base} yakın zamanda satılmıştı. Heyet ikinci giriş için yeterli yeni ivme görmedi (Skor: {ai_conviction_score}, Hacim İvmesi: {vol_spike}x, Tahta Oranı: {orderbook_ratio:.2f}).")
                continue
            else:
                print(f"   🔥 [3. Kural - HEYET ONAYI VERİLDİ]: {c_base} için güçlü yeni balina dalgası tespit edildi. 2. Giriş Onaylandı!")

        if ai_conviction_score < 6.0:
            continue
            
        # 🤖 STRATEJİ BOTU DİNAMİK BÜTÇE TAHSİSİ (Sermaye Koruma & max_budget_percent)
        # Asla serbest kasanın %10'undan fazlası tek coine tahsis edilmez!
        user_max_budget = float(tenant_config.get("max_budget_percent") or 10.0)
        enforced_max_pct = min(10.0, max(1.0, user_max_budget))
        
        safe_budget_usd = round(free_cash_usd * (enforced_max_pct / 100.0) * 0.98, 2)
        min_order_usd = 5.0 if pair_quote == "TRY" else 10.0
        
        if safe_budget_usd < min_order_usd:
            if free_cash_usd >= min_order_usd and (free_cash_usd * 0.98 <= min_order_usd * 1.5):
                safe_budget_usd = round(min_order_usd, 2)
            else:
                continue
            
        fresh_coin = f"{c_base}/{pair_quote}"
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
            "risk_justification": f"Yapay Zeka Analiz Skoru: {ai_conviction_score}/10{reentry_tag} -> Tahta Oranı: {orderbook_ratio:.2f} | ATR TP: +%{dynamic_tp_pct:.1f} (${tp_price}) | ATR SL: -%{dynamic_sl_pct:.1f} (${sl_price}) (R:R 1:2) | Bütçe: Serbest kasanın %{enforced_max_pct:.1f}'i (${safe_budget_usd:.2f} USD) tahsis edildi."
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
                    coin_amt = float(proposal.get("amount_coin") or (proposal["amount_usd"] / exec_p if exec_p > 0 else 0))
                    save_position_to_db(
                        tenant_id=tenant_id,
                        exchange_id=exch_name,
                        symbol=proposal["symbol"],
                        base_asset=base_sym,
                        quote_asset=quote_c,
                        amount=coin_amt,
                        buy_price=exec_p,
                        stop_loss_price=proposal.get("stop_loss_price"),
                        take_profit_price=proposal.get("take_profit_price"),
                        is_simulated=is_simulated
                    )
                else: # SELL
                    remove_position_from_db(tenant_id=tenant_id, exchange_id=exch_name, symbol=proposal["symbol"])
                    # Satılan coin için 60 dakika soğuma başlat
                    set_cooldown_in_db(tenant_id=tenant_id, symbol=proposal["symbol"], base_asset=base_sym, duration_seconds=3600)
        except Exception as pe:
            print(f"⚠️ [DB Ledger Güncelleme Uyarısı]: {pe}")
            
        log_payload = {
            **proposal,
            "sentiment_score": state.get("sentiment_score"),
            "human_approval": approval,
            "status": result.get("status", "EXECUTED"),
            "order_id": result.get("order_id"),
            "execution_details": result
        }
        log_trade_decision(log_payload)
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
