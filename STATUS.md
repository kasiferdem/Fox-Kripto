# 🦊 Fox-Kripto Proje Durumu ve Hafıza Dosyası (STATUS.md)

> **Bu dosya, Antigravity AI asistanlarının yeni sohbet oturumlarında projenin neresinde olunduğunu anında hatırlaması için otomatik güncellenen canlı durum belgesidir.**

---

## 📌 Proje Özeti
- **Proje Adı:** Fox-Kripto (Otonom Multi-Tenant Kripto Analiz, Erken Balina Takip ve İnsan-Onaylı Alım-Satım Sistemi)
- **Teknoloji Yığını:** Python 3.12, FastAPI, LangGraph, OpenAI GPT-4o, CCXT & Binance REST, Supabase (PostgreSQL), Telegram Bot API
- **GitHub Reposu:** `kasiferdem/Fox-Kripto`
- **Aktif Mimari:**
  - 🛡️ **3 Altın Kural:** Dipte Erken Hacim Kırılımı (FOMO Engeli $\le \%8.5$), Tahta Doyum ve Alıcı Baskısı ($\ge 0.77$), Supabase Atomik Soğuma (60dk).
  - 🎯 **Risk/Ödül:** ATR(14) Dinamik Stop-Loss ve $R:R \ge 1:2$ Take-Profit.
  - 🛑 **Fiziksel Stop:** Borsa emir defterine doğrudan `STOP_LOSS_LIMIT` emri.
  - ⚡ **Devre Kesici (Circuit Breaker):** Maks 3 eşzamanlı pozisyon, 3 ardışık stop kilidi, günlük %3 azami zarar sınırı (Tenant yalıtımlı).
  - 🌐 **Piyasa Rejimi:** BTC 1s EMA(200) trend filtresi ve Fail-Closed sermaye koruması.
  - 🧪 **Tek Tuş Test / Canlı Mod:** `/test` (Paper Trading $100) ve `/canli` (Real Binance).

---

## 🛠️ Tamamlanan Özellikler (Yapılanlar)

1. **Güvenlik ve Kimlik Doğrulama (P0 Düzeltmeleri):**
   - Kaynak koddan tüm sızıntı/hardcoded anahtarlar temizlendi (`prompts.py`, `telegram_poller.py`).
   - Tüm admin execution rotaları `HTTPBasic` (`ADMIN_USERNAME` / `ADMIN_PASSWORD`) ile kilitlendi.
   - Telegram poller `from.id` ve allowlist bazlı sıkı yetkilendirmeye geçirildi.

2. **OpenRouter AI Mimarisi & Güvenli İnfaz Ayrımı (Eylül 2026):**
   - `openrouter_gateway.py`: Pydantic şema doğrulamalı, failover zincirli ve deduplication önbellekli merkezi AI gateway.
   - `binance_execution_service.py`: Tek yetkili borsa emir servisi.
   - `entry_safety_policy.py`: 10 Kademeli ExecutionGate; AI modellerinin yetkisi `NONE` ve `BLOCK_ONLY` olarak sınırlandı.
   - Deterministik Python infazı: RSI, ATR, VWAP, Lot, SL/TP hesaplamaları tamamen koda devredildi.

3. **Dinamik Yönetim Paneli & Sıfır Hardcode (V2 Dashboard):**
   - `/v2/dashboard` parametre ızgarası üzerinden BTC Taban RSI, Retest Onayı, İlk Pump Engeli, TP, SL, Trailing Callback gibi tüm kritik ayarlar canlı dinamik kontrol altına alındı.
   - 2-3 Eylül kazandıran çevik strateji parametreleri kataloglandı (`KAZANDIRAN_STRATEJI_AYARLARI.md`).

4. **Retest Durum Makinesi ve Risk Koruma:**
   - 12 durumlu retest state machine ve ilk pump mumu tepe alım engeli (`first_pump_candle_entry_blocked = True`).
   - Retest zorunluluğu (`retest_required = True`), dinamik Stop-Loss (%2.2) ve 30 dakikalık katı işlem soğuması (`cooldown_minutes = 30`).
   - ATR(14) dinamik stop-loss, fiziksel borsa stop limit emirleri ve çoklu devre kesiciler.

