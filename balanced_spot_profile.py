"""Conservative starting parameters for paper evaluation, not a return forecast."""

import math


BALANCED_SPOT_PROFILE = {
    "active_preset": "balanced_spot_v1",
    "execution_mode": "PAPER_TRADING",
    "signal_interval": "15m",
    "deterministic_entry_required": True,
    "require_market_preflight": True,
    "volume_spike_multiplier": 2.0,
    "min_taker_buy_pct": 60.0,
    "min_volume_usd": 50000.0,
    "min_5m_volume_usd": 50000.0,
    "min_24h_quote_volume_usd": 10000000.0,
    "max_recent_gain_24h": 15.0,
    "min_ai_score": 7.5,
    "max_daily_trades": 5,
    "max_consecutive_losses": 3,
    "max_budget_percent": 20.0,
    "max_concurrent_positions": 3,
    "max_total_exposure_pct": 60.0,
    "take_profit_pct": 4.5,
    "take_profit_percent": 4.5,
    "stop_loss_pct": 2.2,
    "stop_loss_percent": 2.2,
    "hard_stop_loss_pct": 2.2,
    "daily_loss_limit_pct": 2.0,
    "daily_max_loss_usd": None,
    "retest_required": True,
    "first_pump_candle_entry_blocked": True,
    "cooldown_minutes": 60,
    "post_stop_cooldown_minutes": 180,
    "break_even_trigger_pct": 1.2,
    "break_even_buffer_pct": 0.25,
    "time_decay_be_minutes": 30.0,
    "time_decay_gain_threshold": 1.2,
    "time_decay_callback_pct": 0.6,
    "trailing_activation_pct": 1.8,
    "trailing_callback_pct": 0.7,
    "micro_trailing_activation_pct": 1.8,
    "micro_trailing_callback_pct": 0.7,
    "true_trailing_run": False,
    "btc_min_rsi": 40.0,
    "btc_trend_filter_enabled": True,
    "btc_ema_tolerance_pct": 1.0,
    "btc_flash_dump_5m_pct": 0.5,
    "btc_flash_dump_15m_pct": 1.0,
    "require_futures_oi": False,
    "hybrid_micro_cut_enabled": False,
    "r_exit_enabled": False,
    "dca_enabled": False,
    "net_advantage_gate_enabled": True,
    "minimum_expected_net_rr": 1.5,
    "max_spread_pct": 0.15,
    "max_one_way_slippage_pct": 0.15,
    "new_buy_orders_enabled": True,
    "existing_position_protection_enabled": True,
    "live_validation_status": "NOT_TESTED",
    "coin_dna_enabled": True,
    "coin_dna_execution_authority": "SMART_BLOCK_ONLY",
}


def capped_entry_budget(equity, free_cash, exposure, tenant_pct, config):
    values = (equity, free_cash, exposure, tenant_pct)
    if not all(math.isfinite(float(v)) and float(v) >= 0 for v in values):
        return 0.0
    allocation = min(float(tenant_pct), float(config["max_budget_percent"]))
    headroom = equity * float(config.get("max_total_exposure_pct", 100.0)) / 100.0 - exposure
    return round(max(0.0, min(equity * allocation / 100.0, free_cash * 0.95, headroom)), 2)


def candidate_entry_flags(evaluation, retest_required):
    technical = (evaluation.get("evidence_groups") or {}).get("TechnicalStructureEvidence") or {}
    blocked = bool(evaluation.get("is_first_pump_blocked") or technical.get("first_pump_blocked"))
    confirmed = bool(evaluation.get("is_ready") or evaluation.get("is_whale_confirmed"))
    state = "RETEST_CONFIRMED" if confirmed or not retest_required else "WAITING_PULLBACK"
    return state, blocked


def assess_buy_orderbook(book, quote_budget):
    bids, asks = book.get("bids") or [], book.get("asks") or []
    if not bids or not asks or not math.isfinite(quote_budget) or quote_budget <= 0:
        raise ValueError("Missing order book or budget")
    bid, ask = float(bids[0][0]), float(asks[0][0])
    if not all(math.isfinite(v) and v > 0 for v in (bid, ask)) or ask < bid:
        raise ValueError("Invalid top of book")
    remaining, quantity = quote_budget, 0.0
    last_price = 0.0
    for raw_price, raw_quantity, *_ in asks:
        price, size = float(raw_price), float(raw_quantity)
        if not all(math.isfinite(v) and v > 0 for v in (price, size)) or price < last_price:
            raise ValueError("Invalid depth level")
        last_price = price
        spent = min(remaining, price * size)
        quantity += spent / price
        remaining -= spent
        if remaining <= quote_budget * 1e-10:
            break
    if remaining > quote_budget * 1e-10 or quantity <= 0:
        raise ValueError("Insufficient visible liquidity")
    return {"spread_pct": (ask - bid) / ask * 100.0,
            "slippage_pct": (quote_budget / quantity / ask - 1.0) * 100.0,
            "best_ask": ask}
