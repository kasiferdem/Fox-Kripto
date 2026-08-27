"""
Fox-Kripto V2: Hacim Scalping Motoru (Volume Scalping Engine)
Kısa süreli hacim ve momentum patlamalarını yakalayan, hızlı ve çevik scalp algoritması.
"""
import time
import requests
from typing import Dict, Any, List, Optional
from v2_models import V2_SCALPING_PRESETS, SignalStatus

class V2ScalpingEngine:
    def __init__(self, risk_level: str = "BALANCED", custom_params: Optional[Dict[str, Any]] = None):
        self.risk_level = risk_level.upper() if risk_level else "BALANCED"
        base_preset = V2_SCALPING_PRESETS.get(self.risk_level, V2_SCALPING_PRESETS["BALANCED"]).copy()
        if custom_params:
            base_preset.update(custom_params)
        self.params = base_preset

    def evaluate_ticker_data(self, ticker: Dict[str, Any], depth_data: Optional[Dict[str, Any]] = None, klines_5m: Optional[List[Any]] = None) -> Dict[str, Any]:
        """
        Spot paritenin scalping kriterlerine uygunluğunu puanlar ve açıklar.
        """
        symbol = ticker.get("symbol", "")
        last_price = float(ticker.get("lastPrice", 0.0) or ticker.get("price", 0.0))
        vol_usd = float(ticker.get("quoteVolume", 0.0) or 0.0)
        gain_24h = float(ticker.get("priceChangePercent", 0.0) or 0.0)
        trades_count = int(ticker.get("count", 0) or 0)

        passed_criteria = []
        failed_criteria = []
        scores = {}

        # 1. 24s Tavan Kontrolü (FOMO Engeli)
        max_premium = self.params.get("max_24h_premium_pct", 10.0)
        if gain_24h > max_premium:
            failed_criteria.append(f"24s Artış (+%{gain_24h:.1f}) tavan sınırını (+%{max_premium}) aşıyor (Anti-FOMO).")
            scores["price_score"] = 3.0
        else:
            passed_criteria.append(f"24s Prim (+%{gain_24h:.1f}) izin verilen %{max_premium} tavanı altında.")
            scores["price_score"] = 8.5

        # 2. Hacim ve Likidite Kontrolü
        min_vol = self.params.get("min_5m_volume_usd", 50000.0)
        vol_5m_est = vol_usd / 288.0 # 24s hacmin ortalama 5dk karşılığı
        if vol_5m_est < (min_vol * 0.5):
            failed_criteria.append(f"5dk Tahmini Hacim (${vol_5m_est:,.0f}) minimum ${min_vol:,.0f} barajının altında.")
            scores["volume_score"] = 4.0
        else:
            passed_criteria.append(f"5dk Hacim (${vol_5m_est:,.0f}) yeterli likidite sağlıyor.")
            scores["volume_score"] = 8.0

        # 3. Spread ve Slippage Kontrolü (Derinlik varsa)
        spread_pct = 0.15 # Varsayılan güvenli spread
        if depth_data and "bids" in depth_data and "asks" in depth_data and depth_data["bids"] and depth_data["asks"]:
            best_bid = float(depth_data["bids"][0][0])
            best_ask = float(depth_data["asks"][0][0])
            if best_ask > 0 and best_bid > 0:
                spread_pct = ((best_ask - best_bid) / best_ask) * 100.0

        max_spread = self.params.get("max_spread_pct", 0.40)
        if spread_pct > max_spread:
            failed_criteria.append(f"Spread (%{spread_pct:.2f}) izin verilen %{max_spread:.2f} sınırından geniş.")
            scores["liquidity_score"] = 4.5
        else:
            passed_criteria.append(f"Spread (%{spread_pct:.2f}) dar ve işlem için son derece elverişli.")
            scores["liquidity_score"] = 9.0

        # 4. Taker Alış Baskısı Tahmini (Mum hacimlerinden)
        taker_buy_ratio = 62.5 # Ortalama güçlü alım tahmini
        if klines_5m and len(klines_5m) > 0:
            last_kline = klines_5m[-1]
            total_k_vol = float(last_kline[5]) if len(last_kline) > 5 else 1.0
            taker_k_vol = float(last_kline[9]) if len(last_kline) > 9 else (total_k_vol * 0.6)
            if total_k_vol > 0:
                taker_buy_ratio = (taker_k_vol / total_k_vol) * 100.0

        min_taker = self.params.get("min_taker_buy_pct", 61.0)
        if taker_buy_ratio < min_taker:
            failed_criteria.append(f"Taker Alış Oranı (%{taker_buy_ratio:.1f}) %{min_taker:.1f} hedefinin altında.")
            scores["taker_score"] = 5.0
        else:
            passed_criteria.append(f"Taker Alış Baskısı (%{taker_buy_ratio:.1f}) net boğa momentumu teyit ediyor.")
            scores["taker_score"] = 8.8

        # Nihai Ağırlıklı Skor
        final_score = (
            scores.get("volume_score", 6.0) * 0.30 +
            scores.get("taker_score", 6.0) * 0.30 +
            scores.get("liquidity_score", 7.0) * 0.20 +
            scores.get("price_score", 7.0) * 0.20
        )

        min_req_score = self.params.get("min_strategy_score", 7.5)
        is_ready = (final_score >= min_req_score) and (len(failed_criteria) == 0 or (len(failed_criteria) == 1 and final_score >= 8.0))

        status = SignalStatus.READY if is_ready else (SignalStatus.WATCHING if final_score >= 6.0 else SignalStatus.REJECTED)

        return {
            "engine": "VOLUME_SCALPING",
            "profile_name": self.params.get("name", "Scalping"),
            "risk_level": self.risk_level,
            "symbol": symbol,
            "last_price": last_price,
            "gain_24h": gain_24h,
            "final_score": round(final_score, 2),
            "status": status.value,
            "passed_criteria": passed_criteria,
            "failed_criteria": failed_criteria,
            "entry_plan": {
                "tp_pct": self.params.get("take_profit_pct", 3.0),
                "sl_pct": self.params.get("stop_loss_pct", 1.5),
                "trailing_callback_pct": self.params.get("trailing_callback_pct", 0.6),
                "max_budget_percent": self.params.get("max_budget_percent", 25.0)
            }
        }
