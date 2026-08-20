# 🦊 Fox-Kripto — Bağımsız Kod ve Risk Denetim Raporu

**Denetim tarihi:** 20 Ağustos 2026
**Denetlenen sürüm:** commit `6674bb6` (feat: implement 3 Golden Rules…)
**Kapsam:** `app.py`, `graph.py`, `exchange.py`, `surge_detector.py`, `telegram_poller.py`, `db.py`, deployment dosyaları
**Toplam:** ~4.200 satır Python

---

## 0. Kısa Cevap: Bu proje daha iyi hale getirilebilir mi?

**Evet — ama mevcut kod tabanının strateji katmanı kurtarılamaz, yeniden yazılmalı.**

Altyapı (FastAPI + Supabase + Telegram + CCXT/REST + Docker + DigitalOcean) sağlam ve korunmaya değer. Sorun altyapıda değil.

Sizi zarara uğratan şey "AI'ın kötü tahmin yapması" değil. **Bu sistemde çalışan bir yapay zeka yok.** Analiz motoru ölü kod. Skorlama sistemi ölü kod. Emniyet kuralları ölü kod. Geriye kalan şey şu:

> Her 5 saniyede bir, Binance'in o anki **en çok yükselmiş coinini** al, borsada hiçbir stop emri kurma, %1.5 yukarı ya da %1.5 aşağı gidince sat, sonra aynı coini tekrar al.

Bu bir strateji değil, matematiksel olarak **negatif beklentili bir komisyon pompası**. Aşağıda bunun her adımını satır numarasıyla kanıtlıyorum.

**Ek olarak:** Codex'in raporunda hiç geçmeyen, kasanızın tamamının 3. şahıslar tarafından boşaltılmasına izin veren **3 kritik güvenlik açığı** buldum. Bunlar P0'ın da önünde, bugün kapatılmalı.

---

# 🔴 BÖLÜM 1 — ACİL GÜVENLİK AÇIKLARI (Codex bunları kaçırdı)

Bu üç madde para kaybetmenizle ilgili değil; **paranızın tamamının çalınmasıyla** ilgili. Kod GitHub'da ve uygulama DigitalOcean'da halka açık bir URL'de çalışıyor.

### 🚨 G-1. `/api/tenants` uç noktası TÜM Binance API anahtarlarınızı ve gizli anahtarlarınızı şifresiz yayınlıyor

`app.py:759-769`

```python
@app_api.get("/api/tenants")          # ← Depends(authenticate_admin) YOK
def list_tenants():
    tenants = get_all_active_tenants()
    for t in tenants:
        if "exchange_api_key" in t and t["exchange_api_key"]:
            key = t["exchange_api_key"]
            t["exchange_api_key_masked"] = key[:6] + "..." + key[-4:]   # ← YENİ alan
        if "exchange_secret_key" in t:
            t["exchange_secret_key"] = "***HIDDEN***"
    return {"tenants": tenants}
```

Maskeleme **yeni bir alana** (`exchange_api_key_masked`) yazılıyor. Orijinal `exchange_api_key` alanı **hiç silinmiyor ve olduğu gibi döndürülüyor.**

Ve `exchange_api_key` alanı düz bir anahtar değil — içinde şu var (`db.py:106-124`, `exchange.py:518-530`):

```json
{"binancetr": {"api_key": "...", "secret_key": "..."},
 "binance":   {"api_key": "...", "secret_key": "..."}}
```

**Yani `exchange_secret_key = "***HIDDEN***"` satırı hiçbir şeyi korumuyor.** Gerçek gizli anahtarların ikisi de `exchange_api_key` blobunun içinde, kimlik doğrulaması olmadan, GET isteğiyle internete açık.

> **Sonuç:** Uygulamanızın URL'sini bilen herkes `curl https://<uygulamanız>.ondigitalocean.app/api/tenants` yazarak sizin ve tüm kullanıcılarınızın Binance TR + Binance Global tam yetkili API anahtarlarını indirebilir.

---

### 🚨 G-2. Kimlik doğrulaması olmayan 11 adet canlı emir uç noktası

`app.py:450-670`. Hiçbirinde `Depends(authenticate_admin)` yok ve hepsi **GET** metodu:

| Uç nokta | Ne yapıyor |
|---|---|
| `/api/admin/buy-spot?symbol=X&amount_usd=N` | Herhangi bir coini, herhangi bir tutarda **satın alır** |
| `/api/admin/sell-spot?symbol=X` | Herhangi bir coini **satar** |
| `/api/admin/liquidate-all-to-cash` | **Tüm portföyü piyasa fiyatından satar** |
| `/api/admin/convert-dust` | Bakiyeleri BNB'ye çevirir |
| `/api/admin/convert-bnb-to-usdt` | 55$ BNB satar |
| `/api/debug-binance` | Spot + Earn + Funding cüzdanlarının tamamını döker |
| `/api/admin/demo-swap-moonwalker` | Başka bir kullanıcının hesabında BNB→SOL swap yapar |

`authenticate_admin` fonksiyonu `app.py:32`'de tanımlanmış ama **sadece `/run-graph`'a** uygulanmış (`app.py:877`). Diğer hepsi açık.

GET olması ayrıca şu demek: bir arama motoru botu, bir link önizlemesi veya bir `<img src>` etiketi bile emri tetikleyebilir.

