"""
Test Paketi: CoinBehavioralProbabilityEngine & Admin Parametre Yönetimi
Telif Hakkı (c) 2026 Fox-Kripto Quant Ekibi.
"""

import unittest
import time
import json
from coin_behavioral_probability_engine import (
    CoinBehavioralProbabilityEngine,
    CoinDnaDecisionClass,
    ExecutionAuthority,
    sanitize_advisory_text,
    PROHIBITED_PHRASES
)
from db import get_strategy_config, save_strategy_config, save_coin_dna_snapshot, get_latest_coin_dna_snapshot

class TestCoinBehavioralProbabilityEngine(unittest.TestCase):

    def setUp(self):
        self.engine = CoinBehavioralProbabilityEngine({
            "coin_dna_enabled": True,
            "coin_dna_execution_authority": "ADVISORY_ONLY",
            "coin_dna_min_sample_count": 20,
            "coin_dna_target_levels": [0.5, 1.0, 1.5, 2.0, 2.5, 4.0],
            "coin_dna_cache_ttl_minutes": 60,
            "coin_dna_history_days": 30
        })

    def test_01_advisory_authority_boundary(self):
        """Motorun yetkisi kesinlikle ADVISORY_ONLY olmalı, emir açma yetkisi olmamalı."""
        self.assertEqual(self.engine.execution_authority, ExecutionAuthority.ADVISORY_ONLY.value)
        self.assertNotEqual(self.engine.execution_authority, "EXECUTE")

    def test_02_sanitize_advisory_text(self):
        """Pazarlamacı ve kesinlik ifade eden yasaklı kelimeler elenmeli."""
        bad_text = "Bu coin kesin fiyata gider ve balina maliyeti altına inemez."
        clean = sanitize_advisory_text(bad_text)
        for phrase in PROHIBITED_PHRASES:
            self.assertNotIn(phrase, clean.lower())

    def test_03_synthetic_breakout_detection(self):
        """Look-ahead bias olmadan hacim ve gövde patlaması tespit edilmeli."""
        # 45 mumluk sentetik kline: Son 10 mum yatay, 25. mumda 3.5x hacim ve %3 gövde
        klines = []
        base_time = 1700000000000
        for i in range(45):
            t = base_time + i * 300000
            o = 100.0
            h = 100.5
            l = 99.5
            c = 100.1
            v = 1000.0
            if i == 25:
                o = 100.0
                c = 103.0 # +%3 gövde
                h = 103.5
                l = 99.8
                v = 4000.0 # 4x hacim
            klines.append([t, str(o), str(h), str(l), str(c), str(v), t+299999, "100000", 50, "500", "50000", "0"])

        events = self.engine.identify_historical_breakouts(klines, breakout_threshold_pct=2.0, volume_surge_mult=2.0)
        self.assertGreaterEqual(len(events), 1)
        found_idx = [e["event_index"] for e in events]
        self.assertIn(25, found_idx)

    def test_04_measure_event_excursions_and_mfe_mae(self):
        """MFE ve MAE hesaplaması doğrulanmalı."""
        klines = []
        base_time = 1700000000000
        # 15 barlık hareket: 0. barda giriş, sonraki barlarda önce %1 geri çekilme, sonra %4 yükselme
        for i in range(15):
            t = base_time + i * 300000
            if i == 0:
                o, h, l, c = 100.0, 102.5, 99.8, 102.0
            elif i == 1:
                o, h, l, c = 102.0, 102.2, 99.0, 101.0 # %1 dip (MAE ~ 1.0%)
            elif i == 2:
                o, h, l, c = 101.0, 104.5, 100.5, 104.0 # %4 tepe (MFE ~ 4.5%)
            else:
                o, h, l, c = 104.0, 104.2, 103.5, 103.8
            klines.append([t, str(o), str(h), str(l), str(c), "1000.0", t+299999, "100000", 50, "500", "50000", "0"])

        event = {"candle_index": 0, "open_time": base_time, "entry_price": 100.0}
        measured = self.engine.measure_event_excursions(klines, event, forward_bars=12)

        self.assertGreaterEqual(measured["mfe_pct"], 4.0)
        self.assertGreaterEqual(measured["mae_pct"], 1.0)
        self.assertIn("mfe_60m", measured["excursions"])

    def test_05_probability_matrix_and_expectancy(self):
        """Hedef olasılıkları ve net matematiksel beklenti hesaplanmalı."""
        events = [
            {"mfe_pct": 3.0, "mae_pct": 0.8, "target_outcomes": {1.0: "HIT_TARGET", 2.0: "HIT_TARGET"}},
            {"mfe_pct": 1.2, "mae_pct": 0.5, "target_outcomes": {1.0: "HIT_TARGET", 2.0: "HIT_STOP"}},
            {"mfe_pct": 0.4, "mae_pct": 1.5, "target_outcomes": {1.0: "HIT_STOP", 2.0: "HIT_STOP"}},
            {"mfe_pct": 2.5, "mae_pct": 0.9, "target_outcomes": {1.0: "HIT_TARGET", 2.0: "HIT_TARGET"}},
        ]
        matrix = self.engine.estimate_target_probabilities(events, sl_pct=1.2)
        self.assertEqual(len(matrix), 6) # [0.5, 1.0, 1.5, 2.0, 2.5, 4.0]

        row_1 = next(r for r in matrix if r["target_pct"] == 1.0)
        self.assertEqual(row_1["target_hits"], 3)
        self.assertEqual(row_1["probability_target_before_stop"], 75.0)
        self.assertIn("net_expectancy", row_1)

    def test_06_insufficient_sample_decision(self):
        """N < 20 durumunda INSUFFICIENT_SAMPLE kararı verilmeli."""
        # Sahte klines ile az sayıda patlama
        engine = CoinBehavioralProbabilityEngine({"coin_dna_min_sample_count": 50})
        res = engine.evaluate_coin_dna("TESTCOIN/USDT", live_ticker={"lastPrice": "10.0"})
        # Veri çekilemezse DATA_UNAVAILABLE veya N < 50 ise INSUFFICIENT_SAMPLE
        self.assertIn(res["decision_class"], [CoinDnaDecisionClass.DATA_UNAVAILABLE.value, CoinDnaDecisionClass.INSUFFICIENT_SAMPLE.value])

    def test_07_db_strategy_config_and_snapshot_persistence(self):
        """db.py üzerinden Coin DNA parametreleri ve snapshot kaydı doğrulanmalı."""
        cfg = get_strategy_config(use_cache=False)
        self.assertIn("coin_dna_enabled", cfg)
        self.assertIn("coin_dna_execution_authority", cfg)
        self.assertIn("coin_dna_min_sample_count", cfg)

        # Snapshot kaydı
        dummy_snap = {
            "symbol": "BTC/USDT",
            "decision_class": "MODERATE_ROOM",
            "sample_count": 28,
            "probability_matrix": [{"target_pct": 1.5, "probability_target_before_stop": 62.5}]
        }
        ok = save_coin_dna_snapshot(dummy_snap)
        self.assertTrue(ok)

        retrieved = get_latest_coin_dna_snapshot("BTC/USDT")
        self.assertIsNotNone(retrieved)
        self.assertEqual(retrieved.get("decision_class"), "MODERATE_ROOM")

    def test_08_is_coin_dna_blocked_rules(self):
        """Öneri 1: BLOCK_ONLY modunda yetersiz örnek, direnç ve aşırı uzama engellenmeli."""
        from coin_behavioral_probability_engine import is_coin_dna_blocked

        # 1. N < 20 / INSUFFICIENT_SAMPLE
        snap_low_n = {
            "decision_class": "INSUFFICIENT_SAMPLE",
            "sample_count": 8,
            "status": "SUCCESS",
            "probability_matrix": [{"target_pct": 1.0, "probability_target_before_stop": 50.0}]
        }
        blocked, reason = is_coin_dna_blocked(snap_low_n, {"coin_dna_execution_authority": "BLOCK_ONLY"})
        self.assertTrue(blocked)
        self.assertIn("Karar Sınıfı Engeli", reason)

        # 2. RESISTANCE_NEAR
        snap_res = {
            "decision_class": "RESISTANCE_NEAR",
            "sample_count": 25,
            "status": "SUCCESS"
        }
        blocked, reason = is_coin_dna_blocked(snap_res, {"coin_dna_execution_authority": "BLOCK_ONLY"})
        self.assertTrue(blocked)
        self.assertIn("RESISTANCE_NEAR", reason)

        # 3. EXTENDED_MOVE (AVWAP > %7.5)
        snap_ext = {
            "decision_class": "EXTENDED_MOVE",
            "sample_count": 30,
            "anchored_vwap_distance_pct": 8.2,
            "status": "SUCCESS"
        }
        blocked, reason = is_coin_dna_blocked(snap_ext, {"coin_dna_execution_authority": "BLOCK_ONLY"})
        self.assertTrue(blocked)
        self.assertIn("EXTENDED_MOVE", reason)

        # 4. DATA_UNAVAILABLE (Fail-Closed)
        blocked, reason = is_coin_dna_blocked(None, {"coin_dna_execution_authority": "BLOCK_ONLY"})
        self.assertTrue(blocked)
        self.assertIn("Fail-Closed", reason)

    def test_09_is_coin_dna_blocked_walls_and_probabilities(self):
        """Öneri 1: 2.2% satış duvarı veya < %40 kazanma olasılığı engellenmeli."""
        from coin_behavioral_probability_engine import is_coin_dna_blocked

        # Satış Duvarı (< %2.2)
        snap_wall = {
            "decision_class": "MODERATE_ROOM",
            "sample_count": 25,
            "status": "SUCCESS",
            "order_book": {"has_wall": True, "wall_distance_pct": 1.4},
            "probability_matrix": [{"target_pct": 1.0, "probability_target_before_stop": 55.0}]
        }
        blocked, reason = is_coin_dna_blocked(snap_wall, {"coin_dna_execution_authority": "BLOCK_ONLY"})
        self.assertTrue(blocked)
        self.assertIn("Satış duvarı çok yakın", reason)

        # Düşük Olasılık (< %40)
        snap_low_p = {
            "decision_class": "MODERATE_ROOM",
            "sample_count": 25,
            "status": "SUCCESS",
            "order_book": {"has_wall": False, "wall_distance_pct": 99.0},
            "probability_matrix": [{"target_pct": 1.0, "probability_target_before_stop": 32.0}]
        }
        blocked, reason = is_coin_dna_blocked(snap_low_p, {"coin_dna_execution_authority": "BLOCK_ONLY"})
        self.assertTrue(blocked)
        self.assertIn("olasılığı kritik seviyenin altında", reason)

    def test_10_approved_candidate_passes_gate(self):
        """Koşu alanı geniş, N >= 20 ve olasılık yüksek coin onaylanmalı."""
        from coin_behavioral_probability_engine import is_coin_dna_blocked

        snap_good = {
            "decision_class": "WIDE_ROOM",
            "sample_count": 35,
            "status": "SUCCESS",
            "order_book": {"has_wall": False, "wall_distance_pct": 99.0},
            "anchored_vwap_distance_pct": 2.1,
            "probability_matrix": [{"target_pct": 1.0, "probability_target_before_stop": 68.0}]
        }
        blocked, reason = is_coin_dna_blocked(snap_good, {"coin_dna_execution_authority": "BLOCK_ONLY"})
        self.assertFalse(blocked)
        self.assertIn("Onaylandı", reason)

if __name__ == "__main__":
    unittest.main()
