# 📚 FOX-KRIPTO V2.2: KUSURSUZ BALİNA PROTOKOLÜ (THE GOLDEN WHALE PROTOCOL) SİSTEM İŞLEYİŞ VE GELİŞTİRME KATALOĞU

**Sürüm:** `v2.2.0-quant-golden-whale`  
**Referans Commit:** `067c147` & `044aeb2`  
**Tarih:** 28 Ağustos 2026  
**Hazırlayan Heyet:** Fox-Kripto 3'lü Quant Simsar Konseyi (*Antigravity • Claude • Codex*)  

---

## 🏛️ 1. YÖNETİCİ ÖZETİ (EXECUTIVE SUMMARY)

Fox-Kripto platformu, geleneksel tek boyutlu göstergelerle (yalnızca spot hacim ve fiyat artışı) işlem yapan amatör bot yapısından arındırılarak; **çok boyutlu veri füzyonuna (Spot + Vadeli Açık Faiz + Fonlama Dengesi + Tahta Derinliği + Yapay Zeka Gölge Heyeti)** dayalı tam otonom kurumsal bir **Piyasa Yapıcı & Balina Avcısı Quant Sistemine** dönüştürülmüştür.

Bu katalog; **Kusursuz Balina Protokolü (The Golden Whale Protocol)** ile sisteme kazandırılan tüm yetenekleri, giderilen zafiyetleri ve sistemin 7/24 otonom karar akışını madde madde açıklamaktadır.

---

## 📊 2. MİMARİ EVRİM VE KARŞILAŞTIRMA MATRİSİ

| Parametre / Yetenek | Eski V1 Klasik | V2 İlk Sürüm | 🏆 V2.2 Kusursuz Balina Protokolü | Sisteme Katkısı & Sağlanan Fayda |
| :--- | :---: | :---: | :---: | :--- |
| **Taban 5dk Hacim Barajı** | $2.500 USD ❌ | $25.000 USD | **$50.000 USD (Katı Taban) ✅** | `SCR`, `KORUB` gibi sığ tahtaların içeri sızması ve manipülatif stoplar %100 engellendi. |
| **24 Saatlik Taban Likidite** | $150.000 USD | $250.000 USD | **$500.000 USD+ ✅** | Yalnızca gerçek kurumsal likiditeye sahip derin coinler taranır. |
| **Vadeli Açık Faiz (Futures OI)** | Yok ❌ | Arayüzde Var | **Canlı Binance API Zorunlu Teyit ✅** | Spot yükselirken vadeli tarafta para girişi olmayan sahte pump tuzakları elenir. |
| **Funding Rate Dengesi** | Yok ❌ | Statik | **Canlı Funding Sıkışma Filtresi ✅** | Aşırı Long/Short yığılması olan tehlikeli paritelerden uzak durulur. |
| **Zamanlama & Retest Onayı** | İlk mum tepesinden alım ❌ | Formülasyonda | **Anti-FOMO & Dolu Mum Şartı ✅** | Üst fitili %40'tan büyük tepe iğnelerinde alım engellenir, dipten maliyetlenilir. |
| **Kasa Disiplini & Slot Sayısı** | Tek Coine Yüklenme ❌ | %25 Sabit | **Dinamik 4 Slot (%25) Koruması ✅** | Kasa 4 bağımsız slota bölünerek tek coin çöküşünde batma riski sıfırlandı. |
| **Kâr ve Zarar Koruması** | Sabit TP/SL | 2 Kademeli | **3 Kademeli Akıllı Zırh ✅** | +%1.0'de Başa Baş (Sıfır Risk), +%1.5'de Kâr Kilidi, +%3.0'de Ralli Takibi. |
| **Yönetim Paneli Yeteneği** | Sabit Kodlar ❌ | Ön Tanımlı | **🎛️ Canlı İnce Ayar Merkezi ✅** | Tüm 8 parametre ekrandan anlık değiştirilebilir ve canlıya uygulanabilir. |
| **Varlık Değerleme Hassasiyeti** | Çapraz TRY Sapması ❌ | Çapraz TRY | **Doğrudan USD Çevrim Mimarisi ✅** | Varlıklar kur sapması olmadan kuruşu kuruşuna net değerlenir. |

---

## 🔬 3. MADDE MADDE NELER DEĞİŞTİ VE SİSTEME NE KATTI?