> **Sonuç:** URL'yi bilen biri `?symbol=SHIB/USDT&amount_usd=100000` ile kasanızı istediği coine yatırabilir veya `/liquidate-all-to-cash` ile hepsini dibinde nakde çevirebilir.

---

### 🚨 G-3. Telegram bot token'ı kaynak koda gömülü ve GitHub'a push edilmiş

`telegram_poller.py:15`

```python
TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "8938326996:AAFLmy3S4uAb_GbF8TotsdL0CgWq4jGCFik")
```

Bu token git geçmişinde. Bu token'a sahip olan kişi botunuzun **tüm mesaj akışını okuyabilir.**

Bu, kayıt sihirbazıyla birleşince ciddileşiyor: bot, kullanıcılardan Binance API anahtarlarını **düz sohbet mesajı olarak** istiyor (`telegram_poller.py:57-61`, `AWAITING_API_KEY`). Yani anahtarlar hem Telegram sohbet geçmişinde hem Supabase'de şifresiz duruyor, ve token açığa çıktığı için akış izlenebilir.

Ek olarak `db.py:9`'da Supabase URL'niz kodda sabit: `https://guxltqbzlquozniriznm.supabase.co`.

---

### ✅ Bugün yapılması gerekenler (sırayla, 30 dakika)

1. **Binance TR ve Binance Global'deki tüm API anahtarlarını SİL ve yenisini oluştur.** Yenilerinde:
   - "Enable Withdrawals" **kapalı**
   - IP whitelist → sadece DigitalOcean egress IP'niz (`104.248.135.128`)
2. **Telegram bot token'ını BotFather'dan `/revoke` ile iptal et**, yenisini sadece `.env`'e koy, koddaki fallback string'i sil.
3. **Supabase service_role key'ini rotate et.**
4. DigitalOcean uygulamasını **durdur** veya tüm `/api/admin/*` ve `/api/tenants` rotalarına `dependencies=[Depends(authenticate_admin)]` ekleyip yeniden deploy et.
5. `ADMIN_PASSWORD` varsayılanı `foxkripto2026` — kodda yazıyor (`app.py:29`). Değiştir.
6. GitHub reposunu **private** yap.

---

# 🔴 BÖLÜM 2 — ZARARIN GERÇEK KÖK NEDENİ: SİSTEMDE ÇALIŞAN BİR STRATEJİ YOK

Codex "algoritma iyileştirilmeli" dedi. Durum daha kötü: **algoritma hiç çalışmıyor.** Aşağıdaki 5 hata, karar mekanizmasının tamamını devre dışı bırakıyor.

### 💀 S-1. `graph.py`'de `requests` import edilmemiş → "2. Kural: Doyum Analizi" hiçbir zaman çalışmadı

`graph.py:1` → `import os, sys, time, json` (requests yok)
`graph.py:223` → `depth_res = requests.get(...)`

Statik analiz çıktısı:
```
graph.py:223:25: undefined name 'requests'
```

Bu satır her çalıştığında `NameError` fırlatıyor, `graph.py:228`'deki `except Exception` bunu sessizce yutuyor ve `orderbook_ratio = 1.0` yapıyor.

**Sonuç:** "Satış baskısı varsa alma" kuralı (`if orderbook_ratio < 0.75`) hiçbir zaman tetiklenmedi. Emir defteri derinliği hiç okunmadı. `orderbook_boost` her zaman `0.0`.

---

### 💀 S-2. Aday listesi string tutuyor ama kod sözlük bekliyor → tüm skorlama sabit

`graph.py:161-175` — adaylar listeye **string** olarak ekleniyor:

```python
for es in early_surges:
    sym_c = es.get("symbol", "")      # ← sadece "ACE/USDT" string'i
    dynamic_candidates.append(sym_c)   # ← metadata ATILDI
```

`graph.py:202-212` — sonra sözlük bekleniyor:

```python
best_candidate_meta = c if isinstance(c, dict) else {}   # ← HER ZAMAN {}
base_score       = float(best_candidate_meta.get("momentum_score", 7.0))     # → hep 7.0
price_change_5m  = float(best_candidate_meta.get("price_change_5m", 2.0))    # → hep 2.0
vol_spike        = float(best_candidate_meta.get("volume_spike_ratio", 2.0)) # → hep 2.0
cand_24h_change  = float(best_candidate_meta.get("price_change_24h", 0.0))   # → hep 0.0
```

Bunun zincirleme sonuçları:

| Etkilenen mekanizma | Gerçekte ne oluyor |
|---|---|
| **AI Güven Skoru** | `7.0 + 0.0` = **her işlemde tam olarak 7.0** |
| **Dinamik bütçe tahsisi** | Skor hep 7.0 → **her zaman %30** (`graph.py:263`) |
| **1. Kural (FOMO filtresi)** | `cand_24h_change` hep 0.0 → `if > 8.5` **asla doğru olmaz** |
| **3. Kural (Heyet onayı)** | `vol_spike` hep 2.0 → `>= 3.0` **asla sağlanmaz** |

Yani "Yapay Zeka Analiz Skoru: 7.0/10" diye Telegram'a düşen mesaj bir hesaplama sonucu değil, **bir varsayılan değer.**

---

