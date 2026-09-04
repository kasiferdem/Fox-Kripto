"""
Fox-Borsa: Küresel Piyasa ve Öncü Seans Radarı (GlobalMarketRadar)
Telif Hakkı (c) 2026 Fox-Kripto / Fox-Borsa Quant Ekibi.

Güneş Döngüsü (24-Hour Global Macro Cycle) prensibiyle çalışır:
1. 🇯🇵 Asya Seansı: Tokyo (Nikkei 225 / EWJ), Tayvan Çip (TSM)
2. 🇬🇧 Avrupa Seansı: Frankfurt (DAX / EWG), Londra (FTSE / EWU)
3. 🇺🇸 ABD Ön Piyasa (Pre-Market Futures): S&P 500 (SPY), Nasdaq 100 (QQQ)

Wall Street açılmadan (16:30 TSI öncesi) küresel rüzgarın yönünü hesaplar.
"""

import time
import requests
from typing import Dict, Any, List, Optional
from alpaca_client import AlpacaClient

class GlobalMarketRadar:
    def __init__(self, alpaca_client: Optional[AlpacaClient] = None):
        self.client = alpaca_client or AlpacaClient()
        self.radar_symbols = [
            "EWJ",   # Japonya / Tokyo Nikkei Tracker
            "TSM",   # Tayvan Yarı İletken (Küresel Çip Öncüsü)
            "EWG",   # Almanya Frankfurt DAX Tracker
            "EWU",   # İngiltere Londra FTSE Tracker
            "SPY",   # ABD S&P 500 Endeksi
            "QQQ"    # ABD Nasdaq 100 Teknoloji Endeksi
        ]

    def evaluate_global_sentiment(self) -> Dict[str, Any]:
        """
        Küresel endeks ve ETF verilerini çeker, küresel makro skorunu (0-10) hesaplar.
        """
        bars = self.client.get_latest_bars(self.radar_symbols)
        
        asia_score = 5.0
        europe_score = 5.0
        us_premarket_score = 5.0
        
        details = {}
        
        # 1. Asya Puanlaması (EWJ & TSM)
        ewj = bars.get("EWJ", {})
        tsm = bars.get("TSM", {})
        ewj_chg = ((ewj.get("price", 0) - ewj.get("open", 0)) / ewj.get("open", 1)) * 100 if ewj.get("open", 0) > 0 else 0.0
        tsm_chg = ((tsm.get("price", 0) - tsm.get("open", 0)) / tsm.get("open", 1)) * 100 if tsm.get("open", 0) > 0 else 0.0
        asia_avg = (ewj_chg + tsm_chg) / 2.0
        
        if asia_avg > 0.8: asia_score = 8.5
        elif asia_avg > 0.2: asia_score = 7.0
        elif asia_avg < -0.8: asia_score = 2.5
        elif asia_avg < -0.2: asia_score = 3.5
        else: asia_score = 5.5
        
        details["asia"] = {
            "name": "🇯🇵 Asya Seansı (Tokyo & TSMC)",
            "ewj_price": ewj.get("price", 0.0),
            "ewj_change_pct": round(ewj_chg, 2),
            "tsm_price": tsm.get("price", 0.0),
            "tsm_change_pct": round(tsm_chg, 2),
            "score": asia_score,
            "status": "POZİTİF 🟢" if asia_avg >= 0.2 else ("NEGATİF 🔴" if asia_avg <= -0.2 else "NÖTR 🟡")
        }

        # 2. Avrupa Puanlaması (EWG & EWU)
        ewg = bars.get("EWG", {})
        ewu = bars.get("EWU", {})
        ewg_chg = ((ewg.get("price", 0) - ewg.get("open", 0)) / ewg.get("open", 1)) * 100 if ewg.get("open", 0) > 0 else 0.0
        ewu_chg = ((ewu.get("price", 0) - ewu.get("open", 0)) / ewu.get("open", 1)) * 100 if ewu.get("open", 0) > 0 else 0.0
        europe_avg = (ewg_chg + ewu_chg) / 2.0
        
        if europe_avg > 0.8: europe_score = 8.5
        elif europe_avg > 0.2: europe_score = 7.0
        elif europe_avg < -0.8: europe_score = 2.5
        elif europe_avg < -0.2: europe_score = 3.5
        else: europe_score = 5.5
        
        details["europe"] = {
            "name": "🇬🇧 Avrupa Seansı (DAX & FTSE)",
            "ewg_price": ewg.get("price", 0.0),
            "ewg_change_pct": round(ewg_chg, 2),
            "ewu_price": ewu.get("price", 0.0),
            "ewu_change_pct": round(ewu_chg, 2),
            "score": europe_score,
            "status": "POZİTİF 🟢" if europe_avg >= 0.2 else ("NEGATİF 🔴" if europe_avg <= -0.2 else "NÖTR 🟡")
        }

        # 3. ABD Ön Piyasa (SPY & QQQ)
        spy = bars.get("SPY", {})
        qqq = bars.get("QQQ", {})
        spy_chg = ((spy.get("price", 0) - spy.get("open", 0)) / spy.get("open", 1)) * 100 if spy.get("open", 0) > 0 else 0.0
        qqq_chg = ((qqq.get("price", 0) - qqq.get("open", 0)) / qqq.get("open", 1)) * 100 if qqq.get("open", 0) > 0 else 0.0
        us_avg = (spy_chg + qqq_chg) / 2.0
        
        if us_avg > 0.8: us_premarket_score = 9.0
        elif us_avg > 0.2: us_premarket_score = 7.5
        elif us_avg < -0.8: us_premarket_score = 2.0
        elif us_avg < -0.2: us_premarket_score = 3.5
        else: us_premarket_score = 5.5
        
        details["us_futures"] = {
            "name": "🇺🇸 ABD Vadeli / Ön Piyasa (S&P & Nasdaq)",
            "spy_price": spy.get("price", 0.0),
            "spy_change_pct": round(spy_chg, 2),
            "qqq_price": qqq.get("price", 0.0),
            "qqq_change_pct": round(qqq_chg, 2),
            "score": us_premarket_score,
            "status": "POZİTİF 🟢" if us_avg >= 0.2 else ("NEGATİF 🔴" if us_avg <= -0.2 else "NÖTR 🟡")
        }

        # Ağırlıklı Küresel Skor (Asya %25, Avrupa %35, ABD Ön Piyasa %40)
        global_score = round((asia_score * 0.25) + (europe_score * 0.35) + (us_premarket_score * 0.40), 1)
        
        if global_score >= 6.5:
            regime = "RISK_ON_BULLISH"
            badge = "🟢 KÜRESEL BOĞA (Risk-On İştahı Yüksek)"
            advice = "Küresel rüzgar arkamızda; 2. Dalga Retest kırılımlarında agresif alım onaylandı."
            allow_aggressive_buys = True
        elif global_score <= 4.0:
            regime = "RISK_OFF_BEARISH"
            badge = "🔴 KÜRESEL AYI (Risk-Off / Satış Baskısı)"
            advice = "Küresel borsalarda satış var; savunma kalkanı devrede, yalnızca güçlü ayrışan hisselere izin verilir."
            allow_aggressive_buys = False
        else:
            regime = "NEUTRAL_BALANCED"
            badge = "🟡 KÜRESEL NÖTR (Dengeli Piyasa)"
            advice = "Küresel piyasalar yatay/dengeli; standart 2. Dalga Retest kuralları geçerli."
            allow_aggressive_buys = True

        return {
            "status": "success",
            "global_macro_score": global_score,
            "regime": regime,
            "badge": badge,
            "advice": advice,
            "allow_aggressive_buys": allow_aggressive_buys,
            "details": details,
            "evaluated_at": time.strftime("%Y-%m-%d %H:%M:%S")
        }