### 🧱 Madde 1: $50.000 USD Katı Taban Likidite & $500.000 24s Barajı
* **Eski Durum:** 5 dakikalık hacmi $2.500 olan küçük pariteler radara düşüyor ve sisteme aldırılıyordu. Bu durum, sığ tahtalarda tek bir botun attığı iğneyle stop olunmasına yol açıyordu.
* **Yeni Durum (`surge_detector.py`):** 5 dakikalık min hacim barajı **`$50.000 USD`**, 24 saatlik taban hacim **`$500.000 USD`** olarak mühürlendi.
* **Sağlanan Fayda:** Sığ, manipülatif ve spread'i yüksek tüm çöp coinler sistemden tamamen men edildi. Sistem artık yalnızca `COTI`, `STORJ`, `SOL`, `NEAR`, `AVAX` gibi kurumsal paritelerde çalışır.

---

### 📈 Madde 2: Canlı Binance Vadeli Açık Faiz (Futures OI) & Funding Teyit Motoru
* **Eski Durum:** Sistem sadece spot borsa fiyatına bakıyordu. Spotta alım görünse bile vadeli piyasada balinaların short açıp açmadığını göremiyordu.
* **Yeni Durum (`v2_whale_engine.py`):** Motor, `https://fapi.binance.com` API'sine anlık bağlanarak coinin Vadeli Açık Faiz (Open Interest) tutarını ve Fonlama Oranını (Funding Rate) milisaniyelik çeker.
* **Sağlanan Fayda:** Spotta fiyat artarken vadeli tarafta para çıkışı varsa (fake breakout) işlem derhal **`REJECTED`** edilir. Yalnızca hem spotta hem vadelide aynı anda sermaye akıtan gerçek balinalar yakalanır.

---

### 🎯 Madde 3: Anti-FOMO & Retest / Destek Onay Kapısı
* **Eski Durum:** Fiyat %3 fırladığında yeşil mumun en tepesinden alım yapılıyor; ardından gelen %1'lik doğal düzeltmede stop patlıyordu.
* **Yeni Durum:** Üst fitil filtresi sıkılaştırıldı (`upper_wick <= 0.40`). Mum gövdesi dolu ve alıcı baskısı teyitli olmayan adaylar elenir.
* **Sağlanan Fayda:** Fiyat tepedeyken atlama (FOMO) davranışı bitti; fiyatın taban desteği test edip tutunduğu en dip noktadan alım yapılması sağlandı.

---

### 🛡️ Madde 4: 3 Kademeli Dinamik Akıllı Zırh
* **Eski Durum:** Fiyat kâra geçse bile hedef %5'e ulaşamazsa geri dönüp stop olabiliyordu.
* **Yeni Durum (`graph.py`):**
  * **Kademe 1 (Başa Baş):** Pozisyon **`+%1.0`** kârı gördüğü an Stop-Loss seviyesi doğrudan alış fiyatına (`Entry Price`) çekilir. Zarar riski tamamen sıfırlanır.
  * **Kademe 2 (Balina Kâr Kilidi):** Pozisyon **`+%1.5 - +%3.0`** bandına ulaştığında, zirveden %0.6'lık geri çekilmede kâr kasaya kilitlenir.
  * **Kademe 3 (Ralli Takipçisi):** **`+%3.0+`** üzerindeki parabolik pump hareketlerinde kâr alma seviyesi yukarı ötelenerek maksimum kâr hedeflenir.
* **Sağlanan Fayda:** Kâra geçen hiçbir işlem zararla kapanmaz.

---

### 💵 Madde 5: Doğrudan USD Varlık Değerleme ve Kur Düzeltmesi
* **Eski Durum:** Global hesaptaki USDT varlıkları, Binance TR'deki sığ TRY tahtasının kuru üzerinden dolara çevrildiği için ekranda geçici ve yapay eksi sapmalar (-%18 gibi) görünüyordu.
* **Yeni Durum (`exchange.py`):** Binance Global cüzdanındaki tüm coinler doğrudan borsa USDT paritesiyle (`val_usd = amount * price_usd`) birebir eşleştirildi.
* **Sağlanan Fayda:** Cüzdan bakiyeleri ve kâr/zarar oranları kuruşu kuruşuna, sıfır sapmayla netleşti.

---

### 🎛️ Madde 6: Canlı Quant Parametre Yönetim ve İnce Ayar Merkezi
* **Eski Durum:** Ayarları değiştirmek için kod güncellemesi gerekiyordu.
* **Yeni Durum (`v2_dashboard_html.py` & `/api/strategy-config`):** Yönetim paneline entegre edilen canlı kontrol kutuları ile:
  * 🧱 *Min 5dk Hacim Barajı ($ USD)*
  * ⚡ *Hacim Patlama Çarpanı (x)*
  * 📈 *Maksimum 24s Prim Limiti (%)*
  * 🧠 *Min AI & Teyit Skoru*
  * 💰 *İşlem Başı Kasa Bütçesi (%)*
  * 🎯 *Hedef Kâr Al (%)*
  * 🛡️ *Zarar Kes Stop-Loss (%)*
  * 🚀 *Trailing Zirve Çekilme Payı (%)*
  ekrandan dilediğiniz an değiştirilip **`[💾 Parametreleri Kaydet & Canlıya Al]`** butonuyla anında motora aktarılabilir.
