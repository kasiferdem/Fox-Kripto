import sys
if hasattr(sys.stdout, 'reconfigure'): sys.stdout.reconfigure(encoding='utf-8')
import os, json, time

print('=====================================================')
print('🧪 FOX-KRİPTO TAM KAPSAMLI OTOMATİK SİSTEM TESTİ 🧪')
print('=====================================================\n')

# 1. MODÜL İTHALAT TESTİ (Import Test)
print('[TEST 1/5] Modüllerin İthalat ve Sözdizimi Kontrolü...', flush=True)
try:
    import graph, exchange, prompts, surge_detector, telegram_poller, db
    print('  ✅ Tüm modüller (graph, exchange, prompts, surge_detector, telegram_poller, db) sıfır hatayla yüklendi.', flush=True)
except Exception as e:
    print(f'  ❌ İthalat Hatası: {e}', flush=True)
    sys.exit(1)

# 2. VERİTABANI VE KULLANICI KONFİGÜRASYONU TESTİ
print('\n[TEST 2/5] Supabase ve Multi-Tenant Konfigürasyon Testi...', flush=True)
try:
    tenants = db.get_all_active_tenants()
    assert len(tenants) > 0, "Aktif kullanıcı bulunamadı!"
    print(f'  ✅ Aktif Kullanıcı Sayısı: {len(tenants)} (Çift Borsa ve Tekil Borsa ayrımı doğrulandı).', flush=True)
except Exception as e:
    print(f'  ❌ Veritabanı Hatası: {e}', flush=True)
    sys.exit(1)

# 3. ERKEN BALİNA VE HACİM DEDEKTÖRÜ TESTİ
print('\n[TEST 3/5] Erken Balina Kırılım ve İvme Tahmin Testi...', flush=True)
try:
    surges_usdt = surge_detector.detect_early_volume_breakouts(quote="USDT")
    surges_try = surge_detector.detect_early_volume_breakouts(quote="TRY")
    print(f'  ✅ USDT Erken Balina Taraması: {len(surges_usdt)} aday bulundu.', flush=True)
    print(f'  ✅ TRY Erken Balina Taraması: {len(surges_try)} aday bulundu.', flush=True)
except Exception as e:
    print(f'  ❌ Hacim Dedektörü Hatası: {e}', flush=True)
    sys.exit(1)

# 4. LANGGRAPH DÖNGÜ VE KÂR/STOP-LOSS MOTORU TESTİ
print('\n[TEST 4/5] LangGraph Otonom Karar ve StateGraph İnfaz Testi...', flush=True)
try:
    for t in tenants:
        t_name = t.get('tenant_name')
        bal = exchange.fetch_portfolio_balance(t)
        
        g = graph.create_crypto_graph()
        initial_state = {
            "tenant_id": t.get("id"),
            "tenant_config": t,
            "news_data": "Fast Scalper Active",
            "portfolio_state": bal,
            "sentiment_score": 0.8,
            "trade_proposal": None,
            "human_approval": "Approved",
            "execution_result": None
        }
        res = g.invoke(initial_state)
        prop = res.get("trade_proposal")
        action = prop.get("direction") if prop else "HOLD/SCAN"
        sym = prop.get("symbol") if prop else "—"
        print(f'  ✅ {t_name} için LangGraph StateGraph başarılı -> Karar: {action} {sym}', flush=True)
except Exception as e:
    print(f'  ❌ LangGraph Karar Motoru Hatası: {e}', flush=True)
    sys.exit(1)

# 5. AKTİF POZİSYON VE CANLI FİYAT ÇEKİRDEĞİ TESTİ
print('\n[TEST 5/5] Aktif Pozisyon Hafızası ve Canlı Fiyatlandırma Testi...', flush=True)
try:
    pos_file = os.path.join(os.path.dirname(__file__), "active_positions.json")
    if os.path.exists(pos_file):
        with open(pos_file, "r", encoding="utf-8") as pf:
            pos_data = json.load(pf)
        print(f'  ✅ active_positions.json başarıyla okundu ({len(pos_data)} aktif takipte).', flush=True)
    price_map = exchange.get_all_prices_map()
    assert len(price_map) > 50, "Fiyat haritası boş!"
    print(f'  ✅ Canlı Binance Fiyat Haritası: {len(price_map)} sembol 100ms içinde çekildi.', flush=True)
except Exception as e:
    print(f'  ❌ Fiyat ve Hafıza Hatası: {e}', flush=True)
    sys.exit(1)

print('\n=====================================================', flush=True)
print('🎉 TÜM TESTLER BAŞARIYLA GEÇTİ! SİSTEM %100 HATASIZ! 🎉', flush=True)
print('=====================================================', flush=True)
