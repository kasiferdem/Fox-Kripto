"""
Fox-Kripto V2.3 — Maliyet ve Net Avantaj Motoru (Cost & Edge Engine)
Telif Hakkı (c) 2026 Fox-Kripto Quant Ekibi.

Brüt kâr yerine komisyon, spread, tahmini slippage ve stop kayması sonrası
gerçek net beklenen ödül/risk (Net R/R) oranını hesaplar.
"""

import time
from typing import Dict, Any, Optional

# Varsayılan Binance Taker / Maker Komisyon Oranları (%0.10 Spot)
DEFAULT_MAKER_FEE_PCT = 0.10
DEFAULT_TAKER_FEE_PCT = 0.10

def fetch_exchange_commission_rate(tenant_config: Optional[Dict[str, Any]] = None, symbol: str = "BTC/USDT") -> Dict[str, float]:
    """
    Binance API üzerinden ilgili kullanıcının net komisyon oranlarını sorgular veya güvenli üst sınır döner.
    """
    # Güvenli varsayılan (%0.10 Alış + %0.10 Satış)
    return {
        "maker_fee_pct": DEFAULT_MAKER_FEE_PCT,
        "taker_fee_pct": DEFAULT_TAKER_FEE_PCT,
        "fee_asset": "USDT",
        "is_bnb_discount_active": False
    }

def estimate_round_trip_cost(
    symbol: str,
    entry_price: float,
    spread_pct: float = 0.05,
    order_size_usd: float = 50.0,
    is_market_entry: bool = True,
    is_market_exit: bool = True,
    slippage_buffer_pct: float = 0.08
) -> Dict[str, float]:
    """
    Gidiş-Dönüş (Round-Trip) Toplam Maliyeti Hesabını Yapar:
    1. Giriş Komisyonu (%0.10 taker)
    2. Çıkış Komisyonu (%0.10 taker)
    3. Giriş Spread Geçiş Maliyeti (Spread / 2)
    4. Çıkış Spread Geçiş Maliyeti (Spread / 2)
    5. Beklenen Giriş Slippage (Likiditeye bağlı)
    6. Beklenen Çıkış Slippage (Likiditeye bağlı)
    7. Stop Kayma Tamponu (Stop Slippage Buffer)
    """
    entry_comm = DEFAULT_TAKER_FEE_PCT if is_market_entry else DEFAULT_MAKER_FEE_PCT
    exit_comm = DEFAULT_TAKER_FEE_PCT if is_market_exit else DEFAULT_MAKER_FEE_PCT
    
    spread_crossing = max(0.04, spread_pct) # En az 4 bps spread
    expected_entry_slippage = max(0.05, slippage_buffer_pct / 2.0)
    expected_exit_slippage = max(0.05, slippage_buffer_pct / 2.0)
    stop_slippage_buffer = 0.10 # Ani stop tetiklenmesinde ek kayma tamponu
    
    total_cost_pct = (
        entry_comm +
        exit_comm +
        spread_crossing +
        expected_entry_slippage +
        expected_exit_slippage +
        stop_slippage_buffer
    )
    
    cost_usd = (total_cost_pct / 100.0) * order_size_usd
    
    return {
        "entry_commission_pct": entry_comm,
        "exit_commission_pct": exit_comm,
        "spread_crossing_pct": round(spread_crossing, 3),
        "expected_slippage_pct": round(expected_entry_slippage + expected_exit_slippage, 3),
        "stop_slippage_buffer_pct": stop_slippage_buffer,
        "total_round_trip_cost_pct": round(total_cost_pct, 3),
        "total_cost_usd": round(cost_usd, 4)
    }

def evaluate_net_reward_risk_gate(
    gross_take_profit_pct: float,
    gross_stop_loss_pct: float,
    round_trip_cost_pct: float,
    min_net_rr_required: float = 1.50,
    max_cost_to_tp_ratio: float = 0.35
) -> Dict[str, Any]:
    """
    V2.3 Şartname Zorunlu Kapısı (Section 5):
    - expectedNetRewardPct = gross_take_profit_pct - total_round_trip_cost_pct
    - expectedNetLossPct   = gross_stop_loss_pct + total_round_trip_cost_pct
    - netRewardRiskRatio  = expectedNetRewardPct / expectedNetLossPct
    
    Koşullar:
    1. expectedNetRewardPct > 0
    2. netRewardRiskRatio >= min_net_rr_required (örn: 1.50)
    3. round_trip_cost_pct <= (gross_take_profit_pct * max_cost_to_tp_ratio)
    """
    net_reward_pct = gross_take_profit_pct - round_trip_cost_pct
    net_loss_pct = gross_stop_loss_pct + round_trip_cost_pct
    
    net_rr = (net_reward_pct / net_loss_pct) if net_loss_pct > 0 else 0.0
    cost_share = (round_trip_cost_pct / gross_take_profit_pct) if gross_take_profit_pct > 0 else 1.0
    
    passed = (
        net_reward_pct > 0 and
        net_rr >= min_net_rr_required and
        cost_share <= max_cost_to_tp_ratio
    )
    
    reasons = []
    if net_reward_pct <= 0:
        reasons.append(f"Maliyet ({round_trip_cost_pct:.2f}%) brüt kârı ({gross_take_profit_pct:.2f}%) tamamen yutuyor.")
    if net_rr < min_net_rr_required:
        reasons.append(f"Net R/R oranı ({net_rr:.2f}) minimum şartı ({min_net_rr_required:.2f}) karşılamıyor.")
    if cost_share > max_cost_to_tp_ratio:
        reasons.append(f"Maliyet payı (%{cost_share*100:.1f}) izin verilen azami payı (%{max_cost_to_tp_ratio*100:.0f}) aşıyor.")
        
    return {
        "passed": passed,
        "gross_take_profit_pct": gross_take_profit_pct,
        "gross_stop_loss_pct": gross_stop_loss_pct,
        "round_trip_cost_pct": round_trip_cost_pct,
        "net_reward_pct": round(net_reward_pct, 2),
        "net_loss_pct": round(net_loss_pct, 2),
        "net_reward_risk_ratio": round(net_rr, 2),
        "cost_to_tp_ratio": round(cost_share, 3),
        "failure_reasons": reasons
    }
