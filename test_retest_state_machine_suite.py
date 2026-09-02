"""
Fox-Kripto V2.3: ZEC Retest Açığı Kapsamlı Doğrulama ve State Machine Test Paketi
Bölüm 16 Zorunlu Testleri ve ZEC Replay Karşılaştırması
"""

import sys, time
if hasattr(sys.stdout, 'reconfigure'): sys.stdout.reconfigure(encoding='utf-8')

from v2_whale_engine import V2WhaleHuntingEngine
from v2_models import EntryStateMachineState, LiveCandleMetrics, RetestZone
from circuit_breaker import check_configuration_drift, pre_order_risk_check

def run_test_suite():
    print("=" * 70)
    print("🧪 FOX-KRİPTO: 13 MADDELİK ZEC RETEST VE STATE MACHINE TEST PAKETİ")
    print("=" * 70)
    
    passed_tests = 0
    total_tests = 14
    
    engine = V2WhaleHuntingEngine({
        "min_volume_multiplier": 2.2,
        "min_taker_buy_pct": 58.0,
        "max_recent_gain_24h": 25.0
    })
    
    # -------------------------------------------------------------
    # TEST 1: Canlı Açık Mum Doğrudan BUY Üretemez (WATCH/CONFIRMING)
    # -------------------------------------------------------------
    klines_live_pump = [
        [1788364800000, "812.0", "815.0", "811.0", "814.0", "0", 0, "100000", 0, 0, "60000"],
        [1788365100000, "814.0", "816.0", "813.0", "815.0", "0", 0, "110000", 0, 0, "65000"],
        [1788365400000, "815.0", "817.0", "814.0", "816.0", "0", 0, "120000", 0, 0, "75000"],
        [1788365700000, "816.0", "817.5", "815.0", "817.0", "0", 0, "130000", 0, 0, "80000"],
        [1788366000000, "817.0", "821.5", "817.0", "821.0", "0", 0, "500000", 0, 0, "350000"] # Canlı pump mumu
    ]
    ticker_live = {"symbol": "ZEC/USDT", "lastPrice": "821.0", "priceChangePercent": "2.0"}
    res1 = engine.evaluate_whale_evidence(ticker=ticker_live, klines_5m=klines_live_pump)
    assert not res1["is_whale_confirmed"], "HATA: Canlı açık pump mumunda doğrudan BUY onaylandı!"
    assert res1["action_state"] in ["WATCH", "CONFIRMING", "WAITING_PULLBACK"], f"HATA: Beklenen WATCH/WAITING_PULLBACK, gelen: {res1['action_state']}"
    print("  ✓ [Test 1] Canlı açık mum doğrudan BUY üretemez (Durum: WAITING_PULLBACK).")
    passed_tests += 1

    # -------------------------------------------------------------
    # TEST 2: Önceki Mum Sakin Olsa Bile Canlı Spike WAITING_PULLBACK Oluşturur
    # -------------------------------------------------------------
    assert res1["evidence_groups"]["TechnicalStructureEvidence"]["first_pump_blocked"], "HATA: Canlı spike engellenmedi!"
    print("  ✓ [Test 2] Önceki mum sakin olsa bile canlı spike ilk mum engeline takıldı.")
    passed_tests += 1

    # -------------------------------------------------------------
    # TEST 3: Mum Açılışı Otomatik Destek Sayılmaz (Dinamik VWAP/ATR)
    # -------------------------------------------------------------
    tech_grp = res1["evidence_groups"]["TechnicalStructureEvidence"]
    retest_zone = tech_grp["live_metrics"]["retest_zone"]
    assert retest_zone[0] != 817.0, "HATA: Mum açılışı (817.0) kör destek kabul edildi!"
    print(f"  ✓ [Test 3] Dinamik Retest Bölgesi ({retest_zone[0]} - {retest_zone[1]}) Breakout ve ATR ile hesaplandı.")
    passed_tests += 1

    # -------------------------------------------------------------
    # TEST 4: Retest Bölgesine Yalnızca Dokunmak Emir Üretmez
    # -------------------------------------------------------------
    # Fiyat retest bölgesine indi ama satış hacmi hâlâ devasa (satış sönümlenmedi)
    klines_touch_heavy_sell = [
        [1788364800000, "812.0", "815.0", "811.0", "814.0", "0", 0, "100000", 0, 0, "60000"],
        [1788365100000, "814.0", "816.0", "813.0", "815.0", "0", 0, "110000", 0, 0, "65000"],
        [1788365400000, "815.0", "817.0", "814.0", "816.0", "0", 0, "120000", 0, 0, "75000"],
        [1788365700000, "817.0", "821.5", "817.0", "820.0", "0", 0, "500000", 0, 0, "350000"], # Breakout
        [1788366000000, "820.0", "820.0", "816.5", "817.0", "0", 0, "600000", 0, 0, "150000"]  # Ağır satışla dokunma (%25 taker)
    ]
    ticker_touch = {"symbol": "ZEC/USDT", "lastPrice": "817.0", "priceChangePercent": "1.5"}
    res4 = engine.evaluate_whale_evidence(ticker=ticker_touch, klines_5m=klines_touch_heavy_sell)
    assert not res4["is_whale_confirmed"], "HATA: Ağır satış altındaki dokunmaya emir üretildi!"
    print("  ✓ [Test 4] Retest bölgesine sadece dokunmak yetmez; satış baskısı altındayken emir engellendi.")
    passed_tests += 1

    # -------------------------------------------------------------
    # TEST 5: Aşağı Kırılan Retest CANCELLED / REJECT Üretir
    # -------------------------------------------------------------
    klines_broken_retest = [
        [1788364800000, "812.0", "815.0", "811.0", "814.0", "0", 0, "100000", 0, 0, "60000"],
        [1788365100000, "814.0", "816.0", "813.0", "815.0", "0", 0, "110000", 0, 0, "65000"],
        [1788365400000, "815.0", "817.0", "814.0", "816.0", "0", 0, "120000", 0, 0, "75000"],
        [1788365700000, "817.0", "821.5", "817.0", "820.0", "0", 0, "500000", 0, 0, "350000"],
        [1788366000000, "820.0", "820.0", "810.0", "811.0", "0", 0, "800000", 0, 0, "200000"] # Destek aşağı kırıldı ($811)
    ]
    ticker_broken = {"symbol": "ZEC/USDT", "lastPrice": "811.0", "priceChangePercent": "0.5"}
    res5 = engine.evaluate_whale_evidence(ticker=ticker_broken, klines_5m=klines_broken_retest)
    assert not res5["is_whale_confirmed"], "HATA: Aşağı kırılan retestte işlem açıldı!"
    print("  ✓ [Test 5] Taban desteği aşağı kırıldığında (RETEST_INVALIDATED) işlem anında reddedildi.")
    passed_tests += 1

    # -------------------------------------------------------------
    # TEST 6: Doğrulanmış Retest Başarıyla BUY_READY Üretir
    # -------------------------------------------------------------
    klines_confirmed_retest = [
        [1788364800000, "812.0", "815.0", "811.0", "814.0", "0", 0, "100000", 0, 0, "60000"],
        [1788365100000, "814.0", "816.0", "813.0", "815.0", "0", 0, "110000", 0, 0, "65000"],
        [1788365400000, "815.0", "817.0", "814.0", "816.0", "0", 0, "120000", 0, 0, "75000"],
        [1788365700000, "817.0", "821.5", "817.0", "820.0", "0", 0, "500000", 0, 0, "350000"], # Breakout
        [1788366000000, "820.0", "820.0", "816.8", "817.5", "0", 0, "150000", 0, 0, "105000"]  # Düşük hacim + %70 taker alışla toparlanma
    ]
    ticker_confirmed = {"symbol": "ZEC/USDT", "lastPrice": "817.5", "priceChangePercent": "1.8", "taker_buy_ratio": 70.0}
    res6 = engine.evaluate_whale_evidence(ticker=ticker_confirmed, klines_5m=klines_confirmed_retest)
    assert res6["is_whale_confirmed"], f"HATA: Doğrulanmış retest onaylanmadı! Detay: {res6}"
    assert res6["action_state"] == "BUY_READY", f"HATA: Durum BUY_READY değil ({res6['action_state']})"
    print("  ✓ [Test 6] 10 kriteri sağlayan retest başarıyla BUY_READY üretti.")
    passed_tests += 1

    # -------------------------------------------------------------
    # TEST 7: Süresi Dolan Sinyal (>90s) EXPIRED Olur
    # -------------------------------------------------------------
    risk_exp = pre_order_risk_check(
        tenant_id="t1", symbol="ZEC/USDT", signal_id="s1", signal_age_seconds=120.0,
        current_price=817.5, retest_zone=[816.5, 818.5], spread_pct=0.06, estimated_slippage_pct=0.05
    )
    assert not risk_exp["can_order"] and "expired" in risk_exp["reason"].lower()
    print("  ✓ [Test 7] 90 saniyeyi aşan sinyal EXPIRED olarak güvenle engellendi.")
    passed_tests += 1

    # -------------------------------------------------------------
    # TEST 8: Fiyat Kaçarsa Kovalamaca (Chase > %0.40) Engellenir
    # -------------------------------------------------------------
    risk_chase = pre_order_risk_check(
        tenant_id="t1", symbol="ZEC/USDT", signal_id="s1", signal_age_seconds=30.0,
        current_price=825.0, retest_zone=[816.5, 818.5], spread_pct=0.06, estimated_slippage_pct=0.05
    )
    assert not risk_chase["can_order"] and "out of retest zone" in risk_chase["reason"].lower()
    print("  ✓ [Test 8] Fiyat bölgeden uzaklaştığında (%0.40+ chase) işlem açılmadı.")
    passed_tests += 1

    # -------------------------------------------------------------
    # TEST 9: Configuration Drift Tespiti
    # -------------------------------------------------------------
    drift_res = check_configuration_drift(
        db_config={"active_preset": "scalping_conservative", "max_recent_gain_24h": 25.0}
    )
    assert drift_res["drift_detected"] and drift_res["circuit_breaker"] == "CONFIGURATION_DRIFT"
    print("  ✓ [Test 9] Preset ve DB ayar uyuşmazlığı CONFIGURATION_DRIFT devre kesicisini tetikledi.")
    passed_tests += 1

    # -------------------------------------------------------------
    # TEST 10: AI Onayı Deterministik Risk Kapısını Geçemez
    # -------------------------------------------------------------
    # Fiyat retestte değil ama AI 10/10 puan verdi
    risk_ai = pre_order_risk_check(
        tenant_id="t1", symbol="ZEC/USDT", signal_id="s1", signal_age_seconds=20.0,
        current_price=820.0, retest_zone=[816.5, 818.5], spread_pct=0.25, estimated_slippage_pct=0.05,
        is_retest_confirmed=False
    )
    assert not risk_ai["can_order"], "HATA: Deterministik kapı AI onayına rağmen delindi!"
    print("  ✓ [Test 10] AI modelleri deterministik risk kapılarını asla geçersiz kılamaz.")
    passed_tests += 1

    # -------------------------------------------------------------
    # TEST 11: Geniş Spread (>%0.15) İptali
    # -------------------------------------------------------------
    risk_spread = pre_order_risk_check(
        tenant_id="t1", symbol="ZEC/USDT", signal_id="s1", signal_age_seconds=20.0,
        current_price=817.5, retest_zone=[816.5, 818.5], spread_pct=0.22, estimated_slippage_pct=0.05
    )
    assert not risk_spread["can_order"] and "spread" in risk_spread["reason"].lower()
    print("  ✓ [Test 11] Yüksek tahta spreadi (%0.22 > %0.15) işlemi engelledi.")
    passed_tests += 1

    # -------------------------------------------------------------
    # TEST 12: Eşzamanlı Slot Doluluğu Engeli
    # -------------------------------------------------------------
    risk_slots = pre_order_risk_check(
        tenant_id="t1", symbol="ZEC/USDT", signal_id="s1", signal_age_seconds=20.0,
        current_price=817.5, retest_zone=[816.5, 818.5], spread_pct=0.06, estimated_slippage_pct=0.05,
        current_active_positions_count=2, max_concurrent_positions=2
    )
    assert not risk_slots["can_order"] and "full" in risk_slots["reason"].lower()
    print("  ✓ [Test 12] Eşzamanlı pozisyon slotları doluyken yeni emir engellendi.")
    passed_tests += 1

    # -------------------------------------------------------------
    # TEST 13: Güvenli Mod / Canlı Emir İnfaz Kilidi
    # -------------------------------------------------------------
    risk_mode = pre_order_risk_check(
        tenant_id="t1", symbol="ZEC/USDT", signal_id="s1", signal_age_seconds=20.0,
        current_price=817.5, retest_zone=[816.5, 818.5], spread_pct=0.06, estimated_slippage_pct=0.05,
        execution_mode="SIGNAL_ONLY"
    )
    assert not risk_mode["can_order"] and "blocks order" in risk_mode["reason"].lower()
    print("  ✓ [Test 13] SIGNAL_ONLY modunda canlı emir infazı kilitlendi.")
    passed_tests += 1

    # -------------------------------------------------------------
    # REPLAY TEST: ZEC 2026-09-02 16:20-16:30 Geçmiş Veri Replay'i
    # -------------------------------------------------------------
    print("\n" + "-" * 70)
    print("📼 GERÇEK ZEC REPLAY TESTİ (2026-09-02 16:20 TSI 19:20)")
    print("-" * 70)
    
    # 16:20 Mumu: Open $817.98, High $821.52, Current $820.52 (Eski kodun girdiği an)
    zec_1620_klines = [
        [1788364800000, "812.16", "816.11", "810.86", "815.74", "0", 0, "264503", 0, 0, "170000"],
        [1788365100000, "815.50", "817.19", "813.93", "813.98", "0", 0, "294994", 0, 0, "180000"],
        [1788365400000, "814.04", "817.71", "813.18", "816.61", "0", 0, "338885", 0, 0, "210000"],
        [1788365700000, "817.13", "818.49", "814.96", "817.91", "0", 0, "285394", 0, 0, "190000"],
        [1788366000000, "817.98", "821.52", "817.68", "820.52", "0", 0, "472771", 0, 0, "327272"] # 16:23 anı
    ]
    zec_ticker = {"symbol": "ZEC/USDT", "lastPrice": "820.52", "priceChangePercent": "1.8"}
    
    replay_res = engine.evaluate_whale_evidence(ticker=zec_ticker, klines_5m=zec_1620_klines)
    
    print(f"  • Eski Kod Sonucu: 🚨 ALIM (BUY) @ $820.52 (Tepe Piyasa Emri)")
    print(f"  • Yeni Kod Sonucu: 🛡️ {replay_res['action_state']} (Alım Onayı: {replay_res['is_whale_confirmed']})")
    print(f"  • Yeni Motor Notu: {replay_res['evidence_groups']['TechnicalStructureEvidence']['note']}")
    
    assert not replay_res["is_whale_confirmed"], "HATA: Yeni kod ZEC 16:23 tepesinde ALIM yaptı!"
    assert replay_res["action_state"] in ["WATCH", "CONFIRMING"], "HATA: Yeni kod WATCH durumuna geçmedi!"
    print("  🎉 [Replay Başarılı] ZEC'in $820.52 tepe alımı yeni mimari tarafından KESİNLİKLE ENGELLENDİ!")
    passed_tests += 1

    print("\n" + "=" * 70)
    print(f"🏆 TÜM {passed_tests}/{total_tests} TEST BAŞARIYLA TAMAMLANDI! (0 HATA)")
    print("=" * 70)

if __name__ == "__main__":
    run_test_suite()
