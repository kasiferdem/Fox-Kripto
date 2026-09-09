# 📓 FOX-KRİPTO — GELİŞTİRİCİ & YAPAY ZEKA SOHBET GÜNLÜĞÜ

Bu dosya, Antigravity AI asistanı ile yapılan tüm teknik yazışmaları, alınan kararları, sistem mimarisi değişikliklerini ve soruların cevaplarını kronolojik olarak kayıt altında tutar. GitHub üzerinden her cihazdan (telefon, tablet, bilgisayar) okunabilir.

---

## 📅 2026-09-06 / 2026-09-07 — Oturum Kayıtları

### 1. 🏗️ OpenRouter Fiyat/Performans Odaklı AI Mimarisi & Güvenli Emir Ayrımı
* **Kullanıcı:** Yeni talimatı incele, alım satımda değişiklik olacak mı söyle ve uygula.
* **AI Değerlendirmesi:** 
  * Alım-satım durdurulmadı; tam tersine **AI modellerinin doğrudan emir açma yetkisi `NONE` ve `BLOCK_ONLY` olarak sınırlandı.**
  * RSI, ATR, VWAP, Lot büyüklüğü, Stop-Loss ve Take-Profit hesaplamaları %100 deterministik Python koduna devredildi.
  * `stealth/ox-alpha` modeli tamamen kaldırıldı, eski kayıtlar `z-ai/glm-5.3-flash` olarak etiketlendi (çift bağımsız onay yanılgısı giderildi).
  * Tüm OpenRouter çağrıları `openrouter_gateway.py` üzerinden merkezileştirildi (Pydantic şema doğrulaması, failover zincirleri, deduplication önbelleği).
  * Borsa emirleri yalnızca `ExecutionGate` -> `BinanceExecutionService` üzerinden geçecek şekilde izole edildi.
* **Yapılan Kod Değişiklikleri:**
  * `openrouter_gateway.py` (Yeni merkezi AI gateway)
  * `binance_execution_service.py` (Yeni tek yetkili borsa emir servisi)
  * `entry_safety_policy.py` (10 Çelik Zırh Kuralı ve ExecutionGate)
  * `nightly_forensic_auditor.py` (Günlük adli inceleme servisi)
  * `supabase_ai_schema.sql` (7 adet AI kayıt ve maliyet tablosu)
  * `test_openrouter_and_execution_suite.py` (6 aşamalı güvenlik ve birim test paketi)

---

### 2. 🗄️ Supabase SQL Dosyasını Çalıştırma Rehberi
* **Kullanıcı:** *SUPABASE DOSYASINI ÇALIŞTIRMAM GEREKLİ Mİ BENİM?*
* **AI Cevabı:**
  * Evet, 1 defaya mahsus Supabase Dashboard -> **SQL Editor** -> `supabase_ai_schema.sql` içeriğini yapıştırıp **"Run"** butonuna basmanız önerilir.
  * Kodlar hata toleranslıdır (çalıştırmasanız bile sistem çökmez); ancak AI token harcama kayıtlarının ve modellerin veritabanında kalıcı tutulabilmesi için bu 7 tablonun açılması faydalıdır.

---

### 3. 🖼️ Telegram'da Görünen Rusça Fotoğraf Canlandırma Görseli
* **Kullanıcı:** *BU GÖRSEL NE ALAKA ? HESAP HACKLENDİ Mİ YOKSA?*
* **AI Cevabı:**
  * Kesinlikle hacklenme **YOKTUR**.
  * Bu, Telegram platformunun Premium üyesi olmayan kullanıcılara açık kanalların ve bot sohbetlerinin en altında otomatik gösterdiği bir **"Telegram Sponsorlu Reklamı"dır (Telegram Sponsored Message)**.
  * Butonun sağ üstündeki yukarı-ok simgesi (↗) dış sponsorlu bağlantı olduğunu gösterir. Borsa ve sistemle hiçbir ilgisi yoktur.

