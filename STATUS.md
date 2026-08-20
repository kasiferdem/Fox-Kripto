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

1. **Güvenlik ve Kimlik Doğrulama (P0 Düzeltmeleri Tamamlandı):**
   - Kaynak koddan tüm sızıntı/hardcoded anahtarlar temizlendi (`prompts.py`).
   - Tüm güvensiz admin execution rotaları silindi; yönetim uç noktaları `HTTPBasic` (`ADMIN_USERNAME` / `ADMIN_PASSWORD`) ile kilitlendi.
   - Telegram poller `from.id` ve allowlist bazlı sıkı yetkilendirmeye geçirildi.

2. **LangGraph & Borsa İnfazı (`graph.py`, `exchange.py`, `atr_calculator.py`):**
   - Çift borsa (Binance TR + Binance Global) ve Sanal Paper Trading istemcisi.
   - Gerçek VWAP ve borsa stop emirleri.
   - Pozisyon çıkışlarında dinamik ATR seviyesi ve Supabase DB ledger senkronizasyonu.

3. **Veritabanı ve Ledger (`db.py`):**
   - Supabase PostgreSQL: `user_tenants`, `crypto_agent_states` (pozisyonlar, soğuma, trading modu, sanal bakiye), `crypto_trade_logs` (işlem geçmişi ve coin karnesi).

---

## ⚙️ Güvenli Çalıştırma

```bash
# Web Paneli + Otonom Botu Çalıştırma
python app.py
```
*Web Arayüzü:* `http://localhost:8000/dashboard` (Ortam değişkeninde tanımlı `ADMIN_USERNAME` ve `ADMIN_PASSWORD` ile giriş yapılır).

- [ ] **Canlı / Paper Trading Testi:** Borsa API bağlantısı ile küçük tutarlı gerçek test işlemi yapılması.
- [ ] **DigitalOcean Deployment:** Projenin canlı sunucuya push edilerek 7/24 kesintisiz sunucuda çalıştırılması.
- [ ] **İndikatör Çeşitlendirme:** RSI, MACD ve Bollinger bandı haricinde ek teknik göstergelerin `prompts.py` ajanına beslenmesi.

---
*Son Güncelleme Tarihi: 2026-08-14*
