"""Offline regressions. Never import app/pollers or read production credentials."""

import ast
import copy
import importlib.util
import json
import math
from pathlib import Path
import socket
import sys
import time
import types
import unittest
from datetime import datetime, timezone, timedelta
from unittest.mock import patch, Mock

import circuit_breaker
from balanced_spot_profile import (
    BALANCED_SPOT_PROFILE, assess_buy_orderbook, capped_entry_budget, candidate_entry_flags,
)
from net_advantage_gate import evaluate_net_advantage_gate


ROOT = Path(__file__).resolve().parents[1]


class FakeQuery:
    def __init__(self, client, table):
        self.client, self.table_name = client, table
        self.filters = {}
        self.start, self.end = 0, 999
        self.payload = None
        self.since = None

    def select(self, *_):
        return self

    def eq(self, key, value):
        self.filters[key] = value
        return self

    def gte(self, _, value):
        self.since = value
        return self

    def order(self, *_, **__):
        return self

    def range(self, start, end):
        self.start, self.end = start, end
        return self

    def insert(self, payload):
        self.payload = payload
        return self

    def upsert(self, payload):
        self.payload = payload
        return self

    def execute(self):
        if self.client.fail:
            raise RuntimeError("offline DB failure")
        if self.table_name == "crypto_agent_states":
            if self.payload:
                sid = self.payload["session_id"]
                self.client.states[sid] = copy.deepcopy(self.payload["state_data"])
                return types.SimpleNamespace(data=[self.payload])
            data = self.client.states.get(self.filters.get("session_id"))
            return types.SimpleNamespace(data=[] if data is None else [{"state_data": copy.deepcopy(data)}])
        rows = self.client.trades
        if self.since:
            rows = [t for t in rows if t["created_at"] >= self.since]
        return types.SimpleNamespace(data=rows[self.start:self.end + 1])


class FakeClient:
    def __init__(self):
        self.trades, self.states, self.fail = [], {}, False

    def table(self, table):
        return FakeQuery(self, table)


class OfflineTest(unittest.TestCase):
    def setUp(self):
        self.network = patch.object(socket.socket, "connect", side_effect=AssertionError("Network forbidden"))
        self.network.start()
        self.addCleanup(self.network.stop)


class ProfileTests(OfflineTest):
    def test_profile_matches_local_fallback(self):
        cfg = json.loads((ROOT / "strategy_config_local.json").read_text(encoding="utf-8"))
        for key, value in BALANCED_SPOT_PROFILE.items():
            self.assertEqual(cfg[key], value, key)

    def test_selected_risk_and_mode(self):
        cfg = BALANCED_SPOT_PROFILE
        self.assertEqual(cfg["execution_mode"], "PAPER_TRADING")
        self.assertEqual(cfg["daily_loss_limit_pct"], 2)
        self.assertIsNone(cfg["daily_max_loss_usd"])
        self.assertTrue(cfg["retest_required"])
        self.assertFalse(cfg["dca_enabled"])
        self.assertEqual(cfg["signal_interval"], "15m")

    def test_budget_honors_global_cap_over_tenant(self):
        self.assertEqual(capped_entry_budget(10000, 10000, 0, 80, BALANCED_SPOT_PROFILE), 2000)

    def test_budget_honors_lower_tenant_cap(self):
        self.assertEqual(capped_entry_budget(10000, 10000, 0, 10, BALANCED_SPOT_PROFILE), 1000)

    def test_budget_honors_total_exposure(self):
        self.assertEqual(capped_entry_budget(10000, 4500, 5500, 20, BALANCED_SPOT_PROFILE), 500)
        self.assertEqual(capped_entry_budget(10000, 3000, 7000, 20, BALANCED_SPOT_PROFILE), 0)

    def test_budget_reserves_cash_for_fees(self):
        self.assertEqual(capped_entry_budget(10000, 100, 0, 20, BALANCED_SPOT_PROFILE), 95)

    def test_budget_invalid_input(self):
        for equity in (0, -1, math.nan, math.inf):
            self.assertEqual(capped_entry_budget(equity, 100, 0, 20, BALANCED_SPOT_PROFILE), 0)

    def test_retest_uses_engine_proof_not_analyst_score(self):
        self.assertEqual(candidate_entry_flags({"potential_score": 10}, True)[0], "WAITING_PULLBACK")
        self.assertEqual(candidate_entry_flags({"is_whale_confirmed": True}, True)[0], "RETEST_CONFIRMED")
        self.assertEqual(candidate_entry_flags({"is_ready": True}, True)[0], "RETEST_CONFIRMED")

    def test_first_pump_proof_is_preserved(self):
        result = candidate_entry_flags({"evidence_groups": {"TechnicalStructureEvidence": {"first_pump_blocked": True}}}, True)
        self.assertTrue(result[1])


