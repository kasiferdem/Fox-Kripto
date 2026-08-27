"""
Fox-Kripto V2: Veri Modelleri ve Strateji Presetleri
Hacim Scalping ve Gerçek Balina Avı Motoru Tanımları
"""
from enum import Enum
from typing import Dict, Any, List, Optional
from pydantic import BaseModel

class StrategyMode(str, Enum):
    VOLUME_SCALPING = "VOLUME_SCALPING"
    WHALE_HUNTING = "WHALE_HUNTING"

class RiskLevel(str, Enum):
    AGGRESSIVE = "AGGRESSIVE"
    BALANCED = "BALANCED"
    DEFENSIVE = "DEFENSIVE"
    CUSTOM = "CUSTOM"

class ExecutionMode(str, Enum):
    SIGNAL_ONLY = "SIGNAL_ONLY"
    APPROVAL_REQUIRED = "APPROVAL_REQUIRED"
    PAPER_TRADING = "PAPER_TRADING"
    LIVE_TRADING = "LIVE_TRADING"

class StrategySubscription(str, Enum):
    SCALPING = "SCALPING"
    WHALE_HUNTING = "WHALE_HUNTING"
    BOTH = "BOTH"
    NONE = "NONE"

class SignalStatus(str, Enum):
    REJECTED = "REJECTED"
    WATCHING = "WATCHING"
    WAITING_CONFIRMATION = "WAITING_CONFIRMATION"
    WAITING_RETEST = "WAITING_RETEST"
    READY = "READY"
    APPROVAL_PENDING = "APPROVAL_PENDING"
    ORDER_SENT = "ORDER_SENT"
    FILLED = "FILLED"
    CANCELLED = "CANCELLED"
    RISK_BLOCKED = "RISK_BLOCKED"

# -------------------------------------------------------------
# V2 BAŞLANGIÇ PRESETLERİ (ŞARTNAME TABLOLARINA BİREBİR UYGUN)
# -------------------------------------------------------------
V2_SCALPING_PRESETS = {
    "AGGRESSIVE": {
        "name": "⚡ Scalping · Agresif (Hızlı İvme)",
        "volume_multiplier": 1.3,
        "min_5m_volume_usd": 25000.0,
        "max_24h_premium_pct": 15.0,
        "min_strategy_score": 6.5,
        "min_taker_buy_pct": 58.0,
        "max_spread_pct": 0.60,
        "max_slippage_pct": 0.75,
        "max_daily_trades": 5,
        "risk_per_trade_pct": 0.50,
        "max_budget_percent": 25.0,
        "trailing_callback_pct": 0.6,
        "take_profit_pct": 2.5,
        "stop_loss_pct": 1.5,
        "description": "1m-5m grafiklerinde dipteki taze taker alış patlamalarını yakalayan, hızlı kâr alıp çıkan çevik motor."
    },
    "BALANCED": {
        "name": "⚡ Scalping · Dengeli (Önerilen)",
        "volume_multiplier": 1.6,
        "min_5m_volume_usd": 50000.0,
        "max_24h_premium_pct": 10.0,
        "min_strategy_score": 7.5,
        "min_taker_buy_pct": 61.0,
        "max_spread_pct": 0.40,
        "max_slippage_pct": 0.50,
        "max_daily_trades": 3,
        "risk_per_trade_pct": 0.40,
        "max_budget_percent": 25.0,
        "trailing_callback_pct": 0.6,
        "take_profit_pct": 3.0,
        "stop_loss_pct": 1.5,
        "description": "Dengeli likidite ve hacim teyidi ile çalışan, sahte iğneleri filtreleyen güvenilir scalp motoru."
    },
    "DEFENSIVE": {
        "name": "⚡ Scalping · Defansif (Yüksek Güvenlik)",
        "volume_multiplier": 2.0,
        "min_5m_volume_usd": 100000.0,
        "max_24h_premium_pct": 7.0,
        "min_strategy_score": 8.0,
        "min_taker_buy_pct": 64.0,
        "max_spread_pct": 0.25,
        "max_slippage_pct": 0.30,
        "max_daily_trades": 2,
        "risk_per_trade_pct": 0.30,
        "max_budget_percent": 20.0,
        "trailing_callback_pct": 0.8,
        "take_profit_pct": 3.5,
        "stop_loss_pct": 1.2,
        "description": "Yalnızca en yüksek hacimli ve en dar spreadli paritelerde devreye giren yüksek güvenlikli scalp motoru."
    }
}

