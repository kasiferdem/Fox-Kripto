# 🏆 14 Eylül Kazandıran Strateji & Parametre Rehberi (Altın Kasa Profili)

> **Bu belge, 14 Eylül 2026 gecesinde genel piyasa (BTC ve ETH) düşüş ve durgunluktayken, ardışık 4 kâr ve 1 kontrollü stop ile net +$3.08 USD nakit kâr üreten ve kasanın 3 slotunu mükemmel yöneten canlı parametre setinin tam yedeğidir.**
> 
> 🤖 **Yapay Zeka Talimatı (Antigravity Directives):** Kullanıcı bu dosyayı sohbete attığında veya *"14 Eylül ayarlarını geri yükle / uygula"* dediğinde, bu dosyadaki Bölüm 3'te yer alan JSON konfigürasyonunu doğrudan Supabase `strategy_config` ve `global_system_settings` tablolarına uygulayınız.

---

## 📈 1. 14 Eylül Canlı Performans Özeti

* **Piyasa Durumu:** BTC kırmızı/düşüşte (-%0.52, $77,348 ➔ $76,820), ETH (-%1.87).
* **Uygulanan Mod:** 3 Slot Çevik Balina Avı & Yüksek Beta Dip Patlaması (`whale_hunting_balanced` + `v21_smart_armor`).
* **Kapanan İşlemler:**
  1. 🟢 **SC/USDT:** $0.000914 ➔ $0.000938 | **+$1.51 USD (+%2.63 Net)**
  2. 🔴 **MBL/USDT:** $0.000911 ➔ $0.000894 | **-$1.15 USD (-%1.80 Kontrollü Stop)**
  3. 🟢 **STRAX/USDT:** $0.01060 ➔ $0.01077 | **+$0.86 USD (+%1.70 Net)**
  4. 🟢 **SOLV/USDT:** $0.00524 ➔ $0.00535 | **+$1.31 USD (+%2.10 Net)**
  5. 🟢 **AVA/USDT:** $0.17200 ➔ $0.17370 | **+$0.55 USD (+%1.00 Net)**
* 🏆 **Net Realize Nakit Kâr:** **+$3.08 USD**
* 📦 **Aktif Açık Slotlar:** **COTI/USDT** ($60.18), **HIVE/USDT** ($60.82)
* 💵 **Serbest Kasa (USDT):** **$59.87 USD** (AVA satışı sonrası anında taze nakit)
* 💰 **Toplam Portföy:** **$182.85 - $183.10 USD**

---

## 📊 2. Canlı Strateji Parametre Tablosu

| Parametre Adı | Değer | Teknik Açıklama & Formül |
| :--- | :--- | :--- |
| **`active_preset`** | **`whale_hunting_balanced`** | Hızlı çevik momentum ve akıllı hacim dengeli hibrit mod. |
| **`volume_spike_multiplier`** | **`1.15x`** | 5 dakikalık hacim, 20 mumluk ortalamayı $\ge 1.15$ kat aştığında erken dip kırılımını yakalar. |
| **`min_5m_volume_usd`** | **`$2,500`** | Düşük hacimli coinlerdeki taze kurumsal/balina para girişlerini yakalama eşiği. |
| **`min_24h_quote_volume_usd`**| **`$1,000,000`** | En az $1M günlük likiditesi olan güvenli Binance Spot tahtalarını seçer. |
| **`max_recent_gain_24h`** | **`%45.0`** | %45'in üzerindeki aşırı şişmiş tepe coinleri eler; ancak %10-%35 primli güçlü trend coinlerine izin verir. |
| **`take_profit_pct`** | **`%3.0`** | İlk hedef kâr alma seviyesi (Scalp için %2.5 - %3.0). |
| **`trailing_callback_pct`** | **`%0.6`** | Zirveden %0.6 gevşeme olduğunda kârı cebe kilitler (Kârı geri vermez). |
| **`stop_loss_pct`** | **`%1.2`** | Yanlış yönde sert hareketlere karşı sermayeyi koruyan katı stop sınırı. |
| **`break_even_trigger_pct`** | **`%1.2`** | Pozisyon +%1.2 kâra geçtiğinde başa-baş (Break-even) koruma kilidi devreye girer. |
| **`max_concurrent_positions`** | **`3`** | Aynı anda en fazla 3 aktif pozisyon (Slot bazlı risk dağıtımı). |
| **`max_budget_percent`** | **`%33.3`** | Kasanın her coin için ayrılan maksimum bütçe payı (3 eşit slot). |
| **`max_daily_trades`** | **`60`** | Günlük maksimum infaz edilebilir canlı işlem kotası. |
| **`daily_loss_limit_pct`** | **`%3.0`** | Günlük maksimum portföy zarar tavanı (Aşılırsa bot yeni alımı keser). |
| **`cooldown_minutes`** | **`30 dk`** | Stop veya satış sonrası aynı coinde 30 dakika dinlenme kuralı. |
| **`btc_min_rsi`** | **`35.0`** | Bitcoin 1 saatlik RSI $\ge 35.0$ olduğu sürece alım serbesttir. |
| **`btc_trend_filter_enabled`** | **`True`** | Bitcoin ani çöküş filtresi devrede. |
| **`retest_required`** | **`False`** | İkinci mumu beklemeden hacim patlaması anında doğrudan alım (Kaçırmama modu). |
| **`first_pump_candle_entry_blocked`** | **`False`** | İlk yeşil kırılım mumunda alıma izin verir (Erken ivme yakalama). |
| **`coin_dna_enabled`** | **`True`** | Coin DNA derinlik ve direnç kümesi kontrolü aktif. |
| **`coin_dna_execution_authority`** | **`SMART_BLOCK_ONLY`** | AI modelleri sadece satış duvarı varsa işlemi engeller; alım yetkisi deterministik koddadır. |