class CircuitBreakerTests(OfflineTest):
    def setUp(self):
        super().setUp()
        self.client = FakeClient()
        self.cfg = copy.deepcopy(BALANCED_SPOT_PROFILE)
        self.db = types.ModuleType("db")
        self.db.get_supabase = lambda: self.client
        self.db.get_strategy_config = lambda **_: self.cfg
        self.db.get_system_setting = lambda key, default=None: "PAPER_TRADING" if key == "execution_mode" else default
        p = patch.dict(sys.modules, {"db": self.db})
        p.start()
        self.addCleanup(p.stop)

    def trade(self, direction="BUY", pnl=None, tenant="tenant-a", paper=True, status=None, when=None):
        details = {"tenant_id": tenant}
        if pnl is not None:
            details["realized_pnl_usd"] = pnl
        return {"id": "test", "tenant_id": tenant, "direction": direction,
                "status": status or ("EXECUTED_SIMULATED" if paper else "success"), "symbol": "BTC/USDT",
                "amount_usd": 2000, "created_at": (when or datetime.now(timezone.utc)).isoformat(),
                "execution_details": details}

    def check(self, **overrides):
        return circuit_breaker.check_tenant_circuit_breakers(
            **{"tenant_id": "tenant-a", "exchange_id": "paper", "is_simulated": True,
               "current_equity_usd": 10000, **overrides})

    def test_valid_account_passes(self):
        result = self.check()
        self.assertTrue(result["passed"])
        self.assertEqual(result["daily_loss_limit_usd"], 200)

    def test_database_missing_blocks_entries(self):
        self.db.get_supabase = lambda: None
        self.assertEqual(self.check()["circuit_breaker"], "RISK_DATA_UNAVAILABLE")

    def test_database_error_blocks_entries(self):
        self.client.fail = True
        self.assertFalse(self.check()["passed"])

    def test_missing_equity_cannot_invent_balance(self):
        self.assertFalse(self.check(current_equity_usd=None)["passed"])
        self.assertFalse(self.check(current_equity_usd=0)["passed"])

    def test_daily_reference_persists(self):
        self.check()
        self.assertEqual(self.check(current_equity_usd=50000)["daily_loss_limit_usd"], 200)

    def test_paper_buy_quota_is_enforced(self):
        self.client.trades = [self.trade() for _ in range(5)]
        self.assertEqual(self.check()["circuit_breaker"], "MAX_DAILY_TRADES_EXCEEDED")

    def test_failures_and_rejected_orders_do_not_consume_quota(self):
        self.client.trades = [self.trade(status="NO_TRADE") for _ in range(10)]
        self.assertTrue(self.check()["passed"])

    def test_paper_daily_loss_at_two_percent_blocks(self):
        self.client.trades = [self.trade("SELL", -200)]
        self.assertEqual(self.check()["circuit_breaker"], "DAILY_LOSS_LIMIT_EXCEEDED")

    def test_net_daily_pnl_offsets_wins_and_losses(self):
        self.client.trades = [self.trade("SELL", -220), self.trade("SELL", 50)]
        self.assertTrue(self.check()["passed"])

    def test_smaller_dollar_limit_is_also_respected(self):
        self.cfg["daily_max_loss_usd"] = 150
        self.client.trades = [self.trade("SELL", -160)]
        self.assertFalse(self.check()["passed"])

    def test_tenant_isolation(self):
        self.client.trades = [self.trade("SELL", -10000, tenant="other")]
        self.assertTrue(self.check()["passed"])

    def test_live_losses_do_not_affect_paper(self):
        self.client.trades = [self.trade("SELL", -10000, paper=False)]
        self.assertTrue(self.check()["passed"])

    def test_paper_losses_do_not_affect_live(self):
        self.client.trades = [self.trade("SELL", -10000)]
        self.assertTrue(self.check(is_simulated=False, exchange_id="binance")["passed"])

    def test_exchange_isolation(self):
        trade = self.trade("SELL", -1000, paper=False)
        trade["symbol"] = "BTC/TRY"
        self.client.trades = [trade]
        self.assertTrue(self.check(is_simulated=False, exchange_id="binance")["passed"])

    def test_three_losses_trigger_cooldown(self):
        self.client.trades = [self.trade("SELL", -1) for _ in range(3)]
        self.assertEqual(self.check()["circuit_breaker"], "CONSECUTIVE_LOSS_COOLDOWN_ACTIVE")

    def test_win_breaks_losing_streak(self):
        self.client.trades = [self.trade("SELL", 1)] + [self.trade("SELL", -1) for _ in range(3)]
        self.assertTrue(self.check()["passed"])

    def test_expired_cooldown_allows_new_entry(self):
        self.cfg["post_stop_cooldown_minutes"] = 1
        when = datetime.now(timezone.utc) - timedelta(minutes=2)
        self.client.trades = [self.trade("SELL", -1, when=when) for _ in range(3)]
        self.assertTrue(self.check()["passed"])

    def test_missing_pnl_blocks_rather_than_assuming_zero(self):
        self.client.trades = [self.trade("SELL")]
        self.assertEqual(self.check()["circuit_breaker"], "RISK_DATA_UNAVAILABLE")

    def test_real_zero_pnl_does_not_fall_back_to_negative_percent(self):
        trade = self.trade("SELL", 0)
        trade["execution_details"]["net_profit_pct"] = -20
        self.assertEqual(circuit_breaker.realized_pnl_usd(trade), 0)

    def test_nan_pnl_blocks(self):
        self.client.trades = [self.trade("SELL", math.nan)]
        self.assertFalse(self.check()["passed"])

    def test_open_position_cap(self):
        self.assertEqual(self.check(current_active_positions_count=3)["circuit_breaker"], "MAX_CONCURRENT_POSITIONS_FULL")

    def test_invalid_risk_config_blocks(self):
        for limit in (0, -2, math.nan, math.inf):
            self.cfg["daily_loss_limit_pct"] = limit
            self.assertFalse(self.check()["passed"])

    def test_trade_history_is_paginated(self):
        self.client.trades = [self.trade(tenant="other") for _ in range(500)] + [self.trade("SELL", -201)]
        self.assertEqual(self.check()["circuit_breaker"], "DAILY_LOSS_LIMIT_EXCEEDED")

    def test_old_day_does_not_consume_limit(self):
        self.client.trades = [self.trade("SELL", -500, when=datetime.now(timezone.utc) - timedelta(days=2))]
        self.assertTrue(self.check()["passed"])