### 💀 S-3. `trade_cooldowns.json` hiç yazılmıyor → testere (whipsaw) döngüsü serbest

```
$ grep -rn "trade_cooldowns" *.py
graph.py:179:  cooldown_file = os.path.join(...)   ← okuma
graph.py:181:  cooldown_file = os.path.join(...)   ← aynı satır tekrar (kopyala-yapıştır)
```

Dosya **hiçbir yerde `json.dump` ile yazılmıyor.** Hiç var olmayan bir dosya okunuyor:

```python
recent_sold_coins = {}          # boş kalıyor
last_exit_time = float(recent_sold_coins.get(c_base, 0))   # → hep 0
if (time.time() - last_exit_time) < 3600:                  # → hep False
```

**Sonuç:** Soğuma kilidi yok. Bot, %1.5 stop-loss ile zararına sattığı coini **5 saniye sonra tekrar alabiliyor.** Codex bu maddeyi "dosya senkronizasyonu" olarak yorumlamış — asıl sorun senkronizasyon değil, **dosyanın hiç yazılmaması.**

Bu, Codex'in raporundaki "sattığı coini tekrar alıyordu" gözleminin gerçek teknik sebebi.

---

### 💀 S-4. Aday havuzu literal olarak "günün en çok yükselenleri" — yani tepe noktası

`graph.py:170` yedek aday kaynağı olarak `fetch_top_volume_gainers(limit=15)` çağırıyor.

`exchange.py:805`:
```python
valid_list.sort(key=lambda x: x["percentage_change"], reverse=True)
return valid_list[:limit]
```

Bu, **24 saatte en çok yükselmiş 15 coini** döndürüyor — yani %40, %80, %150 yapmış olanları. `surge_detector` bir aday bulamadığında (ki filtreleri dar olduğu için sık olur), bot doğrudan bu listeden alım yapıyor.

Ve S-2 nedeniyle FOMO filtresi (`1. Kural`) devre dışı olduğu için **hiçbir engel yok.**

> Sistemin fiili davranışı: *günün zirvesini yapmış coini piyasa emriyle satın al.*

---

### 💀 S-5. Sinyal, kapanmamış (oluşmakta olan) mumdan üretiliyor

`surge_detector.py:31` → `fetch_5m_candles(sym, limit=6)`
`surge_detector.py:35` → `last_candle = candles[-1]`

Binance `klines` uç noktası son eleman olarak **henüz kapanmamış, o an oluşan mumu** döndürür.

Bunun iki sonucu var:
1. **Hacim karşılaştırması bozuk.** Yarım kalmış bir mumun hacmi, tamamlanmış 5 mumun ortalamasıyla kıyaslanıyor. Elma-armut.
2. **Sinyal "repaint" ediyor.** `price_change_5m` mum kapanana kadar değişmeye devam ediyor. Saniye 10'da +%1.2 görünen mum, saniye 290'da −%0.4 kapanabilir. Bot ise saniye 10'da alım yapmış oluyor.

---

# 🔴 BÖLÜM 3 — RİSK YÖNETİMİ: MATEMATİKSEL OLARAK KAYBETMEYE AYARLI

### R-1. Borsada gerçek stop-loss emri **hiç kurulmuyor** (Codex ile aynı bulgu, doğrulandı)

`exchange.py:811-899`, `execute_spot_trade` fonksiyonu `stop_loss_price` parametresini alıyor ve… sadece dönüş sözlüğüne geri koyuyor:

```python
return {
    "status": "success",
    ...
    "stop_loss_price": stop_loss_price,   # ← sadece ekrana yazmak için
}
```

Kod tabanının tamamında `OCO`, `STOP_LOSS_LIMIT`, `STOP_MARKET` geçen tek bir satır yok. README'nin "OCO emirlerini kurar" iddiası **gerçek değil.**

Stop-loss tamamen `graph.py:102`'deki Python karşılaştırmasına bağlı — yani:
- Sunucu yeniden başlarsa → stop yok
- Döngü hata verirse (`app.py:390` yakalıyor) → stop yok
- Binance rate-limit atarsa → stop yok
- Gece bir coin %30 çakılırsa ve döngü takılıysa → stop yok

### R-2. Risk/Ödül oranı 1:1'in altında → uzun vadede kayıp garantili

| Parametre | Değer | Kaynak |
|---|---|---|
| Take-Profit | net %1.5 → **brüt %1.7** gerekir | `graph.py:32`, `:99` |
| Stop-Loss | brüt %1.5 → **net %1.7 kayıp** | `graph.py:102` |
| Komisyon | %0.20 gidiş-dönüş | `graph.py:98` |
| Kayma (slippage) | market emri, düşük hacimli coin → **%0.3–1.0** | `exchange.py` hep `type='market'` |

Kazanç = +%1.5 net. Kayıp = −%1.7 net. **Kayma dahil edilince kayıp %2.0–2.5'e çıkıyor.**

Başabaş için gereken isabet oranı: **%58–62.**

Şimdi bunu S-4 ile birleştirin: 5 dakikada %1–5 hareket etmiş bir altcoin alıyorsunuz. Bu coinin 5 dakikalık gerçekleşen oynaklığı **%1.5'in çok üzerinde.** Yani stop seviyeniz gürültü bandının *içinde*. Fiyat hiçbir yöne gitmese bile, rastgele salınım stop'unuzu vuracaktır.

