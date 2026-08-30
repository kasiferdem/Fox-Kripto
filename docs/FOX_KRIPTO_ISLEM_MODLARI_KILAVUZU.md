# 🛡️ FOX-KRİPTO V2.3 İŞLEM MODLARI KILAVUZU

**Sürüm:** V2.3.0  
**Telif Hakkı:** (c) 2026 Fox-Kripto Quant Ekibi  
**Kapsam:** Admin Paneli (`/v2/dashboard`) İşlem Modları ve Güvenlik Şalterleri Rehberi  

---

## 📌 GENEL BAKIŞ

Fox-Kripto V2.3 işlem modları çubuğu, sistemin **kullanıcı sermayesine ne derece dokunacağını** belirleyen ana güvenlik merkezidir. 

Risk derecesine göre en güvenli izleme modundan (`SIGNAL_ONLY`), tam otonom canlı işlem moduna (`LIVE_TRADING`) kadar 6 kademeli bir yapı sunar.

```text
[ 📡 SIGNAL_ONLY ] ➔ [ 📝 PAPER_TRADING ] ➔ [ 👤 SHADOW_TRADING ] ➔ [ ⏳ APPROVAL_REQUIRED ] ➔ [ 🐥 LIVE_CANARY ] ➔ [ 🚀 LIVE_TRADING ]
(Sıfır Risk / İzleme)                                                                                (Tam Yetkili Canlı İşlem)
```

---

## 🎛️ 6 İŞLEM MODUNUN DETAYLI ANALİZİ

### 1️⃣ 📡 `SIGNAL_ONLY` (Yalnızca İzleme / Sinyal Modu)
* **Gerçek Paraya Dokunur mu?** ❌ **HAYIR (Sıfır Risk)**
* **Kasa Güvenliği:** %100 Nakitte Bekleme.
* **Ne Yapar?**
  * Borsada hiçbir alım veya satım emri açmaz.
  * 7/24 piyasayı tarayarak belirlenen Hacim Scalping veya Balina kriterlerine uyan bir coin tespit ettiğinde Telegram üzerinden anlık bilgi mesajı üretir.
  * Sistemin veya yeni bir piyasa kuralının doğrulanmasında güvenli izleme için kullanılır.

---

### 2️⃣ 📝 `PAPER_TRADING` (Sanal Para / Deneme Sürüşü)
* **Gerçek Paraya Dokunur mu?** ❌ **HAYIR (Sıfır Risk)**
* **Kasa Güvenliği:** Gerçek bakiye tamamen kilitli ve güvendedir.
* **Ne Yapar?**
  * Sanal $10,000 USD bakiye ile sanki gerçek piyasadaymış gibi işlem açar, kâr alır ve zarar durdurur.
  * Stratejinizin, hacim eşiklerinizin ve stop seviyelerinizin başarı oranını (Win Rate) tek kuruş kaybetmeden test etmenizi sağlar.

---

### 3️⃣ 👤 `SHADOW_TRADING` (Gölge Mod / Çift AI Karşılaştırması)
* **Gerçek Paraya Dokunur mu?** ❌ **HAYIR (Sıfır Risk)**
* **Kasa Güvenliği:** Sıfır Borsa Etkileşimi.
* **Ne Yapar?**
  * İki farklı yapay zekayı (**GLM-5.2** ve **Gemini 3.7 Flash**) arka planda yarıştırır.
  * Bir sinyal geldiğinde her iki modelin bağımsız analizlerini kaydeder ve hangi modelin daha isabetli olduğunu raporlar.

---

### 4️⃣ ⏳ `APPROVAL_REQUIRED` (Yönetici Onaylı İşlem Modu)
* **Gerçek Paraya Dokunur mu?** ⚠️ **YALNIZCA SİZ ONAYLARSANIZ**
* **Kasa Güvenliği:** Kullanıcı izni olmadan 1 kuruş bile harcanamaz.
* **Ne Yapar?**
  * Bot tüm kriterleri geçen kusursuz bir fırsat bulsa dahi doğrudan emir göndermez!
  * Telegram üzerinden Yöneticiye (**S**) bir onay penceresi ve `[ ✅ ONAYLA ]` / `[ ❌ REDDET ]` butonları gönderir.
  * Siz onay verirseniz işlem açılır, vermezseniz pozisyon pas geçilir.

---

### 5️⃣ 🐥 `LIVE_CANARY` (Küçük Parayla Canlı Test Modu)
* **Gerçek Paraya Dokunur mu?** 🟢 **EVET (Sembolik Küçük Tutar: 10$)**
* **Kasa Güvenliği:** Kasanın %95'i serbest nakitte kalır.
* **Ne Yapar?**
  * Canlı borsada tüm bütçeyi riske atmadan, sadece 10 dolarlık minimal bir işlem açar.
  * Binance API bağlantısını, alım hızını, Stop-Loss ve Take-Profit emirlerinin borsada milisaniyelik yerleştiğini gerçek tahtada doğrular.

---

### 6️⃣ 🚀 `LIVE_TRADING` (Tam Otonom Canlı İşlem Modu)
* **Gerçek Paraya Dokunur mu?** 🟢 **EVET (Tam Canlı Hesap)**
* **Kasa Güvenliği:** Deterministik Stop-Loss (%1.0) ve Devre Kesiciler devrededir.
* **Ne Yapar?**
  * Kasanızdaki serbest nakit ($198 USD) ile panelde belirlediğiniz kurallara göre (%2.4 Kâr Al, %1.0 Zarar Kes, 45 Dk Zaman Stopu) Binance üzerinde tam otonom alım-satım yürütür.

---

## 🔄 PANEL ÜZERİNDEN MOD DEĞİŞTİRME ADIMLARI

1. [https://fox-kripto-m7n46.ondigitalocean.app/v2/dashboard](https://fox-kripto-m7n46.ondigitalocean.app/v2/dashboard) adresine gidin.
2. Üstteki **İşlem Modu** çubuğundan dilediğiniz mod butonuna tıklayın (Örn: `[ 📝 PAPER_TRADING ]` veya `[ 🚀 LIVE_TRADING ]`).
3. Sağdaki **`[ 🚀 Canlıya Al (V2.3) ]`** butonuna basarak ayarı sisteme mühürleyin.
4. Sistem anında seçtiğiniz güvenlik modunda çalışmaya başlar.
