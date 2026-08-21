import requests
from typing import Dict, Any, List

def calculate_ema(prices: List[float], period: int) -> float:
    """Belirli periyot için Basit Üstel Hareketli Ortalama (EMA) hesaplar."""
    if len(prices) < period:
        return prices[-1] if prices else 0.0
    multiplier = 2.0 / (period + 1.0)
    ema = sum(prices[:period]) / period
    for p in prices[period:]:
        ema = (p - ema) * multiplier + ema
    return ema

def check_market_regime() -> Dict[str, Any]:
    """
    BTC/USDT 1 Saatlik Mum Verileri Üzerinden Piyasa Rejimini Denetler.
    BTC EMA(200) altında ise veya sert düşüş trendindeyse piyasa 'BEARISH' kabul edilir.
    Hata durumlarında sermaye koruma amacıyla Fail-Closed (is_bullish=False) döner.
    """
    try:
        url = "https://api.binance.com/api/v3/klines?symbol=BTCUSDT&interval=1h&limit=450"
        r = requests.get(url, timeout=4)
        if r.status_code != 200:
            return {"is_bullish": False, "status": "API_UNAVAILABLE", "reason": "BTC kline API geçici olarak yanıt vermedi (Sermaye Koruma / Fail-Closed)."}
            
        data = r.json()
        if len(data) < 200:
            return {"is_bullish": False, "status": "INSUFFICIENT_DATA", "reason": "Yetersiz BTC mum verisi (Sermaye Koruma)."}
            
        # Kapanmış mumların kapanış fiyatları
        close_prices = [float(k[4]) for k in data[:-1]]
        current_btc_price = float(data[-1][4])
        
        ema50 = calculate_ema(close_prices, 50)
        ema200 = calculate_ema(close_prices, 200)
        
        # 1. EMA200 Kontrolü: Fiyat EMA200'ün %1.5'ten fazla altındaysa piyasa net ayı modundadır
        is_below_ema200 = current_btc_price < (ema200 * 0.985)
        
        # 2. Son 4 saatlik BTC sert düşüş kontrolü (4 mum aralığı)
        recent_4h_change = ((close_prices[-1] - close_prices[-5]) / close_prices[-5]) * 100.0 if len(close_prices) >= 5 else 0.0
        is_dumping = recent_4h_change < -2.5

        # 3. Kısa Vadeli Fırtına Kalkanı: BTC 15 Dakikalık Ani Mum Çöküş Kontrolü
        is_15m_dumping = False
        try:
            url_15m = "https://api.binance.com/api/v3/klines?symbol=BTCUSDT&interval=15m&limit=10"
            r_15m = requests.get(url_15m, timeout=3)
            if r_15m.status_code == 200:
                d_15m = r_15m.json()
                if len(d_15m) >= 3:
                    c15_last = float(d_15m[-1][4])
                    c15_prev = float(d_15m[-3][1]) # 30 dk önceki açılış
                    pct_15m = ((c15_last - c15_prev) / c15_prev) * 100.0
                    if pct_15m < -1.5:
                        is_15m_dumping = True
        except Exception:
            pass
        
        if is_below_ema200 or is_dumping or is_15m_dumping:
            if is_15m_dumping:
                reason = "BTC son 30 dakikada ani fırtına düşüşü (-%1.5+) başlattı (Fırtına Kalkanı Aktif)"
            elif is_below_ema200:
                reason = f"BTC (${current_btc_price:,.0f}) EMA200 (${ema200:,.0f}) altında (Ayı Rejimi)"
            else:
                reason = f"BTC son 4 saatte %{recent_4h_change:.1f} sert düştü"

            return {
                "is_bullish": False,
                "status": "BEARISH_REGIME",
                "btc_price": current_btc_price,
                "ema50": round(ema50, 2),
                "ema200": round(ema200, 2),
                "recent_4h_change": round(recent_4h_change, 2),
                "reason": reason
            }
            
        return {
            "is_bullish": True,
            "status": "BULLISH_OR_NEUTRAL",
            "btc_price": current_btc_price,
            "ema50": round(ema50, 2),
            "ema200": round(ema200, 2),
            "recent_4h_change": round(recent_4h_change, 2),
            "reason": "Piyasa rejimi altcoin momentum alımları için uygun."
        }
    except Exception as e:
        return {"is_bullish": False, "status": "FAIL_CLOSED_ERROR", "reason": f"Piyasa rejimi sorgu hatası: {e} (Sermaye Koruma Devrede)"}
