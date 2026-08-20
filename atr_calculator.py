import requests
from typing import List, Dict, Any, Tuple

def calculate_atr(candles: List[Dict[str, float]], period: int = 14) -> float:
    """
    True Range (TR) ve Average True Range (ATR) Hesaplar.
    TR = max(High - Low, abs(High - PrevClose), abs(Low - PrevClose))
    """
    if len(candles) < 2:
        return 0.0
        
    true_ranges = []
    for i in range(1, len(candles)):
        high = candles[i]["high"]
        low = candles[i]["low"]
        prev_close = candles[i - 1]["close"]
        tr = max(high - low, abs(high - prev_close), abs(low - prev_close))
        true_ranges.append(tr)
        
    if not true_ranges:
        return 0.0
        
    # Son 'period' kadar mumu al
    recent_tr = true_ranges[-period:]
    return sum(recent_tr) / len(recent_tr)

def calculate_atr_sl_tp(
    symbol: str,
    entry_price: float,
    user_tp_override: float = 0.0,
    user_sl_override: float = 0.0
) -> Tuple[float, float, float, float]:
    """
    Coinin oynaklığına (volatilitesine) göre ATR(14) tabanlı Stop-Loss ve Take-Profit hesaplar.
    Risk / Ödül Oranı: Daima En Az 1:2 (Kâr mesafesi = 2x Stop mesafesi).
    
    Dönüş: (take_profit_price, stop_loss_price, tp_percent, sl_percent)
    """
    try:
        clean_sym = symbol.replace("/", "").replace("_", "").upper()
        url = f"https://api.binance.com/api/v3/klines?symbol={clean_sym}&interval=5m&limit=20"
        r = requests.get(url, timeout=3)
        if r.status_code == 200:
            raw_data = r.json()
            candles = []
            # Yalnızca kapanmış mumları al
            for k in raw_data[:-1]:
                candles.append({
                    "open": float(k[1]),
                    "high": float(k[2]),
                    "low": float(k[3]),
                    "close": float(k[4]),
                    "volume": float(k[5])
                })
            
            atr_14 = calculate_atr(candles, period=14)
            if atr_14 > 0 and entry_price > 0:
                # Oynaklığa göre Stop Mesafesi = 1.5 * ATR
                sl_dist = atr_14 * 1.5
                # Risk:Ödül 1:2 için Kâr Mesafesi = 3.0 * ATR
                tp_dist = atr_14 * 3.0
                
                raw_sl_pct = (sl_dist / entry_price) * 100.0
                raw_tp_pct = (tp_dist / entry_price) * 100.0
                
                # Gürültü bandı koruması: Stop en az %1.5, en fazla %4.0 olsun
                clamped_sl_pct = min(4.0, max(1.5, raw_sl_pct))
                # R:R >= 2.0 kuralı: Kâr mesafesi daima stopun en az 2 katı olmalıdır
                clamped_tp_pct = max(clamped_sl_pct * 2.0, raw_tp_pct)
                
                if user_tp_override > 0:
                    clamped_tp_pct = max(clamped_tp_pct, user_tp_override)
                if user_sl_override > 0:
                    clamped_sl_pct = min(clamped_sl_pct, user_sl_override)
                    
                sl_price = round(entry_price * (1.0 - (clamped_sl_pct / 100.0)), 6 if entry_price < 1.0 else 4)
                tp_price = round(entry_price * (1.0 + (clamped_tp_pct / 100.0)), 6 if entry_price < 1.0 else 4)
                
                return tp_price, sl_price, round(clamped_tp_pct, 2), round(clamped_sl_pct, 2)
    except Exception as e:
        print(f"⚠️ [ATR Hesabı Hatası]: {e}")
        
    # Varsayılan Matematiksel Güvenli Değerler (SL: %2.0, TP: %4.0 -> R:R 1:2)
    def_sl = user_sl_override if user_sl_override > 0 else 2.0
    def_tp = user_tp_override if user_tp_override > 0 else (def_sl * 2.0)
    sl_price = round(entry_price * (1.0 - (def_sl / 100.0)), 6 if entry_price < 1.0 else 4)
    tp_price = round(entry_price * (1.0 + (def_tp / 100.0)), 6 if entry_price < 1.0 else 4)
    return tp_price, sl_price, round(def_tp, 2), round(def_sl, 2)
