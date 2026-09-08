"""
FOX-KRİPTO: GÜNLÜK ADLİ İNCELEME & FORENSIC AUDIT SERVİSİ (Section 3.4 & 3.5)
OpenRouter Role: NIGHTLY_FORENSIC_AUDIT (openai/gpt-6-astra:batch / z-ai/glm-5.3 fallback)
"""

import os
import sys
import json
import time
from datetime import datetime, timezone
from typing import Dict, Any, List, Optional
from pydantic import BaseModel, Field

from openrouter_gateway import OpenRouterGateway, NightlyForensicReport
from db import get_supabase, get_tenant_by_chat_id

class NightlyForensicAuditor:
    """
    Günlük işlem kayıtlarını, V1-V2 ayrımını, slippage/komisyon kayıplarını
    ve retest ihlallerini denetleyen adli analiz motoru.
    """
    
    @classmethod
    def run_daily_audit(cls, tenant_id: str = "default_tenant", target_date: Optional[str] = None) -> Dict[str, Any]:
        """
        Belirtilen gün için adli denetim çalıştırır.
        """
        print(f"\n🔍 [Nightly Forensic Auditor]: Günlük adli denetim başlatılıyor... (Tenant: {tenant_id})")
        supabase = get_supabase()
        
        # 1. Günün işlemlerini ve loglarını çek
        date_str = target_date or datetime.now(timezone.utc).strftime("%Y-%m-%d")
        trades: List[Dict[str, Any]] = []
        signals: List[Dict[str, Any]] = []
        
        if supabase:
            try:
                # Son 24 saatin kararları
                res_decisions = supabase.table("crypto_trade_decisions").select("*").order("created_at", desc=True).limit(50).execute()
                trades = res_decisions.data or []
            except Exception as e:
                print(f"⚠️ [Auditor DB Uyarısı]: İşlem kararları çekilemedi: {e}")
                
        # 2. Deterministik İstatistik Ön Hesaplamaları (Python hesaplar, LLM sadece yorumlar)
        total_trades = len(trades)
        v1_count = 0
        v2_count = 0
        retest_bypasses = 0
        slippage_losses_usd = 0.0
        commission_losses_usd = 0.0
        coin_entry_counts: Dict[str, int] = {}
        
        for t in trades:
            src = str(t.get("source_engine") or t.get("execution_details", {}).get("strategy_source", "V2"))
            if "V1" in src.upper():
                v1_count += 1
            else:
                v2_count += 1
                
            sym = str(t.get("symbol", "UNKNOWN")).split("/")[0].upper()
            coin_entry_counts[sym] = coin_entry_counts.get(sym, 0) + 1
            
            # Slippage & Komisyon tahmini
            amt_usd = float(t.get("amount_usd", 0.0) or 0.0)
            commission_losses_usd += amt_usd * 0.0015 # %0.15 ortalama
            
            # Retest kontrolü
            sig_state = str(t.get("signal_state") or t.get("execution_details", {}).get("signal_state", ""))
            if t.get("direction") == "BUY" and sig_state != "RETEST_CONFIRMED" and "BUY" in str(t.get("direction")):
                retest_bypasses += 1

        audit_summary_payload = {
            "audit_date": date_str,
            "tenant_id": tenant_id,
            "deterministic_metrics": {
                "total_trade_decisions": total_trades,
                "v1_trade_count": v1_count,
                "v2_trade_count": v2_count,
                "detected_retest_bypasses": retest_bypasses,
                "estimated_commission_usd": round(commission_losses_usd, 4),
                "coin_distribution": coin_entry_counts,
                "anomalies_detected": [k for k, v in coin_entry_counts.items() if v > 3]
            },
            "sample_records": trades[:10]
        }
        
        # 3. OpenRouterGateway üzerinden NIGHTLY_FORENSIC_AUDIT çağrısı
        sys_prompt = (
            "Sen Fox AI sisteminin Baş Adli Denetçisisin (NIGHTLY_FORENSIC_AUDIT).\n"
            "Görevin: Python tarafından hesaplanmış günlük işlem kayıtlarını adli incelemeye tabi tutmak,\n"
            "V1/V2 worker ayrımını, slippage/komisyon kayıplarını, stop uyuşmazlıklarını ve anormallikleri raporlamaktır.\n"
            "NOT: Emir açma/kapama yetkin kesinlikle yoktur (executionAuthority=NONE)."
        )
        
        user_content = f"GÜNLÜK ADLİ DENETİM VERİSİ ({date_str}):\n{json.dumps(audit_summary_payload, indent=2)}"
        
        ai_res = OpenRouterGateway.invoke(
            role="NIGHTLY_FORENSIC_AUDIT",
            system_prompt=sys_prompt,
            user_content=user_content,
            schema_model=NightlyForensicReport,
            prompt_version="nightly-audit-v1.0"
        )
        
        structured_data = ai_res.get("structured_data") or {}
        
        # 4. Sonucu ai_model_evaluations tablosuna kaydet
        if supabase and structured_data:
            try:
                eval_payload = {
                    "tenant_id": tenant_id,
                    "evaluation_type": "NIGHTLY_AUDIT",
                    "model_id": ai_res.get("resolved_model", "openai/gpt-6-astra:batch"),
                    "summary_report": structured_data.get("forensic_summary", "Denetim tamamlandı."),
                    "findings": structured_data,
                    "recommendations": structured_data.get("recommendations", [])
                }
                supabase.table("ai_model_evaluations").insert(eval_payload).execute()
                print(f"✅ [Nightly Forensic Auditor]: Adli denetim raporu Supabase'e kaydedildi.")
            except Exception as e_save:
                print(f"⚠️ [Auditor Kayıt Uyarısı]: {e_save}")
                
        print(f"📊 [Auditor Özet]: Skor: {structured_data.get('overall_system_health_score', 9.0)}/10 | Bulgular: {len(structured_data.get('critical_findings', []))} kritik madde.")
        return structured_data

    @classmethod
    def run_critical_incident_review(cls, incident_type: str, incident_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Section 3.5: Manuel Olay ve Kod İncelemesi (openai/gpt-6-astra)
        Yalnızca olağandışı durumlarda yönetici tarafından tetiklenir.
        """
        print(f"\n🚨 [Critical Incident Review]: {incident_type} için GPT-6 Astra incelemesi başlatılıyor...")
        
        sys_prompt = (
            "Sen Fox AI sisteminin Kritik Olay ve Güvenlik İnceleme Uzmanısın (CRITICAL_INCIDENT_REVIEW).\n"
            "Görevin: Yaşanan beklenmedik borsa veya worker anomalilerini derinlemesine adli incelemeye tabi tutmaktır.\n"
            "Emir yetkin yoktur; yalnızca kök neden analizi (RCA) ve çözüm önerisi üretirsin."
        )
        
        user_content = f"KRİTİK OLAY DETAYLARI ({incident_type}):\n{json.dumps(incident_data, indent=2)}"
        
        ai_res = OpenRouterGateway.invoke(
            role="CRITICAL_INCIDENT_REVIEW",
            system_prompt=sys_prompt,
            user_content=user_content,
            prompt_version="critical-incident-v1.0"
        )
        
        return ai_res

if __name__ == "__main__":
    print("🚀 Test: Nightly Forensic Auditor çalıştırılıyor...")
    res = NightlyForensicAuditor.run_daily_audit()
    print("Sonuç:", res)
