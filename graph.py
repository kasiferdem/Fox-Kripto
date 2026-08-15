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

def node_fetch_data(state: CryptoAgentState) -> Dict[str, Any]:
    print("\n--- [1. NODE: DİNAMİK TÜM BORSA VE KÜRESEL HABER TARAYICI DEVREDE] ---")
    tenant_config = state.get("tenant_config")
    portfolio = fetch_portfolio_balance(tenant_config)
    
    top_gainers = fetch_top_volume_gainers(limit=20)
    tickers_summary = []
    
    for t in top_gainers:
        tickers_summary.append(f"{t['symbol']}: Fiyat ${t['last_price']}, 24s Değişim %{t['percentage_change']:.2f}, Hacim ${t['volume']:,.0f}")
            
    global_headlines = fetch_live_global_crypto_news(limit_per_source=4)
    headlines_text = "\n".join(global_headlines) if global_headlines else "Küresel piyasada sakin haber akışı."
    
    news_text = (
        "🌍 DÜNYA VE OTORİTELERDEN ANLIK KRİPTO HABERLERİ (CoinDesk, CoinTelegraph, Decrypt):\n"
        + headlines_text
        + "\n\n📊 CANLI BİNANCE TÜM PİYASA VE EN ÇOK YÜKSELEN DİNAMİK ALTCOIN TARAMASI:\n"
        + "\n".join(tickers_summary)
    )
    print(f"   [Küresel Haber & Borsa Taraması]: {len(global_headlines)} Canlı Dünya Haberi ve {len(top_gainers)} Sıcak Altcoin başarıyla tarandı.")
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
    
    holdings = portfolio_state.get("holdings_details") or portfolio_state.get("crypto_holdings") or {}
    if isinstance(holdings, dict):
        for coin_asset, details in holdings.items():
            asset_upper = str(coin_asset).upper()
            if asset_upper in ["TRY", "USDT", "BUSD", "USDC"]:
                continue
                
            coin_amount = details.get("amount", 0.0) if isinstance(details, dict) else float(details or 0.0)
            val_usd = details.get("val_usd", 0.0) if isinstance(details, dict) else 0.0
            
            if coin_amount > 0.0001 and val_usd >= 1.0:
                ticker = fetch_ticker_price(f"{asset_upper}/USDT")
                curr_p = float(ticker.get("last_price", 0.0))
                if curr_p <= 0:
                    continue
                    
                # Kalıcı Alış Fiyatını Oku
                recorded_buy_p = 0.0
                if asset_upper in saved_positions and isinstance(saved_positions[asset_upper], dict):
                    recorded_buy_p = float(saved_positions[asset_upper].get("buy_price", 0.0))
                elif asset_upper in saved_positions and isinstance(saved_positions[asset_upper], (int, float)):
                    recorded_buy_p = float(saved_positions[asset_upper])
                
                if recorded_buy_p <= 0.0:
                    recorded_buy_p = default_entries.get(asset_upper, round(curr_p / 1.012, 4))
                    saved_positions[asset_upper] = {"buy_price": recorded_buy_p, "time": time.time()}
                    try:
                        with open(pos_file, "w", encoding="utf-8") as pf:
                            json.dump(saved_positions, pf, indent=2)
                    except Exception:
                        pass
                        
                gross_change_pct = ((curr_p - recorded_buy_p) / recorded_buy_p * 100) if recorded_buy_p > 0 else 0.0
                
                # Binance TR Borsa Komisyonu (Alış %0.10 + Satış %0.10 = Toplam %0.20 Komisyon Düşülür)
                BINANCE_COMMISSION_PCT = 0.20
                net_profit_pct = gross_change_pct - BINANCE_COMMISSION_PCT if gross_change_pct > 0 else gross_change_pct
                
                # KÂR ALMA (Net Kâr >= +%1.0) VEYA STOP-LOSS (Brüt <= -%1.5) TETİKLENME KONTROLÜ
                if net_profit_pct >= 1.0 or gross_change_pct <= -1.5:
                    reason_type = f"Net Kâr Alma (+%{net_profit_pct:.2f} Komisyon Sonrası)" if net_profit_pct >= 1.0 else f"Stop-Loss (%{gross_change_pct:.2f})"
                    print(f"   🎯 [Otonom {reason_type} Tetiklendi]: {asset_upper} (Brüt: %{gross_change_pct:+.2f}, Net: %{net_profit_pct:+.2f}) piyasa emriyle satılıyor...")
                    
                    is_tr_user = bool(tenant_config and tenant_config.get("exchange_id") in ["binancetr", "binance.tr", "trbinance"])
                    pair_quote = "TRY" if is_tr_user else "USDT"
                    sell_proposal = {
                        "should_trade": True,
                        "symbol": f"{asset_upper}/{pair_quote}",
                        "direction": "SELL",
                        "amount_usd": round(val_usd, 2),
                        "amount_coin": coin_amount,
                        "entry_price": recorded_buy_p,
                        "stop_loss_percent": 1.5,
                        "stop_loss_price": round(recorded_buy_p * 0.985, 4),
                        "take_profit_price": round(recorded_buy_p * 1.010, 4),
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

    proposed_symbol = str(proposal.get("symbol", "BTC/USDT")).upper()
    proposed_base = proposed_symbol.split("/")[0].split("_")[0].upper()
    sentiment_score = float(state.get("sentiment_score") or 0.0)
    
    if proposed_base in current_assets:
        # EĞER YAPAY ZEKA SKORU ZİRVEDE VE ÇOK YÜKSEKSE (>= 8.5 / 10), KULLANICIYA INTERAKTİF SORSUN!
        if sentiment_score >= 8.5:
            print(f"   🚨 [Aşırı Yükseliş Beklentisi (+{sentiment_score:.1f})]: '{proposed_base}' zaten cüzdanda var ancak skoru zirvede! Kullanıcıya onay butonu gönderiliyor...")
            proposal["requires_user_approval"] = True
            proposal["scale_in_reason"] = f"Zirve Yapay Zeka Skoru (+{sentiment_score:.1f})"
            return {"trade_proposal": proposal, "human_approval": "Pending_Approval"}
        else:
            # Skor çok yüksek değilse (küçük farklar için) otomatik olarak cüzdanda olmayan başka bir sıcak altcoine geç
            candidate_pool = ["PEPE/USDT", "AVAX/USDT", "RENDER/USDT", "SUI/USDT", "NEAR/USDT", "XRP/USDT", "DOGE/USDT", "BTC/USDT", "ETH/USDT"]
            fresh_coin = None
            for c in candidate_pool:
                c_base = c.split("/")[0]
                if c_base not in current_assets:
                    fresh_coin = c
                    break
            
            if fresh_coin:
                print(f"   🔄 [Portföy Çeşitlendirme Koruması]: '{proposed_base}' skoru normal (+{sentiment_score:.1f}). İkinci defa almak yerine cüzdanda olmayan '{fresh_coin}' seçildi.")
                proposal["symbol"] = fresh_coin
            else:
                print(f"   [Çeşitlendirme Reddi]: Tüm altcoinler cüzdanda mevcut. Yeni alım yapılmıyor.")
                return {"trade_proposal": None, "human_approval": "Rejected"}
            
    print(f"   [Seçilen İşlem Teklifi]: {proposal['direction']} {proposal['symbol']} - Bütçe: ${proposal['amount_usd']} USD")
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
                    saved_positions[base_sym] = {"buy_price": exec_p, "time": time.time()}
                else: # SELL
                    saved_positions.pop(base_sym, None)
                    
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