5. **Veritabanı ve Ledger (`db.py`):**
   - Supabase PostgreSQL: `user_tenants`, `crypto_agent_states`, `crypto_trade_logs` ve 7 adet AI denetim/maliyet tablosu (`supabase_ai_schema.sql`).
   - Tüm geçici test ve scratch dosyaları `_archive/scratch/` altına temizlendi ve izole edildi.

---

## ⚙️ Güvenli Çalıştırma

```bash
# Web Paneli + Otonom Botu Çalıştırma
python app.py
```
*Web Arayüzü:* `http://localhost:8000/v2/dashboard` (veya `/dashboard`)

---

## 📋 Mevcut Yapılacaklar Listesi

- [x] **Kusursuz Risk Profili Devrede:** `first_pump_blocked: True`, `retest_required: True`, `cooldown: 30 dk`, `stop_loss: %2.2` hem veritabanına hem UI'a dinamik bağlandı.
- [x] **Çöp Dosyaların Temizlenmesi:** Tüm `scratch_*.py`, `check_orders*.py`, `fetch_*.py` dosyaları `_archive/scratch/` dizinine taşındı.
- [x] **3'lü Test Paketi Onayı:** Tüm testler (`test_openrouter`, `test_execution_gate`, `test_retest_state_machine`) 0 hata ile %100 geçti.
- [x] **DigitalOcean Canlı Dağıtım Senkronizasyonu:** Güncel stabil ve güvenli sürüm (`main`) GitHub ve DigitalOcean'a push edildi, canlı sunucu güncellendi.
- [x] **GitGuardian Gizli Anahtar Temizliği:** `.do/app.yaml`, `stock_telegram_bot.py`, `dev_agent_bridge.py`, `get_chat_id.py` ve denetim raporundaki tüm açıkta kalan Telegram token'ları tamamen temizlendi/redacte edildi ve `type: SECRET` formatına geçirildi.
- [x] **Fox-Borsa (@FoxBorsaBot) Dinamik Token Onarımı:** Bot token'ı kod tabanına asla sızmayacak şekilde Supabase (`global_system_settings`) üzerinden dinamik bağlandı, `getMe` doğrulaması yapıldı ve bot 7/24 aktif edildi.
- [x] **Fox-Borsa Wall Street Otomasyon & Risk Zırhı:**
  - `alpaca_client.py`: Bracket emirler `"day"` yerine `"gtc"` (Good 'Til Cancelled) yapıldı; seans kapanışında stop-loss emirlerinin borsada iptal olması engellendi.
  - `stock_autonomous_worker.py`: Açık pozisyonlar için aktif yazılımsal Stop-Loss (-%1.5) ve Take-Profit (+%3.0) takip ve tasfiye döngüsü eklendi; Telegram bildirimleri entegre edildi.
  - `stock_autonomous_worker.py`: Sabit $1,000 bütçe yerine tenant ayarındaki `max_budget_percent` (%25) üzerinden dinamik pozisyon büyüklüğü ($25,000) hesaplaması getirildi.
  - `app.py`: Dashboard üzerindeki "🔴 Kapat" butonlarının çalıştığı `/api/stock/positions/{symbol}/close` endpoint'i ve canlı bildirim mekanizması tamamlandı.

- [x] **Fiziksel Stop-Loss Mutabakat & Bildirim Onarımı (`reconciliation.py`):**
  - `reconciliation.py` dosyasında `SyntaxError` (eksik `except` bloğu) giderildi.
  - API ve bakiye okuma hatalarında (`port.get("api_error")`) veritabanındaki pozisyonların yanlışlıkla silinmesini engelleyen kalkan eklendi.
  - Binance Global emir tahtasında fiziksel stop-loss limit emri eşleştiğinde (`STOP_LOSS_LIMIT` dolduğunda), sistemin bunu tespit edip veritabanını temizlemesi ve Telegram'a anlık bildirim (`🛑 FİZİKSEL STOP-LOSS TETİKLENDİ`) göndermesi sağlandı.

---
*Son Güncelleme Tarihi: 2026-09-10 (16:45 TSİ)*

