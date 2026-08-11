import os
import requests
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from dotenv import load_dotenv

load_dotenv()

app = FastAPI(title="Fox-Kripto Autonomous AI Trading & Risk System")

# -----------------------------------------
# RİSK & BÜTÇE AYARLARI
# -----------------------------------------
MAX_BUDGET_PER_TRADE = float(os.environ.get("MAX_BUDGET_PER_TRADE_USD", "200"))
MAX_DAILY_LOSS = float(os.environ.get("MAX_DAILY_LOSS_USD", "50"))
MAX_OPEN_POSITIONS = int(os.environ.get("MAX_OPEN_POSITIONS", "3"))

class SignalRequest(BaseModel):
    symbol: str  # Örn: BTCUSDT, ETHUSDT
    allocated_budget_usd: float

@app.get("/")
def home():
    return {
        "status": "active",
        "system": "Fox-Kripto Otonom Kripto Ticaret ve Risk Sistem",
        "risk_limits": {
            "max_budget_per_trade_usd": MAX_BUDGET_PER_TRADE,
            "max_daily_loss_usd": MAX_DAILY_LOSS,
            "max_open_positions": MAX_OPEN_POSITIONS
        }
    }

@app.get("/ticker/{symbol}")
def get_binance_ticker(symbol: str):
    """Binance REST API'den canlı fiyat takibi."""
    url = f"https://api.binance.com/api/v3/ticker/24hr?symbol={symbol.upper()}"
    res = requests.get(url, timeout=10)
    if res.status_code == 200:
        data = res.json()
        return {
            "symbol": data.get("symbol"),
            "lastPrice": data.get("lastPrice"),
            "highPrice": data.get("highPrice"),
            "lowPrice": data.get("lowPrice"),
            "volume": data.get("volume"),
            "priceChangePercent": data.get("priceChangePercent")
        }
    else:
        raise HTTPException(status_code=400, detail=f"Borsa fiyatı alınamadı: {res.text}")

@app.post("/analyze-signal")
def analyze_signal(request: SignalRequest):
    """
    1. Canlı borsa fiyatını alır
    2. Bütçe ve risk denetimi yapar
    3. AI Strateji Ajanı ile İnsan-Onay Kartı üretir
    """
    symbol = request.symbol.upper()
    budget = request.allocated_budget_usd

    # 1. Bütçe Denetimi (Risk Auditor)
    if budget > MAX_BUDGET_PER_TRADE:
        return {
            "status": "REJECTED_BY_RISK_AUDITOR",
            "reason": f"Talep edilen bütçe (${budget}), izin verilen maks bütçe sınırını (${MAX_BUDGET_PER_TRADE}) aşıyor!"
        }

    # 2. Canlı Fiyat
    ticker = get_binance_ticker(symbol)
    last_price = float(ticker["lastPrice"])

    # 3. AI Strateji (Seviye Hesabı)
    stop_loss = round(last_price * 0.98, 2)  # %2 Stop Loss
    tp1 = round(last_price * 1.04, 2)         # %4 Take Profit 1
    tp2 = round(last_price * 1.08, 2)         # %8 Take Profit 2

    return {
        "status": "AWAITING_HUMAN_APPROVAL",
        "signal_card": {
            "title": f"🚨 FOX-KRİPTO ALIM-SATIM FIRSATI: {symbol}",
            "symbol": symbol,
            "direction": "LONG / ALIM",
            "current_price": last_price,
            "suggested_entry": last_price,
            "stop_loss": stop_loss,
            "take_profit_1": tp1,
            "take_profit_2": tp2,
            "allocated_budget": f"${budget} USD",
            "risk_reward_ratio": "1:2.0",
            "human_approval_required": True,
            "action_prompt": "Bu işlemi onaylıyor musunuz?"
        }
    }

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
