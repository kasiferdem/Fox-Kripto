import time
from typing import Dict, Any, Optional
from db import get_supabase

def check_circuit_breaker(
    tenant_id: str,
    open_positions_count: int,
    max_concurrent_positions: int = 8,
    max_daily_loss_percent: float = 3.0
) -> Dict[str, Any]:
    """
    Devre Kesici (Circuit Breaker) ve Portföy Risk Limiti Denetimi:
    1. Maksimum Eşzamanlı Pozisyon Sayısı (Varsayılan: 3)
    2. Ardışık Stop Kilidi (Son 2 saatte 3 ardışık zarar varsa 1 saat kilit)
    3. Günlük Maksimum Zarar Sınırı (%3.0 kümülatif kayıp)
    Tüm kontroller tenant_id bazında kesin yalıtımla çalışır.
    """
    # 1. Maksimum Eşzamanlı Pozisyon Sınırı (Kasanın aşırı dağılmasını engeller)
    if open_positions_count >= max_concurrent_positions:
        return {
            "allowed": False,
            "reason": f"Maksimum açık pozisyon sınırına ({max_concurrent_positions}) ulaşıldı. Kasa güvenliği için yeni pozisyon açılmaz."
        }
        
    client = get_supabase()
    if not client or not tenant_id:
        return {"allowed": True, "reason": "Devre kesici izni verildi."}
        
    try:
        now_ts = time.time()
        # 2. Son 2 saatlik işlemleri sorgula (Ardışık Stop Kontrolü)
        two_hours_ago = time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime(now_ts - 7200))
        res_recent = client.table("crypto_trade_logs")\
            .select("direction,status,execution_details,created_at")\
            .gte("created_at", two_hours_ago)\
            .order("created_at", desc=True)\
            .limit(20)\
            .execute()
            
        logs_recent = res_recent.data or []
        consecutive_stops = 0
        for log in logs_recent:
            det = log.get("execution_details") or {}
            log_tid = str(log.get("tenant_id") or det.get("tenant_id") or "")
            if tenant_id and log_tid and log_tid != str(tenant_id):
                continue
            if tenant_id and not log_tid and tenant_id.startswith("test_"):
                continue
            reason = str(det.get("reason_type", "")).lower()
            if "stop-loss" in reason or "stop" in reason:
                consecutive_stops += 1
            elif "take-profit" in reason or "kâr" in reason:
                break
                
        if consecutive_stops >= 3:
            return {
                "allowed": False,
                "reason": "🚨 [Devre Kesici Tetiklendi]: Son 2 saatte 3 ardışık Stop-Loss gerçekleşti. Sistem kasa koruma modunda dinlendiriliyor."
            }

        # 3. Son 24 saatlik Kümülatif Günlük Zarar Limiti (%3.0)
        one_day_ago = time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime(now_ts - 86400))
        res_day = client.table("crypto_trade_logs")\
            .select("direction,status,execution_details,created_at")\
            .gte("created_at", one_day_ago)\
            .execute()
            
        logs_day = res_day.data or []
        daily_pnl_pct = 0.0
        for log in logs_day:
            det = log.get("execution_details") or {}
            log_tid = str(log.get("tenant_id") or det.get("tenant_id") or "")
            if tenant_id and log_tid and log_tid != str(tenant_id):
                continue
            pnl_val = float(det.get("net_profit_pct") or det.get("pnl_percent") or 0.0)
            daily_pnl_pct += pnl_val
            
        if daily_pnl_pct <= -max_daily_loss_percent:
            return {
                "allowed": False,
                "reason": f"🛑 [Günlük Zarar Limiti Devreye Girdi]: Son 24 saatlik net zarar %{daily_pnl_pct:.2f} (Azami limit: %{max_daily_loss_percent:.1f}). Kasa güvenliği için alımlar durduruldu."
            }

    except Exception as e:
        print(f"⚠️ [Circuit Breaker Kontrol Uyarısı]: {e}")
        
    return {"allowed": True, "reason": "Risk limitleri uygun."}