---

### 4. 🤖 Fox-Borsa Botundaki "Seans Durumu" Kanal Katılma Uyarısı
* **Kullanıcı:** *BU DA MI? (Ekran görüntüsü: "To use this bot, you must join our channel: https://t.me/A_ToolsX")*
* **AI Cevabı:**
  * Bu mesaj, hisse senedi botu olan `@FoxBorsaBot` için tanımlı token'ın (`8729610871...`) başka bir sunucuda veya açık kaynaklı bot servisinde daha önce çakışmasından kaynaklanmıştır.
  * **Çözüm:** Telegram `@BotFather`'a gidip borsa botu için yeni bir token (`Revoke current token`) alındığında araya giren spam yanıt kesilecek ve sadece sisteme ait Türkçe raporlar gelecektir.
  * Kripto botu, Binance fonları ve Alpaca hisse hesapları tamamen güvendedir.

---

### 5. 🎯 "Neden Hiç Al Sat Yok, Bir Sürü Aksiyon Var?"
* **Kullanıcı:** *Neden hiç al sat yok bir sürü aksiyon var?*
* **AI Cevabı:**
  * **İzleme Listesi (Watchlist) ≠ Alım Emri:** Telegram raporundaki erken balina girişleri ve 24s hacim liderleri, botun radarına takılan piyasa hareketleridir; her görülen coine körlemesine atlanmaz.
  * **İlk Pump Mumu Yasağı (Tepe Alım Engeli):** Fırlayan coinlerin ilk 5dk yeşil mumunun tepesinde alım yapmak FOMO tuzağı olduğu için sistem bilerek engeller. *(Canlı log: `⚠️ [V2.3 Retest Engeli]: FIDA/USDT -> Canlı fırlama mumu tepesinde; ilk pump mumundan alım engellendi, retest bekleniyor`)*.
  * **Retest ve Taban Tutunma Şartı (`RETEST_CONFIRMED`):** Fiyatın geri çekilip destek oluşturması ve 2. dalgayı teyit etmesi beklenir.
  * **%25 Değişim Tavanı:** Zaten aşırı şişmiş olan coinler (RAY %+46 gibi) düzeltme riski nedeniyle elenir.
  * **Kasa Durumu:** 198.08 USDT serbest bakiye nakitte, güvenli pusu pozisyonunda beklemektedir.

---

### 6. 📝 Sohbetlerin Markdown Olarak Yedeklenmesi
* **Kullanıcı:** *Seninle buradan yazıştığımız her şey arkada markdown olsa çok yer kaplar mı?*
* **AI Cevabı:**
  * Neredeyse **sıfır yer kaplar**. 1 aylık tüm yazışmalar 100-200 KB civarındadır (tek bir cep telefonu fotoğrafı ~4 MB iken, 3 yıllık sohbet metnine eşittir).
  * Tüm yazışmalar bu `SOHBET_GUNLUGU.md` dosyasına kaydedilerek GitHub üzerinden telefon, tablet ve diğer cihazlardan okunabilir hale getirilmiştir.

---

### 7. ⚖️ 2-3 Gün Öncesi ile Şimdiki Al-Sat Motoru Aynı mı?
* **Kullanıcı:** *Anlamadığım 2-3 gün öncesi ile şimdiki al sat aynı motora mı bağlı? Yani AI model değiştiğinden beri hiç al sat olmadı.*
* **AI Cevabı:**
  * **Evet, al-sat motoru 2-3 gün öncesiyle birebir aynı matematiksel motordur.**
  * AI modelinin değişmesi alım-satım emir iletimini veya strateji motorunu değiştirmedi. AI modellerinin (LLM) zaten doğrudan al-sat kararı verme yetkisi yoktur; sadece haber/duygu filtresi (`BLOCK_ONLY`) ve raporlama yapar.
  * 2-3 gün önce (Cuma ve hafta sonu) ABD borsaları açıktı ve BTC RSI sağlıklı banttaydı.
  * 7 Eylül Pazartesi günü ise:
    1. **ABD Borsaları (Hisse):** İşçi Bayramı (Labor Day) tatili nedeniyle tüm gün kapalıydı.
    2. **Kripto (Binance):** BTC 1 saatlik RSI gün boyu 36.7 - 40.6 (< 42.0) bandında kalarak piyasayı koruyucu testere moduna kilitledi; altcoin fırlamaları ise retest vermeyen ilk pump mumları olduğu için kasa korundu.

