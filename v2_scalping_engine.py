"""
Fox-Kripto V2.3 — Hacim Scalping Motoru (Volume Scalping Engine)
Telif Hakkı (c) 2026 Fox-Kripto Quant Ekibi.

Likit piyasalardaki kısa süreli, doğrulanmış mikro-momentum ve retest fırsatlarını arar.
İlk pump mumuna doğrudan girmez; iki aşamalı (WATCH -> RETEST -> READY) durum makinesini uygular.
"""

import time
from typing import Dict, Any, List, Optional
from cost_engine import estimate_round_trip_cost, evaluate_net_reward_risk_gate

class V2ScalpingEngine:
    """
    V2.3 Güvenli Scalping Motoru
    """
    def __init__(self, risk_level: str = "BALANCED", custom_params: Optional[Dict[str, Any]] = None):
        self.risk_level = risk_level.upper() if risk_level else "BALANCED"
        self.params = {
            "name": "SCALPING_BALANCED_RESEARCH_V1",
            "timeframes": ["1m", "3m", "5m"],
            "max_24h_premium_pct": 3.5,
            "min_spike_multiplier": 1.4,
            "min_5m_volume_usd": 15000.0,
            "min_taker_buy_pct": 58.0,
            "max_spread_pct": 0.25,
            "max_single_candle_spike_pct": 2.20,
            "retest_required": True,
            "first_pump_candle_blocked": True,
            "min_strategy_score": 7.5,
            "target_take_profit_pct": 2.2,
            "target_stop_loss_pct": 1.1,
            "min_net_rr": 1.50
        }
        if custom_params:
            self.params.update(custom_params)

    def evaluate_candidate(
        self,
        ticker: Dict[str, Any],
        klines_1m: Optional[List[Any]] = None,
        depth_data: Optional[Dict[str, Any]] = None,
        user_tp: float = 2.2,
        user_sl: float = 1.1
    ) -> Dict[str, Any]:
        """
        Spot pariteyi V2.3 kurallarına göre analiz eder, puanlar ve durum makinesi durumunu belirler.
        """
        symbol = ticker.get("symbol", "")
        last_p = float(ticker.get("lastPrice", 0.0) or ticker.get("price", 0.0))
        vol_usd = float(ticker.get("quoteVolume", 0.0) or 0.0)
        gain_24h = float(ticker.get("priceChangePercent", 0.0) or 0.0)
        
        passed_criteria = []
        failed_criteria = []
        scores = {}
        
        # 1. 24s Dip/Prim Kontrolü (Anti-FOMO Tavanı)
        max_premium = self.params.get("max_24h_premium_pct", 3.5)
        if gain_24h > max_premium:
            failed_criteria.append(f"24s Artış (+%{gain_24h:.1f}) tavan sınırını (+%{max_premium}) aşıyor (Tepeden Alma Engeli).")
            scores["price_score"] = 2.0
        elif gain_24h < -6.0:
            failed_criteria.append(f"24s Düşüş (%{gain_24h:.1f}) aşırı negatif rejim gösteriyor.")
            scores["price_score"] = 3.0
        else:
            passed_criteria.append(f"24s Prim (+%{gain_24h:.1f}) izin verilen %{max_premium} tavanı altında (Taze Dip).")
            scores["price_score"] = 9.0

        # 2. Spread ve Likidite Derinliği Kontrolü
        spread_pct = 0.08
        if depth_data and "bids" in depth_data and "asks" in depth_data and depth_data["bids"] and depth_data["asks"]:
            best_bid = float(depth_data["bids"][0][0])
            best_ask = float(depth_data["asks"][0][0])
            if best_ask > 0 and best_bid > 0:
                spread_pct = ((best_ask - best_bid) / best_ask) * 100.0

        max_spread = self.params.get("max_spread_pct", 0.25)
        if spread_pct > max_spread:
            failed_criteria.append(f"Spread (%{spread_pct:.2f}) izin verilen azami %{max_spread:.2f} sınırından geniş.")
            scores["liquidity_score"] = 4.0
        else:
            passed_criteria.append(f"Spread (%{spread_pct:.2f}) dar ve scalping için güvenli.")
            scores["liquidity_score"] = 9.2

        # 3. 1m / 3m Hacim ve İvme Analizi (Retest & Anti-Pump Kontrolü)
        spike_ratio = 1.0
        gain_recent_pct = 0.0
        taker_buy_pct = 60.0
        upper_wick_ratio = 0.10
        state_machine_stage = "IDLE"

        if klines_1m and len(klines_1m) >= 6:
            recent_3 = klines_1m[-4:-1]
            prev_3 = klines_1m[-7:-4] if len(klines_1m) >= 7 else klines_1m[:3]
            
            v_recent = sum(float(k[7]) for k in recent_3)
            v_prev = sum(float(k[7]) for k in prev_3) if prev_3 else 1.0
            spike_ratio = (v_recent / v_prev) if v_prev > 0 else 1.0
            
            o = float(recent_3[0][1])
            c = float(recent_3[-1][4])
            h = max(float(k[2]) for k in recent_3)
            l = min(float(k[3]) for k in recent_3)
            gain_recent_pct = ((c - o) / o) * 100.0 if o > 0 else 0.0
            
            candle_range = h - l
            upper_wick_ratio = ((h - max(o, c)) / candle_range) if candle_range > 0 else 0.0
            
            tb_vol = sum(float(k[10]) for k in recent_3)
            taker_buy_pct = (tb_vol / v_recent * 100.0) if v_recent > 0 else 55.0

            # Durum Makinesi Geçişleri:
            # - Tek mum fırlaması > %2.2 -> İlk mum kovalanmaz (WAITING_RETEST)
            # - 3dk artış %0.3 - %2.0 ve alıcı baskısı > %58 -> READY
            if gain_recent_pct > self.params.get("max_single_candle_spike_pct", 2.20):
                state_machine_stage = "WAITING_RETEST"
                failed_criteria.append(f"İlk sıçrama (%{gain_recent_pct:.2f}) çok agresif; retest bekleniyor (Anti-FOMO).")
                scores["momentum_score"] = 6.0
            elif spike_ratio >= self.params.get("min_spike_multiplier", 1.4) and (0.20 <= gain_recent_pct <= 2.20) and upper_wick_ratio <= 0.35:
                state_machine_stage = "READY"
                passed_criteria.append(f"Taze kırılım (%{gain_recent_pct:.2f} 3dk) ve {spike_ratio:.1f}x hacim patlaması onaylandı.")
                scores["momentum_score"] = 9.0
            elif spike_ratio >= 1.2:
                state_machine_stage = "WATCH"
                passed_criteria.append(f"İntrabar hacim kıpırdanması ({spike_ratio:.1f}x) izleme listesine alındı.")
                scores["momentum_score"] = 7.0
            else:
                state_machine_stage = "IDLE"
                scores["momentum_score"] = 5.0
        else:
            scores["momentum_score"] = 6.0

        # 4. Taker Alıcı Baskısı Skoru
        min_taker = self.params.get("min_taker_buy_pct", 58.0)
        if taker_buy_pct < min_taker:
            failed_criteria.append(f"Taker Alış Oranı (%{taker_buy_pct:.1f}) %{min_taker:.1f} barajının altında.")
            scores["taker_score"] = 5.0
        else:
            passed_criteria.append(f"Taker Alış Baskısı (%{taker_buy_pct:.1f}) alıcıların tahtayı süpürdüğünü gösteriyor.")
            scores["taker_score"] = 9.0

        # 5. Maliyet ve Net R/R Kapısı (V2.3 Zorunlu)
        round_trip = estimate_round_trip_cost(symbol=symbol, entry_price=last_p, spread_pct=spread_pct)
        cost_gate = evaluate_net_reward_risk_gate(
            gross_take_profit_pct=user_tp,
            gross_stop_loss_pct=user_sl,
            round_trip_cost_pct=round_trip["total_round_trip_cost_pct"],
            min_net_rr_required=self.params.get("min_net_rr", 1.50)
        )

        if not cost_gate["passed"]:
            failed_criteria.extend(cost_gate["failure_reasons"])
            scores["cost_score"] = 4.0
        else:
            passed_criteria.append(f"Net R/R ({cost_gate['net_reward_risk_ratio']:.2f}) maliyet sonrası pozitif avantaj sağlıyor.")
            scores["cost_score"] = 9.5

        # Ağırlıklı Toplam Skor
        final_score = round(
            scores.get("momentum_score", 6.0) * 0.30 +
            scores.get("taker_score", 6.0) * 0.25 +
            scores.get("cost_score", 6.0) * 0.20 +
            scores.get("price_score", 7.0) * 0.15 +
            scores.get("liquidity_score", 8.0) * 0.10,
            1
        )

        is_ready = (
            state_machine_stage == "READY" and
            cost_gate["passed"] and
            final_score >= self.params.get("min_strategy_score", 7.5) and
            len(failed_criteria) == 0
        )

        return {
            "engine": "VOLUME_SCALPING",
            "version": "v2.3",
            "symbol": symbol,
            "price": last_p,
            "state_machine_stage": state_machine_stage,
            "is_ready": is_ready,
            "strategy_score": final_score,
            "passed_criteria": passed_criteria,
            "failed_criteria": failed_criteria,
            "cost_details": round_trip,
            "net_rr_details": cost_gate,
            "indicators": {
                "gain_24h_pct": gain_24h,
                "gain_recent_pct": gain_recent_pct,
                "volume_spike_ratio": spike_ratio,
                "taker_buy_pct": taker_buy_pct,
                "spread_pct": spread_pct,
                "upper_wick_ratio": upper_wick_ratio
            }
        }