---

## 💾 3. Makine Tarafından Çalıştırılabilir JSON Konfigürasyonu

AI veya sistem yöneticisi bu bloğu doğrudan okuyarak veritabanına ve yerel yapılandırmaya yazabilir:

```json
{
  "active_preset": "whale_hunting_balanced",
  "volume_spike_multiplier": 1.15,
  "min_volume_usd": 2500.0,
  "min_5m_volume_usd": 2500.0,
  "min_24h_quote_volume_usd": 1000000.0,
  "max_daily_trades": 60,
  "max_recent_gain_24h": 45.0,
  "min_ai_score": 4.5,
  "max_budget_percent": 33.3,
  "max_concurrent_positions": 3,
  "take_profit_pct": 3.0,
  "take_profit_percent": 3.5,
  "stop_loss_pct": 1.2,
  "stop_loss_percent": 1.2,
  "break_even_trigger_pct": 1.2,
  "trailing_callback_pct": 0.6,
  "micro_trailing_activation_pct": 3.0,
  "micro_trailing_callback_pct": 0.6,
  "daily_max_loss_usd": 6.0,
  "daily_loss_limit_pct": 3.0,
  "retest_required": false,
  "first_pump_candle_entry_blocked": false,
  "post_stop_cooldown_minutes": 30,
  "cooldown_minutes": 30,
  "btc_min_rsi": 35.0,
  "btc_trend_filter_enabled": true,
  "btc_ema_tolerance_pct": 10.0,
  "btc_flash_dump_5m_pct": 0.5,
  "btc_flash_dump_15m_pct": 1.0,
  "require_futures_oi": false,
  "new_buy_orders_enabled": true,
  "existing_position_protection_enabled": true,
  "coin_dna_enabled": true,
  "coin_dna_execution_authority": "SMART_BLOCK_ONLY",
  "coin_dna_min_sample_count": 20,
  "coin_dna_target_levels": [0.5, 1.0, 1.5, 2.0, 2.5, 4.0],
  "coin_dna_cache_ttl_minutes": 60,
  "coin_dna_history_days": 30,
  "coin_dna_breakout_threshold_pct": 2.5,
  "coin_dna_volume_surge_multiplier": 2.0,
  "coin_dna_ambiguous_bar_threshold_pct": 0.1,
  "coin_dna_resistance_cluster_tolerance_pct": 0.8,
  "hybrid_micro_cut_enabled": false,
  "r_exit_enabled": false,
  "r_first_tp_at_r": 1.0,
  "r_trailing_at_r": 1.5,
  "r_breakeven_at_r": 1.0,
  "r_final_target_r": 2.0,
  "use_atr_dynamic_r": false,
  "r_first_tp_qty_pct": 40.0,
  "micro_cut_time_loss_pct": 0.25,
  "minimum_expected_net_rr": 1.2,
  "micro_cut_taker_sell_ratio": 65.0,
  "net_advantage_gate_enabled": false,
  "micro_cut_time_limit_minutes": 999,
  "micro_cut_taker_window_minutes": 3
}
```

