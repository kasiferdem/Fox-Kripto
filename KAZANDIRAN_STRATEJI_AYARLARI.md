# 🏆 2-3 Eylül Kazandıran Strateji & Parametre Rehberi

Bu belge, **2-3 Eylül** tarihlerinde $5 - $6 net kâr elde eden, piyasadaki erken hacim girişlerini ve anlık altcoin momentum patlamalarını yakalayan orijinal **Çevik / Hızlı Scalping (v2.1 Smart Armor / Agile)** stratejisinin tüm formüllerini ve parametrelerini içerir.

---

## 📊 1. Canlı Strateji Parametre Tablosu

| Parametre Adı | Paneldeki Karşılığı | Değer | Teknik Açıklama & Formül |
| :--- | :--- | :--- | :--- |
| **`volume_spike_multiplier`** | Hacim Çarpanı (x) | **`1.15x`** | Son 5 dakikalık hacmin, önceki 20 mumluk ortalama hacme oranı $\ge 1.15$ olduğunda tetiklenir. Erken sinyal yakalar. |
| **`min_5m_volume_usd`** | Min 5dk Hacim ($) | **`$2,500`** | Düşük piyasa değerli altcoinlerdeki ilk $2.500 ve üzeri para girişlerini filtreye takılmadan işleme alır. |
| **`min_24h_quote_volume_usd`** | Min 24s Hacim ($) | **`$1,000,000`** | Günlük hacmi en az $1M olan likit Binance Spot tahtalarını seçer. |
| **`max_recent_gain_24h`** | Maks 24s Prim (%) | **`%60.0`** | Günlük %15 - %40 prim yapmış coinleri "aşırı yükseldi" diye engellemez; güçlü trend devam formasyonlarına izin verir. |
| **`take_profit_pct`** | Hedef Kâr (TP %) | **`%2.5`** | Pozisyon açıldıktan sonra ilk hedef kâr seviyesi. |
| **`trailing_callback_pct`** | Trailing SL (İzleyen Kâr %) | **`%0.6`** | Fiyat yükselirken zirveden %0.6 geri çekilme olduğunda kârı cebe kilitler (Kâr kaçırmaz). |
| **`stop_loss_pct`** | Zarar Kes (SL %) | **`%1.2`** | Yanlış yöne giden işlemlerde riski katı bir şekilde %1.2 ile sınırlar. |
| **`btc_min_rsi`** | BTC Taban RSI | **`35.0`** | Bitcoin 1 saatlik RSI 35.0 üzerinde olduğu sürece altcoin taramasına izin verir (Piyasa panik çöküşünde değilse çalışır). |
| **`retest_required`** | Retest Onayı | **`Kapalı (False)`** | Kırılım sonrası ikinci mumu veya desteğe geri çekilmeyi beklemez; kırılım anında momentumu satın alır. |
| **`first_pump_candle_entry_blocked`** | İlk Pump Engeli | **`Kapalı (False)`** | İlk fırlayan yeşil mumda trene binilmesine izin verir (Fırsatı kaçırmaz). |
| **`min_ai_score`** | Min AI Skoru | **`4.5`** | Yapay zeka teyit eşiğini hafifletir; gereksiz gecikme ve filtrelemeyi önler. |
| **`max_daily_trades`** | Günlük İşlem Kotası | **`10`** | Günde 10 işleme kadar fırsat yakalama özgürlüğü tanır. |
| **`max_budget_percent`** | Kasa Bütçesi (%) | **`%25 - %33`** | Toplam bakiyenin her işlem için ayrılan payı. |
| **`max_concurrent_positions`** | Maks Açık Slot | **`3`** | Aynı anda en fazla 3 farklı altcoin pozisyonu taşır. |

---

## 🎯 2. Bu Ayarlar Neden Kazandırdı? (Mantık & Formül)

1. **Erken Giriş Formülü (Early Trigger):**
   $$\text{Mevcut 5dk Hacim} \ge 1.15 \times \text{Ortalama 5dk Hacim}$$
   Filtre eşiği $1.15x$ ve $\$2,500$ olduğu için balina veya piyasa yapıcı tahtaya ilk alımı attığı anda bot bunu tespit etti.
2. **Kâr Kilitleme Mekanizması (Trailing Profit Lock):**
   Fiyat %1.5 veya %2.5 fırladığında, zirveden yalnızca `%0.6` sarktığı anda satış emri tetiklenerek kâr realize edildi.
3. **Piyasa Filtresinin Esnekliği:**
   BTC hafif dinlenirken bile (RSI 35-45 arası) altcoinlerdeki bağımsız hareketler engellenmeden kazanca dönüştürüldü.

---

## 💾 3. Doğrudan JSON Konfigürasyonu (`strategy_config_local.json`)

```json
{
  "active_preset": "v21_smart_armor",
  "volume_spike_multiplier": 1.15,
  "min_volume_usd": 2500.0,
  "min_5m_volume_usd": 2500.0,
  "min_24h_quote_volume_usd": 1000000.0,
  "max_daily_trades": 10,
  "max_recent_gain_24h": 60.0,
  "min_ai_score": 4.5,
  "max_budget_percent": 25.0,
  "max_concurrent_positions": 3,
  "trailing_callback_pct": 0.6,
  "take_profit_pct": 2.5,
  "stop_loss_pct": 1.2,
  "btc_min_rsi": 35.0,
  "first_pump_candle_entry_blocked": false,
  "retest_required": false,
  "require_futures_oi": false
}
```

---

## 🎛️ 4. Admin Panelinden Geri Yükleme Rehberi

İstediğiniz zaman Admin Paneline (`/admin/dashboard`) girip şu değerleri kontrol edip **"🚀 Ayarları ve Seçili Modu Uygula"** butonuna basarak bu modu anında aktif edebilirsiniz:
* **Hacim Çarpanı:** `1.15`
* **Min 5dk Hacim:** `2500`
* **Maks 24s Prim:** `60`
* **BTC Taban RSI:** `35`
* **Trailing SL:** `0.6`
* **Retest Onayı:** `Serbest (Momentum)`
* **İlk Pump Engeli:** `İzin Ver (Fırlamaları Yakala)`
