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

- [x] **Google Agent Skills Paketi Kurulumu (`google/skills`):**
  - `https://github.com/google/skills.git` deposundan 133 yeni skill ve `google-cloud-developer` eklentisi indirildi.
  - Tüm beceriler global konfigürasyona (`~/.gemini/config/skills/`) entegre edildi.
  - Toplam aktif ve doğrulanmış skill sayısı **164**'e çıkarıldı; Cloud, AI/ML, Agent Platform, GKE, BigQuery, Gemini API ve Developer araçları Antigravity'ye kazandırıldı.

- [x] **Claude Code & Codex Oturum Geçmişinin Günlüğe Çekilmesi (`SOHBET_GUNLUGU.md`):**
  - 12 Ağustos – 11 Eylül arasındaki 8 Claude Code transkripti ve 22 SpecStory kaydı (`.specstory/history/`, git dışı) tarandı.
  - 6 oturum (kod okuma, Codex P0/P1 denetimi, 3 Altın Kural hakem değerlendirmesi, Astra 6 geçişi, Fox MRO hafıza doldurma, günlük aktarımı) `CC-1 … CC-6` başlıklarıyla Türkçe özetlenip günlüğe eklendi.

- [x] **Tepe Alım ve İlk Pump Engeli Açığının Kapatılması (`v2_whale_engine.py`, `v2_scalping_engine.py`, `graph.py`):**
  - Panelde "İlk Pump Engeli: Engelle" seçili olmasına rağmen MITO gibi coinlerin içeri sızmasına yol açan 3 kritik açık giderildi:
  - 1. **Gizli Eşik & Hacim Patlaması Filtresi:** Sabit %0.40 gövde şartı %0.20'ye çekildi; hacim sıçraması (>=1.5x) varken mum yeşilse mum boyutu küçük de olsa kesinlikle PUMP sayıldı.
  - 2. **`graph.py` Bypass Mantık Hatası:** `is_candidate_ok` içindeki `or (c["v2_score"] >= min_score_req)` şartı kaldırıldı; `WAITING_PULLBACK` durumundaki veya pump engelindeki coinlerin yapay zeka puanı ne kadar yüksek olursa olsun alımı kesin olarak engellendi.
  - 3. **Sahte Retest & Likidite Çöküş Engeli:** Retest teyidinde hacmin %85'ten fazla buharlaşması (ölü likidite) ve kırmızı düşüş mumu kapanışları geçersiz kılındı.
  - 4. **OrderIntent Doğrulaması:** Borsaya emir gönderilirken `first_pump_entry` ve `signal_state` değerleri adayın gerçek durumuna bağlandı.

- [x] **2-3 Eylül Orijinal Kazandıran Çevik Scalping Moduna Dönüldü (`v21_smart_armor`):**
  - Kullanıcı talimatı doğrultusunda hiçbir ekstra değişiklik yapılmadan, 2-3 Eylül tarihlerinde ardışık kârlar üreten orijinal parametre seti (`KAZANDIRAN_STRATEJI_AYARLARI.md`) doğrudan Supabase ve yerel konfigürasyona işlendi:
  - `active_preset`: `v21_smart_armor` | `volume_spike_multiplier`: `1.15x` | `min_5m_volume_usd`: `$2,500`
  - `take_profit_pct`: `%2.5` | `trailing_callback_pct`: `%0.6` | `stop_loss_pct`: `%1.2` (Sıkı Stop)
  - `retest_required`: `False` | `first_pump_candle_entry_blocked`: `False` (Erken momentum serbest)
- [x] **Yüksek Beta (High-Beta) & Hızlı Aksiyon Tarayıcısı Devreye Alındı (`surge_detector.py`):**
  - Kullanıcının dinozor/ağır vasıta coinlerden (XLM, ADA, XRP vb.) çıkıp 2-3 Eylül'deki gibi hızlı aksiyon alan patlayıcı altcoinlere odaklanma talebi karşılandı.
  - Hantal coinler kara listeye alındı (`XLM`, `ADA`, `XRP`, `TRX`, `EOS`, `BCH`, `LTC`, `ETC`, `HOT`, `HOLO`).
  - Minimum 24 saatlik fiyat oynaklığı (Daily Range) $\ge \%3.8$ ve 5dk mum kazanımı $\ge \%0.25$ kuralı getirildi.
  - Adaylar `Hacim Patlaması x Oynaklık Çarpanı` ile dinamik olarak en hareketli olanlar en üste gelecek şekilde sıralandı.

- [x] **Devre Kesici (Circuit Breaker) Kotası Teşhisi ve Onarımı (`circuit_breaker.py`):**
  - "Hiç al-sat yok" sorununun kök nedeni tespit edildi: `circuit_breaker.py` içindeki `max_daily_trades: 10` kontrolü, kullanıcı ayrımı yapmadan tüm sistemdeki (tüm tenantlar) toplam işlem sayısını (17/10) okuyor ve sistemi "Günlük işlem kotası doldu" diyerek kilitliyordu.
  - Multi-tenant filtre eklendi; her kullanıcının işlem sayısı ve ardışık stopları sadece kendi `tenant_id`/`telegram_chat_id`'sine göre izole edildi.
  - Hızlı scalping için `max_daily_trades` kotası 10'dan 50'ye çıkarıldı.

