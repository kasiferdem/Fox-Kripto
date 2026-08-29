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
    "name": "SCALPING_BALANCED_RESEARCH_V1",
    "version": STRATEGY_PROFILE_VERSION,
    "profile_status": ProfileStatus.ACTIVE.value,
    "execution_mode": ExecutionMode.PAPER_TRADING.value,
    "live_validation_status": LiveValidationStatus.NOT_TESTED.value,
    "timeframes": ["1m", "3m", "5m"],
    "max_concurrent_positions": 2,
    "max_daily_trades": 2,
    "max_trades_per_symbol_per_day": 1,
    "risk_per_trade_pct": 0.25,
    "daily_loss_limit_pct": 0.75,
    "max_consecutive_losses": 2,
    "post_stop_cooldown_minutes": 90,
    "retest_required": True,
    "first_pump_candle_blocked": True,
    "max_24h_premium_pct": 3.5,
    "min_5m_volume_usd": 25000.0,
    "min_spike_multiplier": 1.4,
    "min_taker_buy_pct": 58.0,
    "max_spread_pct": 0.25,
    "minimum_net_rr": 1.25,
    "take_profit_pct": 2.4,
    "stop_loss_pct": 1.0,
    "trailing_activation_pct": 1.5,
    "trailing_callback_pct": 0.5,
    "max_holding_minutes": 45
}

V2_WHALE_RESEARCH_PRESET = {
    "name": "WHALE_BALANCED_RESEARCH_V1",
    "version": STRATEGY_PROFILE_VERSION,
    "profile_status": ProfileStatus.ACTIVE.value,
    "execution_mode": ExecutionMode.PAPER_TRADING.value,
    "live_validation_status": LiveValidationStatus.NOT_TESTED.value,
    "max_concurrent_positions": 1,
    "max_daily_trades": 1,
    "max_trades_per_symbol_per_day": 1,
    "risk_per_trade_pct": 0.25,
    "daily_loss_limit_pct": 0.75,
    "max_consecutive_losses": 2,
    "post_stop_cooldown_minutes": 120,
    "min_independent_evidence_groups": 5,
    "cross_venue_preferred": True,
    "retest_or_absorption_required": True,
    "first_pump_candle_blocked": True,
    "max_24h_premium_pct": 3.5,
    "min_24h_volume_usd": 10000000.0,
    "min_spike_multiplier": 2.0,
    "min_taker_buy_pct": 63.0,
    "max_spread_pct": 0.20,
    "minimum_net_rr": 1.50,
    "take_profit_pct": 3.2,
    "stop_loss_pct": 1.2,
    "trailing_activation_pct": 2.0,
    "trailing_callback_pct": 0.6,
    "max_holding_minutes": 120
}

# =====================================================================
# 4. EFFECTIVE STRATEGY CONFIGURATION MODELİ (Section 11.4 & 17)
# =====================================================================
class EffectiveStrategySnapshot(BaseModel):
    tenant_id: str
    symbol: str
    application_version: str = APPLICATION_VERSION
    strategy_engine_version: str = SIGNAL_ENGINE_VERSION
    profile_version: str = STRATEGY_PROFILE_VERSION
    risk_policy_version: str = RISK_POLICY_VERSION
    execution_mode: str = ExecutionMode.PAPER_TRADING.value
    live_validation_status: str = LiveValidationStatus.NOT_TESTED.value
    max_budget_percent: float = 50.0
    risk_per_trade_pct: float = 0.25
    take_profit_pct: float = 2.4
    stop_loss_pct: float = 1.0
    trailing_callback_pct: float = 0.5
    min_volume_usd: float = 25000.0
    max_recent_gain_24h: float = 3.5
    created_at_timestamp: int = Field(default_factory=lambda: int(time.time()))
