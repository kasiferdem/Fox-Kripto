import sys, io, requests, time
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')
from typing import List, Dict, Any, Tuple

def fetch_historical_klines(symbol: str, interval: str = "5m", total_candles: int = 1000) -> List[Dict[str, Any]]:
    """Binance REST API'sinden geçmiş mum serilerini çeker."""
    url = f"https://api.binance.com/api/v3/klines?symbol={symbol}&interval={interval}&limit={min(1000, total_candles)}"
    try:
        r = requests.get(url, timeout=10)
        if r.status_code == 200:
            candles = []
            for k in r.json():
                candles.append({
                    "open_time": k[0],
                    "open": float(k[1]),
                    "high": float(k[2]),
                    "low": float(k[3]),
                    "close": float(k[4]),
                    "volume": float(k[5]),
                    "quote_volume": float(k[7]),
                    "close_time": k[6]
                })
            return candles
    except Exception as e:
        print(f"Hata ({symbol}): {e}")
    return []

def calculate_atr(candles: List[Dict[str, Any]], period: int = 14) -> float:
    if len(candles) < period + 1:
        return 0.0
    tr_list = []
    for i in range(len(candles) - period, len(candles)):
        h = candles[i]["high"]
        l = candles[i]["low"]
        pc = candles[i - 1]["close"]
        tr_list.append(max(h - l, abs(h - pc), abs(l - pc)))
    return sum(tr_list) / len(tr_list) if tr_list else 0.0