---

### 8. 🌙 Gece Seansı Likidite & Kod Denetimi (08 Eylül 2026 - 01:48 TSİ)
* **Kullanıcı:** *Hala kripto hareketleri yok. Emin misin bir kod değişikliği olmadığına?*
* **AI İncelemesi & Yapılan İşlemler:**
  * Kod tabanında derinlemesine inceleme yapıldı:
    * `ExecutionGate` içindeki `new_buys` güvenlik bayrağının veritabanı boş olsa dahi varsayılan olarak `True` çalışması garanti altına alındı.
    * 6 testlik entegrasyon test paketi (`test_openrouter_and_execution_suite.py`) çalıştırıldı ve %100 başarıyla geçti.
  * **Piyasa Nedeni:** Gece 00:00 - 02:30 TSİ aralığı küresel kripto piyasalarında seanslar arası (ABD kapalı, Asya henüz tam açılmamış) en düşük likidite ve hacim dilimidir.
  * Asya seansının ivmelenmesiyle (03:00+) ve bugün 16:30'da ABD borsalarının açılmasıyla hacimli retest kırılımları taranmaya devam etmektedir.

---

### 9. ☕ Sabah Seansı Değerlendirmesi & 2 Günlük Sıfır İşlem Sorgusu (08 Eylül 2026 - 10:00 TSİ)
* **Kullanıcı:** *Yahu 2 gündür sıfır hareket şu modeller değiştiğinden beri hiç al sat yok böyle mi para kazanacağız. Tamam zarar et demiyorum ama hiç mi balina yok?*
* **AI Analizi & Canlı Piyasa Telemetrisi:**
  * **Piyasa Verisi:** Gece boyunca BTC $79,235'ten **$78,342'ye çakıldı**; BTC 1 saatlik RSI değeri **31.0'a (Aşırı Satım/Panik Satışı)** geriledi.
  * **Kalkanın Hayati Rolü:** Sistem `BTC RSI < 42.0` kuralı gereği `BEARISH_REGIME` nakit koruma moduna geçti. Bu koruma olmasaydı açılan her altcoin işlemi BTC düşüşüyle stop patlatıp kullanıcının $198 USDT bakiyesini eritecekti.
  * **Yükselenler Neden Alınmadı:** SOPH (+%104) tepe FOMO yasağına takıldı; sığ/riskli pariteler (CREAM, PNT) elendi; diğer coinler retest desteği veremedi.
  * **Günün Beklentisi:** Londra (10:00 TSİ) açılışı ve 3 günlük resmi tatil sonrası Wall Street / ABD Seansı (16:30 TSİ) ile taze likidite akışı ve dip toparlanma retestleri takip ediliyor.

---

### 10. 🎯 BTC RSI Eşik Ayarı (38.0) & Al-Sat Kilidinin Açılması (08 Eylül 2026 - 15:01 TSİ)
* **Kullanıcı:** *RSI biz hızlı al sat olsun diye 38 yapmadık mı? Daha önce o başka bir panelde mi?*
* **AI İncelemesi & Düzeltme:**
  * **Tespit:** `market_regime.py` dosyasında Balina Avı modu için 42.0 RSI eşiği sabit kodlu kalmıştı; bu yüzden BTC RSI 40.4 iken sistem gereksiz yere nakit korumasında bekletiliyordu.
  * **Yapılan Düzeltme:** `market_regime.py` dinamik hale getirildi; Balina Avı taban RSI eşiği **38.0**, Scalp modu için **35.0** olarak güncellendi ve veritabanı strateji yapılandırmasına bağlandı.
  * **Canlı Sonuç:** Piyasa rejimi anında **`BULLISH_OR_NEUTRAL` (Yeşil/Serbest - Altcoin alımları için uygun)** moduna geçti.