---

## ⚡ 4. Bu Ayarları Tek Tuşla Geri Yükleme Betiği (`restore_14_september_settings.py`)

Kullanıcı bu dosyayı verdiğinde veya terminalden çalıştırmak istediğinde aşağıdaki Python komutu bu ayarları hem Supabase'e hem de yerel dosyalara anında uygular:

```python
import json
from db import save_strategy_config, set_system_setting

# 14 Eylül Başarılı Parametre Seti
SEPTEMBER_14_CONFIG = {
    "active_preset": "whale_hunting_balanced",
    "volume_spike_multiplier": 1.15,
    "min_volume_usd": 2500.0,
    "min_5m_volume_usd": 2500.0,
    "min_24h_quote_volume_usd": 1000000.0,
    "max_daily_trades": 60,
    "max_recent_gain_24h": 45.0,
    "min_ai_score": 4.5,
    "max_budget_percent": 33.3,
    "max_concurrent_positions": 3,
    "take_profit_pct": 3.0,
    "take_profit_percent": 3.5,
    "stop_loss_pct": 1.2,
    "stop_loss_percent": 1.2,
    "break_even_trigger_pct": 1.2,
    "trailing_callback_pct": 0.6,
    "micro_trailing_activation_pct": 3.0,
    "micro_trailing_callback_pct": 0.6,
    "daily_max_loss_usd": 6.0,
    "daily_loss_limit_pct": 3.0,
    "retest_required": False,
    "first_pump_candle_entry_blocked": False,
    "post_stop_cooldown_minutes": 30,
    "cooldown_minutes": 30,
    "btc_min_rsi": 35.0,
    "btc_trend_filter_enabled": True,
    "btc_ema_tolerance_pct": 10.0,
    "btc_flash_dump_5m_pct": 0.5,
    "btc_flash_dump_15m_pct": 1.0,
    "require_futures_oi": False,
    "new_buy_orders_enabled": True,
    "existing_position_protection_enabled": True,
    "coin_dna_enabled": True,
    "coin_dna_execution_authority": "SMART_BLOCK_ONLY"
}

def apply_14_september_profile():
    # 1. Supabase ve Yerel Stratejiyi Güncelle
    save_strategy_config(SEPTEMBER_14_CONFIG)
    
    # 2. Sistem İzinlerini Aç
    set_system_setting("new_buy_orders_enabled", True)
    set_system_setting("execution_mode", "LIVE_TRADING")
    
    # 3. Yerel Yedek Dosyasına Kaydet
    with open("strategy_config_local.json", "w", encoding="utf-8") as f:
        json.dump(SEPTEMBER_14_CONFIG, f, indent=2, ensure_ascii=False)
        
    print("✅ 14 Eylül Kazandıran Strateji Parametreleri Başarıyla Yüklendi ve Canlıya Alındı!")

if __name__ == "__main__":
    apply_14_september_profile()
```

---

## 🛡️ 5. AI Geri Yükleme Protokolü (Antigravity Asistanına Özel Talimat)
Kullanıcı gelecekteki herhangi bir tarihte:
* *"14 Eylül ayarlarını uygula"*
* *"14 Eylül'deki kazandıran parametrelere geri dön"*
* Veya bu dosyanın yolunu/içeriğini verdiğinde:

**AI Asistanı doğrudan şunları yapacaktır:**
1. `14_EYLUL_KAZANDIRAN_STRATEJI_AYARLARI.md` dosyasındaki Bölüm 3 JSON sözlüğünü okur.
2. `db.py` içerisindeki `save_strategy_config(...)` fonksiyonunu bu sözlükle çağırır.
3. Supabase `global_system_settings` tablosundaki `new_buy_orders_enabled = True` ve `execution_mode = LIVE_TRADING` anahtarlarını doğrular.
4. `strategy_config_local.json` dosyasını bu verilerle günceller.
5. Kullanıcıya ayarların eksiksiz geri yüklendiğini teyit eder.
