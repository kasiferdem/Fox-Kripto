"""
Fox-Kripto: Merkezi Güvenlik Politikası ve İnfaz Kapısı (EntrySafetyPolicy & ExecutionGate)
Telif Hakkı (c) 2026 Fox-Kripto Quant Ekibi.

Tüm motorlar (Whale, Scalping, AI, Fallback) doğrudan borsaya emir gönderemez.
Yalnızca OrderIntent nesnesi üretir. Bu niyetler merkezi EntrySafetyPolicy'den ve
ExecutionGate'den geçmek zorundadır.
"""

import time
import hashlib
import json
from dataclasses import dataclass, field, asdict
from typing import Dict, Any, Optional, List, Tuple
from db import get_system_setting, get_strategy_config

@dataclass
class OrderIntent:
    symbol: str
    direction: str  # "BUY" / "SELL"
    amount_usd: float
    source_engine: str  # "WHALE_HUNTING" / "SCALPING"
    signal_state: str  # "RETEST_CONFIRMED", "WAITING_PULLBACK", "EXPIRED", vb.
    first_pump_entry: bool
    risk_decision: str  # "APPROVED" / "REJECTED"
    config_hash: str
    is_expired: bool
    idempotency_key: str
    idempotency_key_unused: bool
    spread_ok: bool
    slippage_ok: bool
    stop_can_be_created: bool
    entry_price: float
    stop_loss_price: Optional[float] = None
    take_profit_price: Optional[float] = None
    created_at_ts: float = field(default_factory=time.time)
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


_processed_idempotency_keys = set()

def compute_runtime_config_hash() -> str:
    """Veritabanındaki aktif strateji ve sistem ayarlarının değişmez hash imzasını üretir."""
    strat_cfg = get_strategy_config(use_cache=False) or {}
    payload = {
        "active_preset": strat_cfg.get("active_preset"),
        "tp": strat_cfg.get("take_profit_pct"),
        "sl": strat_cfg.get("stop_loss_pct"),
        "max_gain": strat_cfg.get("max_recent_gain_24h"),
        "vol_mult": strat_cfg.get("volume_spike_multiplier"),
        "retest_req": strat_cfg.get("retest_required", True),
        "first_pump_blocked": strat_cfg.get("first_pump_candle_entry_blocked", True)
    }
    raw = json.dumps(payload, sort_keys=True)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]


class EntrySafetyPolicy:
    """
    10 Çelik Zırh Kuralını Merkezi Olarak Denetleyen Güvenlik Sınıfı.
    Tek bir kural dahi sağlanamazsa NO_TRADE fırlatır.
    """
    @staticmethod
    def evaluate_intent(intent: OrderIntent) -> Tuple[bool, str, List[str]]:
        reasons = []
        
        # 1. Kaynak Motor Doğrulaması
        if intent.source_engine not in ["SCALPING", "WHALE_HUNTING"]:
            reasons.append(f"Geçersiz kaynak motor: {intent.source_engine}")

        # 2. Retest Teyidi Doğrulaması
        if intent.direction.upper() == "BUY" and intent.signal_state != "RETEST_CONFIRMED":
            reasons.append(f"Sinyal durumu RETEST_CONFIRMED değil ({intent.signal_state})")

        # 3. Canlı / İlk Pump Mumu Engeli
        if intent.direction.upper() == "BUY" and intent.first_pump_entry is not False:
            reasons.append("Canlı ilk pump mumundan alım engeli aktif (first_pump_entry=True)")

        # 4. Risk Kararı
        if intent.risk_decision != "APPROVED":
            reasons.append(f"Risk denetimi onay vermedi (risk_decision={intent.risk_decision})")

        # 5. Konfigürasyon Hash Uyum Kontrolü (Drift Koruması)
        runtime_hash = compute_runtime_config_hash()
        if intent.config_hash != runtime_hash:
            reasons.append(f"Konfigürasyon uyuşmazlığı (Intent: {intent.config_hash} != Runtime: {runtime_hash})")

        # 6. Zaman Aşımı Kontrolü (<90s)
        now_ts = time.time()
        age = now_ts - intent.created_at_ts
        if intent.is_expired or age > 90.0:
            reasons.append(f"Sinyal zaman aşımına uğradı (Yaş: {age:.1f}s > 90s)")

        # 7. Idempotency (Mükerrer Emir) Kontrolü
        global _processed_idempotency_keys
        if not intent.idempotency_key_unused or intent.idempotency_key in _processed_idempotency_keys:
            reasons.append(f"Mükerrer emir anahtarı tespit edildi ({intent.idempotency_key})")

        # 8. Tahta Spread Kontrolü
        if not intent.spread_ok:
            reasons.append("Tahta spread oranı izin verilen tavanı aşıyor")

        # 9. Slippage Kontrolü
        if not intent.slippage_ok:
            reasons.append("Tahmini slippage izin verilen tavanı aşıyor")

        # 10. Koruyucu Stop Doğrulaması
        if intent.direction.upper() == "BUY" and not intent.stop_can_be_created:
            reasons.append("Borsaya iletilebilecek geçerli bir koruyucu stop-loss fiyatı oluşturulamadı")

        # Karar:
        if len(reasons) > 0:
            return False, "NO_TRADE", reasons
        return True, "APPROVED_FOR_EXECUTION", []


class ExecutionGate:
    """
    Binance / Binance TR Borsa Emirlerini İnfaz Eden Yegane Yetkili Kapı.
    EntrySafetyPolicy onaylamadan hiçbir borsa çağrısı yapmaz.
    """
    @staticmethod
    def execute(intent: OrderIntent, tenant_config: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        # 1. Merkezi Güvenlik Politikası Denetimi
        passed, status, violations = EntrySafetyPolicy.evaluate_intent(intent)
        if not passed:
            print(f"🛑 [ExecutionGate REDDİ - NO_TRADE]: {intent.symbol} -> {', '.join(violations)}")
            return {
                "status": "NO_TRADE",
                "symbol": intent.symbol,
                "reason": "SAFETY_POLICY_VIOLATION",
                "violations": violations,
                "order_id": None
            }

        # 2. Idempotency Kilitle
        global _processed_idempotency_keys
        _processed_idempotency_keys.add(intent.idempotency_key)

        # 4. Fiyat Korumalı Limit İnfaz
        from exchange import execute_spot_trade
        exec_mode = str(get_system_setting("execution_mode", "PAPER_TRADING")).upper()
        new_buys = bool(get_system_setting("new_buy_orders_enabled", False))

        if intent.direction.upper() == "BUY" and not new_buys:
            return {
                "status": "NO_TRADE",
                "symbol": intent.symbol,
                "reason": "NEW_BUYS_DISABLED_IN_SAFE_MODE",
                "order_id": None
            }

        # 4. Fiyat Korumalı Limit IOC ile İnfaz
        result = execute_spot_trade(
            symbol=intent.symbol,
            side=intent.direction,
            amount_usd=intent.amount_usd,
            stop_loss_price=intent.stop_loss_price,
            tenant_config=tenant_config
        )
        return result