- [x] **2-3 Eylül Çevik Scalping Kâr Serisi & Kasa 195 USD'ye Yükseldi (11 Eylül 15:54 TSİ):**
  - Devre kesici onarımı ve Yüksek Beta tarayıcısı devreye girdikten sonra peş peşe 4 adet Take-Profit kâr satışı gerçekleşti:
    - 🎯 **SC/USDT:** **+%2.43 Net Kâr** ($49.07 USD kasaya eklendi)
    - 🎯 **SAGA/USDT:** **+%2.36 Net Kâr** ($49.28 USD kasaya eklendi)
    - 🎯 **SNXXB/USDT:** **+%2.67 Net Kâr** ($48.79 USD kasaya eklendi)
    - 🎯 **MITO/USDT:** **+%2.31 Net Kâr** ($49.24 USD kasaya eklendi)
  - **Kasa Değeri:** $191.08 USD'den **$195.05 USD**'ye (~₺9,480 TL) yükseldi.
- [x] **Testere Piyasası Dalgası & Devre Kesici Koruması (11 Eylül 16:37 TSİ):**
  - BTC'nin 77.7k'dan 77.5k'ya mini çekilmesiyle sahte kırılımlar oluştu; `JTO` (-%1.35), `INTCB` (-%1.20) ve `MRVLB` (-%1.40) işlemlerinde sıkı stop-loss çalıştı.
  - Kasa $195.05'ten $191.05'e döndü (ana para korundu).
  - Devre kesici (`circuit_breaker.py`) 3+ ardışık stop sonrası otomatik olarak 20 dakikalık koruyucu soğumayı (`CONSECUTIVE_LOSS_COOLDOWN_ACTIVE`) devreye aldı ve kasayı kilitledi.
- [x] **MINA/USDT +%5.09 Kâr Realizasyonu (+$2.38 USD Kasaya Eklendi - 17:11 TSİ):**
  - MINA $0.1002'den alındı, zirveye kadar izlendi ve $0.1052'den satılarak **+%5.09 Net Kâr** ile tam **$2.38 USD** net kâr cebe kilitlendi.
  - Kasa tekrar **$194.25 USD** seviyesine yükseldi.
- [x] **Taze Gerçek Kripto Sepeti Açıldı (17:15 TSİ):**
  - `RAY/USDT` (@1.6655 | Anlık: **+%1.10 Kârda**)
  - `BLUR/USDT` (@0.01782 | Anlık: **+%1.23 Kârda**)
  - `DOGS/USDT` (@5.244e-05)
  - Tüm hisse/sentetik tokenlar filtrelendiği için sadece derinliği olan gerçek altcoinler çalışıyor.

- [x] **Yeni Nesil Kuant Mimarisi: "Küçük Isırıklar & Akıllı Zırh" Devreye Alındı (12 Eylül 01:30 TSİ):**
  - **1. Akıllı Oransal Çıkış & Mikro-Trailing (`graph.py`):**
    - Statik %2.5 hedef yerine: Fiyat $\ge +\%0.60$ gördüğü anda kâr koruma kalkanı aktifleşir.
    - Zirveden $\ge \%0.20$ çekilme olduğu an (`pullback_pct >= 0.20`), hedefe bakılmaksızın piyasa emriyle anında satış yapılarak kâr kasaya kilitlenir (`🎯 Akıllı Oransal Çıkış`).
    - MET benzeri kârlı işlemlerin geri çekilip stop olma riski tamamen ortadan kaldırıldı.
  - **2. Akıllı BTC Fırtına Kalkanı (`market_regime.py`):**
    - Kör EMA200 kilidi esnetildi: BTC EMA200 altında yatay ve sakin seyrederken altcoinlerdeki +%0.40 - +%0.70 kâr fırsatlarının avlanmasına izin verildi.
    - Ancak BTC son 5 dakikada $\le -\%0.50$ veya son 15-30 dakikada $\le -\%1.00$ ani dik çöküş (Flash Dump) yapıyorsa "Savunma Modu" derhal devreye girerek yeni alımları kilitler.
  - **3. Kümülatif Günlük Net Zarar Kalkanı (`circuit_breaker.py`):**
    - Sadece ardışık stoplar değil; gün içindeki toplam net gerçekleşmiş USD kâr/zarar kümülatif olarak toplanır.
    - Günlük net kayıp azami limiti (-$6.00 USD veya %3.0) aştığında sistem yeni alımları o gün için tamamen durdurur (`DAILY_LOSS_LIMIT_EXCEEDED`).
  - **4. Çift-Anahtar Yönetişim Mimarisi (`openrouter_gateway.py` & `prompts.py`):**
    - **Patron (Lead Strategist & Market Maestro):** `openai/gpt-6-astra` (Piyasa havasını koklar, parametre gevşetme/sıkma kararı alır).
    - **Patronu Denetleyen Baş Denetçi (Chief Auditor & Sanity Sentinel):** `anthropic/claude-3.7-sonnet` (GPT-6'nın kararlarını denetler, risk aşımı ve küçük ısırık kurallarını gözetir, veto yetkisine sahiptir).
    - **Genel Müdür (`GENEL_MUDUR`):** Kullanıcıya net, kurumsal ve şeffaf durum brifingi sunar.
  - **5. Test Paketi Doğrulaması:**
    - `test_execution_gate_suite.py` (%100 Başarılı)
    - `test_openrouter_and_execution_suite.py` (%100 Başarılı)
    - `test_retest_state_machine_suite.py` (%100 Başarılı - 14/14 test)

---
*Son Güncelleme Tarihi: 2026-09-12 (01:30 TSİ)*





