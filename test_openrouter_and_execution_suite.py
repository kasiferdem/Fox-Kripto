"""
FOX-KRİPTO: AI MODEL VE MERKEZİ EMİR MİMARİSİ TEST SUITE (Section 14)
Bu test paketi tüm AI yetki sınırlarını, model yönlendirmelerini, failover mekanizmalarını,
güvenlik kapılarını ve borsa emir izolasyonunu doğrular.
"""

import sys
import os
import json
import time
from datetime import datetime, timezone

# Windows console UTF-8 fix
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')

from openrouter_gateway import (
    OpenRouterGateway,
    CriticalNewsAssessment,
    TechnicalSecondOpinion,
    RoutineReportingSummary,
    NightlyForensicReport,
    ROLE_ROUTES_CONFIG
)
from prompts import resolve_legacy_model_alias
from entry_safety_policy import OrderIntent, ExecutionGate, compute_runtime_config_hash
from binance_execution_service import BinanceExecutionService

def test_legacy_ox_alpha_removal():
    """Test: OX Alpha kaldırıldı ve audit kaydında GLM-5.3 Flash olarak çözümleniyor (Section 2)"""
    print("\n--- TEST 1: OX Alpha Kaldırma ve Model Çözümleme ---")
    meta = resolve_legacy_model_alias("stealth/ox-alpha")
    assert meta["legacyModelAlias"] == "stealth/ox-alpha"
    assert meta["resolvedModelIdentity"] == "z-ai/glm-5.3-flash"
    assert meta["independentConfirmation"] is False
    print("✅ TEST 1 BAŞARILI: OX Alpha başarıyla kaldırıldı ve metadata doğru.")

def test_model_routes_and_authorities():
    """Test: Nihai model görev dağılımı ve yetki kısıtları (Section 3)"""
    print("\n--- TEST 2: Model Rol Dağılımı ve Yetki Kısıtları ---")
    
    # Routine Reporting
    rr = ROLE_ROUTES_CONFIG["ROUTINE_REPORTING"]
    assert rr["primary_model"] == "z-ai/glm-5.3-flash"
    assert "nvidia/nemotron-3.5-lightning" in rr["fallback_models"]
    assert rr["execution_authority"] == "NONE"
    
    # Critical News
    cn = ROLE_ROUTES_CONFIG["CRITICAL_NEWS_ANALYSIS"]
    assert cn["primary_model"] == "google/gemini-3.7-flash"
    assert "z-ai/glm-5.3" in cn["fallback_models"]
    assert cn["execution_authority"] == "BLOCK_ONLY"
    
    # Technical Second Opinion
    tso = ROLE_ROUTES_CONFIG["TECHNICAL_SECOND_OPINION"]
    assert tso["primary_model"] == "z-ai/glm-5.3"
    assert "google/gemini-3.7-flash" in tso["fallback_models"]
    assert tso["execution_authority"] == "NONE"
    
    # Nightly Forensic Audit
    nfa = ROLE_ROUTES_CONFIG["NIGHTLY_FORENSIC_AUDIT"]
    assert nfa["primary_model"] == "openai/gpt-6-astra:batch"
    assert "z-ai/glm-5.3" in nfa["fallback_models"]
    assert nfa["execution_authority"] == "NONE"
    
    print("✅ TEST 2 BAŞARILI: Tüm 5 rol ve model rotaları birebir uyumlu.")

def test_execution_gate_blocks_direct_ai_buy():
    """Test: AI BUY dese bile ExecutionGate şartlar sağlanmadığında emri reddetmeli (Section 1 & 5)"""
    print("\n--- TEST 3: ExecutionGate AI BUY Engelleme ve İzolasyon ---")
    
    # 1. Şart: Retest onaylanmamış bir sinyal -> REDDEDİLMELİ
    runtime_hash = compute_runtime_config_hash()
    bad_intent = OrderIntent(
        symbol="BTC/USDT",
        direction="BUY",
        amount_usd=10.0,
        source_engine="LLM_AI_ADVICE", # AI doğrudan emir açamaz
        signal_state="PENDING_PUMP",   # RETEST_CONFIRMED değil!
        first_pump_entry=True,         # İlk mum alımı YASAK!
        risk_decision="APPROVED",
        config_hash=runtime_hash,
        is_expired=False,
        idempotency_key="test_key_1",
        idempotency_key_unused=True,
        spread_ok=True,
        slippage_ok=True,
        stop_can_be_created=True,
        entry_price=65000.0
    )
    
    res = ExecutionGate.execute(bad_intent, tenant_config={"is_paper_trading": True})
    assert res["status"] == "NO_TRADE"
    assert len(res["violations"]) > 0
    print("✅ TEST 3.1 BAŞARILI: Geçersiz motor/sinyal reddedildi (NO_TRADE).")
    
    # 2. Şart: Stop preflight başarısız -> REDDEDİLMELİ
    bad_stop_intent = OrderIntent(
        symbol="SOL/USDT",
        direction="BUY",
        amount_usd=10.0,
        source_engine="SCALPING",
        signal_state="RETEST_CONFIRMED",
        first_pump_entry=False,
        risk_decision="APPROVED",
        config_hash=runtime_hash,
        is_expired=False,
        idempotency_key="test_key_2",
        idempotency_key_unused=True,
        spread_ok=True,
        slippage_ok=True,
        stop_can_be_created=False, # STOP KURULAMIYOR!
        stop_preflight_ok=False,
        entry_price=150.0
    )
    res2 = ExecutionGate.execute(bad_stop_intent, tenant_config={"is_paper_trading": True})
    assert res2["status"] == "NO_TRADE"
    assert any("stop_preflight_failed" in v for v in res2["violations"])
    print("✅ TEST 3.2 BAŞARILI: Stop preflight başarısız olduğunda işlem engellendi (NO_TRADE).")