> **Bu, teknik bir bug değil — parametre seçiminin kendisi kaybettiriyor.** %1.5 stop, momentum coinleri için matematiksel olarak uygulanamaz.

### R-3. Komisyon kayıpta hesaplanmıyor → gerçek zararınız raporlanandan büyük

`graph.py:99`:
```python
net_profit_pct = gross_change_pct - 0.20 if gross_change_pct > 0 else gross_change_pct
```

Kârda komisyon düşülüyor, **zararda düşülmüyor.** Telegram'da gördüğünüz "−%1.50" aslında **−%1.70**. Yüzlerce işlemde bu, birikmiş kaybınızın raporlanandan sistematik olarak fazla olması demek.

### R-4. `max_budget_percent` alanı veritabanında var ama **hiç okunmuyor**

`db.py:38`'de tanımlı, `schema.sql`'de kolon var, ama `graph.py` bunu hiç sorgulamıyor. Bütçe `allocation_ratio` sabitleriyle belirleniyor (`graph.py:259-267`) ve S-2 nedeniyle **her zaman %30.**

### R-5. Günlük zarar limiti, ardışık stop kilidi, maksimum pozisyon sayısı — **hiçbiri yok**

Kod tabanında `daily_loss`, `max_positions`, `circuit_breaker`, `drawdown` kavramlarının hiçbiri geçmiyor. Bot ard arda 40 kez stop yiyebilir ve durmaz.

### R-6. 5 saniyelik döngü → kasanın 1 dakikada dağılması

`app.py:393` → `time.sleep(5)`

Her turda serbest nakdin %30'u yeni bir coine yatırılıyor. Alınan coin `current_assets`'e girdiği için bir sonraki turda farklı bir coin seçiliyor. Yani:

```
t=0s   → nakit 1000 → 300$ Coin A'ya    (kalan 700)
t=5s   → nakit 700  → 210$ Coin B'ye    (kalan 490)
t=10s  → nakit 490  → 147$ Coin C'ye    (kalan 343)
t=15s  → ...
```

**~1 dakikada kasanın %95'i, elle seçilmemiş 8-10 pump coinine dağılmış oluyor.** `active_positions.json` dosyanızdaki 5 eşzamanlı pozisyon (HEMI, PLUME, PROM, ACM, ACE) tam olarak bunun izidir.

---

# 🟠 BÖLÜM 4 — BORSA ENTEGRASYON HATALARI

### E-1. `math` modülü alım yollarında tanımsız (Codex ile aynı bulgu, kapsamı daha geniş)

```
exchange.py:124:44: undefined name 'math'   ← Binance TR ALIM
exchange.py:133:44: undefined name 'math'   ← Binance TR ALIM
exchange.py:329:40: undefined name 'math'   ← Binance Global ALIM
exchange.py:341:40: undefined name 'math'   ← Binance Global ALIM
```

`import math` sadece **satış** dallarının içinde (`exchange.py:158` ve `:390`) — Python'da fonksiyon içi import yerel kapsamda kalır, alım dalı bunu göremez.

**Sonuç:** Her iki borsada da alım tarafındaki "sıfır küsurat / net satılabilir adet" mantığı `NameError` alıp sessizce `quoteOrderQty` yedeğine düşüyor. Bu yüzden elinizde satılamayan küsuratlar (dust) birikiyor — ve o yüzden `convert-dust` uç noktalarını yazmak zorunda kalmışsınız. Semptomu tedavi etmişsiniz, sebebi değil.

### E-2. 🔥 Binance TR alımlarında bütçe tamamen yok sayılıyor, bakiyenin %95'i tek coine gidiyor

Bu, Codex'in kaçırdığı ve TR tarafındaki zararın büyük kısmını açıklayan hata.

`exchange.py:835`:
```python
res = client_tr.create_order(symbol=clean_sym, type="market", side=side.lower(), amount=amount_val)
#                                                    ^^^ amount_usd PARAMETRESİ GEÇİLMİYOR
```

`create_order` imzası (`exchange.py:46`): `amount_usd: float = 10.0`

Yani `graph.py`'nin hesapladığı bütçe (`safe_budget_usd`) **hiçbir zaman TR emrine ulaşmıyor.** Her TR alımında `amount_usd = 10.0` varsayılanı kullanılıyor.

Sonra `exchange.py:86-94`:
```python
calc_try = round(amount_usd * usdt_try_price, 2)     # = 10 × ~48 = ~480 TL sabit
if free_try >= 10.0 and (calc_try > free_try or calc_try < 10.0):
    calc_try = round(free_try * 0.95, 2)             # ← SERBEST TL'NİN %95'İ
```

**Sonuç:**
- Serbest bakiyeniz 480 TL'den fazlaysa → her alım sabit ~480 TL (bütçe kuralı yok sayılmış)
- Serbest bakiyeniz 480 TL'nin altındaysa → **tek bir pump coinine bakiyenizin %95'i yatırılıyor**

Kasanız 1.215 TL iken bu, her turda ~480 TL'nin rastgele bir coine gitmesi demek; kasa 480'in altına düştüğünde ise **hepsi tek coine.**

### E-3. Binance TR pozisyonlarının maliyeti yanlış borsadan okunuyor

