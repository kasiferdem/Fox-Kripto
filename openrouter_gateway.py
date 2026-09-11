"""
Fox-Kripto V2.4 — Merkezi OpenRouter AI Gateway (Central OpenRouter AI Gateway)
Telif Hakkı (c) 2026 Fox-Kripto Quant Ekibi.

Tüm LLM çağrılarını tek bir merkezden yönetir:
- Rol tabanlı model rotası (ROUTINE_REPORTING, CRITICAL_NEWS_ANALYSIS, TECHNICAL_SECOND_OPINION, NIGHTLY_FORENSIC_AUDIT, CRITICAL_INCIDENT_REVIEW)
- Kesin Failover Zinciri (429, 5xx, timeout, geçersiz şema durumunda)
- Pydantic Yapılandırılmış Çıktı (Structured Output) Doğrulaması
- Token & Maliyet Muhasebesi (ai_call_logs & ai_usage_ledger)
- Hassas Veri Temizleme (Sanitization)
- Asla doğrudan emir (BUY/SELL) açamama kuralı (executionAuthority denetimi)
"""

import os
import sys
import time
import json
import hashlib
import requests
from typing import Dict, Any, List, Optional, Type, Tuple, Literal
from pydantic import BaseModel, Field
from datetime import datetime, timezone
from dotenv import load_dotenv

load_dotenv()

# =====================================================================
# 1. STANDART ROL VE MODEL ROTALARI TANIMI (Section 3)
# =====================================================================
ROLE_ROUTES_CONFIG: Dict[str, Dict[str, Any]] = {
    "LEAD_STRATEGIST": {
        "primary_model": "openai/gpt-6-astra",
        "fallback_models": ["openai/gpt-4o", "anthropic/claude-3.7-sonnet"],
        "execution_authority": "BLOCK_ONLY",
        "timeout_seconds": 20,
        "max_output_tokens": 1500,
        "temperature": 0.2,
        "description": "1 Numara: Baş Stratejist & Karar Motoru (GPT-6)"
    },
    "PATRON": {
        "primary_model": "openai/gpt-6-astra",
        "fallback_models": ["openai/gpt-4o", "anthropic/claude-3.7-sonnet"],
        "execution_authority": "BLOCK_ONLY",
        "timeout_seconds": 20,
        "max_output_tokens": 1500,
        "temperature": 0.2,
        "description": "5 Numara Patron: Baş Stratejist & Piyasa Rejim Yöneticisi (GPT-6 Astra)"
    },
    "CHIEF_AUDITOR": {
        "primary_model": "anthropic/claude-3.7-sonnet",
        "fallback_models": ["openai/gpt-4o", "z-ai/glm-5.3"],
        "execution_authority": "BLOCK_ONLY",
        "timeout_seconds": 20,
        "max_output_tokens": 1200,
        "temperature": 0.1,
        "description": "5 Numara Patronu Denetleyen Baş Denetçi (Claude 3.7 Sonnet) - Veto Yetkili Adli Kuant Denetçisi"
    },
    "GENEL_MUDUR": {
        "primary_model": "openai/gpt-6-astra",
        "fallback_models": ["anthropic/claude-3.7-sonnet", "google/gemini-3.8-flash"],
        "execution_authority": "NONE",
        "timeout_seconds": 15,
        "max_output_tokens": 800,
        "temperature": 0.3,
        "description": "8 Numara Genel Müdür: Kullanıcıya Profesyonel ve Düzenli İcra Brifingi Sunan Yönetici Ajan"
    },
    "ROUTINE_REPORTING": {
        "primary_model": "openai/gpt-6-astra",
        "fallback_models": ["z-ai/glm-5.3-flash", "google/gemini-3.8-flash", "openai/gpt-4o"],
        "execution_authority": "NONE",
        "timeout_seconds": 15,
        "max_output_tokens": 800,
        "temperature": 0.3,
        "description": "Telegram rutin raporları, durum özetleri, işlem bildirimleri (GPT-6)"
    },
    "CRITICAL_NEWS_ANALYSIS": {
        "primary_model": "google/gemini-3.8-flash",
        "fallback_models": ["google/gemini-3.7-flash", "z-ai/glm-5.3", "openai/gpt-4o-mini"],
        "execution_authority": "BLOCK_ONLY",
        "timeout_seconds": 12,
        "max_output_tokens": 500,
        "temperature": 0.1,
        "description": "2 Numara: Makro & Haber Duyarlılık Ajanı (Gemini 3.8 Flash)"
    },
    "TECHNICAL_SECOND_OPINION": {
        "primary_model": "z-ai/glm-5.3",
        "fallback_models": ["google/gemini-3.7-flash", "meta-llama/llama-3.3-70b-instruct"],
        "execution_authority": "NONE",
        "mode": "SHADOW_BY_DEFAULT",
        "timeout_seconds": 15,
        "max_output_tokens": 600,
        "temperature": 0.2,
        "description": "Python tarafından hesaplanmış teknik metriklerin gölge ikinci yorumu"
    },
    "NIGHTLY_FORENSIC_AUDIT": {
        "primary_model": "openai/gpt-6-astra:batch",
        "fallback_models": ["z-ai/glm-5.3", "openai/gpt-4o"],
        "execution_authority": "NONE",
        "timeout_seconds": 30,
        "max_output_tokens": 1500,
        "temperature": 0.1,
        "description": "Günlük adli inceleme, V1-V2 karşılaştırması, slippage ve sapma denetimi"
    },
    "CRITICAL_INCIDENT_REVIEW": {
        "primary_model": "openai/gpt-6-astra",
        "fallback_models": ["z-ai/glm-5.3"],
        "execution_authority": "NONE",
        "manual_trigger_only": True,
        "timeout_seconds": 45,
        "max_output_tokens": 2000,
        "temperature": 0.0,
        "description": "Kritik borsa anomalisi veya güvenlik açığı durumunda manuel inceleme"
    }
}

