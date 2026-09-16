import json
import os
import sys

# Windows konsol UTF-8 desteği
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')

from db import save_strategy_config, set_system_setting

# 🏆 14 Eylül 2026 Gecesi +$3.08 USD Kâr Kazandıran Orijinal Parametre Seti
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

def apply_14_september_profile(is_paper_mode: bool = True):
    print("🚀 [14 Eylül Kazandıran Profil]: Ayarlar uygulanıyor...")
    
    # 1. Supabase ve Bellek Güncellemesi
    save_strategy_config(SEPTEMBER_14_CONFIG)
    
    # 2. Sistem İzinlerini Aç (Kullanıcı talimatıyla PAPER TRADING korunur)
    set_system_setting("new_buy_orders_enabled", True)
    exec_mode = "PAPER_TRADING" if is_paper_mode else "LIVE_TRADING"
    set_system_setting("execution_mode", exec_mode)
    
    # 3. Tenant Trading Modlarını Paper Olarak Kilitle
    from db import get_all_active_tenants, set_tenant_trading_mode, get_supabase
    tenants = get_all_active_tenants()
    for t in tenants:
        t_id = t.get("id")
        tg_id = t.get("telegram_chat_id")
        if t_id:
            set_tenant_trading_mode(t_id, is_paper=is_paper_mode)
        if tg_id:
            set_tenant_trading_mode(tg_id, is_paper=is_paper_mode)
            
    # 4. user_tenants Tablosunu 14 Eylül Parametrelerine Senkronize Et
    client = get_supabase()
    if client:
        try:
            client.table("user_tenants").update({
                "stop_loss_percent": 1.2,
                "max_budget_percent": 33.3
            }).eq("telegram_chat_id", 8739367825).execute()
        except Exception as e_ut:
            print(f"⚠️ [user_tenants update]: {e_ut}")
            
    # 5. Yerel Yedek Dosyasına Kaydet
    with open("strategy_config_local.json", "w", encoding="utf-8") as f:
        json.dump(SEPTEMBER_14_CONFIG, f, indent=2, ensure_ascii=False)
        
    print(f"✅ [BAŞARILI]: 14 Eylül Stratejisi uygulandı! İşlem Modu: {exec_mode} 🧪")

if __name__ == "__main__":
    apply_14_september_profile(is_paper_mode=True)
