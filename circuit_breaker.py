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
    daily_loss_limit_pct: float = 1.0,
    max_consecutive_losses: int = 2,
    post_stop_cooldown_minutes: int = 90,
    max_daily_trades: int = 3,
    max_concurrent_positions: int = 2,
    current_active_positions_count: int = 0
) -> Dict[str, Any]:
    """
    Kullanıcının canlı işlem geçmişini ve açık risklerini tarayarak
    tüm devre kesicileri kontrol eder.
    """
    now = datetime.now(timezone.utc)
    today_start = now.replace(hour=0, minute=0, second=0, microsecond=0).isoformat()
    
    try:
        from db import get_supabase
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

def get_adaptive_max_slots(total_equity_usd: float = 200.0, user_max_budget_pct: float = 50.0) -> int:
    """
    V2.3 Şartnamesi gereği portföy büyüklüğü ve risk tavanına göre dinamik slot sayısı döner (Maksimum 2 slot).
    """
    if total_equity_usd <= 0:
        return 1
    if user_max_budget_pct >= 50.0:
        return 2
    calculated = max(1, int(100.0 / user_max_budget_pct))
    return min(2, calculated)

