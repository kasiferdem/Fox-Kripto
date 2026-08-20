# 🦊 Fox-Kripto Proje Durumu ve Hafıza Dosyası (STATUS.md)

> **Bu dosya, Antigravity AI asistanlarının yeni sohbet oturumlarında projenin neresinde olunduğunu anında hatırlaması için otomatik güncellenen canlı durum belgesidir.**

---

## 📌 Proje Özeti
- **Proje Adı:** Fox-Kripto (Otonom Kripto Analiz, Takip ve İnsan-Onaylı Alım-Satım Sistemi)
- **Teknoloji Yığını:** Python 3.12, FastAPI, LangGraph, OpenAI GPT-4o / Claude 4.5 (OpenRouter), CCXT (Binance), Supabase (PostgreSQL), Telegram Bot API
- **GitHub Reposu:** `kasiferdem/Fox-Kripto`

---

## 🛠️ Tamamlanan Özellikler (Yapılanlar)

1. **LangGraph Otonom Ticaret Akışı (`graph.py`, `state.py`, `prompts.py`):**
   - Piyasa analizi, duyarlılık skoru (`sentiment_score`) hesaplama.
   - Katı bütçe (%10 maks) ve Stop-Loss (%3 - %5) kuralları ile otomatik alım-satım stratejisi üretme.
   - İnsan Onay Mekanizması (Human-in-the-Loop interrupt).

2. **Telegram Bot Entegrasyonu (`telegram_bot.py`, `telegram_poller.py`, `get_chat_id.py`):**
   - `@FoxKriptoBot` entegrasyonu.
   - Butonlu `[ ✅ İŞLEMİ ONAYLA ]` / `[ ❌ REDDET ]` Onay Kartları.
   - Arka planda 7/24 Telegram mesaj ve buton dinleyici poller.

3. **Veritabanı ve Borsa Entegrasyonu (`db.py`, `exchange.py`, `schema.sql`):**
   - Supabase PostgreSQL kayıt (`crypto_trade_logs`, `crypto_agent_states`, `user_tenants`).
   - CCXT Binance API ile bakiye, canlı fiyat çekme ve spot emir infazı.

4. **Multi-Tenant Dashboard Web Arayüzü (`app.py`):**
   - FastAPI tabanlı Glassmorphism canlı yönetim paneli (`http://localhost:8000/dashboard`).
   - 7/24 arka plan otonom piyasa tarama ve otomatik emir infaz döngüsü.

5. **Deployment Hazırlığı (`Dockerfile`, `Procfile`, `.do/app.yaml`):**
   - DigitalOcean App Platform için yayına alma dosyaları hazır.

---

## ⚙️ Çalıştırma Komutları

```bash
# 1. Sanal ortamı aktifleştirme (varsa)
.venv\Scripts\activate

# 2. Bağımlılıkları yükleme
pip install -r requirements.txt

# 3. Telegram Chat ID tespiti (ihtiyaç halinde)
python get_chat_id.py

# 4. Web Paneli + Otonom Botu Çalıştırma (EN ÖNEMLİ)
python app.py
```
*Web Arayüzü:* `http://localhost:8000/dashboard`  
*Giriş Bilgileri:* `admin` / `foxkripto2026`

---

## 🎯 Yapılacaklar Listesi (Kalan Adımlar & Roadmap)

- [ ] **Canlı / Paper Trading Testi:** Borsa API bağlantısı ile küçük tutarlı gerçek test işlemi yapılması.
- [ ] **DigitalOcean Deployment:** Projenin canlı sunucuya push edilerek 7/24 kesintisiz sunucuda çalıştırılması.
- [ ] **İndikatör Çeşitlendirme:** RSI, MACD ve Bollinger bandı haricinde ek teknik göstergelerin `prompts.py` ajanına beslenmesi.

---
*Son Güncelleme Tarihi: 2026-08-14*