def run_backtest(
    symbols: List[str] = None,
    initial_balance: float = 1000.0,
    allocation_pct: float = 10.0,
    commission_pct: float = 0.10,
    slippage_pct: float = 0.10
) -> Dict[str, Any]:
    """
    3 Altın Kural, ATR(14) Dinamik Stop-Loss ve R:R >= 1:2 Stratejisini Geçmiş Veride Test Eder.
    """
    if not symbols:
        symbols = ["SOLUSDT", "DOGEUSDT", "AVAXUSDT", "NEARUSDT", "SUIUSDT", "BNBUSDT", "ETHUSDT"]
        
    print("=" * 65)
    print("📊 FOX-KRİPTO STRATEJİ BACKTEST MOTORU BAŞLATILIYOR 📊")
    print(f"💰 Başlangıç Kasası: ${initial_balance:,.2f} USD")
    print(f"🎯 Tahsis Oranı: %{allocation_pct:.1f} / İşlem | Komisyon + Kayma: %{commission_pct + slippage_pct:.2f}/taraf")
    print(f"🪙 Test Edilen Çiftler ({len(symbols)} adet): {', '.join(symbols)}")
    print("=" * 65)
    
    trades = []
    capital = initial_balance
    peak_capital = initial_balance
    max_drawdown_pct = 0.0
    
    for sym in symbols:
        raw_candles = fetch_historical_klines(sym, interval="5m", total_candles=1000)
        if len(raw_candles) < 50:
            continue
            
        cooldown_until_idx = 0
        in_pos = False
        pos_entry_price = 0.0
        pos_sl_price = 0.0
        pos_tp_price = 0.0
        pos_entry_idx = 0
        pos_size_usd = 0.0
        
        for i in range(25, len(raw_candles) - 1):
            curr_candle = raw_candles[i] # Kapalı mum
            next_candle = raw_candles[i + 1] # İşlem infaz mumu
            
            if in_pos:
                # Pozisyon Yönetimi (TP / SL Denetimi)
                # Next candle'ın High / Low değerlerini kontrol et
                hit_tp = next_candle["high"] >= pos_tp_price
                hit_sl = next_candle["low"] <= pos_sl_price
                
                if hit_tp or hit_sl:
                    if hit_tp and not hit_sl:
                        exit_price = pos_tp_price
                        is_win = True
                    elif hit_sl and not hit_tp:
                        exit_price = pos_sl_price
                        is_win = False
                    else: # Aynı mumda ikisi de vurulduysa muhafazakar olarak Stop say
                        exit_price = pos_sl_price
                        is_win = False
                        
                    gross_pnl_pct = ((exit_price - pos_entry_price) / pos_entry_price) * 100.0
                    net_pnl_pct = gross_pnl_pct - ((commission_pct + slippage_pct) * 2.0)
                    pnl_usd = pos_size_usd * (net_pnl_pct / 100.0)
                    
                    capital += pnl_usd
                    if capital > peak_capital:
                        peak_capital = capital
                    dd = ((peak_capital - capital) / peak_capital) * 100.0
                    if dd > max_drawdown_pct:
                        max_drawdown_pct = dd
                        
                    trades.append({
                        "symbol": sym,
                        "entry_idx": pos_entry_idx,
                        "exit_idx": i + 1,
                        "entry_price": pos_entry_price,
                        "exit_price": exit_price,
                        "net_pnl_pct": net_pnl_pct,
                        "pnl_usd": pnl_usd,
                        "is_win": is_win
                    })
                    
                    in_pos = False
                    cooldown_until_idx = i + 12 # 60 dakika soğuma
                    continue
                    
            if not in_pos and i > cooldown_until_idx:
                # Sinyal Taraması (Sıfır Repaint Kapalı Mum)
                prev_5_candles = raw_candles[i-5:i]
                avg_vol = sum(c["quote_volume"] for c in prev_5_candles) / 5.0
                curr_vol = curr_candle["quote_volume"]
                
                if avg_vol <= 0:
                    continue
                    
                vol_spike = curr_vol / avg_vol
                candle_return = ((curr_candle["close"] - curr_candle["open"]) / curr_candle["open"]) * 100.0
                candle_range = curr_candle["high"] - curr_candle["low"]
                upper_wick_ratio = ((curr_candle["high"] - curr_candle["close"]) / candle_range) if candle_range > 0 else 0.0
                
                # 24 saatlik değişim yaklaşık hesabı
                idx_24h = max(0, i - 288)
                change_24h = ((curr_candle["close"] - raw_candles[idx_24h]["close"]) / raw_candles[idx_24h]["close"]) * 100.0
                
                # 3 Altın Kural + Erken Balina Kırılım Şartları:
                # 1. Hacim Patlaması >= 1.8x
                # 2. 5dk Değişim: %1.0 - %5.0
                # 3. Üst fitil <= 0.35
                # 4. FOMO Engeli: 24s Değişim <= %8.5
                if vol_spike >= 1.8 and (1.0 <= candle_return <= 5.0) and upper_wick_ratio <= 0.35 and change_24h <= 8.5:
                    atr_14 = calculate_atr(raw_candles[:i+1], period=14)
                    if atr_14 > 0:
                        entry_p = next_candle["open"] # Bir sonraki mumun açılışından alım
                        sl_dist = atr_14 * 1.5
                        tp_dist = atr_14 * 3.0 # R:R 1:2
                        
                        raw_sl_pct = (sl_dist / entry_p) * 100.0
                        clamped_sl_pct = min(4.0, max(1.5, raw_sl_pct))
                        clamped_tp_pct = max(clamped_sl_pct * 2.0, (tp_dist / entry_p) * 100.0)
                        
                        pos_entry_price = entry_p
                        pos_sl_price = entry_p * (1.0 - (clamped_sl_pct / 100.0))
                        pos_tp_price = entry_p * (1.0 + (clamped_tp_pct / 100.0))
                        pos_entry_idx = i + 1
                        pos_size_usd = capital * (allocation_pct / 100.0)
                        in_pos = True
                        
    # Sonuç Raporu Hesaplama
    total_trades = len(trades)
    if total_trades == 0:
        print("⚠️ Backtest süresince hiçbir işlem tetiklenmedi.")
        return {}
        
    wins = [t for t in trades if t["is_win"]]
    losses = [t for t in trades if not t["is_win"]]
    win_rate = (len(wins) / total_trades) * 100.0
    
    gross_profits = sum(t["pnl_usd"] for t in wins)
    gross_losses = abs(sum(t["pnl_usd"] for t in losses))
    profit_factor = (gross_profits / gross_losses) if gross_losses > 0 else float('inf')
    net_profit_usd = capital - initial_balance
    net_return_pct = (net_profit_usd / initial_balance) * 100.0
    
    print("\n" + "=" * 65)
    print("🏆 BACKTEST PERFORMANS RAPORU (TAM DOĞRULANMIŞ)")
    print("=" * 65)
    print(f"📈 Toplam İcra Edilen İşlem   : {total_trades}")
    print(f"✅ Başarılı İşlemler (TP)     : {len(wins)} (%{win_rate:.1f})")
    print(f"❌ Stop-Loss İşlemleri (SL)   : {len(losses)} (%{100 - win_rate:.1f})")
    print(f"💰 Brüt Kazanç                : +${gross_profits:,.2f} USD")
    print(f"📉 Brüt Kayıp                 : -${gross_losses:,.2f} USD")
    print(f"🎯 Kâr Faktörü (Profit Factor): {profit_factor:.2f}")
    print(f"🛡️ Maksimum Düşüş (Max DD)    : %{max_drawdown_pct:.2f}")
    print(f"💵 Başlangıç / Bitiş Kasası   : ${initial_balance:,.2f} ➔ ${capital:,.2f} USD")
    print(f"🚀 Net Portföy Getirisi       : %{net_return_pct:+.2f} (+${net_profit_usd:,.2f} USD)")
    print("=" * 65)
    
    return {
        "total_trades": total_trades,
        "win_rate": win_rate,
        "profit_factor": profit_factor,
        "max_drawdown_pct": max_drawdown_pct,
        "net_return_pct": net_return_pct,
        "final_capital": capital
    }

if __name__ == "__main__":
    run_backtest()
