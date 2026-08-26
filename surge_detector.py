import time, sys
if hasattr(sys.stdout, 'reconfigure'): sys.stdout.reconfigure(encoding='utf-8')
import requests
import concurrent.futures
from typing import List, Dict, Any, Optional

_http_session = None

def get_http_session():
    global _http_session
    if _http_session is None:
        _http_session = requests.Session()
        _http_session.headers.update({
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Accept": "application/json"
        })
    return _http_session

def fetch_5m_candles(symbol: str, limit: int = 6) -> List[Dict[str, float]]:
    """Binance REST API üzerinden 5 dakikalık mum verilerini çeker."""
    try:
        clean_sym = symbol.replace("/", "").replace("_", "").upper()
        url = f"https://api.binance.com/api/v3/klines?symbol={clean_sym}&interval=5m&limit={limit}"
        sess = get_http_session()
        r = sess.get(url, timeout=5)
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
    price_change_24h = float(cand.get("priceChangePercent", 0.0))
    candles = fetch_5m_candles(sym, limit=7)
    if len(candles) < 5:
        return None
        
    # Sinyal SIFIR REPAINT: Son kapanmamış mum yerine tamamlanmış en son kapalı mumu kullan
    closed_candles = candles[:-1]
    last_candle = closed_candles[-1]
    prev_candles = closed_candles[:-1]
    
    recent_5m_volume = last_candle["quote_volume"]
    avg_prev_volume = sum(c["quote_volume"] for c in prev_candles) / len(prev_candles) if prev_candles else 1.0
    
    if avg_prev_volume <= 0 or last_candle["open"] <= 0:
        return None
        
    volume_spike_ratio = recent_5m_volume / avg_prev_volume
    price_change_5m = ((last_candle["close"] - last_candle["open"]) / last_candle["open"]) * 100.0
    candle_range = last_candle["high"] - last_candle["low"]
    
    # Mum Formasyonu ve Alıcı Baskısı (Üst Fitil Analizi):
    upper_wick_ratio = ((last_candle["high"] - last_candle["close"]) / candle_range) if candle_range > 0 else 0.0
    
    # DİNAMİK STRATEJİ VE RİSK PROFİLİ OKUMA:
    try:
        from db import get_strategy_config
        strat = get_strategy_config(use_cache=True)
        min_spike_req = float(strat.get("volume_spike_multiplier", 1.3))
        min_vol_req = float(strat.get("min_volume_usd", min_volume_usd))
        max_24h_req = float(strat.get("max_recent_gain_24h", max_recent_gain))
    except Exception:
        min_spike_req = 1.3
        min_vol_req = min_volume_usd
        max_24h_req = max_recent_gain

    # 🛡️ ANTI-FOMO & AKILLI GİRİŞ KONTROLÜ:
    # 1. 5dk değişim 0.5% ile 4.0% arasında olmalıdır (Erken kırılım)
    # 2. Üst fitil <= 0.45 olmalıdır (Gövdesi dolu yeşil mum)
    if volume_spike_ratio >= min_spike_req and recent_5m_volume >= min_vol_req and (0.5 <= price_change_5m <= 4.0) and upper_wick_ratio <= 0.45 and (price_change_24h <= max_24h_req):
        momentum_score = min(10.0, round(5.0 + (volume_spike_ratio * 0.5) + (price_change_5m * 0.4), 1))
        clean_base = sym.replace("USDT", "").replace("TRY", "")
        quote_suffix = "TRY" if sym.endswith("TRY") else "USDT"
        return {
            "symbol": f"{clean_base}/{quote_suffix}",
            "price": last_candle["close"],
            "price_change_5m": round(price_change_5m, 2),
            "price_change_24h": round(price_change_24h, 2),
            "volume_spike_ratio": round(volume_spike_ratio, 1),
            "recent_5m_volume_usd": round(recent_5m_volume, 0),
            "momentum_score": momentum_score,
            "signal": f"🚀 ERKEN BALİNA DİP KIRILIMI (%{price_change_5m:.1f} Başlangıç / {volume_spike_ratio:.1f}x Hacim / 24s: %{price_change_24h:+.1f} / Skor: {momentum_score})",
            "recommendation": f"Sağlıklı Erken Kırılım: Fiyat tepeye koşmadan (%{price_change_5m:.1f} tabanında) yakalandı."
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
        sess = get_http_session()
        r = sess.get("https://api.binance.com/api/v3/exchangeInfo", timeout=6)
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

def detect_early_volume_breakouts(quote: str = "USDT", min_volume_usd: float = 4000.0, max_recent_gain: float = 15.0) -> List[Dict[str, Any]]:
    """
    Tüm Binance USDT veya TRY tahtasını paralel tarayarak taze hacim kırılımlarını tespit eder.
    """
    breakouts = []
    try:
        quote_upper = str(quote).upper()
        active_syms = get_active_trading_symbols()
        
        # Dinamik Strateji Ayarlarını Al
        try:
            from db import get_strategy_config
            strat = get_strategy_config(use_cache=True)
            max_24h_req = float(strat.get("max_recent_gain_24h", max_recent_gain))
            min_spike_req = float(strat.get("volume_spike_multiplier", 1.2))
            min_vol_req = float(strat.get("min_volume_usd", min_volume_usd))
        except Exception:
            max_24h_req = max_recent_gain
            min_spike_req = 1.2
            min_vol_req = min_volume_usd

        sess = get_http_session()
        r = sess.get("https://api.binance.com/api/v3/ticker/24hr", timeout=6)
        if r.status_code != 200:
            return []
            
        tickers = r.json()
        target_tickers = []
        # LİKİDİTE BARAJI: USDT için en az $150,000 USD, TRY için en az ₺5,000,000 TL 24s hacim şartı
        min_24h_quote_vol = 150000.0 if quote_upper == "USDT" else 5000000.0
        
        for t in tickers:
            sym = t.get("symbol", "")
            if not sym.endswith(quote_upper):
                continue
            if active_syms and sym not in active_syms:
                continue
            base_part = sym[:-len(quote_upper)]
            if any(sym.startswith(x) for x in ["USDC", "FDUSD", "EUR", "BUSD", "TUSD"]):
                continue
            if any(base_part.endswith(x) for x in ["UP", "DOWN", "BULL", "BEAR"]):
                continue
            vol = float(t.get("quoteVolume", 0))
            last_p = float(t.get("lastPrice", 0))
            chg = float(t.get("priceChangePercent", 0))
            if vol >= min_24h_quote_vol and last_p > 0 and (-5.0 <= chg <= max_24h_req):
                target_tickers.append(t)
        
        # Hacmi en dinamik adayları seç (Tüm sıcak altcoinleri kapsayacak şekilde 250 parite)
        candidates = sorted(target_tickers, key=lambda x: float(x.get("quoteVolume", 0)), reverse=True)[:250]
        
        from exchange import get_live_usd_try_rate
        live_fx = get_live_usd_try_rate() or 38.5
        min_vol = min_vol_req if quote_upper == "USDT" else (min_vol_req * live_fx)
        with concurrent.futures.ThreadPoolExecutor(max_workers=30) as executor:
            futures = [executor.submit(_evaluate_candidate, c, min_vol, max_24h_req) for c in candidates]
            for f in concurrent.futures.as_completed(futures):
                res = f.result()
                if res:
                    breakouts.append(res)
                    
    except Exception as e:
        print(f"⚠️ Erken Hacim Dedektörü Uyarısı: {e}")
        
    breakouts = sorted(breakouts, key=lambda x: x["volume_spike_ratio"], reverse=True)
    return breakouts[:10]

def fetch_top_volume_gainers(limit: int = 15) -> List[Dict[str, Any]]:
    """Binance 24s hacimli ve primli çiftleri çeker."""
    try:
        r = requests.get("https://api.binance.com/api/v3/ticker/24hr", timeout=4)
        if r.status_code == 200:
            tickers = r.json()
            valid = []
            for t in tickers:
                sym = t.get("symbol", "")
                if sym.endswith("USDT") and not any(sym.startswith(x) for x in ["USDC", "FDUSD", "EUR", "BUSD", "TUSD", "UP", "DOWN"]):
                    chg = float(t.get("priceChangePercent", 0.0))
                    vol = float(t.get("quoteVolume", 0.0))
                    if vol > 500000.0 and -3.0 <= chg <= 8.5:
                        valid.append({
                            "symbol": f"{sym[:-4]}/USDT",
                            "last_price": float(t.get("lastPrice", 1.0)),
                            "price_change_24h": chg,
                            "volume": vol,
                            "momentum_score": min(9.0, 6.0 + (chg / 2.0))
                        })
            valid.sort(key=lambda x: x["price_change_24h"], reverse=True)
            return valid[:limit]
    except Exception:
        pass
    return []

if __name__ == "__main__":
    t0 = time.time()
    results = detect_early_volume_breakouts()
    t1 = time.time()
    print(f"Tarama tamamlandi ({t1-t0:.2f} sn). Toplam {len(results)} Erken Hacim Patlamasi:")
    for b in results:
        print(f"• {b['symbol']}: Fiyat=${b['price']} | 5dk Degisim=+%{b['price_change_5m']}% | Hacim={b['volume_spike_ratio']}x (${b['recent_5m_volume_usd']:,.0f})")
