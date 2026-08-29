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

def fetch_1m_candles(symbol: str, limit: int = 8) -> List[Dict[str, float]]:
    """Binance REST API üzerinden 1 dakikalık gerçek zamanlı mum verilerini çeker."""
    try:
        clean_sym = symbol.replace("/", "").replace("_", "").upper()
        url = f"https://api.binance.com/api/v3/klines?symbol={clean_sym}&interval=1m&limit={limit}"
        sess = get_http_session()
        r = sess.get(url, timeout=3)
        if r.status_code == 200:
            candles = []
            for k in r.json():
                candles.append({
                    "open": float(k[1]),
                    "high": float(k[2]),
                    "low": float(k[3]),
                    "close": float(k[4]),
                    "volume": float(k[5]),
                    "quote_volume": float(k[7]),
                    "trades": int(k[8]),
                    "taker_buy_quote_volume": float(k[10])
                })
            return candles
    except Exception:
        pass
    return []

def _evaluate_candidate(cand: Dict[str, Any], min_volume_usd: float, max_recent_gain: float) -> Optional[Dict[str, Any]]:
    """
    1-3 DAKİKALIK ERKEN DİP VE İLK HACİM PATLAMASI DENETÇİSİ (EARLY DIP ENGINE)
    Yalnızca dipte (+%0.30 - +%2.00) ve 24s primi <%3.5 olan taze kırılımları seçer.
    """
    sym = cand.get("symbol", "")
    price_change_24h = float(cand.get("priceChangePercent", 0.0))
    
    # 🔒 KATI ERKEN DİP TAVANI: 24 saatlik primi %3.5'ten fazla olan coinler ASLA ALINMAZ!
    effective_max_gain = min(3.5, float(max_recent_gain or 3.5))
    if price_change_24h > effective_max_gain or price_change_24h < -6.0:
        return None
        
    candles = fetch_1m_candles(sym, limit=8)
    if len(candles) < 7:
        return None
        
    recent_3 = candles[-4:-1] # Son 3 dakikalık kapalı mumlar
    prev_4 = candles[-8:-4]   # Önceki 4 dakikalık baz hacim
    
    v_recent = sum(float(k["quote_volume"]) for k in recent_3)
    v_prev_avg = sum(float(k["quote_volume"]) for k in prev_4) / len(prev_4) if prev_4 else 1.0
    v_prev_expected = v_prev_avg * 3.0
    
    if v_prev_expected <= 0 or recent_3[0]["open"] <= 0:
        return None
        
    volume_spike_ratio = v_recent / v_prev_expected
    
    o = float(recent_3[0]["open"])
    c = float(recent_3[-1]["close"])
    h = max(float(k["high"]) for k in recent_3)
    l = min(float(k["low"]) for k in recent_3)
    
    gain_3m = ((c - o) / o) * 100.0
    candle_range = h - l
    upper_wick_ratio = ((h - max(o, c)) / candle_range) if candle_range > 0 else 0.0
    
    tb_recent = sum(float(k.get("taker_buy_quote_volume", 0.0)) for k in recent_3)
    taker_buy_ratio = (tb_recent / v_recent * 100.0) if v_recent > 0 else 0.0

    # 🛡️ MATEMATİKSEL ERKEN DİP GİRİŞ FİLTRELERİ:
    # 1. 24s Değişim <= %3.5 (Dipte olmalı)
    # 2. 3dk Erken Yükseliş: +%0.20 ile +%2.20 arasında (Hareketin henüz ilk başlangıcı)
    # 3. Hacim Patlama Çarpanı >= 1.4x
    # 4. 3dk Toplam Hacim >= $10,000 USD
    # 5. Taker Alıcı Baskısı >= %55.0
    # 6. Üst Fitil <= 0.35 (Tepe satıcı reddi yok)
    if (
        volume_spike_ratio >= 1.40 and
        v_recent >= 10000.0 and
        (0.20 <= gain_3m <= 2.20) and
        upper_wick_ratio <= 0.35 and
        taker_buy_ratio >= 55.0 and
        (-6.0 <= price_change_24h <= effective_max_gain)
    ):
        momentum_score = min(10.0, round(6.5 + (volume_spike_ratio * 0.4) + (gain_3m * 0.5) + (taker_buy_ratio / 100.0 * 1.5), 1))
        clean_base = sym.replace("USDT", "").replace("TRY", "")
        quote_suffix = "TRY" if sym.endswith("TRY") else "USDT"
        return {
            "symbol": f"{clean_base}/{quote_suffix}",
            "price": c,
            "price_change_5m": round(gain_3m, 2),
            "price_change_1m": round(gain_3m, 2),
            "price_change_24h": round(price_change_24h, 2),
            "volume_spike_ratio": round(volume_spike_ratio, 1),
            "recent_5m_volume_usd": round(v_recent * 1.67, 0),
            "recent_1m_volume_usd": round(v_recent / 3.0, 0),
            "taker_buy_ratio": round(taker_buy_ratio, 1),
            "upper_wick_ratio": round(upper_wick_ratio, 2),
            "momentum_score": momentum_score,
            "signal": f"⚡ ERKEN DİP KIRILIMI (+%{gain_3m:.2f} Başlangıç / {volume_spike_ratio:.1f}x Hacim / Alıcı: %{taker_buy_ratio:.1f} / 24s: %{price_change_24h:+.1f} / Skor: {momentum_score})",
            "recommendation": f"Taze Dip Girişi: +%{gain_3m:.2f} seviyesinde yakalandı."
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
            symbols = set()
            for s in r.json().get("symbols", []):
                if s.get("status") == "TRADING":
                    symbols.add(s.get("symbol"))
            _cached_active_symbols = symbols
            _cached_active_symbols_ts = now
            return symbols
    except Exception:
        pass
    return set()

def detect_early_volume_breakouts(quote: str = None, quote_asset: str = "USDT", min_volume_usd: float = None, max_recent_gain: float = None, **kwargs) -> List[Dict[str, Any]]:
    """Binance Spot üzerinde erken dip kırılımlarını paralel olarak tespit eder."""
    breakouts = []
    target_quote = quote or quote_asset or "USDT"
    quote_upper = target_quote.upper()
    try:
        active_syms = get_active_trading_symbols()
        try:
            from db import get_strategy_config
            strat = get_strategy_config(use_cache=True)
            max_24h_req = min(3.5, float(max_recent_gain or strat.get("max_recent_gain_24h", 3.5)))
            min_vol_req = float(min_volume_usd or strat.get("min_volume_usd", 15000.0))
        except Exception:
            max_24h_req = 3.5
            min_vol_req = 15000.0

        sess = get_http_session()
        r = sess.get("https://api.binance.com/api/v3/ticker/24hr", timeout=6)
        if r.status_code != 200:
            return []
            
        tickers = r.json()
        target_tickers = []
        min_24h_quote_vol = 300000.0 if quote_upper == "USDT" else 10000000.0
        
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
            # 🔒 SADECE PRİMSİZ/DİPTEKİ COİNLERİ LİSTEYE AL (24s Değişim <= %3.5)
            if vol >= min_24h_quote_vol and last_p > 0 and (-6.0 <= chg <= max_24h_req):
                target_tickers.append(t)
        
        candidates = sorted(target_tickers, key=lambda x: float(x.get("quoteVolume", 0)), reverse=True)[:150]
        
        from exchange import get_live_usd_try_rate
        live_fx = get_live_usd_try_rate() or 38.5
        min_vol = min_vol_req if quote_upper == "USDT" else (min_vol_req * live_fx)
        with concurrent.futures.ThreadPoolExecutor(max_workers=25) as executor:
            futures = [executor.submit(_evaluate_candidate, c, min_vol, max_24h_req) for c in candidates]
            for f in concurrent.futures.as_completed(futures):
                res = f.result()
                if res:
                    breakouts.append(res)
                    
    except Exception as e:
        print(f"⚠️ Erken Dip Dedektörü Uyarısı: {e}")
        
    breakouts = sorted(breakouts, key=lambda x: x["volume_spike_ratio"], reverse=True)
    return breakouts[:10]