`exchange.py:832` → `fetch_ticker_price(symbol)`
`exchange.py:748` → `requests.get("https://api.binance.com/api/v3/ticker/24hr?symbol=HEMITRY")`

Binance TR (`www.binance.tr`) ile Binance Global (`api.binance.com`) **ayrı borsalar, ayrı emir defterleri, ayrı fiyatlar.** TR emirlerinin giriş fiyatı Global'den okunuyor.

**Sonuç:** Kaydedilen maliyet gerçek maliyet değil. TP/SL hesabınız baştan kaymış durumda. `active_positions_tr.json`'daki fiyatlar bu yüzden şüpheli.

### E-4. Sabit döviz kuru `47.80` — 13 farklı yerde

```
app.py:      248, 269, 278, 304, 307, 312, 343, 346
exchange.py: 676, 834
graph.py:    112, 138
surge_detector.py: 126
telegram_poller.py: 270
```

`exchange.py:679`'da canlı `USDTTRY` fiyatını okuyan bir kod **zaten var** ama diğer 13 yerde kullanılmıyor. Kur değiştikçe tüm TL kâr/zarar raporlarınız ve TL bütçe hesaplarınız kayıyor.

### E-5. Emir doldurma fiyatı ağırlıklı ortalama değil

`exchange.py:427` → `exec_p = float(fills[0].get("price", 0.0))`

Market emri birden fazla seviyeden dolduğunda **sadece ilk parçanın fiyatı** kaydediliyor — yani en iyi fiyat. Gerçek ortalama maliyetiniz daha kötü. Kâr hesabı sistematik olarak iyimser çıkıyor.

### E-6. "2. kademe" retry mantığı sessizce miktarı düşürüyor

