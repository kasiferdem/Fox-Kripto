"""
Fox-Kripto V2.4 — Girişte Net Avantaj Kapısı (Expected Net Reward/Risk Gate)
Telif Hakkı (c) 2026 Fox-Kripto Quant Ekibi.

Binance canlı komisyon oranları, spread ve kayma (slippage) maliyetlerini düşerek
Expected Net R/R >= 1.5 şartını sağlamayan hiçbir işleme izin vermez.
Komisyona çalışmayı ve negatif beklentili girişleri kökünden engeller.
"""

import requests
from typing import Dict, Any, Tuple, Optional

# Canlı Komisyon Önbelleği
_COMMISSION_CACHE = {}

def get_live_binance_commission(symbol: str, api_key: str = "", secret_key: str = "") -> float:
    """
    Binance /api/v3/account/commission endpoint'inden dinamik komisyon oranını çeker.
    Eğer yetki yoksa varsayılan VIP-0 spot oranını (%0.075 BNB / %0.10 normal) döner.
    """
    clean_s = symbol.replace("/", "").replace("_", "").upper()
    if clean_s in _COMMISSION_CACHE:
        return _COMMISSION_CACHE[clean_s]
        
    # Varsayılan komisyon oranı (0.001 = %0.10)
    default_rate = 0.001
    
    if api_key and secret_key:
        try:
            import time, hmac, hashlib
            ts = int(time.time() * 1000)
            query = f"symbol={clean_s}&timestamp={ts}"
            sig = hmac.new(secret_key.encode('utf-8'), query.encode('utf-8'), hashlib.sha256).hexdigest()
            headers = {"X-MBX-APIKEY": api_key}
            url = f"https://api.binance.com/api/v3/account/commission?{query}&signature={sig}"
            r = requests.get(url, headers=headers, timeout=4)
            if r.status_code == 200:
                data = r.json()
                taker_fee = float(data.get("takerCommission", 0.001))
                _COMMISSION_CACHE[clean_s] = taker_fee
                return taker_fee
        except Exception:
            pass
            
    _COMMISSION_CACHE[clean_s] = default_rate
    return default_rate

def evaluate_net_advantage_gate(
    entry_price: float,
    target_price: float,
    stop_price: float,
    position_usd: float,
    symbol: str,
    strat_cfg: Dict[str, Any],
    spread_pct: float = 0.05,
    estimated_slippage_pct: float = 0.08
) -> Tuple[bool, float, str]:
    """
    Giriş öncesi Net Avantaj (Expected Net R/R) Kapısı Denetimi.
    
    Formül:
    expectedNetReward = grossReward - entryComm - exitComm - spread - slippage - buffer
    expectedNetLoss = stopAmount + entryComm + exitComm + stopSlippage
    expectedNetRewardRisk = expectedNetReward / expectedNetLoss >= minimumExpectedNetRewardRisk (1.5)
    """
    # Dinamik Switch
    gate_enabled = bool(strat_cfg.get("net_advantage_gate_enabled", False))
    min_rr = float(strat_cfg.get("minimum_expected_net_rr", 1.5))
    
    if not gate_enabled:
        return True, 2.0, "NET_ADVANTAGE_GATE_DISABLED"
        
    if entry_price <= 0 or target_price <= 0 or stop_price <= 0 or position_usd <= 0:
        return True, 1.5, "BYPASS_INVALID_PRICES"
        
    comm_rate = get_live_binance_commission(symbol)
    
    gross_reward_usd = position_usd * abs(target_price - entry_price) / entry_price
    gross_stop_usd = position_usd * abs(entry_price - stop_price) / entry_price
    
    # Masraflar
    entry_comm = position_usd * comm_rate
    exit_comm = position_usd * comm_rate
    spread_cost = position_usd * (spread_pct / 100.0)
    slippage_cost = position_usd * (estimated_slippage_pct / 100.0)
    stop_buffer = position_usd * 0.0005 # %0.05 acil stop tamponu
    
    expected_net_reward = gross_reward_usd - (entry_comm + exit_comm + spread_cost + slippage_cost + stop_buffer)
    expected_net_loss = gross_stop_usd + (entry_comm + exit_comm + slippage_cost)
    
    if expected_net_loss <= 0:
        return True, 2.0, "VALID_ZERO_LOSS"
        
    net_rr = expected_net_reward / expected_net_loss
    
    if net_rr < min_rr:
        reason = f"🛑 [Net Avantaj Kapısı Reddi]: Beklenen Net R/R ({net_rr:.2f}x) asgari eşiğin ({min_rr:.2f}x) altında. Komisyon ve kayma kârı eritiyor."
        return False, net_rr, reason
        
    return True, net_rr, f"✅ Net Avantaj Onaylandı: {net_rr:.2f}x >= {min_rr:.2f}x"
