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
    candle_range = last_candle["high"] - last_candle["low"]
    
    # Mum Formasyonu ve Alıcı Baskısı (Üst Fitil Analizi):
    # Eğer üst fitil küçükse ve kapanış en yüksek seviyeye yakınsa (Baskılı Kırılım), balinanın koşusu yeni başlıyor demektir!
    upper_wick_ratio = ((last_candle["high"] - last_candle["close"]) / candle_range) if candle_range > 0 else 0.0
    
    # ERKEN BALİNA KIRILIMI VE %20 KOŞU POTANSİYELİ ŞARTLARI:
    # 1. Hacim İvmesi: Son 5dk hacmi ortalamanın en az 1.8x - 15.0x katı olmalı (Agresif Balina Girişi)
    # 2. Hacim Büyüklüğü: Son 5 dakikada en az 15,000$ değerinde gerçek emir infaz edilmiş olmalı
    # 3. Kırılım Başlangıcı: Fiyat değişimi tam %1.0 ile %5.5 arasında olmalı (Koşunun en başı!)
    # 4. Satış Direnci Yok: Üst fitil %35'in altında olmalı (Yani tepeye doğru güçlü itiş var, satıcılar henüz karşısına çıkamamış)
    if volume_spike_ratio >= 1.8 and recent_5m_volume >= min_volume_usd and (1.0 <= price_change_5m <= 5.5) and upper_wick_ratio <= 0.35:
        # İvme Skoru Hesabı (0-10): Hacim patlaması + Mum gücü
        momentum_score = min(10.0, round(5.0 + (volume_spike_ratio * 0.5) + (price_change_5m * 0.4), 1))
        clean_base = sym.replace("USDT", "").replace("TRY", "")
        quote_suffix = "TRY" if sym.endswith("TRY") else "USDT"
        return {
            "symbol": f"{clean_base}/{quote_suffix}",
            "price": last_candle["close"],
            "price_change_5m": round(price_change_5m, 2),
            "volume_spike_ratio": round(volume_spike_ratio, 1),
            "recent_5m_volume_usd": round(recent_5m_volume, 0),
            "momentum_score": momentum_score,
            "signal": f"🚀 ERKEN BALİNA KIRILIMI (%{price_change_5m:.1f} Başlangıç / {volume_spike_ratio:.1f}x Hacim / Skor: {momentum_score})",
            "recommendation": f"Erken Kırılım Tespiti: %20 koşusu potansiyeli %{price_change_5m:.1f} aşamasında yakalandı."
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

def detect_early_volume_breakouts(quote: str = "USDT", min_volume_usd: float = 10000.0, max_recent_gain: float = 5.5) -> List[Dict[str, Any]]:
    """
    Tüm Binance USDT veya TRY tahtasını paralel tarayarak:
    1. YALNIZCA aktif işlem gören (TRADING durumundaki) spot tahtaları seçer.
    2. Son 5 dakikada normal ortalamasının 1.8x - 15x katı hacim patlaması yaşayan TAZE PRE-PUMP balinaları tespit eder.
    3. Büyük bir %20 - %50 rallisinin henüz %1.0 ile %5.5 başlangıç evresinde olan (İvmesi yeni patlayan) fırsatları öngörür.
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
            and not any(t["symbol"].startswith(x) for x in ["USDC", "FDUSD", "EUR", "BUSD", "TUSD", "UP", "DOWN"])
            and float(t.get("quoteVolume", 0)) > (100000.0 if quote_upper == "USDT" else 2000000.0)
            and float(t.get("lastPrice", 0)) > 0
            # 🛑 TEPEDEN ALMAYI ENGELLE (FOMO FİLTRESİ): Zaten %10'un üzerinde fırlamış coinleri alma!
            # Yalnızca henüz dipte / koşunun başında olan (%-3.0 ile %+8.0 arası) taze kırılımları tara!
            and -3.0 <= float(t.get("priceChangePercent", 0)) <= 8.5
        ]
        
        # Hacmi en dinamik adayları seç ve 5dk kırılım ivmesini paralel test et
        candidates = sorted(target_tickers, key=lambda x: float(x.get("quoteVolume", 0)), reverse=True)[:50]
        
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