`exchange.py:231-243` ve `:409-421`: LOT_SIZE hatası gelince miktar `int()` ile aşağı yuvarlanıp tekrar deneniyor. Örneğin 0.87 ACE → `int(0.87)` = 0 → emir yine reddedilir; ya da 5.9 → 5 (%15'i satılmadan kalır). Pozisyonun bir kısmı satılmadan kalıyor ve `graph.py` bunu kapalı sayıp `active_positions`'tan siliyor (`graph.py:348`) → **hayalet pozisyon.**

---

# 🟠 BÖLÜM 5 — DURUM (STATE) YÖNETİMİ VE ALTYAPI

### D-1. 🔥 Pozisyon dosyaları git'te takipli — deploy her şeyi geri sarıyor

```
$ git ls-files | grep json
active_positions.json
active_positions_global.json
active_positions_tr.json
```

Bu dosyalar `.gitignore`'da **değil**, repoda takipli. Bu, Codex'in "dosya senkronize olmuyor" tespitinden daha kötü bir durum yaratıyor:

**Her deploy'da konteyner, sizin bilgisayarınızdaki en son commit'lenmiş — yani bayat — pozisyon dosyasıyla başlıyor.**

Ve şimdi kritik zincir (`graph.py:88-95`):

```python
if recorded_buy_p <= 0.0:
    recorded_buy_p = curr_p        # ← MALİYET, GÜNCEL FİYATA SIFIRLANIYOR
```

Yani konteyner yeniden başladığında (DigitalOcean'da bu rutin: deploy, sağlık kontrolü, OOM, yeniden başlatma):

1. Pozisyon hafızası kaybolur veya bayatlar
2. −%25'te olan bir pozisyonun maliyeti **bugünkü fiyata sıfırlanır**
3. Zarar defterden **silinir** — stop-loss o pozisyon için bir daha asla tetiklenmez
4. Bot o coini "yeni açılmış pozisyon" sanar ve sıfırlanmış maliyetin %1.5 üstünde "kâr aldım" diye Telegram'a mesaj atar

> **Bu, zararların neden hiç kapanmayıp biriktiğinin ve neden kârda göründüğü halde kasanın eridiğinin ana açıklamasıdır.**

Ayrıca `Dockerfile`'da volume yok, `.do/app.yaml`'da persistent disk yok. Konteyner dosya sistemi tanım gereği geçici.

### D-2. Hata durumunda "fail-open" → hayali 1000$ bakiye (Codex ile aynı bulgu)

`exchange.py:724-734`: Bakiye API'si hata verdiğinde sistem duracağına şunu döndürüyor:

```python
return {"is_paper_trading": True, "free_usdt": 1000.0, ...}
```

Ama `execute_spot_trade` (`exchange.py:865`) sadece `apiKey` var mı diye bakıyor — `is_paper_trading` bayrağını **hiç kontrol etmiyor.** Yani sahte 1000$ bakiyeyle **gerçek emir gönderiliyor.**

Bu, R-6 ile birleşince: bir rate-limit hatası → sahte 1000$ → 300$ "gerçek" alım denemesi → `-2010 Insufficient Balance` → hata alarmı → döngü kilitlenir.

### D-3. Rate limit ihlali kaçınılmaz

5 saniyelik döngüde, her tenant için:
- `fetch_portfolio_balance` × 2 (biri `app.py:155`, biri `graph.py:22` — **aynı veri iki kez çekiliyor**)
- `exchangeInfo` + `ticker/24hr` (surge detector)
- **50 paralel `klines` isteği** (25 worker thread)
- Her holding için ayrı `ticker/24hr`
- `depth` isteği (NameError'a düşse de)

Kabaca **saniyede 15–20 istek, 7/24.** Binance limiti 1200 ağırlık/dakika. Dual-exchange kullanıcıları `db.py:106-124`'te ikiye açıldığı için bu **iki katına** çıkıyor.

**Sonuç:** Düzenli `-1003 TOO_MANY_REQUESTS` ve IP banları → D-2 zinciri tetiklenir.

### D-4. Hata bildirimi fonksiyonunun kendisi çöküyor

```
app.py:118:20: undefined name 'time'
```

`handle_autonomous_error_alert` içinde `time.time()` çağrılıyor ama `time` modül seviyesinde import edilmemiş (sadece `run_autonomous_trading_loop` içinde yerel olarak, `app.py:143`).

**Sonuç:** Bir borsa hatası olduğunda hata bildirimi göndermeye çalışan kod `NameError` fırlatıyor, bu `app.py:390`'daki genel `except`'e düşüyor ve **o turdaki kalan tüm kullanıcılar atlanıyor.** Yani hataları hiç görmediniz — üstelik hata anında bot diğer hesaplarınıza da bakmayı bıraktı.

### D-5. Yapay zeka katmanının tamamı ölü kod

| Dosya | Durum |
|---|---|
| `prompts.py` (239 satır) | `analyze_crypto_news` ve `formulate_trade_strategy` import ediliyor (`graph.py:9`) ama **hiç çağrılmıyor** |
| `news_service.py` | `fetch_live_global_crypto_news` import ediliyor (`graph.py:16`) ama **hiç çağrılmıyor** |
| `node_analyze_news` | `graph.py:25` → gövdesi tek satır: `return {"sentiment_score": 8.5}` — sabit değer |
| `node_fetch_data` | `graph.py:23` → `news_data` alanına `"Fast Scalper Active"` string'i yazıyor |
| `telegram_bot.py` | `send_telegram_trade_approval` import ediliyor, **hiç çağrılmıyor** |
| `bot.py` (98 satır) | Hiçbir yerden import edilmiyor — tamamen ölü |

**Claude 4.5 ve GPT-4o'ya giden tek bir API çağrısı yok.** README'nin ve STATUS.md'nin bu iddiaları gerçeği yansıtmıyor.

### D-6. İnsan onayı mekanizması kaldırılmış ama dokümantasyon hâlâ vaat ediyor

README (satır 3): *"sizin onayınız olmadan asla işlem yapmayan"*
README (satır 9): *"Siz ONAYLA demeden borsaya emir gitmez"*

`graph.py:305-313`:
```python
def node_human_approval(state):
    # Tam Otonom Mod (Butonsuz Otomatik): Doğrudan onay ver
    return {"human_approval": "Approved"}
```

`app.py:165`: `"human_approval": "Approved",  # FULL AUTONOMOUS MODE`

`langgraph.types.interrupt` import edilmiş (`graph.py:5`) ama **hiç kullanılmıyor.**

Sistem tam otonom. Bu bir hata değil, bilinçli bir değişiklik — ama dokümantasyonla çelişiyor ve muhtemelen sizin beklentinizle de çeliştiği için zararı fark etmeniz gecikti.

### D-7. Bayat Telegram butonu → habersiz BTC alımı

`telegram_poller.py:75-83`: Kayıtlı state bulunamazsa varsayılan bir teklif üretiliyor:

```python
proposal = {"symbol": "BTC/USDT", "direction": "BUY", "amount_usd": 10.0, ...}
```

Haftalar önceki bir mesajdaki "✅ ONAYLA" butonuna yanlışlıkla basılması, **10$ BTC alımı** tetikler.

---

# 📊 BÖLÜM 6 — ÖNCELİKLENDİRİLMİŞ BULGU TABLOSU

| # | Bulgu | Etki | Dosya:Satır | Codex buldu mu? |
|---|---|---|---|---|
| **G-1** | `/api/tenants` API+secret anahtarlarını sızdırıyor | 🔴 Kasa çalınabilir | `app.py:764` | ❌ |
| **G-2** | 11 kimlik doğrulamasız canlı emir uç noktası | 🔴 Kasa boşaltılabilir | `app.py:450-670` | ❌ |
| **G-3** | Telegram token'ı kodda + GitHub'da | 🔴 Bot ele geçirilebilir | `telegram_poller.py:15` | ❌ |
| **D-1** | Pozisyon dosyaları git'te + maliyet sıfırlanması | 🔴 Zarar defterden siliniyor | `graph.py:89`, `.gitignore` | 🟡 kısmen |
| **R-1** | Borsada stop emri yok | 🔴 Korumasız pozisyon | `exchange.py:811` | ✅ |
| **S-3** | `trade_cooldowns.json` hiç yazılmıyor | 🔴 Testere döngüsü | `graph.py:179` | 🟡 sebebi yanlış |
| **E-2** | TR alımında bütçe yok sayılıyor, %95 all-in | 🔴 Pozisyon boyutu kontrolsüz | `exchange.py:835` | ❌ |
| **R-2** | R:R 1:1'in altında, %1.5 stop gürültü içinde | 🔴 Negatif beklenti | `graph.py:32,102` | ❌ |
| **S-2** | Aday metadata'sı kayboluyor → skorlama sabit | 🔴 Tüm kurallar ölü | `graph.py:202` | ❌ |
| **S-1** | `requests` import yok → doyum kuralı ölü | 🟠 2. Kural çalışmıyor | `graph.py:223` | ❌ |
| **S-4** | Aday havuzu = günün en çok yükselenleri | 🟠 Tepeden alım | `exchange.py:805` | ❌ |
| **D-2** | Fail-open sahte 1000$ bakiye | 🟠 Hayali emirler | `exchange.py:728` | ✅ |
| **E-1** | `math` alım yollarında tanımsız | 🟠 Küsurat birikimi | `exchange.py:124,329` | ✅ |
| **R-6** | 5 sn döngü → 1 dk'da kasa dağılıyor | 🟠 Aşırı yayılma | `app.py:393` | ❌ |
| **D-3** | Rate limit ihlali → IP ban | 🟠 Sistem kilitlenmesi | `app.py:145` | ❌ |
| **R-3** | Komisyon kayıpta hesaplanmıyor | 🟠 Zarar olduğundan az raporlanıyor | `graph.py:99` | ❌ |
| **E-3** | TR maliyeti Global'den okunuyor | 🟠 Yanlış TP/SL | `exchange.py:832` | ❌ |
| **S-5** | Kapanmamış mumdan sinyal | 🟠 Repaint | `surge_detector.py:35` | ❌ |
| **D-4** | Hata bildirimi fonksiyonu çöküyor | 🟠 Hatalar görünmüyor | `app.py:118` | ❌ |
| **R-4/5** | Bütçe limiti okunmuyor, devre kesici yok | 🟠 Sınırsız zarar | `graph.py:259` | 🟡 kısmen |
| **E-4** | 13 yerde sabit kur `47.80` | 🟡 Yanlış raporlama | 5 dosya | ✅ |
| **E-5** | `fills[0]` ağırlıklı ortalama değil | 🟡 İyimser kâr | `exchange.py:427` | ❌ |
| **E-6** | Retry `int()` ile pozisyonu yarım bırakıyor | 🟡 Hayalet pozisyon | `exchange.py:233` | ❌ |
| **D-5** | AI katmanı tamamen ölü kod | 🟡 Yanıltıcı | `prompts.py` | ❌ |
| **D-6** | HITL kaldırılmış, doküman vaat ediyor | 🟡 Beklenti uyuşmazlığı | `graph.py:305` | ❌ |
| **D-7** | Bayat buton → habersiz BTC alımı | 🟡 İstenmeyen emir | `telegram_poller.py:76` | ❌ |

**Toplam: 26 önemli bulgu. Codex 5'ini yakalamış, 3'ünü kısmen, 18'ini kaçırmış.**

---

# 🛠️ BÖLÜM 7 — YOL HARİTASI

## Faz 0 — BUGÜN (canlı işlemi durdurun)

- [ ] Binance anahtarlarını iptal et → yeni anahtar (çekim kapalı + IP whitelist)
- [ ] Telegram token'ını revoke et → `.env`'e taşı, koddaki fallback'i sil
- [ ] Supabase service_role key rotate
- [ ] Tüm `/api/admin/*` + `/api/tenants` rotalarına auth ekle, POST'a çevir
- [ ] `/api/debug-binance` ve tek kullanımlık `buy-tut-whale`, `sell-ace-now` vb. rotaları **tamamen sil**
- [ ] GitHub reposunu private yap
- [ ] `.gitignore`'a `active_positions*.json`, `trade_cooldowns.json` ekle + `git rm --cached`
- [ ] `is_active = False` (Codex'in yaptığı gibi) — düzeltmeler bitene kadar kapalı kalsın

## Faz 1 — Doğruluk düzeltmeleri (1-2 gün)

- [ ] `graph.py`'ye `import requests` ekle
- [ ] `exchange.py`'ye modül seviyesinde `import math` ekle, fonksiyon içi import'ları sil
- [ ] `app.py`'ye modül seviyesinde `import time` ekle
- [ ] `dynamic_candidates`'e **sözlük** ekle (string değil) — S-2'yi kapat
- [ ] `create_order`'a `amount_usd=amount_usd` parametresini geçir (`exchange.py:835`)
- [ ] Tüm `47.80` sabitlerini tek bir `get_usdt_try()` fonksiyonuyla değiştir
- [ ] `fills` üzerinden ağırlıklı ortalama fiyat hesapla
- [ ] `pyflakes` / `ruff` CI adımı ekle — bu sınıf hatalar bir daha geçmesin

## Faz 2 — Emniyet mimarisi (3-5 gün)

- [ ] **Pozisyon defterini Supabase'e taşı.** JSON dosyalarını tamamen kaldır. Tablo: `positions(tenant_id, symbol, entry_price, qty, opened_at, exchange, status)`
- [ ] **`recorded_buy_p = curr_p` fallback'ini SİL.** Maliyet bilinmiyorsa pozisyona dokunma, insana sor. Bu tek satır en çok zararı veren satır.
- [ ] **Alım gerçekleşir gerçekleşmez borsaya OCO / STOP_LOSS_LIMIT emri gönder.** Yazılımsal stop yalnızca yedek olsun.
- [ ] `is_paper_trading` bayrağını `execute_spot_trade`'de kontrol et — **fail-closed** yap. Bakiye okunamıyorsa işlem yok.
- [ ] `trade_cooldowns`'u Supabase'e yaz ve gerçekten uygula (min. 4 saat aynı coine giriş yasağı)
- [ ] Devre kesici: günlük max zarar %2 → bot durur; 3 ardışık stop → 1 saat kilit
- [ ] `max_budget_percent`'i Supabase'den oku ve zorla uygula
- [ ] Maksimum eşzamanlı pozisyon sayısı (öneri: 3)
- [ ] Tüm borsa çağrılarına merkezi rate-limiter + exponential backoff
- [ ] Ölü kodu temizle: `bot.py`, `telegram_bot.py`, kullanılmayan `prompts.py`/`news_service.py` import'ları

## Faz 3 — Stratejiyi sıfırdan kur (2-3 hafta)

Buradaki tek doğru sıra: **önce ölç, sonra yaz.**

- [ ] **Backtest altyapısı kur.** Binance'ten 6-12 aylık 5m/15m veriyi indir. Komisyon %0.1/taraf + gerçekçi kayma modelle. Bu olmadan yazılan hiçbir strateji "iyi" olduğunu iddia edemez.
- [ ] **Kapanmış mumla çalış.** `candles[:-1]` — oluşan mumu asla kullanma.
- [ ] **Stop'u ATR'ye bağla.** Sabit %1.5 yerine `SL = entry − 1.5 × ATR(14)`. Stop, coinin oynaklığından büyük olmalı.
- [ ] **R:R ≥ 1:2 hedefle.** TP en az stop mesafesinin 2 katı. Yoksa isabet oranı baskısı altında ezilirsiniz.
- [ ] **Piyasa rejimi filtresi.** BTC 4h EMA200 altındaysa altcoin momentum stratejileri çalışmaz — bot beklemeye geçsin.
- [ ] **Limit emir kullan** (market yerine) — kayma maliyetinin çoğunu siler.
- [ ] **Kademeli çıkış:** %50'yi 1R'de sat, kalanı trailing stop ile taşı. Momentum stratejilerinin kârı uzun kuyruktan gelir; sabit %1.5 TP tam da o kuyruğu kesiyor.
- [ ] En az **2 hafta paper trading**, sonra minimum tutarla canlı.

---

# 🎯 BÖLÜM 8 — SONUÇ

### Neden zarar ettiniz?

Tek bir sebep değil, **birbirini besleyen dört zincir:**

1. **Emniyet mekanizmalarının hiçbiri çalışmıyordu.** Soğuma kilidi (dosya yazılmıyor), doyum analizi (`requests` yok), FOMO filtresi (metadata kayıp), heyet onayı (metadata kayıp) — dördü de sessizce devre dışıydı. Kod bunları yaptığını *söylüyordu*, yapmıyordu.

2. **Stop-loss borsada değil, Python döngüsündeydi** — ve o döngü rate-limit, yeniden başlatma ve `NameError` nedeniyle sürekli kesiliyordu.

3. **Konteyner her yeniden başladığında zarar defterden siliniyordu** (`recorded_buy_p = curr_p`). Kaybeden pozisyonlar hiç kapanmadı, kâr gibi göründü.

4. **Parametrelerin kendisi kaybettiriyordu.** %1.5 stop, %1-5 hareket etmiş bir altcoinin gürültü bandının içinde. Kazanç %1.5, kayıp %1.7+kayma. Bu, mükemmel çalışan bir kodla bile kaybeder.

Buna TR tarafındaki "bakiyenin %95'i tek coine" hatası ve "günün en çok yükseleni al" aday seçimi eklenince, tablo tamamlanıyor.

### Yeniden yazmaya değer mi?

**Altyapı: evet, koruyun.** FastAPI iskeleti, Supabase multi-tenant modeli, Telegram entegrasyonu, Docker/DigitalOcean kurulumu, çift borsa REST istemcileri — bunlar gerçek ve yeniden kullanılabilir işler. Yaklaşık %60'ı korunabilir.

**Strateji katmanı (`graph.py` + `surge_detector.py`): hayır, silin.** Bu iki dosya yamayla düzelmez. Backtest olmadan, kapanmış mum olmadan, ATR tabanlı stop olmadan yazılmış momentum kodu — ne kadar bug düzeltirseniz düzeltin negatif beklentili kalır.

### Dürüst uyarı

Bu düzeltmelerin hepsi yapılsa bile **kârlılık garanti değildir.** Kripto piyasasında kısa vadeli momentum stratejilerinin büyük çoğunluğu, komisyon ve kayma sonrası zarar eder. Yukarıdaki liste sizi "kaybetmesi matematiksel olarak kesin" durumdan "kazanma ihtimali olan" duruma taşır — daha fazlasını değil.

Bu yüzden **Faz 3'teki backtest altyapısı pazarlık konusu değil.** Bir stratejinin çalıştığını canlı parayla öğrenmek, bu projenin şimdiye kadarki en pahalı dersi oldu.

Ben yatırım danışmanı değilim ve bu rapor yatırım tavsiyesi içermez; yalnızca kodun teknik denetimidir.

---

*Denetim: Claude (Cowork) — statik analiz (`pyflakes`), satır satır kod okuma ve git geçmişi incelemesi ile.*
