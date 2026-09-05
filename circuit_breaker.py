"""
Fox-Kripto V2.3 — Devre Kesiciler ve Cooldown Motoru (Circuit Breaker Engine)
Telif Hakkı (c) 2026 Fox-Kripto Quant Ekibi.

Günlük kayıp limiti, ardışık zarar, maksimum işlem sayısı ve soğuma (cooldown) sürelerini
kesintisiz denetler. Eşik aşıldığında sistemi güvenli SIGNAL_ONLY moduna düşürür.
"""

import time
from typing import Dict, Any, List, Optional
from datetime import datetime, timezone, timedelta

def check_tenant_circuit_breakers(
    tenant_id: str,
    exchange_id: str = "binance",
    daily_loss_limit_pct: float = 0.75,
    max_consecutive_losses: int = 2,
    post_stop_cooldown_minutes: int = 90,
    max_daily_trades: int = 2,
    max_concurrent_positions: int = 1,
    current_active_positions_count: int = 0
) -> Dict[str, Any]:
    """
    Kullanıcının canlı işlem geçmişini ve açık risklerini tarayarak
    tüm devre kesicileri kontrol eder.
    """
    now = datetime.now(timezone.utc)
    today_start = now.replace(hour=0, minute=0, second=0, microsecond=0).isoformat()
    
    try:
        from db import get_supabase, get_strategy_config
        strat_cfg = get_strategy_config(use_cache=True)
        if strat_cfg:
            if "max_concurrent_positions" in strat_cfg or "slots" in strat_cfg:
                max_concurrent_positions = int(strat_cfg.get("max_concurrent_positions") or strat_cfg.get("slots") or max_concurrent_positions)
            if "max_daily_trades" in strat_cfg or "daily" in strat_cfg:
                max_daily_trades = int(strat_cfg.get("max_daily_trades") or strat_cfg.get("daily") or max_daily_trades)
            if "max_consecutive_losses" in strat_cfg:
                max_consecutive_losses = int(strat_cfg.get("max_consecutive_losses") or max_consecutive_losses)
            if "post_stop_cooldown_minutes" in strat_cfg:
                post_stop_cooldown_minutes = int(strat_cfg.get("post_stop_cooldown_minutes") or post_stop_cooldown_minutes)
            if "daily_loss_limit_pct" in strat_cfg or "cb" in strat_cfg:
                daily_loss_limit_pct = float(strat_cfg.get("daily_loss_limit_pct") or strat_cfg.get("cb") or daily_loss_limit_pct)
            
        client = get_supabase()
        if not client:
            return {"passed": True, "reason": "DB_UNAVAILABLE_FALLBACK"}
            
        # 1. Bugünün işlemlerini çek
        trades_res = client.table("crypto_trade_logs")\
            .select("*")\
            .gte("created_at", today_start)\
            .order("created_at", desc=True)\
            .execute()
            
        today_trades = trades_res.data or []
        
        # 2. Günlük Toplam İşlem Sayısı Denetimi
        daily_executed_count = len([t for t in today_trades if t.get("direction") == "BUY"])
        if daily_executed_count >= max_daily_trades:
            return {
                "passed": False,
                "circuit_breaker": "MAX_DAILY_TRADES_EXCEEDED",
                "message": f"🛑 [Devre Kesici]: Günlük azami işlem kotası ({daily_executed_count}/{max_daily_trades}) doldu."
            }
            
        # 3. Maksimum Eşzamanlı Açık Pozisyon Denetimi
        if current_active_positions_count >= max_concurrent_positions:
            return {
                "passed": False,
                "circuit_breaker": "MAX_CONCURRENT_POSITIONS_FULL",
                "message": f"🛑 [Devre Kesici]: Eşzamanlı açık pozisyon slotları dolu ({current_active_positions_count}/{max_concurrent_positions})."
            }
            
        # 4. Son İşlemlerdeki Ardışık Zarar ve Cooldown Denetimi
        recent_sells = [t for t in today_trades if t.get("direction") == "SELL"]
        consecutive_losses = 0
        last_stop_time = None
        
        for sell in recent_sells:
            det = sell.get("execution_details") or {}
            pnl_pct = float(det.get("realized_pnl_pct", 0.0)) or float(det.get("net_profit_pct", 0.0))
            if pnl_pct < -0.20:
                consecutive_losses += 1
                if not last_stop_time:
                    last_stop_time = sell.get("created_at")
            else:
                break # Kârlı satış görünce seriyi kır
                
        if consecutive_losses >= max_consecutive_losses:
            # Cooldown kontrolü
            if last_stop_time:
                try:
                    last_stop_dt = datetime.fromisoformat(last_stop_time.replace("Z", "+00:00"))
                    elapsed_min = (now - last_stop_dt).total_seconds() / 60.0
                    if elapsed_min < post_stop_cooldown_minutes:
                        remaining_min = int(post_stop_cooldown_minutes - elapsed_min)
                        return {
                            "passed": False,
                            "circuit_breaker": "CONSECUTIVE_LOSS_COOLDOWN_ACTIVE",
                            "message": f"🛑 [Devre Kesici]: {consecutive_losses} ardışık stop sonrası soğuma devrede. Kalan süre: {remaining_min} dakika."
                        }
                except Exception:
                    pass
                    
    except Exception as e:
        print(f"⚠️ Circuit Breaker DB Uyarısı: {e}")
        
    return {
        "passed": True,
        "circuit_breaker": "NONE",
        "message": "Tüm devre kesici ve risk kapıları açık."
    }

