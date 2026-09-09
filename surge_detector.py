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
    """Binance REST API üzerinden 5 dakikalık gerçek zamanlı mum verilerini çeker."""
    try:
        clean_sym = symbol.replace("/", "").replace("_", "").upper()
        url = f"https://api.binance.com/api/v3/klines?symbol={clean_sym}&interval=5m&limit={limit}"
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
    5 DAKİKALIK GERÇEK BALİNA & ERKEN MOMENTUM TESPİT MOTORU
    Hem canlı oluşan mumdaki anlık patlamaları hem de son kapanmış mumu analiz eder.
    """
    sym = cand.get("symbol", "")
    price_change_24h = float(cand.get("priceChangePercent", 0.0))
    quote_volume_24h = float(cand.get("quoteVolume", 0.0))
    
    from db import get_strategy_config
    strat_cfg = get_strategy_config(use_cache=True) or {}
    min_24h_vol = float(strat_cfg.get("min_24h_quote_volume_usd") or strat_cfg.get("min_24h_vol") or 500000.0)
    min_5m_vol = float(strat_cfg.get("min_5m_volume_usd") or strat_cfg.get("min_volume_usd") or strat_cfg.get("min_vol") or min_volume_usd or 2500.0)
    vol_spike_req = float(strat_cfg.get("volume_spike_multiplier") or strat_cfg.get("spike") or 1.15)
    cfg_max_gain = float(strat_cfg.get("max_recent_gain_24h") or strat_cfg.get("gain") or max_recent_gain or 60.0)

    # 🔒 Likidite ve Maksimum 24s Prim Kontrolü
    if quote_volume_24h < min_24h_vol or price_change_24h > cfg_max_gain or price_change_24h < -10.0:
        return None

    candles = fetch_5m_candles(sym, limit=6)
    if len(candles) < 5:
        return None

    # Önceki 3 mumun ortalama baz hacmi
    prev_vol_avg = sum(c["quote_volume"] for c in candles[-5:-2]) / 3.0 if len(candles) >= 5 else 1.0
    if prev_vol_avg <= 0:
        return None

    # Hem canlı oluşan mumu hem de az önce kapanmış son mumu değerlendir (Erken Kaçırma Engeli)
    for target_c in [candles[-1], candles[-2]]:
        v_curr = target_c["quote_volume"]
        o = target_c["open"]
        c = target_c["close"]
        h = target_c["high"]
        l = target_c["low"]
        if o <= 0:
            continue
        gain_5m = ((c - o) / o) * 100.0
        spike_ratio = v_curr / prev_vol_avg
        
        tb_vol = target_c.get("taker_buy_quote_volume", 0.0)
        tb_pct = (tb_vol / v_curr * 100.0) if v_curr > 0 else 55.0

        if spike_ratio >= vol_spike_req and v_curr >= min_5m_vol and gain_5m >= 0.15:
            momentum_score = min(10.0, round(7.0 + (spike_ratio * 0.4) + (gain_5m * 0.5), 1))
            clean_base = sym.replace("USDT", "").replace("TRY", "")
            quote_suffix = "TRY" if sym.endswith("TRY") else "USDT"
            return {
                "symbol": f"{clean_base}/{quote_suffix}",
                "price": c,
                "price_change_5m": round(gain_5m, 2),
                "price_change_1m": round(gain_5m, 2),
                "price_change_24h": round(price_change_24h, 2),
                "volume_spike_ratio": round(spike_ratio, 1),
                "recent_5m_volume_usd": round(v_curr, 0),
                "momentum_score": momentum_score,
                "taker_buy_ratio": round(tb_pct, 1),
                "signal": f"🐋 GERÇEK BALİNA KIRILIMI (%{gain_5m:.1f} Başlangıç / {spike_ratio:.1f}x Hacim / 5dk Hacim: ${v_curr:,.0f} / Skor: {momentum_score})",
                "recommendation": f"Sağlıklı Likit Balina Girişi: ${v_curr:,.0f} 5dk hacimle desteklendi."
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
            max_24h_req = float(max_recent_gain or strat.get("max_recent_gain_24h", 60.0))
            min_vol_req = float(min_volume_usd or strat.get("min_5m_volume_usd") or strat.get("min_volume_usd", 2500.0))
        except Exception:
            max_24h_req = 60.0
            min_vol_req = 2500.0

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
            # Dinamik 24s Değişim Kontrolü
            if vol >= min_24h_quote_vol and last_p > 0 and (-10.0 <= chg <= max_24h_req):
                target_tickers.append(t)
        
        candidates = sorted(target_tickers, key=lambda x: float(x.get("quoteVolume", 0)), reverse=True)[:250]
        
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
