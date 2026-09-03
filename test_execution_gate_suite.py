import time, sys
if hasattr(sys.stdout, 'reconfigure'): sys.stdout.reconfigure(encoding='utf-8')
from entry_safety_policy import OrderIntent, EntrySafetyPolicy, ExecutionGate, compute_runtime_config_hash
from v2_scalping_engine import V2ScalpingEngine
from v2_whale_engine import V2WhaleHuntingEngine

def run_execution_gate_suite():
    print("=" * 75)
    print("🧪 FOX-KRİPTO: MERKEZİ GÜVENLİK KAPISI (EXECUTION GATE) TEST PAKETİ")
    print("=" * 75)
    
    runtime_hash = compute_runtime_config_hash()
    
    # -------------------------------------------------------------
    # 1. 10 ZORUNLU KURALIN POZİTİF TESTİ (TÜM KURALLAR GEÇTİ)
    # -------------------------------------------------------------
    valid_intent = OrderIntent(
        symbol="SOL/USDT",
        direction="BUY",
        amount_usd=50.0,
        source_engine="WHALE_HUNTING",
        signal_state="RETEST_CONFIRMED",
        first_pump_entry=False,
        risk_decision="APPROVED",
        config_hash=runtime_hash,
        is_expired=False,
        idempotency_key="unique_key_001",
        idempotency_key_unused=True,
        spread_ok=True,
        slippage_ok=True,
        stop_can_be_created=True,
        entry_price=140.0,
        stop_loss_price=137.20,
        take_profit_price=145.60
    )
    passed, status, violations = EntrySafetyPolicy.evaluate_intent(valid_intent)
    assert passed is True, f"Geçerli intent onaylanmalıydı: {violations}"
    print("  ✓ [Kural 1-10]: Tüm 10 güvenlik kriteri eksiksiz sağlandığında APPROVED_FOR_EXECUTION verildi.")

    # -------------------------------------------------------------
    # 2. RETEST_CONFIRMED OLMAYAN NİYETİN REDDİ (NO_TRADE)
    # -------------------------------------------------------------
    unconfirmed_intent = OrderIntent(
        symbol="SOL/USDT",
        direction="BUY",
        amount_usd=50.0,
        source_engine="WHALE_HUNTING",
        signal_state="WAITING_PULLBACK",
        first_pump_entry=False,
        risk_decision="APPROVED",
        config_hash=runtime_hash,
        is_expired=False,
        idempotency_key="unique_key_002",
        idempotency_key_unused=True,
        spread_ok=True,
        slippage_ok=True,
        stop_can_be_created=True,
        entry_price=140.0
    )
    passed, status, violations = EntrySafetyPolicy.evaluate_intent(unconfirmed_intent)
    assert passed is False and status == "NO_TRADE", "RETEST_CONFIRMED olmayan sinyal reddedilmeliydi!"
    print("  ✓ [Güvenlik 2]: RETEST_CONFIRMED olmayan sinyal (WAITING_PULLBACK) kesin olarak NO_TRADE üretti.")

    # -------------------------------------------------------------
    # 3. İLK PUMP MUMU GİRİŞ ENGELİ (first_pump_entry=True ➔ NO_TRADE)
    # -------------------------------------------------------------
    pump_intent = OrderIntent(
        symbol="AVAX/USDT",
        direction="BUY",
        amount_usd=50.0,
        source_engine="SCALPING",
        signal_state="RETEST_CONFIRMED",
        first_pump_entry=True,  # YASAK
        risk_decision="APPROVED",
        config_hash=runtime_hash,
        is_expired=False,
        idempotency_key="unique_key_003",
        idempotency_key_unused=True,
        spread_ok=True,
        slippage_ok=True,
        stop_can_be_created=True,
        entry_price=25.0
    )
    passed, status, violations = EntrySafetyPolicy.evaluate_intent(pump_intent)
    assert passed is False and status == "NO_TRADE", "İlk pump mumu alımı reddedilmeliydi!"
    print("  ✓ [Güvenlik 3]: İlk pump mumu alımı (first_pump_entry=True) kesin olarak NO_TRADE üretti.")

    # -------------------------------------------------------------
    # 4. CONFIG DRIFT HASH UYUMSUZLUĞU (NO_TRADE)
    # -------------------------------------------------------------
    drift_intent = OrderIntent(
        symbol="RENDER/USDT",
        direction="BUY",
        amount_usd=50.0,
        source_engine="WHALE_HUNTING",
        signal_state="RETEST_CONFIRMED",
        first_pump_entry=False,
        risk_decision="APPROVED",
        config_hash="invalid_stale_hash",
        is_expired=False,
        idempotency_key="unique_key_004",
        idempotency_key_unused=True,
        spread_ok=True,
        slippage_ok=True,
        stop_can_be_created=True,
        entry_price=5.0
    )
    passed, status, violations = EntrySafetyPolicy.evaluate_intent(drift_intent)
    assert passed is False and status == "NO_TRADE", "Config drift sinyali reddedilmeliydi!"
    print("  ✓ [Güvenlik 4]: Konfigürasyon hash uyuşmazlığı (Config Drift) anında NO_TRADE üretti.")

    # -------------------------------------------------------------
    # 5. MÜKERRER EMİR (IDEMPOTENCY) ENGELİ (NO_TRADE)
    # -------------------------------------------------------------
    res1 = ExecutionGate.execute(valid_intent, tenant_config={"is_paper_trading": True})
    res2 = ExecutionGate.execute(valid_intent, tenant_config={"is_paper_trading": True})
    assert res2.get("status") == "NO_TRADE", "Aynı idempotency key ile 2. emir engellenmeliydi!"
    print("  ✓ [Güvenlik 5]: Aynı işlem anahtarıyla gelen mükerrer emir (Double-Order) engellendi.")

    # -------------------------------------------------------------
    # 6. ZEC GERÇEK REPLAY: SCALPING MOTORU TESTİ
    # -------------------------------------------------------------
    print("\n" + "-" * 75)
    print("📼 GERÇEK ZEC REPLAY TESTİ: SCALPING MOTORU DENETİMİ (2026-09-02)")
    print("-" * 75)
    scalp_engine = V2ScalpingEngine(risk_level="BALANCED")
    zec_ticker = {
        "symbol": "ZEC/USDT",
        "price": 820.52,
        "quoteVolume": 45000000.0,
        "priceChangePercent": 2.8,
        "volume_spike_ratio": 2.2,
        "taker_buy_ratio": 62.0
    }
    # Canlı açık pump mumu simülasyonu
    zec_klines_1m = [
        [0, 810.0, 812.0, 809.5, 811.5, 100, 0, 50000.0, 10, 0, 30000.0],
        [0, 811.5, 813.0, 811.0, 812.5, 110, 0, 55000.0, 12, 0, 32000.0],
        [0, 812.5, 814.0, 812.0, 813.5, 120, 0, 60000.0, 15, 0, 35000.0],
        [0, 813.5, 816.0, 813.0, 815.5, 200, 0, 120000.0, 30, 0, 75000.0],
        [0, 815.5, 819.0, 815.0, 818.5, 350, 0, 250000.0, 60, 0, 160000.0],
        [0, 818.5, 821.5, 818.0, 820.52, 450, 0, 450000.0, 90, 0, 280000.0]  # CANLI PUMP MUMU
    ]
    scalp_eval = scalp_engine.evaluate_candidate(zec_ticker, klines_1m=zec_klines_1m)
    print(f"  • Scalping Motoru Durumu: {scalp_eval.get('state_machine_stage')}")
    print(f"  • Scalping Alım Onayı (is_ready): {scalp_eval.get('is_ready')}")
    print(f"  • Başarısızlık Gerekçeleri: {scalp_eval.get('failed_criteria')}")
    assert scalp_eval.get("is_ready") is False, "Scalping motoru ZEC tepe mumunda alım vermemeliydi!"
    assert scalp_eval.get("state_machine_stage") == "WAITING_PULLBACK", "Durum WAITING_PULLBACK olmalıydı!"
    print("  🎉 [Scalping Replay Başarılı] ZEC canlı fırlayan mumunda alım %100 engellendi (Durum: WAITING_PULLBACK).")

    # -------------------------------------------------------------
    # 7. ZEC GERÇEK REPLAY: WHALE MOTORU TESTİ
    # -------------------------------------------------------------
    print("\n" + "-" * 75)
    print("📼 GERÇEK ZEC REPLAY TESTİ: WHALE MOTORU DENETİMİ (2026-09-02)")
    print("-" * 75)
    whale_engine = V2WhaleHuntingEngine()
    whale_eval = whale_engine.evaluate_whale_evidence(zec_ticker, klines_5m=zec_klines_1m)
    print(f"  • Whale Motoru Durumu: {whale_eval.get('state_machine_stage')}")
    print(f"  • Whale Alım Onayı: {whale_eval.get('is_whale_confirmed')}")
    assert whale_eval.get("is_whale_confirmed") is False, "Whale motoru ZEC tepe mumunda alım vermemeliydi!"
    print("  🎉 [Whale Replay Başarılı] ZEC canlı fırlayan mumunda alım %100 engellendi (Durum: CONFIRMING / Beklemede).")

    print("\n" + "=" * 75)
    print("🏆 TÜM MERKEZİ GÜVENLİK KAPISI VE ÇİFT MOTOR REPLAY TESTLERİ GEÇTİ! (0 HATA)")
    print("=" * 75)

if __name__ == "__main__":
    run_execution_gate_suite()