# =====================================================================
# 2. PYDANTIC STRUCTURED OUTPUT ŞEMALARI (Section 10)
# =====================================================================
class CriticalNewsAssessment(BaseModel):
    severity: Literal["NORMAL", "CAUTION", "HIGH_RISK", "HALT_RECOMMENDED", "DATA_INSUFFICIENT"] = Field(
        ..., description="Haberin risk şiddeti derecesi"
    )
    confidence: float = Field(default=0.8, description="0.0 ile 1.0 arası güven puanı")
    affected_symbols: List[str] = Field(default_factory=list, description="Etkilenen coin sembolleri")
    evidence: List[str] = Field(default_factory=list, description="Kararı destekleyen haber kanıtları")
    data_timestamp: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    explanation: str = Field(default="", description="Kısa Türkçe gerekçe")

class TechnicalSecondOpinion(BaseModel):
    alignment_score: float = Field(default=7.0, description="0.0 - 10.0 arası teknik formasyon uyum puanı")
    momentum_assessment: Literal["BULLISH", "NEUTRAL", "BEARISH", "EXHAUSTION_RISK"] = Field(default="NEUTRAL")
    retest_quality: Literal["EXCELLENT", "ACCEPTABLE", "POOR", "INVALID"] = Field(default="ACCEPTABLE")
    identified_risks: List[str] = Field(default_factory=list)
    summary_tr: str = Field(default="")

class RoutineReportingSummary(BaseModel):
    title: str = Field(default="")
    formatted_message: str = Field(default="")
    sentiment: Literal["BULLISH", "NEUTRAL", "BEARISH"] = Field(default="NEUTRAL")