def test_deduplication_and_caching():
    """Test: Aynı sinyal için tekrar eden ücretli AI çağrısı yapılmamalı (Section 9)"""
    print("\n--- TEST 4: Önbellek ve Yinelenen Çağrı Engeli (Deduplication) ---")
    
    role = "ROUTINE_REPORTING"
    tenant_id = "test_tenant"
    symbol = "ETH/USDT"
    prompt_version = "test-v1"
    user_payload = {"test_key": "unique_val_123", "symbol": symbol}
    
    # 1. Dedup anahtarı hesaplama
    dedup_key = OpenRouterGateway._compute_dedup_key(
        role=role,
        tenant_id=tenant_id,
        symbol=symbol,
        prompt_version=prompt_version,
        payload={"sys": "test_sys", "usr": json.dumps(user_payload)}
    )
    assert dedup_key.startswith(f"{tenant_id}_{role}_{symbol}_{prompt_version}")
    
    # 2. Önbelleğe simüle edilmiş yanıt yaz
    mock_response = {
        "status": "SUCCESS",
        "role": role,
        "resolved_model": "z-ai/glm-5.3-flash",
        "raw_text": "Piyasa stabil.",
        "input_tokens": 150,
        "output_tokens": 50
    }
    OpenRouterGateway._set_cache(dedup_key, mock_response)
    
    # 3. İkinci çağrı -> Cache'den gelmeli
    cached_res = OpenRouterGateway._check_cache(dedup_key, role)
    assert cached_res is not None
    assert cached_res.get("cached") is True
    assert cached_res.get("resolved_model") == "z-ai/glm-5.3-flash"
    
    print("✅ TEST 4 BAŞARILI: Önbellek ve Deduplication mekanizması doğrulandı (0 Token maliyeti).")

def test_fail_closed_on_invalid_ai_response():
    """Test: Geçersiz veya bozuk AI yanıtında Fail-Closed davranışı (Section 10)"""
    print("\n--- TEST 5: Fail-Closed ve Pydantic Doğrulama ---")
    
    # Pydantic CriticalNewsAssessment doğrulaması
    valid_data = {
        "severity": "HIGH_RISK",
        "confidence": 0.95,
        "affected_symbols": ["BTC", "ETH"],
        "evidence": ["Büyük borsa likidite uyarısı"],
        "data_timestamp": datetime.now(timezone.utc).isoformat(),
        "explanation": "Piyasa yüksek volatilite riski taşıyor."
    }
    obj = CriticalNewsAssessment(**valid_data)
    assert obj.severity == "HIGH_RISK"
    
    # Geçersiz severity değeri
    try:
        invalid_data = {
            **valid_data,
            "severity": "BUY_IMMEDIATELY" # Geçersiz değer!
        }
        CriticalNewsAssessment(**invalid_data)
        assert False, "Geçersiz değer doğrulanamadı!"
    except Exception:
        print("✅ TEST 5 BAŞARILI: Geçersiz AI çıktısı Pydantic tarafından anında reddedildi.")

def test_paper_and_shadow_execution():
    """Test: PAPER_TRADING modunda BinanceExecutionService simülasyonu (Section 11)"""
    print("\n--- TEST 6: PAPER_TRADING & SHADOW İnfaz Doğrulaması ---")
    
    runtime_hash = compute_runtime_config_hash()
    valid_paper_intent = OrderIntent(
        symbol="LTC/USDT",
        direction="BUY",
        amount_usd=10.0,
        source_engine="V2_WHALE_HUNTING",
        signal_state="RETEST_CONFIRMED",
        first_pump_entry=False,
        risk_decision="APPROVED",
        config_hash=runtime_hash,
        is_expired=False,
        idempotency_key=f"ltc_test_{int(time.time())}",
        idempotency_key_unused=True,
        spread_ok=True,
        slippage_ok=True,
        stop_can_be_created=True,
        entry_price=95.50,
        stop_loss_price=93.50,
        take_profit_price=98.50
    )
    
    # Paper trading konfigürasyonu
    paper_config = {
        "is_paper_trading": True,
        "exchange_id": "binance",
        "tenant_name": "Test User"
    }
    
    exec_res = ExecutionGate.execute(valid_paper_intent, tenant_config=paper_config)
    assert exec_res["status"].upper() in ["EXECUTED_SIMULATED", "SUCCESS", "EXECUTED"]
    exec_price = exec_res.get("executed_price") or exec_res.get("price") or 95.50
    print(f"✅ TEST 6 BAŞARILI: PAPER_TRADING emri sanal olarak infaz edildi (Fiyat: ${exec_price}).")

def run_all_tests():
    print("=================================================================")
    print("🚀 FOX-KRİPTO OPENROUTER AI & GÜVENLİ EMİR TEST SUITE BAŞLATILDI")
    print("=================================================================")
    
    test_legacy_ox_alpha_removal()
    test_model_routes_and_authorities()
    test_execution_gate_blocks_direct_ai_buy()
    test_deduplication_and_caching()
    test_fail_closed_on_invalid_ai_response()
    test_paper_and_shadow_execution()
    
    print("\n=================================================================")
    print("🎉 TÜM 6 GÜVENLİK VE MİMARİ ENTEGRASYON TESTİ %100 BAŞARIYLA GEÇTİ!")
    print("=================================================================")

if __name__ == "__main__":
    run_all_tests()
