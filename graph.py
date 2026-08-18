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
    print("\n--- [1. NODE: DİNAMİK TÜM BORSA VE ERKEN BALİNA HACİM TARAYICI DEVREDE] ---")
    tenant_config = state.get("tenant_config")
    portfolio = fetch_portfolio_balance(tenant_config)
    
    top_gainers = fetch_top_volume_gainers(limit=15)
    tickers_summary = []
    for t in top_gainers:
        tickers_summary.append(f"{t['symbol']}: Fiyat ${t['last_price']}, 24s Değişim %{t['percentage_change']:.2f}, Hacim ${t['volume']:,.0f}")
            
    early_surges = detect_early_volume_breakouts()
    surge_summary = []
    for s in early_surges:
        surge_summary.append(f"🚨 {s['symbol']}: Son 5dk Hacim Patlaması {s['volume_spike_ratio']}x, 5dk Fiyat Artışı +%{s['price_change_5m']}% (ERKEN BALİNA GİRİŞİ)")
        
    global_headlines = fetch_live_global_crypto_news(limit_per_source=3)
    headlines_text = "\n".join(global_headlines) if global_headlines else "Küresel piyasada sakin haber akışı."
    
    news_text = (
        "🔥 ERKEN BALİNA VE 5 DAKİKALIK ANİ HACİM PATLAMALARI (PRE-PUMP FIRSATLARI):\n"
        + ("\n".join(surge_summary) if surge_summary else "Şu anda ani 5dk balina patlaması tespit edilmedi.")
        + "\n\n🌍 DÜNYA VE OTORİTELERDEN ANLIK KRİPTO HABERLERİ (CoinDesk, CoinTelegraph, Decrypt):\n"
        + headlines_text
        + "\n\n📊 CANLI BİNANCE TÜM PİYASA VE EN ÇOK YÜKSELEN DİNAMİK ALTCOIN TARAMASI:\n"
        + "\n".join(tickers_summary)
    )
    print(f"   [Erken Balina & Borsa Taraması]: {len(early_surges)} Erken Balina Sinyali, {len(global_headlines)} Canlı Haber ve {len(top_gainers)} Sıcak Altcoin tarandı.")
    return {"news_data": news_text, "portfolio_state": portfolio}

def node_analyze_news(state: CryptoAgentState) -> Dict[str, Any]:
    print("\n--- [2. NODE: HABER & PİYASA ANALİZ AJANI (GPT-4o) DEVREDE] ---")
    analysis = analyze_crypto_news(state.get("news_data", ""), state.get("portfolio_state", {}))
    sentiment = float(analysis.get("sentiment_score", 0.0))
    print(f"   [GPT-4o Piyasa Skoru]: {sentiment} (+10/-10) | Yön: {analysis.get('market_bias')}")
    return {"sentiment_score": sentiment}

