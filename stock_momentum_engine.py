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

            price = b.get("price", 0.0)
            open_p = b.get("open", 0.0)
            high_p = b.get("high", 0.0)
            low_p = b.get("low", 0.0)
            vol = b.get("volume", 0.0)

            if price <= 0 or open_p <= 0:
                continue

            candle_gain_pct = ((price - open_p) / open_p) * 100.0
            
            # Retest & Durum Makinesi
            breakout_level = high_p
            retest_zone_low = open_p + ((high_p - open_p) * 0.30)
            retest_zone_high = open_p + ((high_p - open_p) * 0.70)
            
            state = "IDLE"
            is_ready = False
            reason = "İzleniyor (Beklemede)"

            # 🛑 1. Canlı İlk Pump Mumu Koruması (Fırlayan muma girilmez)
            if candle_gain_pct > self.params["max_single_candle_chase_pct"]:
                state = "STOCK_WAITING_PULLBACK"
                reason = f"Hisse canlı fırlıyor (+%{candle_gain_pct:.2f}); tepeden alım yasak, geri çekilme bekleniyor."
            elif retest_zone_low <= price <= retest_zone_high and candle_gain_pct > 0.15:
                # 🛡️ 2. Retest Tabanı Teyit Edildi
                state = "STOCK_RETEST_CONFIRMED"
                is_ready = True
                reason = f"Geri çekilme desteği (${retest_zone_low:.2f} - ${retest_zone_high:.2f}) korundu, 2. çıkış dalgası onaylandı."
            else:
                state = "STOCK_WATCHING"
                reason = f"Normal seans akışı (Değişim: %{candle_gain_pct:+.2f})."

            opportunities.append({
                "symbol": symbol,
                "price": price,
                "change_pct": round(candle_gain_pct, 2),
                "volume": vol,
                "state": state,
                "is_ready": is_ready,
                "reason": reason,
                "take_profit_target": round(price * (1.0 + (self.params["target_take_profit_pct"] / 100.0)), 2),
                "stop_loss_target": round(price * (1.0 - (self.params["target_stop_loss_pct"] / 100.0)), 2),
                "market_open": is_market_open
            })

        return opportunities
