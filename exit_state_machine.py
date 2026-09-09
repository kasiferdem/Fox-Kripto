"""
Fox-Kripto V2.4 — 12 Durumlu Kurumsal Çıkış Makinesi (Exit State Machine)
Telif Hakkı (c) 2026 Fox-Kripto Quant Ekibi.

Tüm pozisyon kapanışlarını kurumsal risk standartlarına uygun 12 ayrık duruma göre etiketler.
Tahmine dayalı kayıtları engeller; her çıkış gerekçelendirilir.
"""

from enum import Enum
from typing import Dict, Any, Optional

class ExitReason(str, Enum):
    HARD_STOP = "HARD_STOP"
    TRAILING_STOP = "TRAILING_STOP"
    TAKE_PROFIT = "TAKE_PROFIT"
    PARTIAL_TAKE_PROFIT = "PARTIAL_TAKE_PROFIT"
    BREAK_EVEN_STOP = "BREAK_EVEN_STOP"
    TIME_STOP = "TIME_STOP"
    SIGNAL_INVALIDATED = "SIGNAL_INVALIDATED"
    MARKET_CIRCUIT_BREAKER = "MARKET_CIRCUIT_BREAKER"
    MANUAL_EXIT = "MANUAL_EXIT"
    EMERGENCY_EXIT = "EMERGENCY_EXIT"
    RECONCILIATION_EXIT = "RECONCILIATION_EXIT"
    DUST_EXIT = "DUST_EXIT"

def classify_exit_reason(
    net_pnl_pct: float,
    is_stop_loss: bool,
    is_take_profit: bool,
    is_partial: bool = False,
    is_time_decay: bool = False,
    is_taker_reversal: bool = False,
    is_breakeven: bool = False,
    is_manual: bool = False,
    circuit_breaker_active: bool = False
) -> ExitReason:
    """
    Pozisyon kapanış verilerini analiz ederek kesin ExitReason durumunu döner.
    """
    if is_manual:
        return ExitReason.MANUAL_EXIT
    if circuit_breaker_active:
        return ExitReason.MARKET_CIRCUIT_BREAKER
    if is_time_decay:
        return ExitReason.TIME_STOP
    if is_taker_reversal:
        return ExitReason.SIGNAL_INVALIDATED
    if is_breakeven:
        return ExitReason.BREAK_EVEN_STOP
    if is_partial:
        return ExitReason.PARTIAL_TAKE_PROFIT
    if is_take_profit:
        return ExitReason.TRAILING_STOP if net_pnl_pct < 2.3 else ExitReason.TAKE_PROFIT
    if is_stop_loss:
        return ExitReason.HARD_STOP
    return ExitReason.RECONCILIATION_EXIT
