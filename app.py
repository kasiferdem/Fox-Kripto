import os, sys
if hasattr(sys.stdout, 'reconfigure'): sys.stdout.reconfigure(encoding='utf-8')
from dotenv import load_dotenv
from typing import Dict, Any
from state import CryptoAgentState
from exchange import fetch_portfolio_balance, fetch_ticker_price, execute_spot_trade
from db import log_trade_decision, save_graph_state

load_dotenv()

# -----------------------------------------
# LANGGRAPH DÜĞÜM (NODE) ENTEGRASYONU (STEP 2)
# -----------------------------------------

def node_fetch_data(state: CryptoAgentState) -> Dict[str, Any]:
    """
    1. Gözlemci Düğümü (Observer):
    - CCXT ile güncel cüzdan bakiyesini (free USDT ve Coin miktarları) çeker.
    - Tanımlı haber veya piyasa duyarlılık verisini çeker.
    """
    print("\n--- [1. NODE: GÖZLEMCİ (CCXT DATA FETCH) DEVREDE] ---")
    portfolio = fetch_portfolio_balance()
    ticker = fetch_ticker_price("BTC/USDT")
    
    news_text = (
        f"BTC/USDT Anlık Fiyat: ${ticker['last_price']} (24s Değişim: %{ticker['percentage_change']}). "
        f"Piyasa hacmi ${ticker['volume']:,.2f} seviyesinde. Makroekonomik veriler pozitif trendi destekliyor."
    )
    
    print(f"   [Portföy]: Serbest USDT: ${portfolio['free_usdt']} | Toplam USD: ${portfolio['total_usdt']}")
    print(f"   [Canlı Veri]: {news_text}")
    
    return {
        "news_data": news_text,
        "portfolio_state": portfolio
    }

def node_analyze_news(state: CryptoAgentState) -> Dict[str, Any]:
    """
    2. Haber Ajanı Düğümü (News Agent):
    - LLM (GPT-4o) ile haber analiz eder.
    - Sentiment score (-10 ile +10) üretir.
    """
    print("\n--- [2. NODE: HABER ANALİZ AJANI DEVREDE] ---")
    # Step 3'te GPT-4o LLM zinciri eklenecek
    sentiment = 7.5
    print(f"   [Haber Skoru]: {sentiment} (+10 üzerinden Boğa / Pozitif)")
    return {
        "sentiment_score": sentiment
    }

def node_formulate_strategy(state: CryptoAgentState) -> Dict[str, Any]:
    """
    3. Strateji ve Risk Ajanı Düğümü (Strategy & Risk Agent):
    - KURAL: Hiçbir işlem teklifi toplam bütçenin %10'unu aşamaz.
    - KURAL: Her teklifte %3 ile %5 arası dinamik Stop-Loss.
    """
    print("\n--- [3. NODE: STRATEJİ VE RİSK AJANI DEVREDE] ---")
    portfolio = state.get("portfolio_state", {})
    free_usdt = portfolio.get("free_usdt", 1000.0)
    
    # %10 Bütçe Kuralı
    trade_budget = round(free_usdt * 0.10, 2)
    
    ticker = fetch_ticker_price("BTC/USDT")
    entry_price = ticker["last_price"]
    stop_loss_pct = 4.0  # %4 Dinamik Stop Loss
    stop_loss_price = round(entry_price * (1 - (stop_loss_pct / 100)), 2)
    take_profit_price = round(entry_price * 1.06, 2)  # %6 Take Profit
    
    proposal = {
        "symbol": "BTC/USDT",
        "direction": "BUY",
        "amount_usd": trade_budget,
        "entry_price": entry_price,
        "stop_loss_percent": stop_loss_pct,
        "stop_loss_price": stop_loss_price,
        "take_profit_price": take_profit_price
    }
    
    print(f"   [İşlem Teklifi]: {proposal['direction']} {proposal['symbol']} - Bütçe: ${trade_budget} USD | SL: ${stop_loss_price}")
    
    return {
        "trade_proposal": proposal,
        "human_approval": "Pending"
    }

def node_human_approval(state: CryptoAgentState) -> Dict[str, Any]:
    """
    4. Telegram HITL Onay Düğümü:
    - LangGraph interrupt ile duraklatılır (Step 4).
    """
    print("\n--- [4. NODE: TELEGRAM HITL ONAY DEVREDE] ---")
    print("   [HITL]: Kullanıcı Telegram onayı simüle ediliyor -> ONAYLANDI")
    return {
        "human_approval": "Approved"
    }

def node_execute_trade(state: CryptoAgentState) -> Dict[str, Any]:
    """
    5. Uygulayıcı Düğüm (Trade Executor & Supabase Logger):
    - CCXT üzerinden emri borsaya iletir.
    - İşlem sonucunu Supabase 'crypto_trade_logs' tablosuna kaydeder.
    """
    print("\n--- [5. NODE: UYGULAYICI & SUPABASE LOGLAMA DEVREDE] ---")
    approval = state.get("human_approval")
    proposal = state.get("trade_proposal", {})
    
    if approval == "Approved" and proposal:
        # CCXT Spot Trade
        result = execute_spot_trade(
            symbol=proposal["symbol"],
            side=proposal["direction"],
            amount_usd=proposal["amount_usd"],
            stop_loss_price=proposal["stop_loss_price"]
        )
        
        # Supabase Log
        log_payload = {
            **proposal,
            "sentiment_score": state.get("sentiment_score"),
            "human_approval": approval,
            "status": result.get("status", "EXECUTED"),
            "order_id": result.get("order_id"),
            "execution_details": result
        }
        log_trade_decision(log_payload)
        
        # LangGraph State Persistence Test
        save_graph_state("session_test_001", state)
        
        return {"execution_result": result}
    else:
        print("❌ İşlem onaylanmadığı için iptal edildi.")
        return {"execution_result": {"status": "CANCELLED"}}

if __name__ == "__main__":
    print("🚀 Fox-Kripto Step 2 Entegrasyon Testi Çalıştırılıyor...")
    state: CryptoAgentState = {
        "news_data": "",
        "portfolio_state": {},
        "sentiment_score": 0.0,
        "trade_proposal": None,
        "human_approval": "Pending",
        "execution_result": None
    }
    state.update(node_fetch_data(state))
    state.update(node_analyze_news(state))
    state.update(node_formulate_strategy(state))
    state.update(node_human_approval(state))
    state.update(node_execute_trade(state))
    print("\n✅ Step 2 Tamamlandı. Sonuç:", state["execution_result"])