class NightlyForensicReport(BaseModel):
    audit_date: str = Field(default_factory=lambda: datetime.now(timezone.utc).strftime("%Y-%m-%d"))
    total_trades_analyzed: int = Field(default=0)
    slippage_anomalies_detected: int = Field(default=0)
    retest_bypass_violations: int = Field(default=0)
    configuration_drift_events: int = Field(default=0)
    forensic_findings: List[str] = Field(default_factory=list)
    recommended_tuning: List[str] = Field(default_factory=list)

# =====================================================================
# 3. HASSAS VERİ TEMİZLEME (SANITIZATION) (Section 6 & 7)
# =====================================================================
SENSITIVE_PATTERNS = [
    "api_key", "secret_key", "password", "token", "exchange_api_key",
    "exchange_secret_key", "telegram_bot_token", "private_key", "bearer"
]

def sanitize_payload(payload: Any) -> Any:
    """API anahtarları, şifreler ve hassas verileri prompt veya loglara gitmeden temizler."""
    if isinstance(payload, dict):
        clean = {}
        for k, v in payload.items():
            k_lower = str(k).lower()
            if any(s in k_lower for s in SENSITIVE_PATTERNS):
                clean[k] = "[REDACTED_SENSITIVE_DATA]"
            else:
                clean[k] = sanitize_payload(v)
        return clean
    elif isinstance(payload, list):
        return [sanitize_payload(item) for item in payload]
    elif isinstance(payload, str):
        if len(payload) > 40 and not (" " in payload) and any(c.isdigit() for c in payload):
            if "nvapi-" in payload or "workos:" in payload or "sk-" in payload:
                return "[REDACTED_KEY]"
        return payload
    return payload

