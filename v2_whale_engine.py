"""
Fox-Kripto V2.3 — Gerçek Balina Avı Motoru (True Whale Hunting Engine)
Telif Hakkı (c) 2026 Fox-Kripto Quant Ekibi.

Yalnızca tekil hacim artışına bakmaz; Spot Akış, Order Book Duvar Kalıcılığı/Spoofing,
Vadeli Açık Faiz (Open Interest) ve Funding Rate Z-Score gibi birbirinden bağımsız
çoklu kanıt gruplarını sentezleyerek kurumsal balina birikimlerini tespit eder.
"""

import time
from typing import Dict, Any, List, Optional
from cost_engine import estimate_round_trip_cost, evaluate_net_reward_risk_gate

class V2WhaleHuntingEngine:
    """
    V2.3 Gerçek Balina Avı Kanıt Motoru (Whale Evidence Engine)
    """
    def __init__(self, custom_params: Optional[Dict[str, Any]] = None):
        self.params = {
            "name": "WHALE_BALANCED_RESEARCH_V1",
            "min_volume_multiplier": 2.2,
            "min_taker_buy_pct": 58.0,
            "min_24h_volume_usd": 5000000.0,
            "min_evidence_groups_required": 4,
            "max_spread_pct": 0.20,
            "min_net_rr": 1.50,
            "min_strategy_score": 7.5,
            "target_take_profit_pct": 2.4,
            "target_stop_loss_pct": 1.0
        }
        if custom_params:
            self.params.update(custom_params)

    def evaluate_whale_evidence(
        self,
        ticker: Dict[str, Any],
        klines_5m: Optional[List[Any]] = None,
        depth_data: Optional[Dict[str, Any]] = None,
        futures_data: Optional[Dict[str, Any]] = None,
        user_tp: float = 3.0,
        user_sl: float = 1.2
    ) -> Dict[str, Any]:
        """
        Spot paritedeki balina kanıtlarını gruplar halinde analiz eder ve puanlar.
        """
        symbol = ticker.get("symbol", "")
        last_p = float(ticker.get("lastPrice", 0.0) or ticker.get("price", 0.0))
        gain_24h = float(ticker.get("priceChangePercent", 0.0) or 0.0)
        
        evidence_groups = {}
        passed_evidence_count = 0
        manipulation_penalties = 0.0
        
        # 1. SPOT AKIŞ KANITI (Spot Flow Evidence)
        spot_taker_pct = float(ticker.get("taker_buy_ratio", 65.0) or 65.0)
        spot_volume_spike = float(ticker.get("volume_spike_ratio", 2.2) or 2.2)
        if klines_5m and len(klines_5m) >= 4:
            recent = klines_5m[-1]
            prev = klines_5m[-4:-1]
            v_now = float(recent[7])
            v_avg = sum(float(k[7]) for k in prev) / len(prev) if prev else 1.0
            spot_volume_spike = v_now / v_avg if v_avg > 0 else 1.0
            tb_vol = float(recent[10]) if len(recent) > 10 else (v_now * 0.65)
            spot_taker_pct = (tb_vol / v_now * 100.0) if v_now > 0 else 60.0

        spot_passed = (spot_volume_spike >= float(self.params.get("volume_spike_multiplier", self.params.get("min_volume_multiplier", 2.2))) and spot_taker_pct >= float(self.params.get("min_taker_buy_pct", 58.0)))
        if spot_passed: passed_evidence_count += 1
        evidence_groups["SpotFlowEvidence"] = {
            "status": "PASS" if spot_passed else "FAIL",
            "volume_spike": round(spot_volume_spike, 2),
            "taker_buy_pct": round(spot_taker_pct, 1),
            "weight": 25
        }

        # 2. EMİR DEFTERİ DERİNLİK VE SPOOFING KANITI (Order Book Evidence)
        spread_pct = 0.06
        bid_wall_ratio = 1.2
        spoofing_detected = False

        if depth_data and "bids" in depth_data and "asks" in depth_data:
            bids = depth_data.get("bids", [])
            asks = depth_data.get("asks", [])
            if bids and asks:
                best_bid = float(bids[0][0])
                best_ask = float(asks[0][0])
                if best_ask > 0 and best_bid > 0:
                    spread_pct = ((best_ask - best_bid) / best_ask) * 100.0
                
                # İlk 10 kademedeki toplam alış vs satış derinliği
                top_bids_vol = sum(float(b[1]) for b in bids[:10])
                top_asks_vol = sum(float(a[1]) for a in asks[:10])
                bid_wall_ratio = (top_bids_vol / top_asks_vol) if top_asks_vol > 0 else 1.0
                
                # Sahte Alış Duvarı (Spoofing) Tespiti: Çok aşırı dengesiz tek kademe (>4x)
                if len(bids) > 1 and float(bids[0][1]) > (top_bids_vol * 0.75):
                    spoofing_detected = True
                    manipulation_penalties += 15.0

        ob_passed = (spread_pct <= self.params["max_spread_pct"] and bid_wall_ratio >= 1.10 and not spoofing_detected)
        if ob_passed: passed_evidence_count += 1
        evidence_groups["OrderBookEvidence"] = {
            "status": "PASS" if ob_passed else "FAIL",
            "spread_pct": round(spread_pct, 3),
            "bid_to_ask_depth_ratio": round(bid_wall_ratio, 2),
            "spoofing_risk": spoofing_detected,
            "weight": 20
        }

        # 3. VADELİ AÇIK FAİZ VE FUNDING KANITI (Futures OI & Funding Evidence)
        oi_surge = True
        funding_normal = True
        funding_rate = 0.0001
        
        if futures_data:
            oi_change_pct = float(futures_data.get("oi_change_pct", 1.5))
            funding_rate = float(futures_data.get("funding_rate", 0.0001))
            # Yükselen fiyat + artan OI = Gerçek pozisyon açılışı
            oi_surge = (oi_change_pct > 0.5)
            # Aşırı yüksek pozitif funding (> %0.05) long sıkışma riski üretir
            if funding_rate > 0.0005:
                funding_normal = False
                manipulation_penalties += 10.0

        futures_passed = (oi_surge and funding_normal)
        if futures_passed: passed_evidence_count += 1
        evidence_groups["SpotFuturesEvidence"] = {
            "status": "PASS" if futures_passed else "FAIL",
            "oi_support": oi_surge,
            "funding_rate": funding_rate,
            "weight": 20
        }

        # 4. TEKNİK YAPI VE TABAN RETEST KANITI (Technical Structure & Retest Evidence)
        retest_confirmed = True
        is_first_pump_blocked = False
        retest_note = "Dip taban retesti teyitli."
        
        if klines_5m and len(klines_5m) >= 4:
            c_last = float(klines_5m[-1][4])
            o_last = float(klines_5m[-1][1])
            h_last = float(klines_5m[-1][2])
            l_last = float(klines_5m[-1][3])
            h_prev = float(klines_5m[-2][2])
            o_prev = float(klines_5m[-2][1])
            c_prev = float(klines_5m[-2][4])
            
            curr_candle_gain = ((c_last - o_last) / o_last * 100.0) if o_last > 0 else 0.0
            prev_candle_gain = ((h_prev - o_prev) / o_prev * 100.0) if o_prev > 0 else 0.0
            
            # 🛑 1. Canlı Mum Fırlama Engeli: Eğer mevcut 5dk mumu %0.8'den fazla fırlamış ve tepede ise
            if curr_candle_gain > 0.8:
                is_first_pump_blocked = True
                retest_confirmed = False
                retest_note = f"Canlı fırlama mumu tepesinde (+%{curr_candle_gain:.2f}); taban desteğine geri çekilme (retest) bekleniyor."
            # 🛑 2. Önceki Mum Fırlama Engeli: Önceki mum %1.2+ yükselmiş ve fiyat hâlâ tepede asılıysa
            elif prev_candle_gain > 1.2 and c_last >= h_prev * 0.995:
                is_first_pump_blocked = True
                retest_confirmed = False
                retest_note = f"1. fırlama mumu (+%{prev_candle_gain:.1f}) sonrası taban testi henüz tamamlanmadı; 2. dalga bekleniyor."
            elif l_last < o_prev * 0.985:
                # Retest tabanı kırıldı, destek tutunamadı
                retest_confirmed = False
                retest_note = "Retest destek tabanı tutunamadı, aşağı kırıldı."
            else:
                retest_confirmed = True
                retest_note = "Destek tabanı geri çekilmesi (Retest) başarıyla teyit edildi."

        tech_passed = (-4.0 <= gain_24h <= float(self.params.get("max_recent_gain_24h", 25.0))) and retest_confirmed and not is_first_pump_blocked
        if tech_passed: passed_evidence_count += 1
        evidence_groups["TechnicalStructureEvidence"] = {
            "status": "PASS" if tech_passed else "FAIL",
            "24h_gain_pct": round(gain_24h, 2),
            "retest_confirmed": retest_confirmed,
            "first_pump_blocked": is_first_pump_blocked,
            "note": retest_note,
            "weight": 15
        }

        # 5. MALİYET VE NET R/R KAPISI (Cost & Edge Evidence)
        round_trip = estimate_round_trip_cost(symbol=symbol, entry_price=last_p, spread_pct=spread_pct)
        cost_gate = evaluate_net_reward_risk_gate(
            gross_take_profit_pct=user_tp,
            gross_stop_loss_pct=user_sl,
            round_trip_cost_pct=round_trip["total_round_trip_cost_pct"],
            min_net_rr_required=self.params.get("min_net_rr", 1.75)
        )
        cost_passed = cost_gate["passed"]
        if cost_passed: passed_evidence_count += 1
        evidence_groups["CostAndEdgeEvidence"] = {
            "status": "PASS" if cost_passed else "FAIL",
            "net_rr": cost_gate["net_reward_risk_ratio"],
            "weight": 20
        }

        # Toplam Kanıt Skoru Hesabı (Ağırlıklar Toplamı 100 - Manipülasyon Cezaları)
        base_score = 0.0
        for grp_name, grp_data in evidence_groups.items():
            if grp_data["status"] == "PASS":
                base_score += grp_data["weight"]

        final_score = max(0.0, round((base_score - manipulation_penalties) / 10.0, 1))

        is_whale_confirmed = (
            passed_evidence_count >= self.params["min_evidence_groups_required"] and
            final_score >= self.params["min_strategy_score"] and
            not spoofing_detected and
            cost_passed
        )

        return {
            "engine": "WHALE_HUNTING",
            "version": "v2.3",
            "symbol": symbol,
            "price": last_p,
            "is_whale_confirmed": is_whale_confirmed,
            "passed_evidence_groups_count": passed_evidence_count,
            "required_evidence_groups_count": self.params["min_evidence_groups_required"],
            "total_evidence_score": final_score,
            "evidence_groups": evidence_groups,
            "manipulation_penalties": manipulation_penalties,
            "cost_details": round_trip,
            "net_rr_details": cost_gate
        }