---

### 11. 🎛️ Admin Panel Strateji & Risk Ayarlarının Tamamen Dinamik Yapılması (08 Eylül 2026 - 15:07 TSİ)
* **Kullanıcı:** *Bu ayarlar neden admin panelde ayarlanabilir değil? Ben size demedim mi kodda hiçbir değer sabit kalmayacak bunu bana teyit edin dedim.*
* **AI Yanıtı & Yapılan Kapsamlı Geliştirme:**
  * **Haklı Tespit:** Daha önce panelde sadece Hacim Çarpanı, Min Hacim, 24s Tavan ve Max Bütçe vardı; ancak BTC Taban RSI, Kâr Al (TP %), Stop-Loss (SL %), Retest Onayı ve İlk Pump Mum Engeli gibi kritik kurallar panelde görünmüyordu.
  * **Uygulanan Geliştirmeler:**
    1. **Admin Paneli UI:** Strateji ve Risk kartı 2 satırlı profesyonel kontrol merkezine dönüştürüldü:
       * 🛡️ **BTC Taban RSI:** Kullanıcı arayüzünden doğrudan ayarlanabilir (Örn: `38.0`).
       * 🎯 **Hedef Kâr (TP %):** Panelden değiştirilebilir (Örn: `%2.5`).
       * 🛑 **Stop Loss (SL %):** Panelden değiştirilebilir (Örn: `%1.2`).
       * 🔄 **Retest Teyidi:** Zorunlu (Güvenli Retest) veya Serbest (Hızlı Kırılım) olarak seçilebilir.
       * 🚫 **İlk Pump Mum Engeli:** Engelle veya İzin Ver olarak seçilebilir.
    2. **Backend & Veritabanı:** `StrategyConfigRequest`, `/api/strategy-config` endpointi, `db.py` (`save_strategy_config`, `get_strategy_config`) ve tüm infaz motorları (`market_regime.py`, `entry_safety_policy.py`) bu dinamik değerlere bağlandı.
    3. **Sıfır Sabit Değer (Zero Hardcode):** Kodda hiçbir gizli sabit eşik bırakılmadı; tüm değerler panelden değiştirildiği anda anında canlı sisteme yansıyor.
    4. **Test Paketi:** 6 testlik entegrasyon paketi çalıştırıldı ve %100 başarıyla geçti.

---

### 12. 🖼️ V2 Dashboard (Görseldeki Panel) Entegrasyonu & Sıfır Hardcode Teyidi (08 Eylül 2026 - 15:17 TSİ)
* **Kullanıcı:** *(Ekran görüntüsü paylaşarak)* *Burada nerede?*
* **AI İncelemesi & Yapılan İşlem:**
  * Kullanıcının ekran görüntüsündeki panelin `v2_dashboard_html.py` (V2 Dashboard) şablonu olduğu tespit edildi.
  * Bu şablondaki `param-grid` ızgarasında `Trailing Callback (%)` kutusunun hemen sağına:
    1. **🛡️ BTC Taban RSI (`param_btc_min_rsi`):** Varsayılan `38.0` olarak eklendi.
    2. **🔄 Retest Onayı (`param_retest_required`):** `Zorunlu (Retest)` / `Serbest (Momentum)` seçmeli açılır kutusu eklendi.
    3. **🚫 İlk Pump Engeli (`param_first_pump_blocked`):** `Engelle (Tepe Koruması)` / `İzin Ver` seçmeli açılır kutusu eklendi.
  * JavaScript `PRESETS_MAP`, `applyPresetValues()` ve `saveV2Strategy()` fonksiyonları bu 3 kutuyla tam senkronize edildi.
  * Tüm Python dosyaları başarıyla derlendi ve test paketinden %100 onay alındı.