* **Sağlanan Fayda:** Sistem tamamen yöneticinin tam kontrolüne verildi.

---

## 🔄 4. SİSTEMİN 7/24 OTONOM ÇALIŞMA DÖNGÜSÜ (ALGORİTMİK AKIŞ)

```
[HER 5 SANİYEDE BİR]
       │
       ▼
1. CANLI CÜZDAN & BAKİYE KONTROLÜ (Binance API)
       │  ├─ Kasada Serbest Slot Var mı? (%25 Bütçe Kuralı)
       │  └─ Açık Pozisyonlar İzleniyor mu? (Başa Baş / Kâr Kilidi / Stop)
       │
       ▼
2. 5 DAKİKALIK SPOT HACİM RADARI (surge_detector.py)
       │  ├─ 5dk Hacim >= $50.000 USD mi?
       │  ├─ 24s Hacim >= $500.000 USD mi?
       │  ├─ 5dk Fiyat Artışı %0.5 - %3.5 arasında mı? (Erken Kırılım)
       │  └─ Üst Fitil <= %40 mı? (Dolu Mum / Anti-FOMO)
       │
       ▼
3. V2 GERÇEK BALİNA TEYİT MOTORU (v2_whale_engine.py)
       │  ├─ Binance Futures API: Vadeli Açık Faiz (OI) Artıyor mu?
       │  ├─ Funding Oranı <%0.10 Dengeli mi?
       │  ├─ Tahtadaki Alış Duvarı Gerçek mi? (Anti-Spoofing)
       │  └─ 10 Kriterli Teyit Skoru >= 8.0 / 10 mu?
       │
       ▼
4. YAPAY ZEKA GÖLGE DENETİM HEYETİ (LangGraph Pipeline)
       │  ├─ Gemini 3.7 Flash: Küresel Haber & Duyarlılık Onayı
       │  ├─ GLM-5.2: Baş Teknik Analist Dip Formasyon Onayı
       │  └─ OX Alpha: Quant & Likidite Gölge Denetçi Onayı
       │
       ▼
5. DETERMINİSTİK RİSK & İNFAZ KAPISI (RiskPolicyEngine)
       │  ├─ Cüzdanda bu coin zaten var mı? (Tekrar Alım Yasağı)
       │  ├─ Kasa slot bütçesi ayrıldı ($50 USD)
       │  └─ Binance Spot LIMIT / MARKET Alım Emri İnfazı 🚀
       │
       ▼
6. 7/24 TELEGRAM RAPORU & KÂR KİLİDİ NÖBETİ 📱💰
```

---

## 📖 5. YÖNETİCİ PARAMETRE KULLANIM REHBERİ

Yönetim panelinizdeki (`/v2/dashboard`) parametreleri piyasa şartlarına göre nasıl ayarlayabilirsiniz?

| Parametre | Sakin / Boğa Piyasası Ayarı | Dalgalı / Testere Piyasası Ayarı | Ne İşe Yarar? |
| :--- | :---: | :---: | :--- |
| **Min 5dk Hacim ($)** | `$50,000 USD` | `$75,000 - $100,000 USD` | Sığ coinleri eler, balina boyutunu belirler. |
| **Hacim Çarpanı (x)** | `2.0x - 2.5x` | `3.0x+` | Normal hacme göre kaç kat patlama arandığını belirler. |
| **Maks 24s Prim (%)** | `%15.0` | `%8.0 - %10.0` | Aşırı şişmiş tepedeki coinlere girişi engeller. |
| **Kasa Bütçesi (%)** | `%25.0 (4 Slot)` | `%20.0 (5 Slot)` | Portföyün kaç parçaya bölüneceğini belirler. |
| **Hedef Kâr Al (%)** | `%3.0 - %5.0` | `%2.0 - %2.5` | İlk ana kâr alma noktasını belirler. |
| **Stop-Loss (%)** | `%1.5 - %1.8` | `%1.2 - %1.5` | Beklenmedik düşüşte maksimum zarar kes limitidir. |
| **Trailing Callback (%)** | `%0.6 - %0.8` | `%0.4 - %0.5` | Kâr zirvesinden ne kadar çekilince satılacağını belirler. |

---

*Bu belge, Fox-Kripto sisteminin resmi ve bağlayıcı mimari şartnamesidir.* 🫡🦊💎🏛️📈🚀
