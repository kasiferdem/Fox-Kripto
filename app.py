import os, sys
if hasattr(sys.stdout, 'reconfigure'): sys.stdout.reconfigure(encoding='utf-8')
from dotenv import load_dotenv
from typing import Dict, Any
from fastapi import FastAPI, Request, BackgroundTasks
from pydantic import BaseModel

from state import CryptoAgentState
from graph import create_crypto_graph
from db import save_graph_state, load_graph_state, log_trade_decision
from exchange import execute_spot_trade

load_dotenv()

# FastAPI Sunucusu (DigitalOcean & Telegram Webhook için)
app_api = FastAPI(title="Fox-Kripto Autonomous LangGraph Agent Service")

@app_api.get("/")
@app_api.get("/health")
def health_check():
    return {
        "status": "healthy",
        "service": "Fox-Kripto LangGraph Multi-Agent Bot",
        "version": "1.0.0"
    }

class TriggerGraphRequest(BaseModel):
    session_id: str = "session_001"
    symbol: str = "BTC/USDT"

@app_api.post("/run-graph")
def run_graph_endpoint(req: TriggerGraphRequest, background_tasks: BackgroundTasks):
    """LangGraph Otonom Ajan Grafiğini Çalıştırır."""
    def _execute():
        print(f"🚀 [/run-graph]: Akış Başlatıldı -> Session: {req.session_id}")
        graph = create_crypto_graph()
        initial_state = {
            "news_data": "",
            "portfolio_state": {},
            "sentiment_score": 0.0,
            "trade_proposal": None,
            "human_approval": "Pending",
            "execution_result": None
        }
        res = graph.invoke(initial_state)
        save_graph_state(req.session_id, res)
        print(f"✅ [/run-graph]: Akış Tamamlandı/Duraklatıldı.")

    background_tasks.add_task(_execute)
    return {
        "status": "STARTED",
        "message": f"LangGraph otonom akışı başlatıldı (Session: {req.session_id})"
    }

@app_api.post("/telegram-webhook")
async def telegram_webhook(request: Request):
    """
    Telegram Bot Webhook:
    Kullanıcının '✅ İŞLEMİ ONAYLA' veya '❌ REDDET' butonlarına tıklamasını dinler.
    """
    try:
        data = await request.json()
        print(f"📱 [Telegram Webhook Event]: {data}")
        
        callback = data.get("callback_query")
        if callback:
            cb_data = callback.get("data", "")
            user_action = "Approved" if "approve" in cb_data else "Rejected"
            session_id = cb_data.split("_")[-1] if "_" in cb_data else "session_001"
            
            print(f"🎯 [Telegram Onayı Alındı]: Action={user_action}, Session={session_id}")
            
            # State Geri Yükle ve Güncelle
            saved_state = load_graph_state(session_id) or {}
            saved_state["human_approval"] = user_action
            
            if user_action == "Approved" and saved_state.get("trade_proposal"):
                proposal = saved_state["trade_proposal"]
                result = execute_spot_trade(
                    symbol=proposal["symbol"],
                    side=proposal["direction"],
                    amount_usd=proposal["amount_usd"],
                    stop_loss_price=proposal["stop_loss_price"]
                )
                saved_state["execution_result"] = result
                log_trade_decision({
                    **proposal,
                    "sentiment_score": saved_state.get("sentiment_score"),
                    "human_approval": "Approved",
                    "status": result.get("status", "EXECUTED"),
                    "order_id": result.get("order_id"),
                    "execution_details": result
                })
            else:
                saved_state["execution_result"] = {"status": "CANCELLED"}
                
            save_graph_state(session_id, saved_state)
            return {"status": "success", "action": user_action}
            
        return {"status": "ignored"}
    except Exception as e:
        print(f"❌ Telegram Webhook Error: {e}")
        return {"status": "error", "message": str(e)}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app_api, host="0.0.0.0", port=8000)
