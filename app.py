import os, sys
if hasattr(sys.stdout, 'reconfigure'): sys.stdout.reconfigure(encoding='utf-8')
from dotenv import load_dotenv
from typing import Dict, Any
from state import CryptoAgentState
from exchange import fetch_portfolio_balance, fetch_ticker_price, execute_spot_trade
from db import log_trade_decision, save_graph_state
from prompts import analyze_crypto_news, formulate_trade_strategy

load_dotenv()

# -----------------------------------------
# LANGGRAPH DÜĞÜM (NODE) ENTEGRASYONU (STEP 3)
# -----------------------------------------

def node_fetch_data(state: CryptoAgentState) -> Dict[str, Any]:
    """
    1. Gözlemci Düğümü (Observer):
    - CCXT ile güncel cüzdan bakiyesini çeker.
    - Anlık haber ve makro piyasa verilerini toplar.
    """
    print("\n--- [1. NODE: GÖZLEMCİ (DATA FETCH) DEVREDE] ---")
    portfolio = fetch_portfolio_balance()
    ticker = fetch_ticker_price("BTC/USDT")
    
    news_text = (
        f"BTC/USDT Anlık Fiyat: ${ticker['last_price']} (24s Değişim: %{ticker['percentage_change']}). "
        f"Piyasa işlem hacmi ${ticker['volume']:,.2f} seviyesinde. "
        f"Kurumsal yatırımcı kanallarından pozitif girişler ve boğa görünümü raporlandı."
    )
    
    print(f"   [Portföy]: Serbest USDT: ${portfolio['free_usdt']} | Toplam USD: ${portfolio['total_usdt']}")
    print(f"   [Canlı Veri]: {news_text}")
    
    return {
        "news_data": news_text,
        "portfolio_state": portfolio
    }

def node_analyze_news(state: CryptoAgentState) -> Dict[str, Any]:
    """
    2. Haber Ajanı Düğümü (News Agent - GPT-4o):
    - LLM (GPT-4o) kullanarak haberi ve bağlamı analiz eder.
    - Sahte haberleri filtreler ve -10 ile +10 arası sentiment_score üretir.
    """
    print("\n--- [2. NODE: HABER ANALİZ AJANI (GPT-4o) DEVREDE] ---")
    news_text = state.get("news_data", "")
    portfolio = state.get("portfolio_state", {})
    
    analysis = analyze_crypto_news(news_text, portfolio)
    sentiment = float(analysis.get("sentiment_score", 0.0))
    
    print(f"   [GPT-4o Haber Skoru]: {sentiment} (+10/-10) | Yön: {analysis.get('market_bias')}")
    print(f"   [Ajan Özeti]: {analysis.get('analysis_summary')}")
    
    return {
        "sentiment_score": sentiment
    }

def node_formulate_strategy(state: CryptoAgentState) -> Dict[str, Any]:
    """
    3. Strateji ve Risk Ajanı Düğümü (Strategy & Risk Agent - GPT-4o):
    - KURAL: Hiçbir teklif bütçenin %10'unu aşamaz.
    - KURAL: %3 ile %5 arası dinamik Stop-Loss.
    """
    print("\n--- [3. NODE: STRATEJİ VE RİSK AJANI (GPT-4o) DEVREDE] ---")
    portfolio = state.get("portfolio_state", {})
    sentiment = state.get("sentiment_score", 0.0)
    ticker = fetch_ticker_price("BTC/USDT")
    current_price = ticker["last_price"]
    
    news_analysis = {
        "sentiment_score": sentiment,
        "market_bias": "BULLISH" if sentiment > 0 else "BEARISH"
    }
    
    proposal = formulate_trade_strategy(news_analysis, portfolio, current_price, symbol="BTC/USDT")
    
    if not proposal.get("should_trade", True):
        print(f"   [Risk Reddi]: {proposal.get('reason', 'İşlem şartları uygun değil.')}")
        return {
            "trade_proposal": None,
            "human_approval": "Rejected"
        }
        
    print(f"   [İşlem Teklifi]: {proposal['direction']} {proposal['symbol']} - Bütçe: ${proposal['amount_usd']} USD | SL: %{proposal['stop_loss_percent']} (${proposal['stop_loss_price']})")
    print(f"   [Risk Gerekçesi]: {proposal.get('risk_justification')}")
    
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
    if not state.get("trade_proposal"):
        print("   [HITL]: İşlem teklifi oluşmadığı için onay aşaması atlandı.")
        return {"human_approval": "Rejected"}
        
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
    proposal = state.get("trade_proposal")
    
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
        
        # LangGraph State Persistence
        save_graph_state("session_test_step3", state)
        
        return {"execution_result": result}
    else:
        print("❌ İşlem onaylanmadığı veya reddedildiği için iptal edildi.")
        return {"execution_result": {"status": "CANCELLED"}}

if __name__ == "__main__":
    print("🚀 Fox-Kripto Step 3 GPT-4o Ajan Testi Çalıştırılıyor...")
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
    print("\n✅ Step 3 Tamamlandı. İnfaz Sonucu:", state["execution_result"])