def node_formulate_strategy(state: CryptoAgentState) -> Dict[str, Any]:
    print("\n--- [3. NODE: STRATEJİ VE OTONOM KÂR ALMA MOTORU DEVREDE] ---")
    portfolio_state = state.get("portfolio_state") or {}
    tenant_config = state.get("tenant_config") or {}
    
    # 1. ÖNCELİK: Eldeki Pozisyonlarda Kalıcı Alış Takibi & Kâr Alma (+%1.0) / Stop-Loss (-%1.5) Denetimi
    pos_file = os.path.join(os.path.dirname(__file__), "active_positions.json")
    saved_positions = {}
    if os.path.exists(pos_file):
        try:
            with open(pos_file, "r", encoding="utf-8") as pf:
                saved_positions = json.load(pf)
        except Exception:
            pass
            
    default_entries = {
        "SOL": 74.80,
        "SUI": 0.6720,
        "PEPE": 0.00000262,
        "AVAX": 6.420,
        "RENDER": 1.250,
        "BTC": 62900.0,
        "NEAR": 1.580
    }
    
    is_tr_user = bool(tenant_config and tenant_config.get("exchange_id") in ["binancetr", "binance.tr", "trbinance"])
    pair_quote = "TRY" if is_tr_user else "USDT"
    
    holdings = portfolio_state.get("holdings_details") or portfolio_state.get("crypto_holdings") or {}
    if isinstance(holdings, dict):
        for coin_asset, details in holdings.items():
            asset_upper = str(coin_asset).upper()
            if asset_upper in ["TRY", "USDT", "BUSD", "USDC"]:
                continue
                
            coin_amount = details.get("amount", 0.0) if isinstance(details, dict) else float(details or 0.0)
            val_usd = details.get("val_usd", 0.0) if isinstance(details, dict) else 0.0
            
            if coin_amount > 0.0001 and val_usd >= 1.0:
                # KULLANICININ BORSA PARA BİRİMİNDE GERÇEK FİYAT OKU (TRY veya USDT)
                target_symbol = f"{asset_upper}/{pair_quote}"
                ticker = fetch_ticker_price(target_symbol)
                curr_p = float(ticker.get("last_price", 0.0))
                if curr_p <= 0:
                    continue
                    
                # Kalıcı Alış Fiyatını Oku (Doğrudan kullanıcının para biriminde)
                recorded_buy_p = 0.0
                if asset_upper in saved_positions and isinstance(saved_positions[asset_upper], dict):
                    saved_cur = saved_positions[asset_upper].get("currency", pair_quote)
                    if saved_cur == pair_quote:
                        recorded_buy_p = float(saved_positions[asset_upper].get("buy_price", 0.0))
                elif asset_upper in saved_positions and isinstance(saved_positions[asset_upper], (int, float)):
                    recorded_buy_p = float(saved_positions[asset_upper])
                
                # Eğer daha önce kaydedilmemişse, o anki piyasa fiyatı referans alış kabul edilir (0.00% değişim)
                if recorded_buy_p <= 0.0:
                    recorded_buy_p = curr_p
                    saved_positions[asset_upper] = {"buy_price": recorded_buy_p, "currency": pair_quote, "time": time.time()}
                    try:
                        with open(pos_file, "w", encoding="utf-8") as pf:
                            json.dump(saved_positions, pf, indent=2)
                    except Exception:
                        pass
                        
                gross_change_pct = ((curr_p - recorded_buy_p) / recorded_buy_p * 100) if recorded_buy_p > 0 else 0.0

                # Kullanıcıya Özel Kâr Alma ve Stop-Loss Limitleri (Varsayılan: %1.5 Kâr, %1.5 Zarar Kes)
                user_tp = float(tenant_config.get("take_profit_percent") or 1.5)
                user_sl = float(tenant_config.get("stop_loss_percent") or 1.5)
                
                # Binance Borsa Komisyonu (Alış %0.10 + Satış %0.10 = Toplam %0.20 Komisyon Düşülür)
                BINANCE_COMMISSION_PCT = 0.20
                net_profit_pct = gross_change_pct - BINANCE_COMMISSION_PCT if gross_change_pct > 0 else gross_change_pct
                
                # KÂR ALMA (Net Kâr >= user_tp) VEYA STOP-LOSS (Brüt <= -user_sl) TETİKLENME KONTROLÜ
                if net_profit_pct >= user_tp or gross_change_pct <= -user_sl:
                    is_stop_loss = gross_change_pct <= -user_sl
                    reason_type = f"Stop-Loss (%{gross_change_pct:.2f})" if is_stop_loss else f"Net Kâr Alma (+%{net_profit_pct:.2f} Komisyon Sonrası)"
                    print(f"   🎯 [Otonom {reason_type} Tetiklendi]: {asset_upper} (Birim: {pair_quote}, Brüt: %{gross_change_pct:+.2f}, Net: %{net_profit_pct:+.2f} / Hedef: %{user_tp}) piyasa emriyle satılıyor...")
                    
                    sell_proposal = {
                        "should_trade": True,
                        "symbol": target_symbol,
                        "direction": "SELL",
                        "is_stop_loss": is_stop_loss,
                        "amount_usd": round(val_usd, 2),
                        "amount_coin": coin_amount,
                        "entry_price": recorded_buy_p,
                        "net_profit_pct": round(net_profit_pct, 2),
                        "gross_change_pct": round(gross_change_pct, 2),
                        "stop_loss_percent": user_sl,
                        "stop_loss_price": round(recorded_buy_p * (1 - (user_sl/100.0)), 8 if recorded_buy_p < 1 else 2),
                        "take_profit_price": round(recorded_buy_p * (1 + (user_tp/100.0)), 8 if recorded_buy_p < 1 else 2),
                        "risk_justification": f"Otonom {reason_type}: {asset_upper} pozisyonu ({gross_change_pct:+.2f}%) {pair_quote} cüzdanına dönüştürülüyor."
                    }
                    return {"trade_proposal": sell_proposal, "human_approval": "Approved"}
                else:
                    print(f"   ⏳ [Pozisyon Bekletiliyor (HOLD)]: {asset_upper} pozisyonu henüz kâr hedefinde değil ({gross_change_pct:+.2f}%). Satış yapılmıyor.")

    news_analysis = {"sentiment_score": state.get("sentiment_score", 0.0), "market_data": state.get("news_data", "")}
    # Main coins ve altcoinler arasından en yüksek potansiyelli coini seçer
    proposal = formulate_trade_strategy(news_analysis, portfolio_state, 64000.0, symbol="AUTO")
    
    if not proposal.get("should_trade", True):
        print("   [Risk Reddi]: İşlem şartları oluşmadı. Akış sonlandırılıyor.")
        return {"trade_proposal": None, "human_approval": "Rejected"}
        
    # KATI PORTFÖY ÇEŞİTLİLİK ENGELİ: Cüzdanda MADDETEN BULUNAN coinleri tekrar almayı KESİNLİKLE engeller
    current_assets = []
    if isinstance(holdings, dict):
        for k, v in holdings.items():
            amt = v.get("amount", 0.0) if isinstance(v, dict) else float(v or 0.0)
            val = v.get("val_usd", 0.0) if isinstance(v, dict) else 0.0
            if amt > 0.0001 and val >= 1.0:
                current_assets.append(str(k).upper())

    proposed_symbol = str(proposal.get("symbol", "PEPE/USDT")).upper()
    if proposed_symbol.startswith("BTC") or proposed_symbol.startswith("ETH") or "AUTO" in proposed_symbol:
        proposed_symbol = "PEPE/USDT"
        
    from surge_detector import get_active_trading_symbols
    active_syms = get_active_trading_symbols()
    clean_prop_sym = proposed_symbol.replace("/", "").replace("_", "").upper()
    is_prop_active = (not active_syms) or (clean_prop_sym in active_syms)

    if proposed_base in current_assets or proposed_base in ["BTC", "ETH"] or not is_prop_active:
        # KATI KURAL: Sadece o an canlı TRADING durumundaki balina patlaması adayları
        dynamic_candidates = []
        try:
            early_surges = detect_early_volume_breakouts()
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
            c_clean = c.replace("/", "").replace("_", "").upper()
            # Sadece cüzdanda zaten bulunanları, kapalı tahtaları ve sabit paraları atla
            if c_base not in current_assets and c_base not in ["TRY", "USDT", "USDC", "FDUSD", "BUSD"]:
                if not active_syms or c_clean in active_syms:
                    fresh_coin = c
                    break
            
        if fresh_coin:
            fresh_base = fresh_coin.split("/")[0].upper()
            print(f"   🚨 [Canlı Balina Seçimi]: Anlık 5dk hacim patlaması yakalanan '{fresh_base}/{pair_quote}' seçildi.")
            proposal["symbol"] = f"{fresh_base}/{pair_quote}"
        else:
            print(f"   ⏳ [Piyasa Beklemede (HOLD)]: Şu anda anlık balina hacim patlaması şartını sağlayan yeni coin bulunamadı. Nakit boş yere bağlanmıyor, balina bekleniyor.")
            return {"trade_proposal": None, "human_approval": "Rejected"}
                
    final_base = proposal["symbol"].split("/")[0].split("_")[0].upper()
    proposal["symbol"] = f"{final_base}/{pair_quote}"
    
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
        
        # Pozisyon Hafızasını Güncelle (active_positions.json)
        try:
            pos_file = os.path.join(os.path.dirname(__file__), "active_positions.json")
            saved_positions = {}
            if os.path.exists(pos_file):
                with open(pos_file, "r", encoding="utf-8") as pf:
                    saved_positions = json.load(pf)
                    
            base_sym = proposal["symbol"].split("/")[0].split("_")[0].upper()
            status_str = str(result.get("status", "")).upper()
            if status_str in ["SUCCESS", "EXECUTED", "EXECUTED_SIMULATED"]:
                if proposal["direction"].upper() in ["BUY", "ALIM"]:
                    exec_p = float(result.get("executed_price") or proposal.get("entry_price") or 0.0)
                    quote_c = proposal["symbol"].split("/")[1].upper() if "/" in proposal["symbol"] else "TRY"
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