class LiquidityTests(OfflineTest):
    def test_depth_weighted_slippage(self):
        result = assess_buy_orderbook({"bids": [[99.9, 10]], "asks": [[100, 1], [101, 10]]}, 201)
        self.assertAlmostEqual(result["spread_pct"], 0.1)
        self.assertAlmostEqual(result["slippage_pct"], 0.5)

    def test_missing_or_thin_depth_rejected(self):
        for book in ({}, {"bids": [[99, 1]], "asks": [[100, 0.1]]}):
            with self.assertRaises(ValueError):
                assess_buy_orderbook(book, 1000)

    def test_crossed_or_malformed_book_rejected(self):
        for book in ({"bids": [[101, 1]], "asks": [[100, 1]]},
                     {"bids": [[99, 1]], "asks": [[100, math.nan]]}):
            with self.assertRaises(ValueError):
                assess_buy_orderbook(book, 100)

    def test_invalid_net_rr_prices_fail_closed(self):
        for stop, target in ((102, 105), (98, 99), (0, 105), (98, math.nan)):
            result = evaluate_net_advantage_gate(100, target, stop, 1000, "BTC/USDT", BALANCED_SPOT_PROFILE)
            self.assertFalse(result[0])

    def test_profile_has_positive_net_rr_after_assumed_costs(self):
        passed, rr, _ = evaluate_net_advantage_gate(100, 104.5, 97.8, 1000, "BTC/USDT", BALANCED_SPOT_PROFILE)
        self.assertTrue(passed)
        self.assertGreaterEqual(rr, 1.5)


def load_definitions(filename, names, namespace):
    tree = ast.parse((ROOT / filename).read_text(encoding="utf-8"))
    nodes = [n for n in tree.body if isinstance(n, (ast.FunctionDef, ast.ClassDef)) and n.name in names]
    for node in nodes:
        node.decorator_list = []
    exec(compile(ast.Module(body=nodes, type_ignores=[]), filename, "exec"), namespace)
    return namespace


