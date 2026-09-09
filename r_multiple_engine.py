"""
Fox-Kripto V2.4 — R-Tabanlı ve ATR-Tabanlı Dinamik Çıkış Motoru (Politika C & D)
Telif Hakkı (c) 2026 Fox-Kripto Quant Ekibi.

Sabit ve ezbere yüzdeler yerine 1R (Initial Risk USD) ve ATR oynaklığıyla
kademeli kâr alma, komisyon korumalı başabaş ve trailing infazı sağlar.
"""

from typing import Dict, Any, Tuple
from exit_state_machine import ExitReason

def calculate_initial_risk(
    entry_price: float,
    stop_price: float,
    quantity: float,
    commission_rate: float = 0.001
) -> float:
    """
    1R = Initial Risk USD: Pozisyon açılırken üstlenilen net risk miktarı.
    """
    if entry_price <= 0 or stop_price <= 0 or quantity <= 0:
        return 1.0
    price_diff = abs(entry_price - stop_price)
    notional = entry_price * quantity
    estimated_exit_costs = notional * (commission_rate * 2) # Giriş + Çıkış komisyonu
    initial_risk_usd = (price_diff * quantity) + estimated_exit_costs
    return max(0.10, initial_risk_usd)

def evaluate_r_exit_policy(
    curr_price: float,
    entry_price: float,
    highest_price: float,
    quantity: float,
    stop_price: float,
    stage: str,
    strat_cfg: Dict[str, Any],
    atr_value: float = 0.0
) -> Tuple[bool, float, ExitReason, str, str]:
    """
    Politika C (R-Tabanlı Kademeli) ve Politika D (ATR Dinamik) Çıkış Değerlendirmesi.
    
    Dönüş:
    (should_exit, sell_fraction, exit_reason, stage_after, description)
    """
    if entry_price <= 0 or curr_price <= 0 or quantity <= 0:
        return False, 0.0, ExitReason.RECONCILIATION_EXIT, stage, ""
        
    initial_risk_usd = calculate_initial_risk(entry_price, stop_price, quantity)
    
    # Gerçekleşen anlık net PnL (USD)
    gross_pnl_usd = (curr_price - entry_price) * quantity
    total_costs_usd = (entry_price * quantity * 0.001) + (curr_price * quantity * 0.001) # ~%0.20 çift yön komisyon
    net_pnl_usd = gross_pnl_usd - total_costs_usd
    net_pnl_pct = ((curr_price - entry_price) / entry_price * 100.0) - 0.20
    
    # 1R Cinsinden Anlık Getiri (Net R-Multiple)
    current_r = net_pnl_usd / initial_risk_usd if initial_risk_usd > 0 else 0.0
    
    # Dinamik Parametreler (strategy_config üzerinden)
    r_enabled = bool(strat_cfg.get("r_exit_enabled", False))
    if not r_enabled:
        return False, 0.0, ExitReason.RECONCILIATION_EXIT, stage, ""
        
    first_tp_r = float(strat_cfg.get("r_first_tp_at_r", 1.0))
    first_tp_qty_pct = float(strat_cfg.get("r_first_tp_qty_pct", 40.0)) / 100.0
    trailing_r = float(strat_cfg.get("r_trailing_at_r", 1.5))
    final_target_r = float(strat_cfg.get("r_final_target_r", 2.0))
    
    # ATR Çarpanı Dinamik Mesafe (Politika D)
    if bool(strat_cfg.get("use_atr_dynamic_r", False)) and atr_value > 0 and entry_price > 0:
        atr_pct = (atr_value / entry_price) * 100.0
        # Oynaklığa göre R hedeflerini genişlet/daralt
        atr_factor = max(0.6, min(2.0, atr_pct / 1.0))
        first_tp_r *= atr_factor
        trailing_r *= atr_factor
        final_target_r *= atr_factor

    # 1. Aşama: Final TP (Hedef 2.0R Tam Kapanış)
    if current_r >= final_target_r:
        return True, 1.0, ExitReason.TAKE_PROFIT, "CLOSED", f"🎯 Final Hedef Ulaşıldı (+{current_r:.2f}R | Net: %{net_pnl_pct:.2f})"

    # 2. Aşama: Kısmi Kâr Alma (First TP at 1.0R - %40 Satış ve Kalanı Koruma)
    if stage == "INITIAL" and current_r >= first_tp_r:
        desc = f"💰 Kademeli Kâr Alma (+{current_r:.2f}R | %{first_tp_qty_pct*100:.0f} Satış | Net: %{net_pnl_pct:.2f})"
        return True, first_tp_qty_pct, ExitReason.PARTIAL_TAKE_PROFIT, "PARTIAL_CLOSED", desc

    # 3. Aşama: Kısmi Kâr Sonrası Break-Even Stop (Stop Giriş Fiyatına Taşındı)
    if stage in ["PARTIAL_CLOSED", "BREAKEVEN_ARMED"]:
        # Komisyon korumalı başabaş seviyesi
        breakeven_price = entry_price * 1.002 # komisyonu çıkaracak min seviye
        if curr_price <= breakeven_price:
            desc = f"🛡️ Komisyon Korumalı Başabaş Stopu (+{current_r:.2f}R | Fiyat: {curr_price})"
            return True, 1.0, ExitReason.BREAK_EVEN_STOP, "CLOSED", desc

    # 4. Aşama: Kalan Pozisyon İçin Trailing (Trailing at 1.5R)
    if current_r >= trailing_r:
        # Zirveden geri çekilme kontrolü (0.5R çekilirse kilitler)
        peak_pnl_usd = (highest_price - entry_price) * quantity - total_costs_usd
        peak_r = peak_pnl_usd / initial_risk_usd if initial_risk_usd > 0 else current_r
        pullback_r = peak_r - current_r
        if pullback_r >= 0.5:
            desc = f"🎯 R-Tabanlı Trailing Kâr Kilitlendi (+{current_r:.2f}R / Zirve: +{peak_r:.2f}R)"
            return True, 1.0, ExitReason.TRAILING_STOP, "CLOSED", desc

    return False, 0.0, ExitReason.RECONCILIATION_EXIT, stage, ""
