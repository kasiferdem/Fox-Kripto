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

def check_market_regime(is_scalp: bool = False) -> Dict[str, Any]:
    """
    BTC/USDT 1 Saatlik Mum Verileri Üzerinden Piyasa Rejimini Denetler.
    Scalp modunda daha esnek (RSI < 36), Balina Avı modunda katı (RSI < 42) koruma uygular.
    """
    global _last_market_regime, _last_market_regime_ts
    now = time.time()
    if _last_market_regime and (now - _last_market_regime_ts < 60) and not is_scalp:
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
        
        # 🎛️ AKTİF PROFİLDEN TÜM REJİM VE BTC PARAMETRELERİNİ OKU (Sıfır Sabit Değer):
        try:
            from db import get_strategy_config
            strat_cfg = get_strategy_config(use_cache=True) or {}
        except Exception:
            strat_cfg = {}

        # 1. EMA200 Trend Filtresi (Panelden Açılıp Kapanabilir & Toleransı Ayarlanabilir)
        btc_trend_filter_enabled = bool(strat_cfg.get("btc_trend_filter_enabled", False))
        btc_ema_tol_pct = float(strat_cfg.get("btc_ema_tolerance_pct", 10.0))
        ema_multiplier = max(0.50, 1.0 - (btc_ema_tol_pct / 100.0))
        # 💡 KULLANICI ONAYLI 2. MADDE: Scalp modunda sakin havada %0.40-%0.70 kâr fırsatlarını öldürmemek için kör EMA200 kilidi uygulanmaz;
        # Ancak büyük balina swing işlemlerinde trend filtresi tam korunur:
        is_below_ema200 = (not is_scalp) and btc_trend_filter_enabled and (current_btc_price < (ema200 * ema_multiplier))
        
        # 2. Son 4 saatlik BTC sert çöküş kontrolü (Panik Koruması)
        dump_thresh = -float(strat_cfg.get("max_btc_4h_dump_pct", 4.0))
        recent_4h_change = ((close_prices[-1] - close_prices[-5]) / close_prices[-5]) * 100.0 if len(close_prices) >= 5 else 0.0
        is_dumping = recent_4h_change < dump_thresh

        # 3. 🛡️ AKTİF FIRTINA KALKANI (5dk ve 15dk Ani Dik Çöküş Kontrolü - "Ağa Takılan Balık Çırpınışı Engeli")
        is_flash_dump = False
        flash_dump_reason = ""
        dump_5m_thresh = -float(strat_cfg.get("btc_flash_dump_5m_pct") or 0.50)
        dump_15m_thresh = -float(strat_cfg.get("btc_flash_dump_15m_pct") or 1.00)

        # 3a. 5 Dakikalık Hızlı Şelale Kontrolü
        try:
            url_5m = "https://api.binance.com/api/v3/klines?symbol=BTCUSDT&interval=5m&limit=4"
            r_5m = requests.get(url_5m, timeout=3)
            if r_5m.status_code == 200:
                d_5m = r_5m.json()
                if len(d_5m) >= 2:
                    c5_curr = float(d_5m[-1][4])
                    c5_open = float(d_5m[-2][1])
                    pct_5m = ((c5_curr - c5_open) / c5_open) * 100.0
                    if pct_5m <= dump_5m_thresh:
                        is_flash_dump = True
                        flash_dump_reason = f"BTC son 5-10 dakikada ani dik düşüş (-%{abs(pct_5m):.2f}) başlattı (Savunma Modu Aktif)"
        except Exception:
            pass

        # 3b. 15 Dakikalık Dik Çöküş Kontrolü
        if not is_flash_dump:
            try:
                url_15m = "https://api.binance.com/api/v3/klines?symbol=BTCUSDT&interval=15m&limit=6"
                r_15m = requests.get(url_15m, timeout=3)
                if r_15m.status_code == 200:
                    d_15m = r_15m.json()
                    if len(d_15m) >= 3:
                        c15_last = float(d_15m[-1][4])
                        c15_prev = float(d_15m[-3][1]) # ~30 dk önceki açılış
                        pct_15m = ((c15_last - c15_prev) / c15_prev) * 100.0
                        if pct_15m <= dump_15m_thresh:
                            is_flash_dump = True
                            flash_dump_reason = f"BTC son 30 dakikada dik çöküş (-%{abs(pct_15m):.2f}) başlattı (Savunma Modu Aktif)"
            except Exception:
                pass
            
        # 4. RSI Zayıflık Filtresi (Panelden Dinamik Okunur)
        custom_rsi = strat_cfg.get("btc_min_rsi") or strat_cfg.get("min_btc_rsi")
        rsi_floor = float(custom_rsi) if custom_rsi is not None else (30.0 if is_scalp else 35.0)
        is_rsi_weak = btc_rsi < rsi_floor
        
        if is_flash_dump or is_dumping or is_below_ema200 or is_rsi_weak:
            if is_flash_dump:
                reason = flash_dump_reason
            elif is_below_ema200:
                reason = f"BTC (${current_btc_price:,.0f}) EMA200 (${ema200:,.0f}) altında tolerans sınırını (>%{btc_ema_tol_pct}) aştı"
            elif is_rsi_weak:
                reason = f"BTC 1S RSI ({btc_rsi:.1f}) panelden belirlenen taban eşiğin (<{rsi_floor}) altında"
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