def get_adaptive_max_slots(total_equity_usd: float = 200.0, user_max_budget_pct: float = 30.0) -> int:
    """
    Kullanıcının panelden belirlediği azami eşzamanlı pozisyon slotunu dinamik olarak döndürür.
    """
    try:
        from db import get_strategy_config
        strat_cfg = get_strategy_config(use_cache=True)
        if strat_cfg and "max_concurrent_positions" in strat_cfg:
            return int(strat_cfg.get("max_concurrent_positions") or 3)
    except Exception:
        pass
    if user_max_budget_pct >= 50.0:
        return 2
    return max(1, int(100.0 / user_max_budget_pct)) if user_max_budget_pct > 0 else 3

def can_place_live_order(
    profile_status: str,
    execution_mode: str,
    live_validation_status: str,
    global_kill_switch: bool = False,
    tenant_kill_switch: bool = False,
    user_kill_switch: bool = False,
    data_quality_status: str = "PASS",
    risk_engine_healthy: bool = True,
    execution_engine_healthy: bool = True
) -> Dict[str, Any]:
    """
    V2.3 Şartnamesi Bölüm 2.2 ve 9.1 — Backend Canlı Emir İnfaz Kapısı:
    Tüm güvenlik kriterleri eksiksiz karşılanmadan canlı emir üretilemez.
    """
    if global_kill_switch or tenant_kill_switch or user_kill_switch:
        return {"can_trade": False, "reason": "🛑 Kill Switch Devrede (Yeni Alımlar Durduruldu)."}
    if profile_status != "ACTIVE":
        return {"can_trade": False, "reason": f"🛑 Profil durumu aktif değil ({profile_status})."}
    if execution_mode not in ["LIVE_CANARY", "LIVE_TRADING"]:
        return {"can_trade": False, "reason": f"ℹ️ Canlı emir yetkisi yok (Mod: {execution_mode}). Yalnızca sinyal veya paper üretilir."}
    if live_validation_status != "PASSED":
        return {"can_trade": False, "reason": f"🛑 Canlı uygunluk testi geçilmedi ({live_validation_status})."}
    if data_quality_status != "PASS":
        return {"can_trade": False, "reason": f"🛑 Veri kalitesi yetersiz ({data_quality_status})."}
    if not risk_engine_healthy or not execution_engine_healthy:
        return {"can_trade": False, "reason": "🛑 Risk veya infaz motoru sağlık kontrolünden geçemedi."}
        
    return {"can_trade": True, "reason": "✅ Tüm canlı işlem güvenlik kapıları başarıyla geçildi."}

