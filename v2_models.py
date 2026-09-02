"""
Fox-Kripto V2.3: Veri Modelleri, Sürümler ve Strateji Şemaları
Telif Hakkı (c) 2026 Fox-Kripto Quant Ekibi.

V2.3 Şartnamesi Bölüm 2, 3, 4, 8 ve 17 ile tam uyumlu veri modelleri ve sürüm tanımları.
"""

from enum import Enum
from typing import Dict, Any, List, Optional
from pydantic import BaseModel, Field

# =====================================================================
# 1. SİSTEM VE MOTOR SÜRÜMLERİ (Section 2.1)
# =====================================================================
UI_VERSION = "2.3.0"
APPLICATION_VERSION = "2.3.0"
SIGNAL_ENGINE_VERSION = "2.3.0"
STRATEGY_PROFILE_VERSION = "2.3.0"
RISK_POLICY_VERSION = "2.3.0"
EXECUTION_ENGINE_VERSION = "2.3.0"
POSITION_MANAGEMENT_VERSION = "2.3.0"
AI_PROMPT_VERSION = "2.3.0"

# =====================================================================
# 2. ENUM VE TİP TANIMLARI (Section 2.2, 3.2, 4.2)
# =====================================================================
class ProfileStatus(str, Enum):
    DRAFT = "DRAFT"
    ACTIVE = "ACTIVE"
    ARCHIVED = "ARCHIVED"

class ExecutionMode(str, Enum):
    SIGNAL_ONLY = "SIGNAL_ONLY"
    PAPER_TRADING = "PAPER_TRADING"
    SHADOW_TRADING = "SHADOW_TRADING"
    APPROVAL_REQUIRED = "APPROVAL_REQUIRED"
    LIVE_CANARY = "LIVE_CANARY"
    LIVE_TRADING = "LIVE_TRADING"

class LiveValidationStatus(str, Enum):
    NOT_TESTED = "NOT_TESTED"
    TESTING = "TESTING"
    FAILED = "FAILED"
    PASSED = "PASSED"
    REVOKED = "REVOKED"

class MarketRegime(str, Enum):
    TREND_UP = "TREND_UP"
    TREND_DOWN = "TREND_DOWN"
    RANGE = "RANGE"
    HIGH_VOLATILITY = "HIGH_VOLATILITY"
    MARKET_STRESS = "MARKET_STRESS"
    DATA_UNCERTAIN = "DATA_UNCERTAIN"

class DataQualityStatus(str, Enum):
    PASS = "PASS"
    GAP = "GAP"
    STALE = "STALE"
    INVALID = "INVALID"
    UNAVAILABLE = "UNAVAILABLE"

class SignalStatus(str, Enum):
    IDLE = "IDLE"
    WATCH = "WATCH"
    CONFIRMING = "CONFIRMING"
    WAITING_RETEST = "WAITING_RETEST"
    READY = "READY"
    RISK_CHECKED = "RISK_CHECKED"
    APPROVAL_PENDING = "APPROVAL_PENDING"
    ORDER_PENDING = "ORDER_PENDING"
    PROTECTED_OPEN = "PROTECTED_OPEN"
    CLOSED = "CLOSED"
    REJECTED = "REJECTED"

# =====================================================================
# 3. V2.3 BAŞLANGIÇ ARAŞTIRMA VE PAPER PROFİLLERİ (Section 6.8 & 7.10)
# =====================================================================
V2_SCALPING_RESEARCH_PRESET = {
    "name": "SCALPING_CONSERVATIVE_PAPER_V1",
    "version": STRATEGY_PROFILE_VERSION,
    "profile_status": ProfileStatus.ACTIVE.value,
    "execution_mode": ExecutionMode.PAPER_TRADING.value,
    "live_validation_status": LiveValidationStatus.NOT_TESTED.value,
    "timeframes": ["1m", "3m", "5m"],
    "max_concurrent_positions": 1,
    "max_daily_trades": 2,
    "max_trades_per_symbol_per_day": 1,
    "risk_per_trade_pct": 0.25,
    "max_total_exposure_pct": 25.0,
    "daily_loss_limit_pct": 0.75,
    "max_consecutive_losses": 2,
    "post_trade_cooldown_minutes": 30,
    "post_stop_cooldown_minutes": 90,
    "min_24h_quote_volume_usd": 5000000.0,
    "min_5m_volume_usd": 100000.0,
    "volume_multiplier": 2.4,
    "max_spread_pct": 0.15,
    "max_one_way_slippage_pct": 0.15,
    "minimum_net_rr": 1.5,
    "first_pump_candle_entry_blocked": True,
    "retest_required": True,
    "max_signal_age_seconds": 90,
    "max_entry_chase_pct": 0.4,
    "hard_stop_loss_pct": 1.0,
    "take_profit_pct": 2.4,
    "breakeven_activation_pct": 1.0,
    "trailing_activation_pct": 1.3,
    "trailing_distance_pct": 0.5,
    "trailing_callback_pct": 0.5,
    "max_holding_minutes": 45
}