class SourceIntegrationTests(OfflineTest):
    def test_simulation_never_invents_95_dollar_price(self):
        from typing import Dict, Any, Optional
        ns = {"Dict": Dict, "Any": Any, "Optional": Optional, "time": time, "math": math,
              "fetch_ticker_price": lambda _: {"last_price": 0}}
        service = load_definitions("binance_execution_service.py", {"BinanceExecutionService"}, ns)["BinanceExecutionService"]
        for side in ("BUY", "SELL"):
            result = service.execute_market_order("BTC/USDT", side, 100, is_simulated=True)
            self.assertEqual(result["status"], "FAILED")
        self.assertEqual(service.execute_market_order("BTC/USDT", "SELL", 100, entry_price=100, is_simulated=True)["status"], "FAILED")

    def test_position_updates_preserve_open_time(self):
        from typing import Optional
        client = FakeClient()
        client.states["pos_tenant-a_paper"] = {"BTC": {"time": 123, "highest_price": 100, "last_peak_at": 456}}
        ns = {"Optional": Optional, "time": time, "get_supabase": lambda: client, "print": lambda *a, **k: None}
        save = load_definitions("db.py", {"save_position_to_db"}, ns)["save_position_to_db"]
        self.assertTrue(save("tenant-a", "paper", "BTC/USDT", "BTC", "USDT", 1, 100, highest_price=105, is_simulated=True))
        saved = client.states["pos_tenant-a_paper"]["BTC"]
        self.assertEqual(saved["time"], 123)
        self.assertGreater(saved["last_peak_at"], 456)

    def test_market_regime_data_outage_blocks_entry(self):
        import market_regime
        with patch.object(market_regime.requests, "get", return_value=types.SimpleNamespace(status_code=503)), patch.object(market_regime, "_last_market_regime", None):
            self.assertFalse(market_regime.check_market_regime()["is_bullish"])

    def test_api_risk_fields_accept_selected_percentage(self):
        from pydantic import BaseModel, Field, ValidationError
        from typing import Optional, Any
        ns = {"BaseModel": BaseModel, "Field": Field, "Optional": Optional, "Any": Any}
        model = load_definitions("app.py", {"StrategyConfigRequest"}, ns)["StrategyConfigRequest"]
        self.assertEqual(model(daily_loss_limit_pct=2).daily_loss_limit_pct, 2)
        for values in ({"daily_loss_limit_pct": 0}, {"max_budget_percent": 101}, {"stop_loss_pct": -1}):
            with self.assertRaises(ValidationError):
                model(**values)

    def test_partial_api_update_preserves_risk_profile(self):
        from pydantic import BaseModel, Field
        from typing import Optional, Any
        ns = {"BaseModel": BaseModel, "Field": Field, "Optional": Optional, "Any": Any}
        model = load_definitions("app.py", {"StrategyConfigRequest"}, ns)["StrategyConfigRequest"]
        db = types.ModuleType("db")
        db.get_system_setting = lambda key, default=None: default
        db.set_system_setting = Mock(return_value=True)
        db.get_strategy_config = lambda **_: copy.deepcopy(BALANCED_SPOT_PROFILE)
        db.save_strategy_config = Mock(return_value=True)
        ns["HTTPException"] = RuntimeError
        with patch.dict(sys.modules, {"db": db}):
            endpoint = load_definitions("app.py", {"save_strategy_config_endpoint"}, ns)["save_strategy_config_endpoint"]
            result = endpoint(model(trailing_callback_pct=0.8))
        self.assertEqual(result["config"]["trailing_callback_pct"], 0.8)
        self.assertEqual(result["config"]["max_budget_percent"], 20)
        self.assertEqual(result["config"]["daily_loss_limit_pct"], 2)
        self.assertEqual(result["config"]["min_ai_score"], 7.5)
        self.assertTrue(result["config"]["retest_required"])

    def test_dashboard_preserves_profile_and_independent_stop_cooldown(self):
        from v2_dashboard_html import generate_v2_dashboard_html
        html = generate_v2_dashboard_html(strategy_config=BALANCED_SPOT_PROFILE)
        self.assertIn('let currentPreset = "balanced_spot_v1"', html)
        self.assertIn('active_preset: currentPreset', html)
        self.assertNotIn("btoa('admin:", html)
        self.assertNotIn("post_stop_cooldown_minutes: parseInt", html)
        self.assertIn("Günlük net zarar eşiği %2", html)


