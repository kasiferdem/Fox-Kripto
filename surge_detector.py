import time, sys
if hasattr(sys.stdout, 'reconfigure'): sys.stdout.reconfigure(encoding='utf-8')
import requests
import concurrent.futures
from typing import List, Dict, Any, Optional

def fetch_5m_candles(symbol: str, limit: int = 6) -> List[Dict[str, float]]:
    """Binance REST API üzerinden 5 dakikalık mum verilerini çeker."""
    try:
        clean_sym = symbol.replace("/", "").replace("_", "").upper()
        url = f"https://api.binance.com/api/v3/klines?symbol={clean_sym}&interval=5m&limit={limit}"
        r = requests.get(url, timeout=3)
        if r.status_code == 200:
            candles = []
            for k in r.json():
                candles.append({
                    "open": float(k[1]),
                    "high": float(k[2]),
                    "low": float(k[3]),
                    "close": float(k[4]),
                    "volume": float(k[5]),
                    "quote_volume": float(k[7])
                })
            return candles
    except Exception:
        pass
    return []

def _evaluate_candidate(cand: Dict[str, Any], min_volume_usd: float, max_recent_gain: float) -> Optional[Dict[str, Any]]:
    sym = cand.get("symbol", "")
    candles = fetch_5m_candles(sym, limit=6)
    if len(candles) < 4:
        return None
        
    last_candle = candles[-1]
    prev_candles = candles[:-1]
    
    recent_5m_volume = last_candle["quote_volume"]
    avg_prev_volume = sum(c["quote_volume"] for c in prev_candles) / len(prev_candles) if prev_candles else 1.0
    
    if avg_prev_volume <= 0 or last_candle["open"] <= 0:
        return None
        
    volume_spike_ratio = recent_5m_volume / avg_prev_volume
    price_change_5m = ((last_candle["close"] - last_candle["open"]) / last_candle["open"]) * 100.0
    
    # ERKEN FIRSAT ŞARTLARI:
    # 1. Son 5 dakikada hacim ortalamasının en az 1.3x - 10x katı olmalı (Balina girişi)
    # 2. Son 5 dakikada en az 10,000$ hacim girmiş olmalı
    # 3. Fiyat değişimi +%0.3 ile +%6.0 arasında olmalı (Henüz fırlamamış, erken aşamada)
    if volume_spike_ratio >= 1.3 and recent_5m_volume >= min_volume_usd and 0.3 <= price_change_5m <= max_recent_gain:
        clean_base = sym.replace("USDT", "")
        return {
            "symbol": f"{clean_base}/USDT",
            "price": last_candle["close"],
            "price_change_5m": round(price_change_5m, 2),
            "volume_spike_ratio": round(volume_spike_ratio, 1),
            "recent_5m_volume_usd": round(recent_5m_volume, 0),
            "signal": "🔥 GÜÇLÜ BALİNA HACİM GİRİŞİ (Pre-Pump)",
            "recommendation": f"Erken Giriş: +%{price_change_5m:.1f} artış ve {volume_spike_ratio:.1f}x hacim patlaması."
        }
    return None

_cached_active_symbols = set()
_cached_active_symbols_ts = 0

def get_active_trading_symbols():
    global _cached_active_symbols, _cached_active_symbols_ts
    now = time.time()
    if _cached_active_symbols and (now - _cached_active_symbols_ts < 300):
        return _cached_active_symbols
    try:
        r = requests.get("https://api.binance.com/api/v3/exchangeInfo", timeout=5)
        if r.status_code == 200:
            data = r.json()
            _cached_active_symbols = {
                s["symbol"] for s in data.get("symbols", [])
                if s.get("status") == "TRADING" and s.get("isSpotTradingAllowed", True)
            }
            _cached_active_symbols_ts = now
    except Exception:
        pass
    return _cached_active_symbols

def detect_early_volume_breakouts(quote: str = "USDT", min_volume_usd: float = 10000.0, max_recent_gain: float = 6.0) -> List[Dict[str, Any]]:
    """
    Tüm Binance USDT veya TRY tahtasını paralel tarayarak:
    1. YALNIZCA aktif işlem gören (TRADING durumundaki) spot tahtaları seçer.
    2. Son 5 dakikada normal ortalamasının 1.3x - 10x katı hacim girişi (Balina alımı) olan,
    3. Fiyatı henüz %0.3 ile %6 arasında yeni yükselmeye başlamış (Zirveye çıkmamış),
    4. Hacim patlaması yaşayan ERKEN FIRSAT COİNLERİNİ tespit eder.
    """
    breakouts = []
    try:
        quote_upper = str(quote).upper()
        active_syms = get_active_trading_symbols()
        r = requests.get("https://api.binance.com/api/v3/ticker/24hr", timeout=5)
        if r.status_code != 200:
            return []
            
        tickers = r.json()
        target_tickers = [
            t for t in tickers 
            if t["symbol"].endswith(quote_upper) 
            and (not active_syms or t["symbol"] in active_syms)
            and not any(t["symbol"].endswith(x) for x in ["UP" + quote_upper, "DOWN" + quote_upper, "FDUSD" + quote_upper, "USDC" + quote_upper, "EUR" + quote_upper])
            and float(t.get("quoteVolume", 0)) > (100000.0 if quote_upper == "USDT" else 2000000.0)
            and float(t.get("lastPrice", 0)) > 0
        ]
        
        by_gain = sorted(target_tickers, key=lambda x: float(x.get("priceChangePercent", 0)), reverse=True)[:30]
        by_vol = sorted(target_tickers, key=lambda x: float(x.get("quoteVolume", 0)), reverse=True)[:25]
        candidates = list({c["symbol"]: c for c in by_gain + by_vol}.values())
        
        min_vol = min_volume_usd if quote_upper == "USDT" else (min_volume_usd * 47.8)
        with concurrent.futures.ThreadPoolExecutor(max_workers=25) as executor:
            futures = [executor.submit(_evaluate_candidate, c, min_vol, max_recent_gain) for c in candidates]
            for f in concurrent.futures.as_completed(futures):
                res = f.result()
                if res:
                    breakouts.append(res)
                    
    except Exception as e:
        print(f"⚠️ Erken Hacim Dedektörü Uyarısı: {e}")
        
    breakouts = sorted(breakouts, key=lambda x: x["volume_spike_ratio"], reverse=True)
    return breakouts[:6]

if __name__ == "__main__":
    t0 = time.time()
    results = detect_early_volume_breakouts()
    t1 = time.time()
    print(f"Tarama tamamlandi ({t1-t0:.2f} sn). Toplam {len(results)} Erken Hacim Patlamasi:")
    for b in results:
        print(f"• {b['symbol']}: Fiyat=${b['price']} | 5dk Degisim=+%{b['price_change_5m']}% | Hacim={b['volume_spike_ratio']}x (${b['recent_5m_volume_usd']:,.0f})")