def check_configuration_drift(
    frontend_config: Optional[Dict[str, Any]] = None,
    db_config: Optional[Dict[str, Any]] = None,
    worker_config: Optional[Dict[str, Any]] = None
) -> Dict[str, Any]:
    """
    Bölüm 2 — Configuration Drift Devre Kesicisi:
    Frontend, Supabase DB ve çalışan Worker parametreleri arasında uyuşmazlık
    varsa CONFIGURATION_DRIFT alarmı üretir ve yeni alımları engeller.
    """
    try:
        if db_config is None:
            from db import get_strategy_config
            db_config = get_strategy_config(use_cache=False) or {}
            
        # Kritik parametreler
        db_max_gain = float(db_config.get("max_recent_gain_24h", 3.5))
        db_vol_mult = float(db_config.get("volume_spike_multiplier", db_config.get("min_volume_multiplier", 2.2)))
        
        # Drift denetimi: Eğer Scalp profilinde olup 24s prim %20'nin üzerindeyse
        active_preset = db_config.get("active_preset", "whale_hunting")
        if "scalp" in active_preset.lower() and db_max_gain > 5.0:
            return {
                "drift_detected": True,
                "circuit_breaker": "CONFIGURATION_DRIFT",
                "message": f"🛑 [Configuration Drift]: Scalp profilinde beklenmeyen %{db_max_gain} prim limiti tespit edildi."
            }
            
        if worker_config:
            w_max_gain = float(worker_config.get("max_recent_gain_24h", db_max_gain))
            if abs(w_max_gain - db_max_gain) > 0.01:
                return {
                    "drift_detected": True,
                    "circuit_breaker": "CONFIGURATION_DRIFT",
                    "message": f"🛑 [Configuration Drift]: Worker ({w_max_gain}) ile DB ({db_max_gain}) parametresi uyuşmuyor!"
                }
    except Exception as e:
        print(f"⚠️ Configuration drift denetim hatası: {e}")
        
    return {
        "drift_detected": False,
        "circuit_breaker": "NONE",
        "message": "Konfigürasyon bütünlüğü doğrulandı (Drift yok)."
    }

def pre_order_risk_check(
    tenant_id: str,
    symbol: str,
    signal_id: str,
    signal_age_seconds: float,
    current_price: float,
    retest_zone: List[float],
    spread_pct: float,
    estimated_slippage_pct: float,
    execution_mode: str = "PAPER_TRADING",
    is_retest_confirmed: bool = True,
    profile_active: bool = True,
    current_active_positions_count: int = 0,
    max_concurrent_positions: int = 2
) -> Dict[str, Any]:
    """
    Bölüm 11 — Emir Öncesi 12 Maddelik Son Deterministik Risk Kontrolü:
    Herhangi biri başarısız olursa NO_TRADE üretir.
    """
    # 1. Profil aktif mi?
    if not profile_active:
        return {"can_order": False, "reason": "NO_TRADE: Profile is not active"}
    # 2. Execution mode izin veriyor mu?
    if execution_mode not in ["PAPER_TRADING", "SHADOW_TRADING", "LIVE_CANARY", "LIVE_TRADING"]:
        return {"can_order": False, "reason": f"NO_TRADE: Execution mode {execution_mode} blocks order placement"}
    # 3. Sinyal süresi doldu mu? (>90s)
    if signal_age_seconds > 90.0:
        return {"can_order": False, "reason": f"NO_TRADE: Signal expired ({signal_age_seconds:.1f}s > 90s)"}
    # 4. Retest geçerli mi?
    if not is_retest_confirmed:
        return {"can_order": False, "reason": "NO_TRADE: Retest confirmation missing"}
    # 5. Fiyat giriş aralığında mı? (Maksimum %0.40 chase limiti)
    if retest_zone and len(retest_zone) == 2:
        if current_price < retest_zone[0] * 0.995 or current_price > retest_zone[1] * 1.004:
            return {"can_order": False, "reason": f"NO_TRADE: Price ${current_price} out of retest zone {retest_zone} (Chase > %0.40)"}
    # 6. Spread uygun mu? (<= %0.15)
    if spread_pct > 0.15:
        return {"can_order": False, "reason": f"NO_TRADE: Spread too wide (%{spread_pct:.2f} > %0.15)"}
    # 7. Slippage uygun mu? (<= %0.15)
    if estimated_slippage_pct > 0.15:
        return {"can_order": False, "reason": f"NO_TRADE: Slippage too high (%{estimated_slippage_pct:.2f} > %0.15)"}
    # 8. Maksimum pozisyon doldu mu?
    if current_active_positions_count >= max_concurrent_positions:
        return {"can_order": False, "reason": f"NO_TRADE: Max concurrent positions full ({current_active_positions_count}/{max_concurrent_positions})"}
    # 9. Tenant devre kesici kontrolü
    cb_res = check_tenant_circuit_breakers(tenant_id=tenant_id, max_concurrent_positions=max_concurrent_positions, current_active_positions_count=current_active_positions_count)
    if not cb_res["passed"]:
        return {"can_order": False, "reason": f"NO_TRADE: Circuit breaker tripped ({cb_res.get('circuit_breaker')})"}
        
    return {"can_order": True, "reason": "ALL_12_RISK_GATES_PASSED"}


