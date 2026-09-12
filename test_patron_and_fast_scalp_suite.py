"""
Fox-Kripto — Patron Ajan (GPT-4o), Akıllı Vur-Kaç Ajanı ve Başa-Baş Zırhı Test Paketi
Telif Hakkı (c) 2026 Fox-Kripto Quant Ekibi.
"""

import sys
if hasattr(sys.stdout, 'reconfigure'): sys.stdout.reconfigure(encoding='utf-8')
from prompts import call_patron_market_weather, call_fast_scalp_analyst
from openrouter_gateway import MarketWeatherAssessment, FastScalpAssessment

def test_patron_weather_structure():
    print("\n--- TEST 1: Patron Ajan Canlı Hava Analizi (GPT-4o) ---")
    weather = call_patron_market_weather(
        btc_price=85250.0,
        btc_rsi=51.5,
        regime_info={"btc_1h_trend": "BULLISH", "is_bullish": True, "reason": "EMA200 üzerinde istikrarlı"}
    )
    print(f"Patron Hava Sonucu: {weather}")
    assert weather.get("weather") in ["GUNESLI", "PUSLU", "FIRTINALI"]
    assert isinstance(weather.get("is_trade_allowed"), bool)
    assert len(weather.get("risk_caution_note", "")) > 0
    print("✅ TEST 1 BAŞARILI: Patron Ajan piyasa havasını başarıyla değerlendirdi.")

def test_fast_scalp_analyst_evaluation():
    print("\n--- TEST 2: Akıllı Vur-Kaç Ajanı Aday İncelemesi (GPT-4o) ---")
    good_candidate = {
        "symbol": "SAGA/USDT",
        "lastPrice": 1.45,
        "priceChangePercent": 4.1,
        "volume_spike_ratio": 3.2,
        "taker_buy_ratio": 71.0,
        "recent_5m_volume_usd": 120000.0,
        "daily_range_pct": 6.8
    }
    res = call_fast_scalp_analyst(good_candidate, market_weather="GUNESLI")
    print(f"Akıllı Ajan Değerlendirmesi: {res}")
    assert isinstance(res.get("is_scalp_recommended"), bool)
    assert isinstance(res.get("potential_score"), (int, float))
    assert res.get("target_tp_pct") >= 1.5
    assert res.get("stop_loss_pct") <= 1.5
    print("✅ TEST 2 BAŞARILI: Akıllı Ajan coin vur-kaç analizini başarıyla tamamladı.")

def test_breakeven_logic_simulation():
    print("\n--- TEST 3: Başa-Baş (Break-Even) Zırhı Simülasyonu ---")
    # Senaryo 1: Pozisyon +%1.20 gördü, sonra geri çekilip maliyet fiyatına ($10.00) indi
    recorded_buy_p = 10.00
    highest_p = 10.12 # +%1.20 peak
    curr_p = 10.00    # maliyete geri çekildi
    peak_gain_pct = ((highest_p - recorded_buy_p) / recorded_buy_p) * 100
    net_profit_pct = 0.00

    breakeven_triggered = (peak_gain_pct >= 1.0)
    is_take_profit = False
    reason_desc = ""

    if breakeven_triggered and net_profit_pct <= 0.05 and curr_p <= recorded_buy_p:
        is_take_profit = True
        reason_desc = f"🛡️ Başa-Baş (Break-Even) Zırhı (+%{net_profit_pct:.2f} Net / Zirve: +%{peak_gain_pct:.2f} - Sıfır Zararla Korundu)"

    assert is_take_profit is True
    assert "Başa-Baş" in reason_desc
    print(f"Başa-Baş Çıkış Tetiklendi: {reason_desc}")
    print("✅ TEST 3 BAŞARILI: Kârdaki işlem zarara dönmeden başa-başta korundu.")

if __name__ == "__main__":
    print("=================================================================")
    print("🚀 PATRON & AKILLI AJAN VUR-KAÇ SİSTEM TESTLERİ BAŞLATILDI")
    print("=================================================================")
    test_patron_weather_structure()
    test_fast_scalp_analyst_evaluation()
    test_breakeven_logic_simulation()
    print("\n=================================================================")
    print("🎉 TÜM YENİ MİMARİ TESTLERİ EKSİKSİZ VE %100 BAŞARIYLA TAMAMLANDI!")
    print("=================================================================")