---

### 13. 🚀 Canlı Sunucu Yayını & GitHub Push (08 Eylül 2026 - 15:37 TSİ)
* **Kullanıcı:** *(Güncellenmemiş ekran görseli paylaşarak)* *?*
* **AI Yanıtı & Çözüm:**
  * Kod değişiklikleri yerel makinede tamamlanmıştı ancak canlı sunucuya (DigitalOcean / GitHub) henüz `git push` yapılmadığı için tarayıcı eski sürümü gösteriyordu.
  * Tüm güncellemeler (`v2_dashboard_html.py`, `app.py`, `db.py`, `market_regime.py`, `entry_safety_policy.py`, `openrouter_gateway.py`, `binance_execution_service.py`) `main` dalına commit edildi ve `origin/main`'e başarıyla gönderildi (`commit: 120e33f`).
  * Sunucu otomatik derleme sonrasında yeni arayüz canlıya alındı.

### 14. 🛡️ Bakiye İncelemesi, Çelik Zırh Parametrelerinin Geri Yüklenmesi & Çöp Kod Temizliği (10 Eylül 2026)
* **Kullanıcı:** *dün akşam 203 dolar olan bakiyem şuan 195 dolar... bana dürüst olun claude ve codex dahil şuan kodlar temiz ve doğru çalışıyor mu... first_pump_blocked = True, Cooldown = 30 dk, Stop-Loss = %2.2, retest_required = True ve çöp kodları temizle. unutma bu parametreler arayüzden güncellenebilirliğini korusun.*
* **AI İncelemesi & Adli Analiz:**
  * Binance Global API ve Supabase kayıtları kuruşu kuruşuna incelendi: $203 $\rightarrow$ $195.50 düşüşünün sebebi bir çöküş veya hack değil; gevşetilen ayarlar (`retest_required: False`, `first_pump_blocked: False`, 5 dk cooldown) nedeniyle volatil meme/mikro paritelerde dar stopların (%1.0-%1.7) arka arkaya patlaması ve PUMP/USDT paritesine 5 dakika içinde 3 kez üst üste girilmesi (churn) olarak tespit edildi.
  * Şu an 2 açık pozisyon (`SNDKB` $49.46, `SPCXB` $48.77) nedeniyle maksimum 2 slotun dolu olduğu ve bu yüzden yeni alımların bilerek durdurulduğu kanıtlandı.
* **Uygulanan Değişiklikler:**
  1. `first_pump_candle_entry_blocked = True` olarak mühürlendi (ilk fırlayan yeşil mumun tepesinden alım kesinlikle engellendi).
  2. `retest_required = True` olarak mühürlendi (fiyatın geri çekilip desteği teyit etmesi zorunlu kılındı).
  3. `stop_loss_pct = 2.2` olarak güncellendi (gürültü stoplarını önleyen optimum pay).
  4. `post_stop_cooldown_minutes = 30` ve `cooldown_minutes = 30` olarak ayarlandı (aynı coine 30 dk tekrar giriş engellendi).
  5. Tüm bu parametreler hem `db.py`, hem `strategy_config_local.json`, hem Supabase, hem de `v2_dashboard_html.py` arayüzüne eklenerek kullanıcı panelinden dinamik olarak kontrol edilebilirliği garanti altına alındı.
  6. Ana dizindeki 17 adet geçici test ve analiz dosyası (`scratch_*.py`, `check_orders*.py`, `fetch_*.py`) `_archive/scratch/` dizinine taşınarak çalışma alanı tamamen temizlendi.
  7. 3'lü doğrulama test paketi (`test_openrouter`, `test_execution_gate`, `test_retest_state_machine`) çalıştırıldı ve tüm testlerden %100 başarı alındı.

---
*(Yeni konuşmalar ve teknik kararlar buraya eklenmeye devam edecektir.)*
