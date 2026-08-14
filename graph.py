import os, sys
if hasattr(sys.stdout, 'reconfigure'): sys.stdout.reconfigure(encoding='utf-8')
from typing import Dict, Any
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

def node_fetch_data(state: CryptoAgentState) -> Dict[str, Any]:
    print("\n--- [1. NODE: DİNAMİK TÜM BORSA PİYASA TARAYICI (TOP 20 GAINERS) DEVREDE] ---")
    tenant_config = state.get("tenant_config")
    portfolio = fetch_portfolio_balance(tenant_config)
    
    top_gainers = fetch_top_volume_gainers(limit=20)
    tickers_summary = []
    
    for t in top_gainers:
        tickers_summary.append(f"{t['symbol']}: Fiyat ${t['last_price']}, 24s Değişim %{t['percentage_change']:.2f}, Hacim ${t['volume']:,.0f}")
            
    news_text = "CANLI BİNANCE TÜM PİYASA VE EN ÇOK YÜKSELEN DİNAMİK ALTCOIN TARAMASI:\n" + "\n".join(tickers_summary)
    print(f"   [Dinamik Borsa Taraması]: Borsadaki en çok işlem gören {len(top_gainers)} sıcak altcoin başarıyla tarandı.")
    return {"news_data": news_text, "portfolio_state": portfolio}

def node_analyze_news(state: CryptoAgentState) -> Dict[str, Any]:
    print("\n--- [2. NODE: HABER & PİYASA ANALİZ AJANI (GPT-4o) DEVREDE] ---")
    analysis = analyze_crypto_news(state.get("news_data", ""), state.get("portfolio_state", {}))
    sentiment = float(analysis.get("sentiment_score", 0.0))
    print(f"   [GPT-4o Piyasa Skoru]: {sentiment} (+10/-10) | Yön: {analysis.get('market_bias')}")
    return {"sentiment_score": sentiment}

def node_formulate_strategy(state: CryptoAgentState) -> Dict[str, Any]:
    print("\n--- [3. NODE: STRATEJİ VE RİSK AJANI (GPT-4o) DEVREDE] ---")
    news_analysis = {"sentiment_score": state.get("sentiment_score", 0.0), "market_data": state.get("news_data", "")}
    # Main coins ve altcoinler arasından en yüksek potansiyelli coini seçer
    proposal = formulate_trade_strategy(news_analysis, state.get("portfolio_state", {}), 64000.0, symbol="AUTO")
    
    if not proposal.get("should_trade", True):
        print("   [Risk Reddi]: İşlem şartları oluşmadı. Akış sonlandırılıyor.")
        return {"trade_proposal": None, "human_approval": "Rejected"}
        
    print(f"   [Seçilen İşlem Teklifi]: {proposal['direction']} {proposal['symbol']} - Bütçe: ${proposal['amount_usd']} USD")
    return {"trade_proposal": proposal, "human_approval": "Pending"}

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
