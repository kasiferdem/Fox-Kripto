import os, sys, time, json
if hasattr(sys.stdout, 'reconfigure'): sys.stdout.reconfigure(encoding='utf-8')
from typing import Dict, Any, Optional, List
from langgraph.graph import StateGraph, END
from langgraph.types import interrupt
from state import CryptoAgentState
from exchange import fetch_portfolio_balance, fetch_ticker_price, execute_spot_trade, fetch_top_volume_gainers
from db import log_trade_decision, save_graph_state
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
    user_tp = float(tenant_config.get("take_profit_percent") or 1.5)
    user_sl = float(tenant_config.get("stop_loss_percent") or 1.5)
    
    # 🇹🇷 VE 🌍 HER İKİ BORSAYI DA AYRI AYRI VE TAM BAĞIMSIZ DENETLE:
    exchange_silos = []
    bal_tr = portfolio_state.get("binance_tr", {})
    bal_gl = portfolio_state.get("binance_global", {})
    
    if bal_tr and bal_tr.get("holdings_details"):
        exchange_silos.append(("TRY", bal_tr.get("holdings_details", {}), "active_positions_tr.json", True))
    if bal_gl and bal_gl.get("holdings_details"):
        exchange_silos.append(("USDT", bal_gl.get("holdings_details", {}), "active_positions_global.json", False))
        
    if not exchange_silos:
        # Tekil Borsa Fallback
        is_tr_user = bool(tenant_config and tenant_config.get("exchange_id") in ["binancetr", "binance.tr", "trbinance"])
        pair_q = "TRY" if is_tr_user else "USDT"
        pos_f = "active_positions_tr.json" if is_tr_user else "active_positions_global.json"
        h = portfolio_state.get("holdings_details") or portfolio_state.get("crypto_holdings") or {}
        exchange_silos.append((pair_q, h, pos_f, is_tr_user))
        
    for pair_quote, holdings_map, pos_file_name, is_tr_silo in exchange_silos:
        pos_file = os.path.join(os.path.dirname(__file__), pos_file_name)
        saved_positions = {}
        if os.path.exists(pos_file):
            try:
                with open(pos_file, "r", encoding="utf-8") as pf:
                    saved_positions = json.load(pf)
            except Exception:
                pass
                
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
                    elif isinstance(entry_info, (int, float)):
                        recorded_buy_p = float(entry_info)
                        
                    if recorded_buy_p <= 0.0:
                        recorded_buy_p = curr_p
                        saved_positions[asset_upper] = {"buy_price": recorded_buy_p, "currency": pair_quote, "time": time.time()}
                        try:
                            with open(pos_file, "w", encoding="utf-8") as pf:
                                json.dump(saved_positions, pf, indent=2)
                        except Exception:
                            pass
                            
                    gross_change_pct = ((curr_p - recorded_buy_p) / recorded_buy_p * 100) if recorded_buy_p > 0 else 0.0
                    BINANCE_COMMISSION_PCT = 0.20
                    net_profit_pct = gross_change_pct - BINANCE_COMMISSION_PCT if gross_change_pct > 0 else gross_change_pct
                    
                    # KÂR ALMA / STOP-LOSS TETİKLENME DENETİMİ
                    if net_profit_pct >= user_tp or gross_change_pct <= -user_sl:
                        is_stop_loss = gross_change_pct <= -user_sl
                        reason_type = f"Stop-Loss (%{gross_change_pct:.2f})" if is_stop_loss else f"Kâr Alma (+%{net_profit_pct:.2f} Net)"
                        print(f"   🎯 [Otonom {reason_type} Tetiklendi]: {asset_upper} (Borsa: {'TR' if is_tr_silo else 'Global'}, Net: %{net_profit_pct:+.2f}) satılıyor...")
                        
                        sell_proposal = {
                            "should_trade": True,
                            "symbol": target_symbol,
                            "direction": "SELL",
                            "is_stop_loss": is_stop_loss,
                            "amount_usd": round(val_fiat / 47.80 if is_tr_silo else val_fiat, 2),
                            "amount_coin": coin_amount,
                            "entry_price": recorded_buy_p,
                            "net_profit_pct": round(net_profit_pct, 2),
                            "gross_change_pct": round(gross_change_pct, 2),
                            "stop_loss_percent": user_sl,
                            "stop_loss_price": round(recorded_buy_p * (1 - (user_sl/100.0)), 8 if recorded_buy_p < 1 else 2),
                            "take_profit_price": curr_p,
                            "risk_justification": f"Otomatik Kâr/Zarar Kapatma: {asset_upper}/{pair_quote} {reason_type}"
                        }
                        return {"trade_proposal": sell_proposal, "human_approval": "Approved"}
                    else:
                        print(f"   ⏳ [Pozisyon Bekletiliyor (HOLD)]: {asset_upper} (Birim: {pair_quote}, Net: %{net_profit_pct:+.2f}). Hedefe henüz ulaşmadı.")

    # Serbest nakit kontrolü (Çift Borsa ve Tekil Borsa Tam Uyumlu)
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
        free_cash_usd = free_try / 47.80
    else:
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

    from surge_detector import get_active_trading_symbols
    active_syms = get_active_trading_symbols()

    # DOĞRUDAN VE KESİNTİSİZ ERKEN BALİNA VE HACİM PATLAMASI TARAYICI
    dynamic_candidates = []
    try:
        early_surges = detect_early_volume_breakouts(quote=pair_quote)
        for es in early_surges:
            sym_c = es.get("symbol", "")
            if sym_c and sym_c not in dynamic_candidates:
                dynamic_candidates.append(sym_c)
    except Exception:
        pass
        
    try:
        top_g = fetch_top_volume_gainers(limit=15)
        for tg in top_g:
            sym_c = tg.get("symbol", "")
            if sym_c and sym_c not in dynamic_candidates:
                dynamic_candidates.append(sym_c)
    except Exception:
        pass
    
    fresh_coin = None
    for c in dynamic_candidates:
        c_base = c.split("/")[0].split("_")[0].upper()
        target_pair_clean = f"{c_base}{pair_quote}"
        # Sadece cüzdanda zaten bulunanları, kapalı tahtaları ve sabit paraları atla
        if c_base not in current_assets and c_base not in ["TRY", "USDT", "USDC", "FDUSD", "BUSD"]:
            if not active_syms or target_pair_clean in active_syms:
                fresh_coin = f"{c_base}/{pair_quote}"
                break
        
    if not fresh_coin:
        print("   ⏳ [Piyasa Beklemede (HOLD)]: Şu anda anlık balina hacim patlaması şartını sağlayan yeni coin bulunamadı.")
        return {"trade_proposal": None, "human_approval": "Rejected"}

    fresh_base = fresh_coin.split("/")[0].split("_")[0].upper()
    proposal = {
        "should_trade": True,
        "symbol": f"{fresh_base}/{pair_quote}",
        "direction": "BUY",
        "amount_usd": min(15.0, max(10.0, free_cash_usd)),
        "stop_loss_percent": 1.5,
        "risk_justification": f"Otomatik Balina Hacim Patlaması: {fresh_base}/{pair_quote} seçildi."
    }
    final_base = proposal["symbol"].split("/")[0].split("_")[0].upper()
    proposal["symbol"] = f"{final_base}/{pair_quote}"
    proposal["amount_usd"] = min(15.0, max(10.0, free_cash_usd))
    
    # GERÇEK COIN FİYATINI VE TP/SL SEVİYELERİNİ ANLIK TICKER'DAN HESAPLA:
    real_ticker = fetch_ticker_price(proposal["symbol"])
    real_entry_price = float(real_ticker.get("last_price") or 1.0)
    user_tp = float(tenant_config.get("take_profit_percent") or 1.5)
    user_sl = float(tenant_config.get("stop_loss_percent") or 1.5)
    
    proposal["entry_price"] = real_entry_price
    proposal["take_profit_price"] = round(real_entry_price * (1 + (user_tp / 100.0)), 6 if real_entry_price < 1 else 2)
    proposal["stop_loss_price"] = round(real_entry_price * (1 - (user_sl / 100.0)), 6 if real_entry_price < 1 else 2)
    
    print(f"   [Seçilen İşlem Teklifi]: {proposal['direction']} {proposal['symbol']} - Fiyat: ${real_entry_price} | TP: ${proposal['take_profit_price']} | SL: ${proposal['stop_loss_price']} | Bütçe: ${proposal['amount_usd']} USD ({pair_quote})")
    return {"trade_proposal": proposal, "human_approval": "Approved"}

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
        
        # Pozisyon Hafızasını Güncelle (%100 İzole Dosya: TR vs Global)
        try:
            is_try_order = proposal["symbol"].upper().endswith("TRY") or proposal["symbol"].upper().endswith("_TRY")
            pos_file_name = "active_positions_tr.json" if is_try_order else "active_positions_global.json"
            pos_file = os.path.join(os.path.dirname(__file__), pos_file_name)
            saved_positions = {}
            if os.path.exists(pos_file):
                with open(pos_file, "r", encoding="utf-8") as pf:
                    saved_positions = json.load(pf)
                    
            base_sym = proposal["symbol"].split("/")[0].split("_")[0].upper()
            status_str = str(result.get("status", "")).upper()
            if status_str in ["SUCCESS", "EXECUTED", "EXECUTED_SIMULATED"]:
                if proposal["direction"].upper() in ["BUY", "ALIM"]:
                    exec_p = float(result.get("executed_price") or proposal.get("entry_price") or 0.0)
                    quote_c = "TRY" if is_try_order else "USDT"
                    saved_positions[base_sym] = {"buy_price": exec_p, "currency": quote_c, "time": time.time()}
                else: # SELL
                    saved_positions.pop(base_sym, None)
                    # 10$ / 10 TL ALTI KÜSURAT VE TOZ BAKİYELERİ OTONOM TEMİZLE:
                    try:
                        from exchange import convert_dust_to_bnb
                        convert_dust_to_bnb(tenant_config)
                    except Exception:
                        pass
                    
                with open(pos_file, "w", encoding="utf-8") as pf:
                    json.dump(saved_positions, pf, indent=2)
        except Exception as pe:
            print(f"⚠️ [Pozisyon Hafıza Uyarısı]: {pe}")
            
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