V2_WHALE_RESEARCH_PRESET = {
    "name": "WHALE_CONSERVATIVE_PAPER_V1",
    "version": STRATEGY_PROFILE_VERSION,
    "profile_status": ProfileStatus.ACTIVE.value,
    "execution_mode": ExecutionMode.PAPER_TRADING.value,
    "live_validation_status": LiveValidationStatus.NOT_TESTED.value,
    "timeframes": ["1m", "3m", "5m", "15m"],
    "max_concurrent_positions": 1,
    "max_daily_trades": 2,
    "max_trades_per_symbol_per_day": 1,
    "risk_per_trade_pct": 0.25,
    "max_total_exposure_pct": 25.0,
    "daily_loss_limit_pct": 0.75,
    "max_consecutive_losses": 2,
    "post_trade_cooldown_minutes": 30,
    "post_stop_cooldown_minutes": 90,
    "min_24h_quote_volume_usd": 5000000.0,
    "min_5m_volume_usd": 100000.0,
    "volume_multiplier": 2.4,
    "max_spread_pct": 0.15,
    "max_one_way_slippage_pct": 0.15,
    "minimum_net_rr": 1.5,
    "first_pump_candle_entry_blocked": True,
    "retest_required": True,
    "max_signal_age_seconds": 90,
    "max_entry_chase_pct": 0.4,
    "hard_stop_loss_pct": 1.0,
    "take_profit_pct": 2.4,
    "breakeven_activation_pct": 1.0,
    "trailing_activation_pct": 1.3,
    "trailing_distance_pct": 0.5,
    "trailing_callback_pct": 0.5,
    "max_holding_minutes": 180
}

# =====================================================================
# 4. ENTRY STATE MACHINE VE RETEST MODELLERİ (Bölüm 4, 5, 7, 8, 9)
# =====================================================================
class EntryStateMachineState(str, Enum):
    IDLE = "IDLE"
    WATCH = "WATCH"
    IMPULSE_DETECTED = "IMPULSE_DETECTED"
    WAITING_PULLBACK = "WAITING_PULLBACK"
    RETEST_TOUCHED = "RETEST_TOUCHED"
    RETEST_CONFIRMING = "RETEST_CONFIRMED"
    RETEST_CONFIRMED = "RETEST_CONFIRMED"
    ABSORPTION_CONFIRMED = "ABSORPTION_CONFIRMED"
    RISK_CHECKED = "RISK_CHECKED"
    ORDER_PENDING = "ORDER_PENDING"
    POSITION_OPEN = "POSITION_OPEN"
    PROTECTED_OPEN = "PROTECTED_OPEN"
    UNPROTECTED_POSITION = "UNPROTECTED_POSITION"
    CLOSED = "CLOSED"
    CANCELLED = "CANCELLED"
    EXPIRED = "EXPIRED"

class LiveCandleMetrics(BaseModel):
    signal_reference_price: float
    current_price: float
    current_candle_open: float
    current_candle_high: float
    current_candle_low: float
    current_candle_change_pct: float
    price_change_since_signal_pct: float
    breakout_level: float
    distance_from_breakout_pct: float
    vwap: float
    distance_from_vwap_pct: float
    atr: float
    spread_pct: float
    estimated_entry_slippage_pct: float
    signal_age_seconds: float
    maximum_entry_chase_pct: float = 0.40

class RetestZone(BaseModel):
    retest_center: float
    retest_tolerance: float
    retest_zone_low: float
    retest_zone_high: float
    breakout_level: float
    vwap: float
    atr: float

class RetestConfirmationReport(BaseModel):
    state: EntryStateMachineState
    is_confirmed: bool = False
    is_absorption: bool = False
    dwell_time_seconds: float = 0.0
    no_lower_low: bool = False
    sell_volume_decay: bool = False
    taker_buy_rebound: bool = False
    spread_valid: bool = False
    slippage_valid: bool = False
    data_freshness_valid: bool = False
    rejection_reason: Optional[str] = None
    note: str = ""

# =====================================================================
# 5. EFFECTIVE STRATEGY CONFIGURATION MODELİ (Bölüm 2 & 17)
# =====================================================================
class EffectiveStrategySnapshot(BaseModel):
    tenant_id: str
    symbol: str
    signal_id: Optional[str] = None
    profile_id: str = "WHALE_HUNTING_V23"
    profile_version: str = STRATEGY_PROFILE_VERSION
    application_version: str = APPLICATION_VERSION
    strategy_engine_version: str = SIGNAL_ENGINE_VERSION
    risk_policy_version: str = RISK_POLICY_VERSION
    execution_mode: str = ExecutionMode.PAPER_TRADING.value
    live_validation_status: str = LiveValidationStatus.NOT_TESTED.value
    max_budget_percent: float = 30.0
    risk_per_trade_pct: float = 0.25
    take_profit_pct: float = 3.2
    stop_loss_pct: float = 1.2
    trailing_callback_pct: float = 0.6
    min_volume_usd: float = 50000.0
    min_24h_quote_volume_usd: float = 1000000.0
    max_recent_gain_24h: float = 3.5
    volume_multiplier: float = 2.2
    retest_required: bool = True
    first_pump_candle_entry_blocked: bool = True
    maximum_entry_chase_pct: float = 0.40
    order_type: str = "MARKETABLE_LIMIT_IOC"
    maximum_fill_deviation_pct: float = 0.15
    order_timeout_seconds: int = 3
    partial_fill_policy: str = "ACCEPT_FILLED_AND_CANCEL_REMAINDER"
    created_at_timestamp: int = Field(default_factory=lambda: int(time.time()))