# =====================================================================
# 4. MERKEZİ OPENROUTER GATEWAY İSTEMCİSİ (Section 6)
# =====================================================================
class OpenRouterGateway:
    """
    Tüm LLM çağrılarını yöneten tek ve merkezi servis.
    """
    _in_memory_cache: Dict[str, Dict[str, Any]] = {}
    _cache_ttl_seconds: Dict[str, int] = {
        "ROUTINE_REPORTING": 300,        # 5 dk
        "CRITICAL_NEWS_ANALYSIS": 180,   # 3 dk
        "TECHNICAL_SECOND_OPINION": 60,  # 1 dk
        "NIGHTLY_FORENSIC_AUDIT": 86400, # 24 saat
        "CRITICAL_INCIDENT_REVIEW": 3600,# 1 saat
        "PATRON": 180,                   # 3 dk
        "CHIEF_AUDITOR": 180,            # 3 dk
        "GENEL_MUDUR": 300               # 5 dk
    }

    @classmethod
    def _get_api_key(cls) -> str:
        key = os.environ.get("OPENROUTER_API_KEY") or os.environ.get("OPENAI_API_KEY", "")
        if key and not key.startswith("your_"):
            return key
        raise ValueError("CRITICAL: OPENROUTER_API_KEY ortam değişkeni tanımlı değil.")

    @classmethod
    def _compute_dedup_key(cls, role: str, tenant_id: str, symbol: str, prompt_version: str, payload: Any) -> str:
        clean_p = sanitize_payload(payload)
        raw_json = json.dumps(clean_p, sort_keys=True)
        h = hashlib.sha256(raw_json.encode("utf-8")).hexdigest()[:16]
        return f"{tenant_id}_{role}_{symbol}_{prompt_version}_{h}"

    @classmethod
    def _check_cache(cls, dedup_key: str, role: str) -> Optional[Dict[str, Any]]:
        now = time.time()
        cached = cls._in_memory_cache.get(dedup_key)
        if cached:
            ttl = cls._cache_ttl_seconds.get(role, 300)
            if now - cached.get("cached_at", 0) < ttl:
                print(f"⚡ [OpenRouterGateway Cache Hit]: {role} ({dedup_key[:20]}...) önbellekten döndü.")
                res_copy = dict(cached.get("result", {}))
                res_copy["cached"] = True
                return res_copy
        return None

    @classmethod
    def _set_cache(cls, dedup_key: str, result: Dict[str, Any]):
        cls._in_memory_cache[dedup_key] = {
            "cached_at": time.time(),
            "result": result
        }
        if len(cls._in_memory_cache) > 500:
            oldest = sorted(cls._in_memory_cache.keys(), key=lambda k: cls._in_memory_cache[k]["cached_at"])[:100]
            for ok in oldest:
                cls._in_memory_cache.pop(ok, None)

    @classmethod
    def invoke(
        cls,
        role: str,
        system_prompt: str,
        user_content: str,
        tenant_id: str = "default_tenant",
        symbol: str = "GLOBAL",
        prompt_version: str = "v1.0",
        schema_model: Optional[Type[BaseModel]] = None,
        manual_trigger: bool = False
    ) -> Dict[str, Any]:
        """
        Merkezi LLM Çağrı Metodu:
        - Rolü doğrular
        - Failover zincirini yönetir
        - Pydantic doğrulamasını yapar
        - Asla doğrudan BUY/SELL yetkisi vermez (Section 1)
        """
        role_cfg = ROLE_ROUTES_CONFIG.get(role)
        if not role_cfg:
            raise ValueError(f"Geçersiz AI rolü: {role}")

        if role_cfg.get("manual_trigger_only") and not manual_trigger:
            return {
                "status": "BLOCKED",
                "error": f"{role} rolü yalnızca yönetici tarafından manuel olarak tetiklenebilir.",
                "execution_authority": "NONE"
            }

        # 1. Deduplication & Cache Kontrolü
        dedup_key = cls._compute_dedup_key(role, tenant_id, symbol, prompt_version, {"sys": system_prompt, "usr": user_content})
        cached_result = cls._check_cache(dedup_key, role)
        if cached_result:
            return cached_result

        # 2. Model Çağrı Zinciri
        target_models = [role_cfg["primary_model"]] + role_cfg.get("fallback_models", [])
        clean_target_models = [m.replace(":batch", "") for m in target_models]

        headers = {
            "Authorization": f"Bearer {cls._get_api_key()}",
            "Content-Type": "application/json",
            "HTTP-Referer": "https://fox-kripto.internal",
            "X-Title": f"Fox AI Gateway ({role})"
        }

        sanitized_sys = sanitize_payload(system_prompt)
        sanitized_usr = sanitize_payload(user_content)

        last_err = None
        for model_idx, model_name in enumerate(clean_target_models):
            is_fallback = (model_idx > 0)
            start_t = time.time()
            try:
                payload = {
                    "model": model_name,
                    "messages": [
                        {"role": "system", "content": str(sanitized_sys)},
                        {"role": "user", "content": str(sanitized_usr)}
                    ],
                    "temperature": role_cfg.get("temperature", 0.2),
                    "max_tokens": role_cfg.get("max_output_tokens", 500)
                }

                if schema_model:
                    payload["response_format"] = {"type": "json_object"}

                timeout_val = role_cfg.get("timeout_seconds", 12)
                res = requests.post(
                    "https://openrouter.ai/api/v1/chat/completions",
                    headers=headers,
                    json=payload,
                    timeout=timeout_val
                )

                latency_ms = int((time.time() - start_t) * 1000)

                if res.status_code == 200:
                    data = res.json()
                    choices = data.get("choices", [])
                    if choices:
                        raw_text = choices[0].get("message", {}).get("content", "").strip()
                        usage = data.get("usage", {})
                        in_tok = usage.get("prompt_tokens", 0)
                        out_tok = usage.get("completion_tokens", 0)

                        # Pydantic Şema Doğrulaması
                        structured_data = None
                        if schema_model:
                            clean_json_text = raw_text
                            if "```json" in clean_json_text:
                                clean_json_text = clean_json_text.split("```json")[1].split("```")[0].strip()
                            elif "```" in clean_json_text:
                                clean_json_text = clean_json_text.split("```")[1].split("```")[0].strip()
                            
                            try:
                                parsed_dict = json.loads(clean_json_text)
                                validated_obj = schema_model(**parsed_dict)
                                structured_data = validated_obj.model_dump()
                            except Exception as schema_e:
                                print(f"⚠️ [OpenRouterGateway Şema Uyarısı]: {model_name} şema doğrulamasını geçemedi ({schema_e}), fallback'e geçiliyor...")
                                last_err = f"Schema validation failed: {schema_e}"
                                continue

                        response_obj = {
                            "status": "SUCCESS",
                            "role": role,
                            "requested_model": role_cfg["primary_model"],
                            "resolved_model": model_name,
                            "fallback_used": is_fallback,
                            "raw_text": raw_text,
                            "structured_data": structured_data,
                            "execution_authority": role_cfg.get("execution_authority", "NONE"),
                            "input_tokens": in_tok,
                            "output_tokens": out_tok,
                            "latency_ms": latency_ms,
                            "prompt_version": prompt_version,
                            "timestamp": datetime.now(timezone.utc).isoformat()
                        }

                        # 🛑 GÜVENLİK KURALI: AI Asla Emir Açamaz (Section 1)
                        if role_cfg.get("execution_authority") == "NONE":
                            response_obj["execution_blocked"] = True

                        cls._set_cache(dedup_key, response_obj)
                        cls._log_ai_call_async(tenant_id, symbol, response_obj)
                        return response_obj
                    else:
                        last_err = "No choices in response"
                else:
                    last_err = f"HTTP {res.status_code}: {res.text}"
                    print(f"⚠️ [OpenRouterGateway Failover]: {model_name} HTTP {res.status_code} verdi, sıradaki yedeğe geçiliyor...")
                    if res.status_code == 402:
                        print("⚠️ [OpenRouterGateway]: OpenRouter hesap kredisi tükendi (HTTP 402). Gecikmeyi önlemek için yedek zincir sonlandırıldı.")
                        break

            except Exception as call_err:
                last_err = str(call_err)
                print(f"⚠️ [OpenRouterGateway İstisna]: {model_name} çağrı hatası ({call_err}), yedek deneniyor...")

        # Tüm modeller başarısız olduysa FAIL-CLOSED yanıt dön (Section 10)
        fail_closed_resp = {
            "status": "FAILED",
            "role": role,
            "error": last_err or "Tüm model rotaları başarısız oldu.",
            "execution_authority": role_cfg.get("execution_authority", "NONE"),
            "structured_data": None,
            "fallback_used": True,
            "timestamp": datetime.now(timezone.utc).isoformat()
        }
        if role == "CRITICAL_NEWS_ANALYSIS":
            fail_closed_resp["structured_data"] = {
                "severity": "DATA_INSUFFICIENT",
                "explanation": "AI sağlayıcısı yanıt veremedi, Fail-Closed gereği güvenli beklemeye geçildi."
            }
        return fail_closed_resp

    @classmethod
    def _log_ai_call_async(cls, tenant_id: str, symbol: str, res_obj: Dict[str, Any]):
        """Asenkron Supabase log kaydı."""
        try:
            from db import get_supabase
            client = get_supabase()
            if client:
                client.table("ai_call_logs").insert({
                    "tenant_id": str(tenant_id),
                    "symbol": str(symbol),
                    "role": res_obj.get("role"),
                    "requested_model": res_obj.get("requested_model"),
                    "resolved_model": res_obj.get("resolved_model"),
                    "fallback_used": res_obj.get("fallback_used", False),
                    "prompt_version": res_obj.get("prompt_version", "v1.0"),
                    "input_tokens": res_obj.get("input_tokens", 0),
                    "output_tokens": res_obj.get("output_tokens", 0),
                    "latency_ms": res_obj.get("latency_ms", 0),
                    "status": res_obj.get("status"),
                    "created_at": datetime.now(timezone.utc).isoformat()
                }).execute()
        except Exception:
            pass