V2_WHALE_PRESETS = {
    "AGGRESSIVE": {
        "name": "🐋 Balina Avı · Agresif (Erken Takip)",
        "volume_multiplier": 2.5,
        "min_5m_volume_usd": 100000.0,
        "volume_position_multiplier": 75.0,
        "max_24h_premium_pct": 12.0,
        "min_strategy_score": 8.0,
        "full_position_score": 8.5,
        "min_taker_buy_pct": 63.0,
        "max_spread_pct": 0.40,
        "max_slippage_pct": 0.50,
        "minimum_confirmations": 5,
        "confirmation_universe": 10,
        "max_daily_trades": 3,
        "risk_per_trade_pct": 0.50,
        "max_risk_per_trade_pct": 0.75,
        "daily_loss_limit_pct": 2.0,
        "max_budget_percent": 25.0,
        "trailing_callback_pct": 0.8,
        "take_profit_pct": 5.0,
        "stop_loss_pct": 1.8,
        "description": "Spot ve vadeli açık faiz (OI) artışı gösteren erken balina birikimlerini yakalayan kurumsal motor."
    },
    "BALANCED": {
        "name": "🐋 Balina Avı · Dengeli (Kurumsal Altın Standart)",
        "volume_multiplier": 3.0,
        "min_5m_volume_usd": 150000.0,
        "volume_position_multiplier": 85.0,
        "max_24h_premium_pct": 9.0,
        "min_strategy_score": 8.2,
        "full_position_score": 8.7,
        "min_taker_buy_pct": 64.0,
        "max_spread_pct": 0.30,
        "max_slippage_pct": 0.40,
        "minimum_confirmations": 6,
        "confirmation_universe": 10,
        "max_daily_trades": 2,
        "risk_per_trade_pct": 0.40,
        "max_risk_per_trade_pct": 0.50,
        "daily_loss_limit_pct": 1.75,
        "max_budget_percent": 25.0,
        "trailing_callback_pct": 0.8,
        "take_profit_pct": 6.0,
        "stop_loss_pct": 1.8,
        "description": "Spot + Vadeli OI + Tahta Alış Duvarı koruması (10 kriterden 6 teyit) gerektiren tam teyitli balina avcısı."
    },
    "DEFENSIVE": {
        "name": "🐋 Balina Avı · Defansif (Maksimum Teyit)",
        "volume_multiplier": 3.5,
        "min_5m_volume_usd": 250000.0,
        "volume_position_multiplier": 100.0,
        "max_24h_premium_pct": 7.0,
        "min_strategy_score": 8.5,
        "full_position_score": 9.0,
        "min_taker_buy_pct": 65.0,
        "max_spread_pct": 0.25,
        "max_slippage_pct": 0.30,
        "minimum_confirmations": 7,
        "confirmation_universe": 10,
        "max_daily_trades": 1,
        "risk_per_trade_pct": 0.25,
        "max_risk_per_trade_pct": 0.40,
        "daily_loss_limit_pct": 1.50,
        "max_budget_percent": 20.0,
        "trailing_callback_pct": 1.0,
        "take_profit_pct": 8.0,
        "stop_loss_pct": 1.5,
        "description": "Sadece piyasa lideri paritelerde 7/10 teyit sağlandığında yılda birkaç kez mükemmel trendlere giren zırhlı motor."
    }
}