class ExecutionGateTests(OfflineTest):
    def setUp(self):
        super().setUp()
        self.cfg = {**BALANCED_SPOT_PROFILE, "coin_dna_enabled": False}
        db = types.ModuleType("db")
        db.get_strategy_config = lambda **_: self.cfg
        db.get_system_setting = lambda key, default=None: "PAPER_TRADING" if key == "execution_mode" else default
        self.db_patch = patch.dict(sys.modules, {"db": db})
        self.db_patch.start()
        self.addCleanup(self.db_patch.stop)
        spec = importlib.util.spec_from_file_location("offline_policy", ROOT / "entry_safety_policy.py")
        self.policy = importlib.util.module_from_spec(spec)
        modules = patch.dict(sys.modules, {"offline_policy": self.policy})
        modules.start()
        self.addCleanup(modules.stop)
        spec.loader.exec_module(self.policy)

    def intent(self, **changes):
        values = dict(symbol="BTC/USDT", direction="BUY", amount_usd=1000,
                      source_engine="WHALE_HUNTING", signal_state="RETEST_CONFIRMED", first_pump_entry=False,
                      risk_decision="APPROVED", config_hash=self.policy.compute_runtime_config_hash(),
                      is_expired=False, idempotency_key="offline", idempotency_key_unused=True,
                      spread_ok=True, slippage_ok=True, stop_can_be_created=True,
                      entry_price=100.0, stop_loss_price=97.8, take_profit_price=104.5)
        return self.policy.OrderIntent(**{**values, **changes})

    def execute(self, intent, spread=0.1, slippage=0.1, max_budget=2000):
        exchange = types.ModuleType("exchange")
        exchange.fetch_entry_market_quality = lambda *a: {"spread_pct": spread, "slippage_pct": slippage, "best_ask": 100.0}
        service = types.ModuleType("binance_execution_service")
        service.BinanceExecutionService = types.SimpleNamespace(execute_market_order=Mock(return_value={"status": "EXECUTED_SIMULATED"}))
        with patch.dict(sys.modules, {"exchange": exchange, "binance_execution_service": service}), patch.object(
            circuit_breaker, "check_entry_account_risk", return_value={"passed": True, "max_entry_budget_usd": max_budget}
        ):
            result = self.policy.ExecutionGate.execute(intent, {"id": "tenant-a", "is_paper_trading": True})
        return result, service.BinanceExecutionService.execute_market_order

    def test_missing_stop_rejected(self):
        self.assertFalse(self.policy.EntrySafetyPolicy.evaluate_intent(self.intent(stop_loss_price=None))[0])

    def test_overwide_stop_rejected(self):
        self.assertFalse(self.policy.EntrySafetyPolicy.evaluate_intent(self.intent(stop_loss_price=95))[0])

    def test_expired_and_future_signals_rejected(self):
        for ts in (time.time() - 91, time.time() + 60, math.nan):
            self.assertFalse(self.policy.EntrySafetyPolicy.evaluate_intent(self.intent(created_at_ts=ts))[0])

    def test_no_retest_rejected(self):
        self.assertFalse(self.policy.EntrySafetyPolicy.evaluate_intent(self.intent(signal_state="WAITING_PULLBACK"))[0])

    def test_changed_risk_setting_invalidates_signal(self):
        intent = self.intent()
        self.cfg["daily_loss_limit_pct"] = 3
        self.assertFalse(self.policy.EntrySafetyPolicy.evaluate_intent(intent)[0])

    def test_excessive_spread_never_reaches_service(self):
        result, send = self.execute(self.intent(), spread=0.5)
        self.assertEqual(result["status"], "NO_TRADE")
        send.assert_not_called()

    def test_excessive_slippage_never_reaches_service(self):
        result, send = self.execute(self.intent(), slippage=0.5)
        self.assertEqual(result["status"], "NO_TRADE")
        send.assert_not_called()

    def test_over_budget_never_reaches_service(self):
        result, send = self.execute(self.intent(), max_budget=500)
        self.assertEqual(result["status"], "NO_TRADE")
        send.assert_not_called()

    def test_valid_paper_entry_reaches_service_as_simulated(self):
        result, send = self.execute(self.intent())
        self.assertEqual(result["status"], "EXECUTED_SIMULATED")
        self.assertTrue(send.call_args.kwargs["is_simulated"])

    def test_duplicate_key_is_rejected(self):
        self.execute(self.intent())
        result, send = self.execute(self.intent())
        self.assertEqual(result["status"], "NO_TRADE")
        send.assert_not_called()


if __name__ == "__main__":
    unittest.main()
