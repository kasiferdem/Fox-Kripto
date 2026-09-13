import os, sys, unittest, time
if hasattr(sys.stdout, 'reconfigure'): sys.stdout.reconfigure(encoding='utf-8')

from db import get_strategy_config
from circuit_breaker import check_tenant_circuit_breakers

class TestWaveTradingSuite(unittest.TestCase):
    def setUp(self):
        self.cfg = get_strategy_config(use_cache=False)

    def test_01_strategy_parameters(self):
        """v22_asymmetric_wave parametrelerinin eksiksiz yüklendiğini doğrula."""
        self.assertEqual(self.cfg.get("active_preset"), "v22_asymmetric_wave")
        self.assertGreaterEqual(int(self.cfg.get("max_daily_trades")), 6)
        self.assertEqual(int(self.cfg.get("max_concurrent_positions")), 2)
        self.assertAlmostEqual(float(self.cfg.get("take_profit_pct")), 3.5)
        self.assertAlmostEqual(float(self.cfg.get("stop_loss_pct")), 1.2)
        self.assertAlmostEqual(float(self.cfg.get("break_even_trigger_pct")), 1.2)
        self.assertTrue(self.cfg.get("retest_required"))
        self.assertTrue(self.cfg.get("first_pump_candle_entry_blocked"))

    def test_02_max_concurrent_positions_limit(self):
        """2 açık pozisyon varken 3. alımın engellendiğini doğrula."""
        # 1 açık pozisyon varken geçmeli
        res_1 = check_tenant_circuit_breakers("mock_tenant_wave", current_active_positions_count=1)
        self.assertTrue(res_1.get("passed"), "1 açık pozisyon varken alım izni verilmeli")
        
        # 2 açık pozisyon varken (slot dolu) engellenmeli
        res_2 = check_tenant_circuit_breakers("mock_tenant_wave", current_active_positions_count=2)
        self.assertFalse(res_2.get("passed"), "2 açık pozisyon varken yeni alım engellenmeli")
        self.assertEqual(res_2.get("circuit_breaker"), "MAX_CONCURRENT_POSITIONS_FULL")

    def test_03_asymmetric_risk_reward_ratio(self):
        """Risk/Ödül oranının en az 1:2.8 olduğunu doğrula."""
        tp = float(self.cfg.get("take_profit_pct"))
        sl = float(self.cfg.get("stop_loss_pct"))
        rr_ratio = tp / sl
        self.assertGreaterEqual(rr_ratio, 2.8, f"R:R oranı en az 1:2.8 olmalı, bulunan: {rr_ratio:.2f}")

    def test_04_breakeven_threshold(self):
        """Başa-Baş kalkanının %1.2'de kilitlendiğini doğrula."""
        be = float(self.cfg.get("break_even_trigger_pct"))
        self.assertEqual(be, 1.2, "Break-even eşiği %1.2 olmalıdır")

if __name__ == "__main__":
    unittest.main()
