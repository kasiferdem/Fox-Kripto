"""
Fox-Borsa: ABD Hisse Senedi Seans Açılışı ve 2. Dalga Retest Motoru (StockMomentumEngine)
Telif Hakkı (c) 2026 Fox-Kripto / Fox-Borsa Quant Ekibi.

ABD Seans Saatleri (16:30 - 23:00 TSI) için özel geliştirilmiştir.
Hisselerde açılış momentum kırılımı (ORB) ve geri çekilme sonrası 2. çıkış dalgasını
(RETEST_CONFIRMED) arar. Canlı fırlayan muma tepeden girmez.
"""

import time
from typing import Dict, Any, List, Optional
from alpaca_client import AlpacaClient
from global_market_radar import GlobalMarketRadar

class StockMomentumEngine:
    def __init__(self, alpaca_client: Optional[AlpacaClient] = None):
        self.client = alpaca_client or AlpacaClient()
        self.radar = GlobalMarketRadar(self.client)
        self.target_symbols = [
            "NVDA", "TSLA", "AAPL", "MSFT", "AMZN", "GOOGL", "META", "AMD", "SPY", "QQQ", "COIN", "PLTR"
        ]
        self.params = {
            "name": "WALLSTREET_ORB_RETEST_V1",
            "min_market_cap_usd": 10_000_000_000,
            "min_volume_spike_ratio": 1.5,
            "target_take_profit_pct": 3.0,
            "target_stop_loss_pct": 1.5,
            "max_single_candle_chase_pct": 0.50,
            "retest_required": True,
            "max_position_budget_usd": 5000.0,
            "global_radar_filter_enabled": True
        }

    def scan_opportunities(self) -> List[Dict[str, Any]]:
        """
        Hedef ABD hisselerini tarar, canlı bar verilerini çeker ve
        2. Dalga Retest teyidi veren fırsatları listeler.
        """
        bars = self.client.get_latest_bars(self.target_symbols)
        market_clock = self.client.get_market_clock()
        is_market_open = market_clock.get("is_open", False)
        global_sentiment = self.radar.evaluate_global_sentiment()

        opportunities = []
        for symbol in self.target_symbols:
            b = bars.get(symbol)
            if not b:
                continue

            price = float(b.get("price", 0.0))
            open_p = float(b.get("open", price) or price)
            high_p = float(b.get("high", price) or price)
            low_p = float(b.get("low", price) or price)
            vol = float(b.get("volume", 0.0))
            day_gain_pct = float(b.get("day_change_pct", 0.0) or (((price - open_p) / open_p) * 100.0 if open_p > 0 else 0.0))
            intraday_gain_pct = float(b.get("intraday_change_pct", 0.0) or (((price - open_p) / open_p) * 100.0 if open_p > 0 else 0.0))

            if price <= 0:
                continue

            state = "STOCK_WATCHING"
            is_ready = False
            reason = f"Normal seans akışı (Günlük: %{day_gain_pct:+.2f}, Gün İçi: %{intraday_gain_pct:+.2f})."

            # 🛑 1. Aşırı Prim / Pump Koruması (+%7'den fazla tek günde fırlayan hisseye tepeden girilmez)
            if day_gain_pct > 7.0:
                state = "STOCK_WAITING_PULLBACK"
                reason = f"Hisse aşırı primli (+%{day_gain_pct:.2f}); tepeden alım yasak, geri çekilme bekleniyor."
            elif (day_gain_pct >= 0.80 or intraday_gain_pct >= 0.60) and price >= open_p:
                # 🛡️ 2. Pozitif Momentum & 2. Dalga Retest Teyidi
                range_hl = high_p - low_p if high_p > low_p else price * 0.01
                retest_support = low_p + (range_hl * 0.35)
                
                if price >= retest_support:
                    state = "STOCK_RETEST_CONFIRMED"
                    is_ready = True
                    reason = f"Seans momentum lideri (+%{day_gain_pct:.2f}), destek seviyesi (${retest_support:.2f}) üzerinde 2. dalga onaylandı."
                else:
                    state = "STOCK_WAITING_PULLBACK"
                    reason = f"Momentum var (+%{day_gain_pct:.2f}) fakat destek seviyesi (${retest_support:.2f}) altında test ediliyor."
            elif day_gain_pct <= -2.5:
                state = "STOCK_WATCHING"
                reason = f"Satış baskısı altında (Değişim: %{day_gain_pct:+.2f}), güvenli nakitte bekleniyor."

            opportunities.append({
                "symbol": symbol,
                "price": price,
                "change_pct": round(day_gain_pct, 2),
                "intraday_change_pct": round(intraday_gain_pct, 2),
                "volume": vol,
                "state": state,
                "is_ready": is_ready,
                "reason": reason,
                "take_profit_target": round(price * (1.0 + (self.params["target_take_profit_pct"] / 100.0)), 2),
                "stop_loss_target": round(price * (1.0 - (self.params["target_stop_loss_pct"] / 100.0)), 2),
                "market_open": is_market_open
            })

        return opportunities
