import requests, time
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

def calculate_rsi(prices: List[float], period: int = 14) -> float:
    """RSI (Göreceli Güç Endeksi) hesaplar."""
    if len(prices) < period + 1:
        return 50.0
    gains, losses = [], []
    for i in range(1, period + 1):
        diff = prices[i] - prices[i-1]
        if diff >= 0:
            gains.append(diff)
            losses.append(0.0)
        else:
            gains.append(0.0)
            losses.append(abs(diff))
    avg_gain = sum(gains) / period
    avg_loss = sum(losses) / period
    for i in range(period + 1, len(prices)):
        diff = prices[i] - prices[i-1]
        if diff >= 0:
            avg_gain = (avg_gain * (period - 1) + diff) / period
            avg_loss = (avg_loss * (period - 1)) / period
        else:
            avg_gain = (avg_gain * (period - 1)) / period
            avg_loss = (avg_loss * (period - 1) + abs(diff)) / period
    if avg_loss == 0:
        return 100.0
    rs = avg_gain / avg_loss
    return 100.0 - (100.0 / (1.0 + rs))

_last_market_regime = None
_last_market_regime_ts = 0

def check_market_regime() -> Dict[str, Any]:
    """
    BTC/USDT 1 Saatlik Mum Verileri Üzerinden Piyasa Rejimini Denetler.
    BTC EMA(200) altında ise, RSI < 42 ise veya sert düşüş trendindeyse piyasa 'BEARISH' kabul edilir.
    """
    global _last_market_regime, _last_market_regime_ts
    now = time.time()
    if _last_market_regime and (now - _last_market_regime_ts < 120):
        return _last_market_regime

    endpoints = [
        "https://data-api.binance.vision/api/v3/klines?symbol=BTCUSDT&interval=1h&limit=250",
        "https://api1.binance.com/api/v3/klines?symbol=BTCUSDT&interval=1h&limit=250",
        "https://api.binance.com/api/v3/klines?symbol=BTCUSDT&interval=1h&limit=250"
    ]
    data = None
    for url in endpoints:
        try:
            r = requests.get(url, timeout=3)
            if r.status_code == 200:
                data = r.json()
                if len(data) >= 100:
                    break
        except Exception:
            continue

    if not data or len(data) < 100:
        if _last_market_regime:
            return _last_market_regime
        return {"is_bullish": True, "status": "NEUTRAL_FALLBACK", "reason": "Piyasa dengeli kabul edildi."}

    try:
        # Kapanmış mumların kapanış fiyatları
        close_prices = [float(k[4]) for k in data[:-1]]
        current_btc_price = float(data[-1][4])
        
        ema50 = calculate_ema(close_prices, 50)
        ema200 = calculate_ema(close_prices, 200)
        btc_rsi = calculate_rsi(close_prices, 14)
        
        # 1. EMA200 Kontrolü: Fiyat EMA200'ün altında veya zayıfsa ayı rejimidir
        is_below_ema200 = current_btc_price < (ema200 * 0.99)
        
        # 2. Son 4 saatlik BTC sert düşüş kontrolü (4 mum aralığı)
        recent_4h_change = ((close_prices[-1] - close_prices[-5]) / close_prices[-5]) * 100.0 if len(close_prices) >= 5 else 0.0
        is_dumping = recent_4h_change < -1.8

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
                    if pct_15m < -1.0:
                        is_15m_dumping = True
        except Exception:
            pass
            
        # 4. RSI Zayıflık Filtresi (BTC 1S RSI < 42 ise sahte kırılımlar çok fazladır)
        is_rsi_weak = btc_rsi < 42.0
        
        if is_below_ema200 or is_dumping or is_15m_dumping or is_rsi_weak:
            if is_15m_dumping:
                reason = "BTC son 30 dakikada ani fırtına düşüşü (-%1.0+) başlattı (Fırtına Kalkanı Aktif)"
            elif is_below_ema200:
                reason = f"BTC (${current_btc_price:,.0f}) EMA200 (${ema200:,.0f}) altında (Ayı Rejimi)"
            elif is_rsi_weak:
                reason = f"BTC 1S RSI ({btc_rsi:.1f}) kritik eşiğin (<42) altında; sahte kırılım riski yüksek (Nakit Koruması)"
            else:
                reason = f"BTC son 4 saatte %{recent_4h_change:.1f} sert düştü"

            return {
                "is_bullish": False,
                "status": "BEARISH_REGIME",
                "btc_price": current_btc_price,
                "btc_rsi": round(btc_rsi, 1),
                "ema50": round(ema50, 2),
                "ema200": round(ema200, 2),
                "recent_4h_change": round(recent_4h_change, 2),
                "reason": reason
            }
            
        return {
            "is_bullish": True,
            "status": "BULLISH_OR_NEUTRAL",
            "btc_price": current_btc_price,
            "btc_rsi": round(btc_rsi, 1),
            "ema50": round(ema50, 2),
            "ema200": round(ema200, 2),
            "recent_4h_change": round(recent_4h_change, 2),
            "reason": f"Piyasa rejimi ve BTC RSI ({btc_rsi:.1f}) pozitif; altcoin alımları için uygun."
        }
    except Exception as e:
        return {"is_bullish": False, "status": "FAIL_CLOSED_ERROR", "reason": f"Piyasa rejimi sorgu hatası: {e} (Sermaye Koruma Devrede)"}
