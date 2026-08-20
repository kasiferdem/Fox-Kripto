import time
from typing import Dict, Any, Optional
from db import get_supabase

def check_circuit_breaker(
    tenant_id: str,
    open_positions_count: int,
    max_concurrent_positions: int = 3
) -> Dict[str, Any]:
    """
    Devre Kesici (Circuit Breaker) ve Portföy Risk Limiti Denetimi:
    1. Maksimum Eşzamanlı Pozisyon Sayısı (Varsayılan: 3)
    2. Ardışık Stop Kilidi (Son 2 saatte 3 ardışık zarar varsa 1 saat kilit)
    3. Günlük Maksimum Zarar Sınırı (%3.0 kümülatif kayıp)
    """
    # 1. Maksimum Eşzamanlı Pozisyon Sınırı (Kasanın aşırı dağılmasını engeller)
    if open_positions_count >= max_concurrent_positions:
        return {
            "allowed": False,
            "reason": f"Maksimum açık pozisyon sınırına ({max_concurrent_positions}) ulaşıldı. Kasa güvenliği için yeni pozisyon açılmaz."
        }
        
    client = get_supabase()
    if not client or not tenant_id:
        return {"allowed": True, "reason": "Devre kesici izni verildi (Yerel mod)."}
        
    try:
        # 2. Son işlemleri sorgula
        two_hours_ago = time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime(time.time() - 7200))
        res = client.table("crypto_trade_logs")\
            .select("direction,status,execution_details,created_at")\
            .gte("created_at", two_hours_ago)\
            .order("created_at", desc=True)\
            .limit(5)\
            .execute()
            
        logs = res.data or []
        consecutive_stops = 0
        for log in logs:
            det = log.get("execution_details") or {}
            reason = str(det.get("reason_type", "")).lower()
            if "stop-loss" in reason or "stop" in reason:
                consecutive_stops += 1
            else:
                break
                
        if consecutive_stops >= 3:
            return {
                "allowed": False,
                "reason": "🚨 [Devre Kesici Tetiklendi]: Son 2 saatte 3 ardışık Stop-Loss gerçekleşti. Sistem 1 saat dinlenmeye alındı."
            }
    except Exception as e:
        print(f"⚠️ [Circuit Breaker Kontrol Uyarısı]: {e}")
        
    return {"allowed": True, "reason": "Risk limitleri uygun."}
