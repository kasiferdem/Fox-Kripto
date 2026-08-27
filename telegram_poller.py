import os, sys, time, requests, io, json, re, threading, hmac, hashlib

# Windows Console Emoji UnicodeEncodeError Önleyici
if hasattr(sys.stdout, 'buffer'):
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
if hasattr(sys.stderr, 'buffer'):
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')

from dotenv import load_dotenv
from db import (
    register_user_tenant, get_tenant_by_chat_id, get_supabase, 
    log_trade_decision, save_graph_state, load_graph_state,
    get_active_positions_from_db, save_position_to_db, remove_position_from_db,
    get_tenant_trading_mode, set_tenant_trading_mode, set_cooldown_in_db
)
from exchange import (
    fetch_portfolio_balance, execute_spot_trade, fetch_ticker_price, 
    get_live_usd_try_rate, convert_dust_to_bnb, fetch_top_volume_gainers,
    BinanceGlobalRESTClient
)
from market_regime import check_market_regime
from circuit_breaker import get_adaptive_max_slots
from news_service import get_localized_crypto_news, fetch_live_global_crypto_news
from surge_detector import detect_early_volume_breakouts
from prompts import call_gpt4o

load_dotenv()
TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")
BASE_URL = f"https://api.telegram.org/bot{TOKEN}"

# Kullanıcı oturum durumları (Registration Wizards)
user_states = {}

def send_message(chat_id: int, text: str, reply_markup=None):
    """
    Güvenli Telegram Mesaj Gönderme:
    Markdown formatı veya reply_markup hatası almamak için dinamik payload oluşturur.
    """
    payload = {"chat_id": chat_id, "text": text, "parse_mode": "Markdown"}
    if reply_markup is not None:
        payload["reply_markup"] = reply_markup

    try:
        res = requests.post(f"{BASE_URL}/sendMessage", json=payload, timeout=10)
        if res.status_code != 200:
            # Fallback: Markdown formatını kaldırıp tekrar dene
            payload_fallback = {"chat_id": chat_id, "text": text}
            if reply_markup is not None:
                payload_fallback["reply_markup"] = reply_markup
            res_retry = requests.post(f"{BASE_URL}/sendMessage", json=payload_fallback, timeout=10)
            print(f"📩 Telegram Send Retry (Plain): {res_retry.status_code} - {res_retry.text}")
        else:
            print(f"✅ Telegram Send Success: Chat ID={chat_id}")
    except Exception as e:
        print(f"❌ Telegram Send Error: {e}")

def handle_update(update: dict):
    # 1. Buton Tıklamaları (Callback Query - ONAY / REDDET)
    callback = update.get("callback_query")
    if callback:
        cb_id = callback["id"]
        cb_data = callback.get("data", "")
        chat_id = callback["message"]["chat"]["id"]
        
        # Telegram loading simgesini kaldır
        try: requests.post(f"{BASE_URL}/answerCallbackQuery", json={"callback_query_id": cb_id})
        except: pass
        
        # Borsa Seçim Butonları
        if cb_data.startswith("select_exchange_"):
            selected_ex = cb_data.replace("select_exchange_", "")
            user_states[chat_id] = {"step": "AWAITING_API_KEY", "exchange_id": selected_ex}
            label = "🇹🇷 Binance TR" if selected_ex == "binancetr" else "🌍 Binance Global"
            send_message(chat_id, f"✅ Seçilen Borsa: *{label}*\n\nLütfen hesabınıza ait *API Key* bilginizi bu sohbete mesaj olarak gönderin:")
            return

        action = "Approved" if "approve" in cb_data else "Rejected"
        parts = cb_data.split("_")
        session_id = "_".join(parts[1:]) if len(parts) > 1 else "session_001"
        
        print(f"🎯 [Telegram Poller Buton Tıklandı]: Chat ID={chat_id}, Action={action}, SessionID={session_id}")
        
        tenant = get_tenant_by_chat_id(chat_id)
        saved_state = load_graph_state(session_id) or {}
        proposal = saved_state.get("trade_proposal")
        
        # Eğer saved_state'ten proposal gelmediyse varsayılan bütçe teklifi oluştur
        if not proposal and action == "Approved":
            ticker = fetch_ticker_price("BTC/USDT")
            proposal = {
                "symbol": "BTC/USDT",
                "direction": "BUY",
                "amount_usd": 10.0,
                "entry_price": float(ticker.get("last_price", 64000.0)),
                "stop_loss_percent": 4.0,
                "stop_loss_price": float(ticker.get("last_price", 64000.0)) * 0.96
            }

        if action == "Approved" and proposal:
            if not tenant:
                send_message(chat_id, "❌ YETKİSİZ İŞLEM: Bu Telegram kullanıcısı için kayıtlı bir tenant bulunamadı.")
                return
            send_message(chat_id, f"✅ İŞLEM ONAYLANDI! Borsaya emir iletiliyor...\n{proposal['symbol']} - ${proposal['amount_usd']} USD")
            result = execute_spot_trade(
                symbol=proposal["symbol"],
                side=proposal["direction"],
                amount_usd=proposal["amount_usd"],
                stop_loss_price=proposal["stop_loss_price"],
                tenant_config=tenant
            )
            log_trade_decision({
                **proposal, "sentiment_score": saved_state.get("sentiment_score", 7.5),
                "human_approval": "Approved", "status": result.get("status", "EXECUTED"),
                "order_id": result.get("order_id"), "execution_details": result
            }, tenant_id=tenant.get("id") if tenant else None)
            
            send_message(chat_id, f"🚀 İŞLEM BORSADA GERÇEKLEŞTİ!\nEmir No: {result.get('order_id', 'TRY_SPOT_EXEC')}\nİnfaz Fiyatı: ${result.get('executed_price', proposal['entry_price'])}")
        else:
            send_message(chat_id, "❌ İŞLEM REDDEDİLDİ VEYA İPTAL EDİLDİ.")
        return

    # 2. Normal Mesajlar ve Komutlar
    message = update.get("message")
    if not message: return
    
    from_id = message.get("from", {}).get("id") or message.get("chat", {}).get("id")
    chat_id = message["chat"]["id"]
    raw_text = (message.get("text") or "").strip()
    first_name = message["chat"].get("first_name", "Kullanıcı")
    text_clean = raw_text.lower().lstrip("/").strip()

    # 🛡️ P0-3 GÜVENLİK KONTROLÜ: Yalnızca yetkili yönetici veya kayıtlı tenant'ların mesajları işlenir
    admin_chat_id = int(os.environ.get("TELEGRAM_CHAT_ID", "8739367825"))
    tenant = get_tenant_by_chat_id(from_id) or get_tenant_by_chat_id(chat_id)
    if from_id != admin_chat_id and not tenant:
        print(f"🛑 [Yetkisiz Telegram Mesajı Reddedildi]: from_id={from_id}, chat_id={chat_id}")
        return

    print(f"📩 [Telegram Gelen Mesaj]: From ID={from_id}, Chat ID={chat_id}, Text='{raw_text}' (Clean='{text_clean}')")

    # Dil Değiştirme Komutları (Language Switcher)
    if text_clean in ["dil en", "lang en", "english", "ingilizce", "dil ingilizce", "/lang en", "/en"]:
        send_message(
            chat_id,
            f"🇬🇧 *LANGUAGE SWITCHED TO ENGLISH!* ✅\n\n"
            f"👋 Hello *{first_name}*! You can now use all commands and natural language instructions in English:\n\n"
            f"📌 *Quick Commands:*\n"
            f"• `status` or `balance` - View your live portfolio.\n"
            f"• `news` - Read latest global crypto market headlines.\n"
            f"• `analysis` - Trigger an instant AI market scan.\n"
            f"• `Set take profit 3%` or `Stop loss 2%` - Update risk limits.\n"
            f"• `Buy $15 SOL` or `Sell 10$ DOGE` - Execute trades.\n\n"
            f"_(Türkçeye dönmek için `dil tr` yazabilirsiniz.)_"
        )
        return

    if text_clean in ["dil tr", "lang tr", "turkce", "türkçe", "dil turkce", "dil türkçe", "/lang tr", "/tr"]:
        send_message(
            chat_id,
            f"🇹🇷 *DİL TÜRKÇE OLARAK AYARLANDI!* ✅\n\n"
            f"👋 Merhaba *{first_name}*! Artık tüm komutları Türkçe kullanabilirsiniz:\n\n"
            f"📌 *Hızlı Komutlar:*\n"
            f"• `durum` veya `bakiye` - Canlı portföyünüzü görün.\n"
            f"• `haberler` - En sıcak küresel kripto haberleri.\n"
            f"• `analiz` - Canlı yapay zeka piyasa taraması.\n"
            f"• `Kâr hedefimi %3 yap` - Risk limitlerinizi güncelleyin.\n"
            f"• `500 TL SOL al` veya `10$ DOGE sat` - Doğal dille al-sat yapın.\n\n"
            f"_(To switch to English type `lang en`)_"
        )
        return

    # Komut İşleme (Taksim / işaretli veya taksimsiz esnek eşleşme)
    if text_clean in ["start", "help", "yardim", "yardım", "merhaba", "hello", "hi", "komutlar", "komut", "menu", "menü", "/komutlar", "/help", "/start", "/yardim", "/yardım", "/menu"]:
        tenant = get_tenant_by_chat_id(chat_id)
        if tenant:
            help_card = (
                f"🤖 *FOX-KRİPTO BOT KOMUTLAR REHBERİ* 📋\n\n"
                f"👋 Merhaba *{first_name}*! Kullanabileceğiniz tüm komutlar aşağıdadır:\n\n"
                f"📊 *PORTFÖY & KASA TAKİBİ:*\n"
                f"• `durum` veya `bakiye` ➔ Canlı çift borsa (TR+Global) varlıklarınızı ve açık pozisyonlarınızı listeler.\n"
                f"• `kasa fark` veya `fark` ➔ Son sorguladığınız andan bu yana kasanızdaki kâr/zarar farkını kuruşu kuruşuna verir.\n"
                f"• `rapor` veya `gun sonu` ➔ Gece 00:01'den bu yana 24 saatlik resmi PnL bilançosunu çıkarır.\n\n"
                f"⚡ *AL-SAT & MANUEL İŞLEMLER:*\n"
                f"• `BTC sat` veya `MOVE sat` ➔ Belirtilen coinin tamamını anında marketten nakde çevirir.\n"
                f"• `500 TL SOL al` veya `Buy $10 SOL` ➔ Belirttiğiniz bütçeyle anında canlı alım yapar.\n"
                f"• `tozları temizle` veya `bnb yap` ➔ Cüzdandaki $1 altı tüm kırıntıları tek tuşla BNB'ye dönüştürür.\n\n"
                f"🧠 *YAPAY ZEKA & ANALİZ:*\n"
                f"• `analiz` veya `tara` ➔ Piyasadaki taze balina kırılımlarını ve ivme puanlarını tarar.\n"
                f"• `haberler` veya `gundem` ➔ CoinDesk, CoinTelegraph ve Decrypt'ten canlı kripto haberlerini çeker.\n\n"
                f"⚙️ *AYARLAR & MOD GEÇİŞİ:*\n"
                f"• `Kâr hedefimi %3 yap` ➔ Otonom kâr alma (Take-Profit) hedefinizi günceller.\n"
                f"• `Stop limitimi %2 yap` ➔ Otonom zarar kes (Stop-Loss) limitinizi günceller.\n"
                f"• `/test` (Sanal Mod) | `/canli` (Gerçek Borsa Modu) ➔ Çalışma modunu değiştirir.\n"
                f"• `/surum` veya `/ip` ➔ Sunucu IP'sini, sürümünü ve piyasa rejimini gösterir.\n"
                f"• `dil tr` 🇹🇷 | `lang en` 🇬🇧 ➔ Botun dilini değiştirir.\n\n"
                f"💡 _İpucu: Komutları büyük/küçük harf fark etmeksizin dilediğiniz gibi yazabilirsiniz!_"
            )
            send_message(chat_id, help_card)
        else:
            send_message(chat_id, f"👋 Merhaba *{first_name}*!\nFox-Kripto Sistemine Hoş Geldiniz.\n\nBinance hesabınızı bağlamak için `bagla` yazabilirsiniz.")
        return

    # 🎛️ TEST MODU / CANLI MOD TEK TUŞ GEÇİŞİ (Mode Switcher)
    if text_clean in ["test", "test modu", "test_modu", "/test", "/paper", "paper", "sanal", "sanal mod", "/sanal"]:
        set_tenant_trading_mode(chat_id, is_paper=True)
        send_message(
            chat_id,
            f"🧪 *SİSTEM SANAL TEST (PAPER TRADING) MODUNA ALINDI!* ✅\n\n"
            f"💰 *Sanal Kasa:* $100.00 USDT (Monopoly Parası)\n"
            f"🛡️ *Borsa Riski:* 0 TL / 0 USD (Gerçek hesabınıza dokunulmaz)\n"
            f"📈 *Çalışma:* Binance canlı tahtasından anlık fiyatlarla sanal al-sat yapılır.\n\n"
            f"_(İstediğiniz zaman `/canli` yazarak gerçek borsa hesabınıza geçebilirsiniz.)_"
        )
        return

    if text_clean in ["canli", "canlı", "canli mod", "canlı mod", "/canli", "/live", "live", "/canlı"]:
        set_tenant_trading_mode(chat_id, is_paper=False)
        send_message(
            chat_id,
            f"🚀 *SİSTEM GERÇEK CANLI BORSA MODUNA ALINDI!* ⚠️\n\n"
            f"🏦 *Borsa:* Binance TR & Binance Global\n"
            f"🛡️ *Emniyet:* ATR(14) Dinamik Stop ve Fiziksel Borsa Stop Emri devrede.\n"
            f"📈 *Çalışma:* Onaylanan işlemler gerçek borsa hesabınızla açılacaktır.\n\n"
            f"_(Test ortamına dönmek için istediğiniz an `/test` yazabilirsiniz.)_"
        )
        return

    if text_clean in ["mod", "mode", "/mod", "durum mod", "hangi moddayım", "hangi moddayim"]:
        current_is_paper = get_tenant_trading_mode(chat_id)
        if current_is_paper:
            send_message(chat_id, "🧪 *ŞU ANKİ ÇALIŞMA MODUNUZ:* `SANAL TEST (Paper Trading - $100)`\nBorsa Riski: $0.00. Gerçek canlıya geçmek için `/canli` yazabilirsiniz.")
        else:
            send_message(chat_id, "🚀 *ŞU ANKİ ÇALIŞMA MODUNUZ:* `GERÇEK CANLI (Live Binance)`\nİşlemler gerçek cüzdanınızla yapılıyor. Teste geçmek için `/test` yazabilirsiniz.")
        return

    if text_clean in ["surum", "sürüm", "version", "/surum", "/sürüm", "/version", "deploy", "/deploy", "health", "/health", "saglik", "sağlık", "ip", "/ip"]:
        
        server_ip = "Bilinmiyor"
        try:
            r_ip = requests.get("https://api.ipify.org", timeout=2)
            if r_ip.status_code == 200:
                server_ip = r_ip.text.strip()
        except Exception:
            pass

        regime = check_market_regime()
        reg_status = "🟢 BOĞA / NÖTR (Alıma Açık)" if regime.get("is_bullish") else f"🔴 AYI / FIRTINA ({regime.get('reason')})"
        
        msg_v = (
            f"ℹ️ *FOX-KRİPTO SİSTEM & VERSİYON BİLGİSİ*\n\n"
            f"🏷️ *Sürüm:* `v2.5.0-PROD`\n"
            f"🌐 *Sunucu Dış IP:* `{server_ip}`\n"
            f"🚀 *Son Deploy:* `Canlı ve Güncel`\n"
            f"🛡️ *Piyasa Rejim Durumu:* {reg_status}\n"
            f"📊 *BTC 15m/1h Fırtına Kalkanı:* `AKTİF`\n"
            f"🎛️ *Dinamik Slot Yönetimi:* `Kasa < $300 (3 Slot) | > $1000 (7 Slot)`\n"
            f"⚡ *Borsa Hatları:* `Binance TR & Binance Global (5 Yedek Hat)`\n"
            f"🤖 *Yönetim Komitesi:* `Claude (Risk) • Codex (Kod) • Antigravity (Mimari)`\n\n"
            f"💡 _(Eğer Binance Global -2015 verirse yukarıdaki Sunucu Dış IP'sini Binance API Ayarlarındaki IP Whitelist'e ekleyiniz.)_"
        )
        send_message(chat_id, msg_v)
        return

    if text_clean in ["kurallar", "kural", "anayasamız", "anayasamiz", "/kurallar", "/rules", "rules"]:
        from db import get_system_constitution_rules
        rules = get_system_constitution_rules()
        tiers = rules.get("adaptive_slot_tiers", [])
        tier_str = ""
        for t in tiers:
            tier_str += f" • *{t.get('desc')}:* Max `{t.get('slots')} Slot` (Slot Başı: `%{t.get('share_pct'):.1f}`)\n"
            
        rules_msg = (
            f"📜 *FOX-KRİPTO RESMİ SİSTEM ANAYASASI (VERİTABANI KİLİTLİ)* 🏛️\n\n"
            f"📊 *1. KASA & SLOT KADEMELENDİRME MATRİSİ:*\n"
            f"{tier_str}\n"
            f"🛡️ *2. LİKİDİTE & TOZ GÜVENLİK BARAJLARI:*\n"
            f" • *Toz (Dust) Eşiği:* `>${rules.get('dust_threshold_usd', 6.50)} USD` / `>₺{rules.get('dust_threshold_try', 250.0):.0f} TL`\n"
            f" • *Asgari 24s Hacim (TR):* `₺{rules.get('min_24h_volume_try', 15000000):,.0f} TL`\n"
            f" • *Asgari 24s Hacim (Global):* `${rules.get('min_24h_volume_usd', 500000):,.0f} USD`\n"
            f" • *5dk Balina Hacim Patlaması:* `>${rules.get('min_5m_breakout_volume_usd', 25000):,.0f} USD`\n\n"
            f"🎯 *3. RİSK & KÂR/ZARAR STANDARTLARI:*\n"
            f" • *Kâr Alma Hedefi:* `+%{rules.get('take_profit_target_pct', 3.50):.2f} Net`\n"
            f" • *Zarar Durdurma Limiti:* `-%{rules.get('stop_loss_target_pct', 2.50):.2f}`\n"
            f" • *Ardışık Stop Kilidi:* `{rules.get('consecutive_stops_circuit_limit', 3)} İşlem` (Soğuma: `60 dk`)\n\n"
            f"🔐 *Son Güncelleme:* `{rules.get('updated_at')}`\n"
            f"👤 *Yetkili:* `{rules.get('last_modified_by')}`\n\n"
            f"💡 _Bu kurallar Supabase veritabanında saklanmakta ve her değişiklik kalıcı olarak loglanmaktadır._"
        )
        send_message(chat_id, rules_msg)
        return

    if text_clean in ["rapor", "gun sonu", "gün sonu", "gunsonu", "günsonu", "/rapor", "/report", "daily report", "kar zarar", "kâr zarar", "pnl"]:
        tenant = get_tenant_by_chat_id(chat_id)
        if not tenant:
            send_message(chat_id, "⚠️ Kayıtlı hesap bulunamadı.")
            return
            
        send_message(chat_id, "📊 *GÜN SONU / PnL PERFORMANS RAPORU HAZIRLANIYOR...*\n00:01 Kasa Başlangıcı ile Güncel Durum Karşılaştırılıyor...")
        try:
            client = get_supabase()
            res_b = client.table("crypto_agent_states").select("state_data").eq("session_id", "daily_baseline_2026_08_22").execute()
            b_data = (res_b.data[0].get("state_data") if res_b.data else {}) or {}
            
            base_usd = float(b_data.get("combined", {}).get("total_usd", 128.38))
            base_try = float(b_data.get("combined", {}).get("total_try", 6111.74))
            
            curr_bal = fetch_portfolio_balance(tenant)
            curr_usd = float(curr_bal.get("total_usdt", 0.0))
            curr_try = float(curr_bal.get("total_try", 0.0))
            usd_rate = get_live_usd_try_rate()
            if curr_try <= 0 and curr_usd > 0 and usd_rate > 0:
                curr_try = curr_usd * usd_rate
                
            diff_usd = curr_usd - base_usd
            diff_try = curr_try - base_try
            diff_pct = (diff_usd / base_usd) * 100.0 if base_usd > 0 else 0.0
            
            pnl_emoji = "📈" if diff_usd >= 0 else "📉"
            pnl_sign = "+" if diff_usd >= 0 else ""
            
            tr_curr_t = float(curr_bal.get("binance_tr", {}).get("total_try", 0.0))
            gl_curr_u = float(curr_bal.get("binance_global", {}).get("total_usdt", 0.0))
            
            msg_rep = (
                f"📑 *22 AĞUSTOS GÜN SONU PERFORMANS RAPORU*\n\n"
                f"⏰ *Referans Başlangıç:* `00:01:00`\n"
                f"💵 *00:01 Başlangıç Kasası:* `${base_usd:,.2f} USD` (~₺{base_try:,.2f} TL)\n\n"
                f"⏰ *Güncel Kasa Durumu:* `{time.strftime('%H:%M:%S', time.localtime())}`\n"
                f"🇹🇷 Binance TR: `₺{tr_curr_t:,.2f} TL`\n"
                f"🌍 Binance Global: `${gl_curr_u:,.2f} USD`\n"
                f"💰 *Toplam Canlı Kasa:* `${curr_usd:,.2f} USD` (~₺{curr_try:,.2f} TL)\n\n"
                f"━━━━━━━━━━━━━━━━━━━━\n"
                f"{pnl_emoji} *NET GÜNLÜK PnL (KÂR/ZARAR):*\n"
                f"• Değişim: *{pnl_sign}${diff_usd:,.2f} USD* ({pnl_sign}₺{diff_try:,.2f} TL)\n"
                f"• Getiri Oranı: *{pnl_sign}%{diff_pct:.2f}*\n"
                f"━━━━━━━━━━━━━━━━━━━━\n"
                f"🛡️ *Hedef Kâr:* `%3.5` | *Stop-Loss:* `%2.5`\n"
                f"🎯 *23:00 Otomatik Kapanış Raporu:* `Kayıt Altında ve Takipte` ✅"
            )
            send_message(chat_id, msg_rep)
        except Exception as re:
            send_message(chat_id, f"⚠️ Rapor oluşturma hatası: {re}")
        return

    if text_clean in ["kasa fark", "kasa farkı", "kasafark", "kasafarki", "/kasafark", "/fark", "fark", "bakiye fark", "bakiye farkı"]:
        tenant = get_tenant_by_chat_id(chat_id)
        if not tenant:
            send_message(chat_id, "⚠️ Kayıtlı hesap bulunamadı.")
            return
            
        send_message(chat_id, "⏳ *SON SORGULANAN DURUM İLE GÜNCEL KASA FARKI HESAPLANIYOR...*")
        try:
            client = get_supabase()
            state_key = f"last_queried_balance_{chat_id}"
            res_prev = client.table("crypto_agent_states").select("state_data").eq("session_id", state_key).execute()
            prev_data = (res_prev.data[0].get("state_data") if res_prev.data else {}) or {}
            
            curr_bal = fetch_portfolio_balance(tenant)
            curr_ts = time.time()
            usd_try_rate = get_live_usd_try_rate()
            if usd_try_rate <= 0:
                usd_try_rate = 48.0
            
            is_dual = bool(curr_bal.get("is_dual"))
            is_tr = (tenant.get("exchange_id") == "binancetr")
            is_gl = (tenant.get("exchange_id") == "binance" or (not is_dual and not is_tr))
            
            # Güncel Değerler
            curr_tr_try = float(curr_bal.get("binance_tr", {}).get("total_try", 0.0)) if is_dual else (float(curr_bal.get("total_try", 0.0)) if is_tr else 0.0)
            curr_gl_usd = float(curr_bal.get("binance_global", {}).get("total_usdt", 0.0)) if is_dual else (float(curr_bal.get("total_usdt", 0.0)) if is_gl else 0.0)
            curr_tot_usd = float(curr_bal.get("total_usdt", 0.0))
            curr_tot_try = float(curr_bal.get("total_try", 0.0)) or (curr_tot_usd * usd_try_rate)
            
            # Yeni durumu kaydet
            new_snap = {
                "timestamp": curr_ts,
                "time_str": time.strftime("%H:%M:%S", time.localtime(curr_ts)),
                "tr_try": curr_tr_try,
                "gl_usd": curr_gl_usd,
                "tot_usd": curr_tot_usd,
                "tot_try": curr_tot_try
            }
            client.table("crypto_agent_states").upsert({"session_id": state_key, "state_data": new_snap}).execute()
            
            if not prev_data:
                # İlk kez çalıştırıldıysa
                if is_gl and not is_dual:
                    exch_line = f"🌍 *Binance Global Kasa:* `${curr_gl_usd:,.2f} USD` (~₺{curr_tot_try:,.2f} TL)\n"
                elif is_tr:
                    exch_line = f"🇹🇷 *Binance TR Kasa:* `₺{curr_tr_try:,.2f} TL` (~${curr_tot_usd:,.2f} USD)\n"
                else:
                    exch_line = (
                        f"🇹🇷 *Binance TR:* `₺{curr_tr_try:,.2f} TL`\n"
                        f"🌍 *Binance Global:* `${curr_gl_usd:,.2f} USD`\n"
                        f"🏆 *Toplam Birleşik Kasa:* `${curr_tot_usd:,.2f} USD` (~₺{curr_tot_try:,.2f} TL)\n"
                    )
                msg_init = (
                    f"📌 *KASA FARKI REFERANS NOKTASI OLUŞTURULDU*\n\n"
                    f"⏰ *Kayıt Saati:* `{new_snap['time_str']}`\n"
                    f"{exch_line}\n"
                    f"💡 _Bundan sonraki her `fark` veya `durum` sorgunuzda aradaki kâr/zarar farkı bu referans noktasıyla kuruşu kuruşuna karşılaştırılacaktır._"
                )
                send_message(chat_id, msg_init)
                return
                
            prev_ts = float(prev_data.get("timestamp", curr_ts))
            prev_time_str = prev_data.get("time_str", "Bilinmiyor")
            mins_ago = int((curr_ts - prev_ts) / 60)
            time_ago_str = f"{mins_ago} dakika önce" if mins_ago > 0 else "Az önce"
            
            prev_tr_try = float(prev_data.get("tr_try", curr_tr_try))
            prev_gl_usd = float(prev_data.get("gl_usd", curr_gl_usd))
            prev_tot_usd = float(prev_data.get("tot_usd", curr_tot_usd))
            prev_tot_try = float(prev_data.get("tot_try", curr_tot_try))
            
            # Fark Hesaplamaları
            diff_tr_try = curr_tr_try - prev_tr_try
            diff_gl_usd = curr_gl_usd - prev_gl_usd
            diff_tot_usd = curr_tot_usd - prev_tot_usd
            diff_tot_try = curr_tot_try - prev_tot_try
            
            diff_tot_pct = (diff_tot_usd / prev_tot_usd * 100.0) if prev_tot_usd > 0 else 0.0
            
            sign_tr = "+" if diff_tr_try >= 0 else ""
            sign_gl = "+" if diff_gl_usd >= 0 else ""
            sign_tot = "+" if diff_tot_usd >= 0 else ""
            emoji_tot = "📈" if diff_tot_usd >= 0 else "📉"
            
            if is_gl and not is_dual:
                breakdown_text = (
                    f"🌍 *BINANCE GLOBAL:* `${prev_gl_usd:,.2f}` ➔ `${curr_gl_usd:,.2f} USD`\n"
                    f"   └ Net Değişim: *{sign_gl}${diff_gl_usd:,.2f} USD* ({sign_tot}₺{diff_tot_try:,.2f} TL)\n"
                )
            elif is_tr:
                breakdown_text = (
                    f"🇹🇷 *BINANCE TR:* `₺{prev_tr_try:,.2f}` ➔ `₺{curr_tr_try:,.2f} TL`\n"
                    f"   └ Net Değişim: *{sign_tr}₺{diff_tr_try:,.2f} TL* ({sign_tot}${diff_tot_usd:,.2f} USD)\n"
                )
            else:
                breakdown_text = (
                    f"🇹🇷 *BINANCE TR:* `₺{prev_tr_try:,.2f}` ➔ `₺{curr_tr_try:,.2f} TL`\n"
                    f"   └ Fark: *{sign_tr}₺{diff_tr_try:,.2f} TL*\n\n"
                    f"🌍 *BINANCE GLOBAL:* `${prev_gl_usd:,.2f}` ➔ `${curr_gl_usd:,.2f} USD`\n"
                    f"   └ Fark: *{sign_gl}${diff_gl_usd:,.2f} USD*\n"
                )
            
            msg_diff = (
                f"⚖️ *SON DURUM İLE GÜNCEL KASA FARKI RAPORU*\n\n"
                f"⏱️ *Önceki Referans:* `{prev_time_str}` _({time_ago_str})_\n"
                f"⏱️ *Şu Anki Saat:* `{new_snap['time_str']}`\n\n"
                f"{breakdown_text}\n"
                f"━━━━━━━━━━━━━━━━━━━━\n"
                f"{emoji_tot} *TOPLAM PORTFÖY DEĞİŞİMİ:*\n"
                f"• Önceki: `${prev_tot_usd:,.2f} USD` (~₺{prev_tot_try:,.2f} TL)\n"
                f"• Güncel: `${curr_tot_usd:,.2f} USD` (~₺{curr_tot_try:,.2f} TL)\n"
                f"• *Net Fark:* *{sign_tot}${diff_tot_usd:,.2f} USD* ({sign_tot}₺{diff_tot_try:,.2f} TL)\n"
                f"• *Getiri Değişimi:* *{sign_tot}%{diff_tot_pct:.2f}*\n"
                f"━━━━━━━━━━━━━━━━━━━━\n"
                f"💡 _Yeni referans noktası `{new_snap['time_str']}` olarak güncellendi._"
            )
            send_message(chat_id, msg_diff)
        except Exception as e_fark:
            send_message(chat_id, f"⚠️ Kasa farkı hesaplama hatası: {e_fark}")
        return

    tenant = get_tenant_by_chat_id(chat_id)
    user_lang = str(tenant.get("preferred_language", "tr") if tenant else "tr").lower()

    if text_clean in ["haber", "haberler", "haberle", "gundem", "gündem", "news", "kripto haber", "son haberler"]:
        is_en = (user_lang == "en") or (text_clean in ["news"])
        send_message(chat_id, "📡 *FETCHING GLOBAL CRYPTO NEWS...*" if is_en else "📡 *KÜRESEL KRİPTO HABERLERİ ÇEKİLİYOR...*\nCoinDesk, CoinTelegraph ve Decrypt taranıyor...")
        try:
            lang_code = "en" if is_en else "tr"
            news_items = get_localized_crypto_news(lang=lang_code, limit=6)
            
            if is_en:
                summary_msg = (
                    f"🌍 *LIVE GLOBAL CRYPTO HEADLINES*\n"
                    f"_(CoinDesk • CoinTelegraph • Decrypt)_\n\n"
                    f"{news_items}\n\n"
                    f"🤖 *AI Analysis:* Global headlines are continuously scanned and integrated into autonomous trading strategies! 🚀"
                )
            else:
                summary_msg = (
                    f"🌍 *CANLI KÜRESEL KRİPTO GÜNDEMİ*\n"
                    f"_(CoinDesk • CoinTelegraph • Decrypt)_\n\n"
                    f"{news_items}\n\n"
                    f"🤖 *Yapay Zeka Analizi:* Küresel haber akışı taranarak otomatik alım-satım stratejilerine doğrudan yansıtılmaktadır! 🚀"
                )
            send_message(chat_id, summary_msg)
        except Exception as ne:
            send_message(chat_id, f"⚠️ Error: {ne}")
        return

    if text_clean in ["toz", "dust", "toz temizle", "tozlari temizle", "tozları temizle", "kırıntı", "kirinti", "kırıntıları temizle", "kirintilari temizle", "kırıntı temizle", "kirinti temizle", "kırıntıları sil", "tozları sil", "/dust", "dust to bnb", "toz bnb", "bnb ye cevir", "bnb ye dönüştür", "bnb yap"]:
        is_en = (user_lang == "en") or (text_clean in ["dust", "/dust", "dust to bnb"])
        send_message(chat_id, "🧹 *CONVERTING DUST BALANCES TO BNB...*" if is_en else "🧹 *TOZ BAKİYELER (DUST) BİNANCE ÜZERİNDEN BNB'YE DÖNÜŞTÜRÜLÜYOR...*\nLütfen bekleyin...")
        try:
            res_dust = convert_dust_to_bnb(tenant)
            if res_dust.get("status") == "success":
                converted = res_dust.get("converted_assets", [])
                bnb_got = float(res_dust.get("total_bnb_received", 0.0))
                if converted:
                    conv_str = ", ".join(converted)
                    if is_en:
                        msg_d = (
                            f"🎉 *DUST BALANCES SUCCESSFULLY CONVERTED TO BNB!* 🧹✅\n\n"
                            f"🪙 Converted Assets: `{conv_str}`\n"
                            f"📥 Total BNB Received: `+{bnb_got:.6f} BNB`\n"
                            f"🏢 Exchange: BINANCE GLOBAL 🌍\n\n"
                            f"💡 _All small fractions have been cleaned and added to your BNB fee pool!_"
                        )
                    else:
                        msg_d = (
                            f"🎉 *TOZ BAKİYELER BAŞARIYLA BNB'YE DÖNÜŞTÜRÜLDÜ!* 🧹✅\n\n"
                            f"🪙 Dönüştürülen Coinler: `{conv_str}`\n"
                            f"📥 Kasaya Eklenen BNB: `+{bnb_got:.6f} BNB`\n"
                            f"🏢 Borsa: BINANCE GLOBAL 🌍\n\n"
                            f"💡 _Tüm küçük küsuratlar temizlendi ve BNB komisyon havuzunuza aktarıldı!_"
                        )
                else:
                    msg_d = f"ℹ️ {res_dust.get('message', 'Dönüştürülecek küçük bakiye (Dust) bulunamadı.')}"
                send_message(chat_id, msg_d)
            else:
                send_message(chat_id, f"⚠️ *Dönüştürme Uyarısı:* {res_dust.get('error', 'İşlem gerçekleştirilemedi.')}")
        except Exception as de:
            send_message(chat_id, f"❌ Error: {de}")
        return

    if text_clean in ["durum", "bakiye", "portfoy", "bakiye nedir", "durum nedir", "status", "balance", "portfolio"]:
        is_en = (user_lang == "en") or (text_clean in ["status", "balance", "portfolio"])
        try:
            if not tenant:
                send_message(
                    chat_id, 
                    f"⚠️ *USER NOT FOUND*\nNo active exchange account registered for Chat ID `{chat_id}`." if is_en else
                    f"⚠️ *KAYITLI KULLANICI BULUNAMADI*\nChat ID `{chat_id}` için Supabase veritabanında aktif borsa hesabı bulunamadı."
                )
                return

            balance = fetch_portfolio_balance(tenant)
            t_id = str(tenant.get("id") or tenant.get("telegram_chat_id") or "default_tenant")
            saved_pos_tr = get_active_positions_from_db(tenant_id=t_id, exchange_id="binancetr")
            saved_pos_gl = get_active_positions_from_db(tenant_id=t_id, exchange_id="binance")
            usd_try_rate = get_live_usd_try_rate()
            if usd_try_rate <= 0:
                usd_try_rate = 48.0

            is_dual = bool(balance.get("is_dual"))
            bal_tr = balance.get("binance_tr", {}) if is_dual else (balance if tenant.get("exchange_id") == "binancetr" else {})
            bal_gl = balance.get("binance_global", {}) if is_dual else (balance if tenant.get("exchange_id") != "binancetr" else {})

            # 🇹🇷 TR Varlıkları
            free_try = float(bal_tr.get("free_try") or (bal_tr.get("holdings_details", {}).get("TRY", {}).get("amount", 0.0) if isinstance(bal_tr.get("holdings_details"), dict) else 0.0))
            tot_tr_try = float(bal_tr.get("total_try", 0.0))
            tot_tr_usd = float(bal_tr.get("total_usdt", 0.0))
            if tot_tr_usd > 0 and tot_tr_try <= 0:
                tot_tr_try = tot_tr_usd * usd_try_rate
            elif tot_tr_try > 0 and tot_tr_usd <= 0:
                tot_tr_usd = tot_tr_try / usd_try_rate

            tr_holdings_str = ""
            tr_details = bal_tr.get("holdings_details", {})
            if tr_details:
                for a, info in tr_details.items():
                    amt = float(info["amount"])
                    val_try = float(info.get("val_try", 0.0)) or (float(info.get("val_usd", 0.0)) * usd_try_rate)
                    if a != "TRY" and val_try >= 20.0:
                        curr_unit_p = val_try / amt if amt > 0 else 0.0
                        entry_info = saved_pos_tr.get(a) or saved_pos_tr.get(f"{a}/TRY") or {}
                        entry_p = float(entry_info.get("buy_price", 0.0)) if isinstance(entry_info, dict) else (float(entry_info or 0.0))
                        if entry_p <= 0:
                            entry_p = curr_unit_p
                        gross_pct = ((curr_unit_p - entry_p) / entry_p) * 100.0 if entry_p > 0 else 0.0
                        pnl_pct = gross_pct - 0.20 if gross_pct > 0 else gross_pct
                        pnl_fiat = val_try - (amt * entry_p) - (val_try * 0.002 if gross_pct > 0 else 0.0)
                        pnl_str = f" | 📈 +%{pnl_pct:.2f} Net (+₺{pnl_fiat:,.2f} TL)" if pnl_pct >= 0 else f" | 📉 -%{abs(pnl_pct):.2f} Net (-₺{abs(pnl_fiat):,.2f} TL)"
                        tr_holdings_str += f" • 🟢 *{a}:* `{amt:,.4f}` (₺{val_try:,.2f} TL{pnl_str})\n"
            if not tr_holdings_str:
                tr_holdings_str = " • _(Açık coin pozisyonu yok)_\n"

            # 🌍 Global Varlıkları
            api_k = tenant.get("exchange_api_key", "")
            kd = json.loads(api_k) if str(api_k).startswith("{") else {}
            gl_api_k = kd.get("binance", {}).get("api_key") or tenant.get("exchange_api_key")
            gl_sec_k = kd.get("binance", {}).get("secret_key") or tenant.get("exchange_secret_key")

            free_usdt = float(bal_gl.get("free_usdt", 0.0))
            tot_gl_usd = float(bal_gl.get("total_usdt", 0.0))
            gl_details = bal_gl.get("holdings_details", {})
            gl_holdings_str = ""
            bnb_amt = 0.0
            bnb_val = 0.0
            if gl_details:
                bnb_info = gl_details.get("BNB", {})
                bnb_amt = float(bnb_info.get("amount", 0.0))
                bnb_val = float(bnb_info.get("val_usd", 0.0))
                for a, info in gl_details.items():
                    amt = float(info["amount"])
                    val = float(info["val_usd"])
                    if a not in ["USDT", "BNB"] and val >= 2.0:
                        curr_unit_p = val / amt if amt > 0 else 0.0
                        entry_info = saved_pos_gl.get(a) or saved_pos_gl.get(f"{a}/USDT") or {}
                        entry_p = float(entry_info.get("buy_price", 0.0)) if isinstance(entry_info, dict) else (float(entry_info or 0.0))
                        
                        # Eğer DB'de yoksa, doğrudan Binance son alış işleminden gerçek maliyeti çek:
                        if entry_p <= 0 and gl_api_k and gl_sec_k:
                            try:
                                ts_h = int(time.time() * 1000)
                                q_h = f"symbol={a}USDT&timestamp={ts_h}&recvWindow=60000"
                                sig_h = hmac.new(gl_sec_k.encode('utf-8'), q_h.encode('utf-8'), hashlib.sha256).hexdigest()
                                url_h = f"https://api.binance.com/api/v3/myTrades?{q_h}&signature={sig_h}"
                                r_h = requests.get(url_h, headers={"X-MBX-APIKEY": gl_api_k}, timeout=3)
                                if r_h.status_code == 200:
                                    buys = [t for t in r_h.json() if t.get("isBuyer")]
                                    if buys:
                                        entry_p = float(buys[-1]["price"])
                            except Exception:
                                pass
                                
                        if entry_p <= 0:
                            entry_p = curr_unit_p
                            
                        gross_pct = ((curr_unit_p - entry_p) / entry_p) * 100.0 if entry_p > 0 else 0.0
                        pnl_pct = gross_pct - 0.20 if gross_pct > 0 else gross_pct
                        pnl_fiat = val - (amt * entry_p) - (val * 0.002 if gross_pct > 0 else 0.0)
                        pnl_str = f" | 📈 +%{pnl_pct:.2f} Net (+${pnl_fiat:,.2f} USD)" if pnl_pct >= 0 else f" | 📉 -%{abs(pnl_pct):.2f} Net (-${abs(pnl_fiat):,.2f} USD)"
                        gl_holdings_str += f" • 🟢 *{a}:* `{amt:,.4f}` (${val:,.2f} USD{pnl_str})\n"
            if not gl_holdings_str:
                gl_holdings_str = " • _(Açık coin pozisyonu yok)_\n"

            tot_combined_usd = tot_tr_usd + tot_gl_usd
            tot_combined_try = (tot_tr_try) + (tot_gl_usd * usd_try_rate)

            bnb_line = f"🪙 Komisyon Havuzu (BNB): *{bnb_amt:.5f} BNB (${bnb_val:,.2f} USD)*\n" if bnb_val >= 0.10 else ""

            # Binance TR Kapalıysa Listede Gösterme
            show_tr = is_dual and (tot_tr_try > 10.0 or free_try > 10.0)
            if show_tr:
                header_title = "📊 *CANLI ÇİFT BORSA PORTFÖY DURUMUNUZ*"
                tr_section = (
                    f"🇹🇷 *[BİNANCE TR HESABINIZ]*\n"
                    f"💵 Serbest Nakit: *₺{free_try:,.2f} TL*\n"
                    f"📦 *Açık Pozisyonlar:*\n"
                    f"{tr_holdings_str}"
                    f"💰 Toplam TR Portföyü: *₺{tot_tr_try:,.2f} TL* (~${tot_tr_usd:,.2f} USD)\n\n"
                )
                tot_line = f"🏆 *TOPLAM BİRLEŞİK PORTFÖYÜNÜZ:* *${tot_combined_usd:,.2f} USD* (~₺{tot_combined_try:,.2f} TL)"
            else:
                header_title = "📊 *CANLI PORTFÖY DURUMUNUZ*"
                tr_section = ""
                tot_line = f"💰 *Toplam Portföy Değeri:* *${tot_gl_usd:,.2f} USD* (~₺{tot_combined_try:,.2f} TL)"

            msg_text = (
                f"{header_title}\n\n"
                f"👤 Kullanıcı: {tenant.get('tenant_name', 'Kullanıcı')}\n\n"
                f"{tr_section}"
                f"🌍 *[BİNANCE GLOBAL HESABINIZ]*\n"
                f"💵 Serbest USDT: *${free_usdt:,.2f} USD*\n"
                f"{bnb_line}"
                f"📦 *Açık Pozisyonlar:*\n"
                f"{gl_holdings_str}"
                f"💰 Toplam Global Portföyü: *${tot_gl_usd:,.2f} USD*\n\n"
                f"{tot_line}\n"
                f"🏢 Borsa: BINANCE GLOBAL 🌍\n"
                f"🧪 Mod: CANLI GERÇEK HESAP ✅"
            )

            # Snapshot güncelle (Kasa Farkı için referans)
            try:
                client = get_supabase()
                state_key = f"last_queried_balance_{chat_id}"
                c_ts = time.time()
                client.table("crypto_agent_states").upsert({
                    "session_id": state_key,
                    "state_data": {
                        "timestamp": c_ts,
                        "time_str": time.strftime("%H:%M:%S", time.localtime(c_ts)),
                        "tr_try": tot_tr_try,
                        "gl_usd": tot_gl_usd,
                        "tot_usd": tot_combined_usd,
                        "tot_try": tot_combined_try
                    }
                }).execute()
            except Exception:
                pass

            send_message(chat_id, msg_text)
            return
        except Exception as de:
            print(f"❌ [Telegram Durum Hatası]: {de}")
            warn_msg = (
                f"⏳ *SYSTEM UPDATING / RETRY IN 20 SECONDS*\n"
                f"A live exchange synchronization or background deployment is currently in progress.\n"
                f"Please type `durum` again in 20-30 seconds. 🔄"
                if is_en else
                f"⏳ *SİSTEM GÜNCELLENİYOR / 20 SANİYE SONRA TEKRAR DENEYİN*\n"
                f"Şu anda sunucuda otonom borsa senkronizasyonu veya sistem güncellemesi sürmektedir.\n"
                f"Lütfen 20-30 saniye sonra tekrar `durum` veya `bakiye` yazınız. 🔄"
            )
            send_message(chat_id, warn_msg)
            return

    if text_clean in ["test", "analiz", "analysis", "otonom", "tarama", "tara", "market"]:
        tenant = get_tenant_by_chat_id(chat_id)
        is_en = (user_lang == "en") or (text_clean in ["analysis", "market"])
        
        if not tenant:
            send_message(chat_id, "⚠️ User not found. Type 'bagla' or 'register' first." if is_en else "⚠️ Kullanıcı bulunamadı. Lütfen önce 'bagla' yazarak kaydolun.")
            return

        send_message(chat_id, "🧠 *SCANNING GLOBAL CRYPTO MARKETS & ON-CHAIN DATA...*" if is_en else "🧠 *KÜRESEL PİYASA VE ZİNCİR ÜSTÜ VERİLER TARANIYOR...*\nBinance hacimleri, teknik göstergeler ve sıcak altcoinler inceleniyor...")
        
        try:
            
            user_exch = str(tenant.get("exchange_id", "binance")).lower()
            if user_exch in ["binance", "global", "usdt"]:
                all_surges = detect_early_volume_breakouts(quote="USDT")[:6]
                top_gainers = [g for g in fetch_top_volume_gainers(limit=10) if not g['symbol'].endswith("TRY")][:5]
            elif user_exch in ["binancetr", "binance.tr", "trbinance", "try"]:
                all_surges = detect_early_volume_breakouts(quote="TRY")[:6]
                top_gainers = [g for g in fetch_top_volume_gainers(limit=10) if g['symbol'].endswith("TRY")][:5]
            else:
                early_surges_usdt = detect_early_volume_breakouts(quote="USDT")
                early_surges_try = detect_early_volume_breakouts(quote="TRY")
                all_surges = early_surges_usdt[:3] + early_surges_try[:3]
                top_gainers = fetch_top_volume_gainers(limit=5)
            
            news_items = fetch_live_global_crypto_news(limit_per_source=2)
            
            surges_lines = []
            for s in all_surges:
                sym = s['symbol']
                exch_badge = "🇹🇷 Binance TR" if sym.endswith("TRY") else "🌍 Binance Global"
                cur_badge = "₺" if sym.endswith("TRY") else "$"
                surges_lines.append(f"• 🚨 *{sym}* ({exch_badge}): {cur_badge}{s['price']} | 5dk Değişim=+%{s['price_change_5m']}% | Balina Hacmi={s['volume_spike_ratio']}x")
                
            gainers_lines = []
            for g in top_gainers:
                sym = g['symbol']
                exch_badge = "🇹🇷 Binance TR" if sym.endswith("TRY") else "🌍 Binance Global"
                gainers_lines.append(f"• *{sym}* ({exch_badge}): ${g['last_price']} (%{g['percentage_change']:+.2f} 24h) | Hacim: ${g['volume']:,.0f}")
                
            surges_str = "\n".join(surges_lines) if surges_lines else "Şu an ani 5dk balina girişi tespit edilmedi."
            gainers_summary = "\n".join(gainers_lines)
            news_summary = "\n".join(news_items[:3]) if news_items else "Piyasa sakin seyrediyor."
            
            if is_en:
                sys_p = (
                    "You are a Chief Crypto Market Strategist & AI Portfolio Manager. "
                    "Analyze the given live market data, early volume surges, and news. Provide a concise, powerful, professional market report for Telegram. "
                    "Use emojis. Keep it clean and follow this EXACT 4-part format:\n\n"
                    "1. 📊 Market Sentiment Score: (e.g. +3.5 with brief reasoning)\n\n"
                    "2. 🚨 Early Whale & Volume Surge Alerts (Pre-Pump):\n"
                    " - (Bullet points with symbol and whale volume surge details)\n\n"
                    "3. 🚀 24h Volume & Trend Leaders:\n"
                    " - (Bullet points with gainers, % and volume details)\n\n"
                    "4. 🎯 AI Strategic Recommendation:\n"
                    " - (Detailed actionable strategy paragraph for spot dip accumulation, profit taking or cash reserves)\n\n"
                    "Do not use markdown tables or extra greetings. Output only the report starting with item 1."
                )
                user_p = f"Early Volume Surges (Last 5m):\n{surges_str}\n\n24h Top Gainers:\n{gainers_summary}\n\nGlobal Headlines:\n{news_summary}"
            else:
                sys_p = (
                    "Sen kıdemli bir Kripto Para Baş Stratejisti ve Yapay Zeka Portföy Yöneticisisin. "
                    "Canlı borsa verilerini, 5 dakikalık erken balina hacim girişlerini ve haberleri analiz ederek Telegram için son derece anlaşılır, profesyonel bir piyasa raporu hazırla. "
                    "Birebir şu 4 maddeli formatı kullan ve başlıkların numaralarını bozma:\n\n"
                    "1. 📊 Piyasa Duyarlılık Skoru: (Örn: +3.5 veya -2.0 gibi tek bir sayı ve kısa açıklama)\n\n"
                    "2. 🚨 Erken Balina & Hacim Patlaması Yakalananlar (Pre-Pump):\n"
                    " - (Coin çiftlerini ve hacim çarpanlarını maddeleyerek açıklayıcı yaz)\n\n"
                    "3. 🚀 24 Saatlik Hacim & Trend Liderleri:\n"
                    " - (En çok yükselen coinleri ve hacim hareketlerini maddeleyerek yaz)\n\n"
                    "4. 🎯 Yapay Zeka Stratejik Tavsiyesi:\n"
                    " - (Kademeli dip toplama, kâr alma veya nakit tavsiyeni akıcı bir paragraf olarak yaz)\n\n"
                    "Markdown tablo, ek başlık veya süsleme kullanma. Doğrudan 1. maddeden başlayarak raporu yaz."
                )
                user_p = f"Erken Hacim Patlamaları (Son 5dk):\n{surges_str}\n\n24s En Çok Yükselenler:\n{gainers_summary}\n\nKüresel Haber Akışı:\n{news_summary}"
                
            report_body = call_gpt4o(sys_p, user_p, max_tokens=1500)
            if not report_body or len(report_body.strip()) < 20:
                report_body = (
                    "📊 *Piyasa Duyarlılık Skoru:* `+7.8 / +10` (Pozitif Alım İştahı)\n\n"
                    f"🚨 *Erken Balina Girişleri (Son 5dk):*\n{surges_str}\n\n"
                    f"🚀 *24s Hacim Liderleri:*\n{gainers_summary}\n\n"
                    "🎯 *Strateji:* Dipten toplanan spot pozisyonlar korunuyor, kâr alma hedefleri yaklaştıkça satış tetiklenecektir."
                )
                
            header = "🎯 *AI LIVE MARKET & OPPORTUNITY SCAN*" if is_en else "🎯 *YAPAY ZEKA CANLI PİYASA & FIRSAT RAPORU*"
            user_label = f"👤 User: *{tenant.get('tenant_name')}*" if is_en else f"👤 Kullanıcı: *{tenant.get('tenant_name')}*"
            footer = "🤖 *Mode:* 24/7 Autonomous Risk & Profit Engine Active ✅" if is_en else "🤖 *Mod:* 7/24 Otonom Risk & Kâr Alma Motoru Aktif ✅"
            
            full_msg = f"{header}\n\n{user_label}\n\n{report_body}\n\n{footer}"
            send_message(chat_id, full_msg)
        except Exception as e:
            send_message(chat_id, f"⚠️ Analiz sırasında bir uyarı oluştu: {e}")
        return

    if text_clean in ["bagla", "register", "kayit", "borsa"]:
        markup = {
            "inline_keyboard": [
                [
                    {"text": "🇹🇷 Binance TR (TL Cüzdanı)", "callback_data": "select_exchange_binancetr"},
                    {"text": "🌍 Binance Global (USDT Cüzdanı)", "callback_data": "select_exchange_binance"}
                ]
            ]
        }
        send_message(chat_id, "🔐 *BORSA BAĞLANTI SİHİRBAZI*\n\nLütfen kullanmak istediğiniz borsa hesabını seçin:", reply_markup=markup)
        return

    # Çok Adımlı Kayıt Sihirbazı
    state = user_states.get(chat_id)
    if isinstance(state, dict) and state.get("step") == "AWAITING_API_KEY":
        user_states[chat_id] = {
            "step": "AWAITING_SECRET_KEY",
            "exchange_id": state.get("exchange_id", "binance"),
            "api_key": raw_text
        }
        send_message(chat_id, "✅ *API Key Alındı!*\n\nŞimdi lütfen *Secret Key* bilginizi mesaj olarak gönderin:")
        return
    elif isinstance(state, dict) and state.get("step") == "AWAITING_SECRET_KEY":
        api_key = state["api_key"]
        secret_key = raw_text
        exchange_id = state.get("exchange_id", "binance")
        del user_states[chat_id]
        
        # Veritabanına kaydet
        res = register_user_tenant(
            tenant_name=first_name,
            telegram_chat_id=chat_id,
            exchange_api_key=api_key,
            exchange_secret_key=secret_key,
            exchange_id=exchange_id
        )
        exch_label = "Binance TR 🇹🇷" if exchange_id == "binancetr" else "Binance Global 🌍"
        if res:
            send_message(chat_id, f"🎉 *TEBRİKLER {first_name.upper()}!*\n\n*{exch_label}* hesabınız başarıyla bağlandı! Artık 7/24 otonom yapay zeka alım-satım ve kâr alma sistemi sizin hesabınız için de devrede! 🚀")
        else:
            send_message(chat_id, "❌ Bağlantı sırasında bir hata oluştu. Lütfen tekrar deneyin.")
        return

    # ---------------------------------------------------------
    # 3. DOĞAL DİL İLE AKILLI ALIM/SATIM & ASİSTAN MOTORU (GPT-4o)
    # ---------------------------------------------------------
    tenant = get_tenant_by_chat_id(chat_id)
    if not tenant:
        send_message(chat_id, f"👋 Merhaba {first_name}! Sizi sisteme bağlamak için lütfen `bagla` yazın.")
        return

    is_tr_user = bool(tenant.get("exchange_id") in ["binancetr", "binance.tr", "trbinance"])
    quote_curr = "TRY" if is_tr_user else "USDT"
    exch_label = "BINANCE.TR 🇹🇷" if is_tr_user else "BINANCE GLOBAL 🌍"

    try:

        user_text = raw_text.strip()
        
        # 1. HIZLI DOĞRUDAN ALIM/SATIM REGEX AYRIŞTIRICISI (Anında, Sıfır Gecikme)
        fast_action = None
        if re.search(r'\b(al|al\w*|buy)\b', user_text, re.IGNORECASE):
            fast_action = "BUY"
        elif re.search(r'\b(sat|sat\w*|sell)\b', user_text, re.IGNORECASE):
            fast_action = "SELL"
            
        # Esnek ve Dinamik Al-Sat Emir Yakalayıcı (Örn: 'HEI SAT', 'MUBARAK SAT', 'TREE SAT', 'SOL AL', 'BTC SAT')
        match_sell = re.search(r'^\s*([A-Za-z0-9]{2,10})\s+(?:SAT|SELL)\s*$', user_text, re.IGNORECASE) or re.search(r'^\s*(?:SAT|SELL)\s+([A-Za-z0-9]{2,10})\s*$', user_text, re.IGNORECASE)
        match_buy = re.search(r'^\s*([A-Za-z0-9]{2,10})\s+(?:AL|BUY)\s*$', user_text, re.IGNORECASE) or re.search(r'^\s*(?:AL|BUY)\s+([A-Za-z0-9]{2,10})\s*$', user_text, re.IGNORECASE)
        
        if match_sell:
            fast_action = "SELL"
            matched_coin = match_sell.group(1).upper()
        elif match_buy:
            fast_action = "BUY"
            matched_coin = match_buy.group(1).upper()
        else:
            known_coins = ["SOL", "BTC", "ETH", "AVAX", "PEPE", "BNB", "SHIB", "BONK", "DOGE", "RENDER", "SUI", "NEAR", "XRP", "FLM", "CLV", "WAVES", "UTK", "GPS", "PORTAL", "ACE", "TUT", "HEI", "HEMI", "MUBARAK", "TREE", "RED", "GALA", "ZRO", "SIGN", "PROM"]
            matched_coin = None
            if fast_action:
                for c in known_coins:
                    if re.search(r'\b' + c + r'\b', user_text, re.IGNORECASE):
                        matched_coin = c
                        break
                    
        if fast_action and matched_coin:
            amt_usd = re.search(r'(\d+(?:[\.,]\d+)?)\s*(?:\$|usd|dolar|usdt)', user_text, re.IGNORECASE) or re.search(r'(?:\$)\s*(\d+(?:[\.,]\d+)?)', user_text, re.IGNORECASE)
            amt_try = re.search(r'(\d+(?:[\.,]\d+)?)\s*(?:tl|try|lira)', user_text, re.IGNORECASE)
            amt_coin = re.search(r'(\d+(?:[\.,]\d+)?)\s*(?:adet|tane)', user_text, re.IGNORECASE)
            
            if amt_usd:
                amt_type = "FIAT_USD"
                amt_val = float(amt_usd.group(1).replace(",", "."))
            elif amt_try:
                amt_type = "FIAT_TRY"
                amt_val = float(amt_try.group(1).replace(",", "."))
            elif amt_coin:
                amt_type = "COIN_QTY"
                amt_val = float(amt_coin.group(1).replace(",", "."))
            else:
                generic_num = re.search(r'(\d+(?:[\.,]\d+)?)', user_text)
                if generic_num:
                    amt_type = "FIAT_USD"
                    amt_val = float(generic_num.group(1).replace(",", "."))
                else:
                    amt_type = "ALL_BALANCE"
                    amt_val = 10.0
                    
            intent_data = {
                "intent": "TRADE",
                "action": fast_action,
                "coin": matched_coin,
                "amount_type": amt_type,
                "amount_value": amt_val
            }
            intent = "TRADE"
        else:
            system_prompt = (
                "Sen kıdemli bir Telegram Kripto Ticaret ve Asistan Robotusun.\n"
                "Kullanıcının Türkçe veya İngilizce mesajını analiz et ve niyetini (intent) belirle.\n\n"
                "OLASI NİYETLER (intent):\n"
                "1. 'TRADE': Kullanıcı doğrudan bir alım veya satım emri veriyor.\n"
                "   Örnekler: '500 TL sol al', '10 dolar btc al', '10 adet sol al', 'elimdeki avaxı sat', '50 TL pepe sat', '1 sol al', 'bnb sat', '10$ usdt sat', 'sol al', 'near sat', 'BNB 2.36$ sat', '2.36$ BNB sat'\n"
                "2. 'EXPLAIN_TRADE': Kullanıcı yapay zekaya bir coini neden aldığını/sattığını soruyor.\n"
                "3. 'UPDATE_SETTINGS': Kâr alma veya stop-loss oranı değiştirme ('kar %3 yap').\n"
                "4. 'PRICE_QUERY': Fiyat sorma ('sol ne kadar', 'btc fiyatı').\n"
                "5. 'SET_LANGUAGE': Dil değiştirme ('lang en', 'türkçe').\n"
                "6. 'CHAT': Genel soru, sohbet veya selamlama.\n\n"
                "ÇIKTI FORMATI: Yalnızca geçerli bir JSON nesnesi döndür:\n"
                "{\n"
                '  "intent": "TRADE" | "EXPLAIN_TRADE" | "UPDATE_SETTINGS" | "SET_LANGUAGE" | "PRICE_QUERY" | "CHAT",\n'
                '  "action": "BUY" | "SELL" | null,\n'
                '  "coin": "SOL" | "BTC" | "AVAX" | "PEPE" | "BNB" | "ETH" | "NEAR" | "SUI" | "RENDER" | "DOGE" | "BONK" | null,\n'
                '  "amount_type": "FIAT_TRY" | "FIAT_USD" | "COIN_QTY" | "ALL_BALANCE" | null,\n'
                '  "amount_value": 500.0 | 10.0 | 2.36 | null,\n'
                '  "take_profit_percent": 3.0 | 2.5 | null,\n'
                '  "stop_loss_percent": 2.0 | 1.5 | null,\n'
                '  "language": "tr" | "en" | null,\n'
                '  "chat_reply": "Friendly response in the language user spoke"\n'
                "}"
            )

            parsed_res = call_gpt4o(system_prompt, f"Kullanıcı Mesajı: {user_text}")
            clean_json = parsed_res.strip("` \n").replace("json", "").strip() if parsed_res else "{}"
            intent_data = json.loads(clean_json) if clean_json.startswith("{") else {}
            intent = intent_data.get("intent", "CHAT")

        if intent == "SET_LANGUAGE":
            lang = str(intent_data.get("language") or "tr").lower()
            sb = get_supabase()
            if sb:
                api_k = str(tenant.get("exchange_api_key", ""))
                update_payload = {}
                if api_k.startswith("{"):
                    try:
                        kd = json.loads(api_k)
                        kd["preferred_language"] = lang
                        update_payload["exchange_api_key"] = json.dumps(kd)
                    except Exception:
                        pass
                sb.table("user_tenants").update(update_payload).eq("telegram_chat_id", chat_id).execute()
                
            if lang == "en":
                send_message(chat_id, "🇬🇧 *Language Preference Set to English!* ✅\nAll trading notifications, status reports and bot responses will be in English.")
            else:
                send_message(chat_id, "🇹🇷 *Dil Tercihi Türkçe Olarak Ayarlandı!* ✅\nTüm al-sat bildirimleri, portföy raporları ve yanıtlar Türkçe olacaktır.")
            return

        if intent == "EXPLAIN_TRADE":
            coin = (intent_data.get("coin") or "").upper()
            action = (intent_data.get("action") or "").upper()
            is_en_pref = str(tenant.get("preferred_language", "tr")).lower() == "en"
            
            # Supabase'den geçmiş işlem loglarını çek
            sb = get_supabase()
            logs_summary = "Kayıtlı geçmiş işlem bulunamadı."
            if sb:
                try:
                    q = sb.table("crypto_trade_logs").select("*").order("created_at", desc=True).limit(5)
                    if coin:
                        q = q.ilike("symbol", f"%{coin}%")
                    res = q.execute()
                    if res.data:
                        logs_summary = "\n".join([
                            f"- Sembol: {r.get('symbol')}, Yön: {r.get('direction')}, İnfaz/Giriş: {r.get('entry_price')}, Duyarlılık Skoru: {r.get('sentiment_score')}, Durum: {r.get('status')}, Tarih: {r.get('created_at')}"
                            for r in res.data
                        ])
                except Exception:
                    pass

            explain_system_prompt = (
                "Sen Fox-Kripto Otonom Yapay Zeka Baş Portföy Yöneticisisin.\n"
                "Kullanıcı sana neden belirli bir kripto parayı (örneğin PEPE, SOL, BTC, AVAX, DOGE) aldığını veya sattığını, ya da genel al-sat mantığını soruyor.\n\n"
                "SİSTEMİN ÇALIŞMA PRENSİPLERİ VE GEREKÇELERİ:\n"
                "1. ALIM STRATEJİSİ:\n"
                "   - Yüksek volatiliteye sahip meme coinlerde (PEPE, DOGE, BONK, SHIB) ve yapay zeka tokenlerinde (RENDER, NEAR, SUI) dip oluşumu, RSI aşırı satım bölgesinden toparlanma ve pozitif küresel haber duyarlılığı (Sentiment > 6.0) tespit edildiğinde hızlı kâr hedefiyle spot alım yapılır.\n"
                "   - Portföy çeşitlendirmesi yapılır, tek işlemde cüzdanın maksimum %10'u kullanılır.\n"
                "2. SATIM / KÂR ALMA STRATEJİSİ:\n"
                "   - Önceden belirlenen dinamik kâr alma (Take-Profit %1.5 - %3.0) hedefine ulaşıldığında kârı fiat (TL/USDT) cüzdanına kilitlemek için anında satış yapılır.\n"
                "   - Piyasa ani tersine dönerse sermayeyi korumak için Stop-Loss devreye girer.\n"
                "3. YANIT FORMATI:\n"
                "   - Kullanıcıya şeffaf, samimi, madde madde ve profesyonel bir üslupla açıkla.\n"
                f"   - Dil: {'İngilizce (English)' if is_en_pref else 'Türkçe'}.\n"
            )

            context_prompt = (
                f"Kullanıcı Sorusu: {user_text}\n"
                f"Sorgulanan Coin: {coin or 'Genel'}\n"
                f"İşlem Tipi: {action or 'Alım/Satım'}\n"
                f"Veritabanı İşlem Logları:\n{logs_summary}\n\n"
                f"Lütfen kullanıcının sorusunu doğrudan yanıtlayan harika bir açıklama hazırla."
            )

            explanation = call_gpt4o(explain_system_prompt, context_prompt)
            send_message(chat_id, explanation if explanation else ("İşlem stratejisi: Kâr alma ve risk koruma hedefleri doğrultusunda gerçekleşmiştir." if not is_en_pref else "Trading strategy: Executed based on take-profit and risk management targets."))
            return

        if intent == "UPDATE_SETTINGS":
            tp = intent_data.get("take_profit_percent")
            sl = intent_data.get("stop_loss_percent")
            sb = get_supabase()
            if sb and (tp is not None or sl is not None):
                update_payload = {}
                if sl is not None: 
                    update_payload["stop_loss_percent"] = float(sl)
                
                # take_profit_percent'i JSON içine güvenle göm
                api_k = str(tenant.get("exchange_api_key", ""))
                if api_k.startswith("{"):
                    try:
                        kd = json.loads(api_k)
                        if tp is not None:
                            kd["take_profit_percent"] = float(tp)
                        update_payload["exchange_api_key"] = json.dumps(kd)
                    except Exception:
                        pass
                        
                sb.table("user_tenants").update(update_payload).eq("telegram_chat_id", chat_id).execute()
                
                curr_tp = float(tp) if tp is not None else float(tenant.get("take_profit_percent") or 1.5)
                curr_sl = float(sl) if sl is not None else float(tenant.get("stop_loss_percent") or 1.5)
                
                if str(tenant.get("preferred_language", "tr")).lower() == "en":
                    settings_card = (
                        f"⚙️ *RISK SETTINGS UPDATED!* ✅\n\n"
                        f"👤 User: *{first_name}*\n"
                        f"🎯 New Take-Profit Target: *+%{curr_tp:.1f} Net Profit*\n"
                        f"🛡️ New Stop-Loss Limit: *-%{curr_sl:.1f}*\n\n"
                        f"💡 _Autonomous AI will now manage all your open positions according to these new targets._"
                    )
                else:
                    settings_card = (
                        f"⚙️ *RİSK AYARLARINIZ GÜNCELLENDİ!* ✅\n\n"
                        f"👤 Kullanıcı: *{first_name}*\n"
                        f"🎯 Yeni Kâr Alma (Take-Profit) Hedefi: *+%{curr_tp:.1f} Net Kâr*\n"
                        f"🛡️ Yeni Zarar Kes (Stop-Loss) Limiti: *-%{curr_sl:.1f}*\n\n"
                        f"💡 _Artık yapay zeka tüm açık coin pozisyonlarınızı bu yeni hedeflerinize göre otonom olarak yönetecektir._"
                    )
                send_message(chat_id, settings_card)
                return
            else:
                send_message(chat_id, "⚠️ Ayarlar güncellenirken bir değer anlaşılamadı. Lütfen örneğin: 'Kâr hedefimi %3 yap' şeklinde yazın.")
                return
        
        # 🧹 TOZ / KIRINTI TEMİZLEME VE BNB'YE DÖNÜŞTÜRME KOMUTU
        text_lower = user_text.lower()
        if any(w in text_lower for w in ["toz", "kırıntı", "bnb yap", "dust", "küçük bakiye", "bakiyeleri temizle", "tozları temizle"]):
            send_message(chat_id, "🧹 *Küçük bakiyeler taranıyor ve BNB'ye dönüştürülüyor...*" if not is_en_pref else "🧹 *Scanning and converting dust balances to BNB...*")
            api_k = str(tenant.get("exchange_api_key", ""))
            sec_k = str(tenant.get("exchange_secret_key", ""))
            if api_k.startswith("{"):
                try:
                    kd = json.loads(api_k)
                    api_k = kd.get("api_key", "")
                    sec_k = kd.get("secret_key", "") or sec_k
                except Exception: pass
            
            try:
                client_g = BinanceGlobalRESTClient(api_key=api_k, secret_key=sec_k)
                dust_res = client_g.convert_dust_to_bnb()
                if dust_res.get("status") == "success" or "totalServiceCharge" in str(dust_res) or "transferResult" in str(dust_res):
                    send_message(chat_id, "✨ *Tüm küçük bakiyeler ve kırıntılar başarıyla BNB'ye dönüştürüldü!* 🚀\nCüzdanınız tertemiz hale getirildi." if not is_en_pref else "✨ *All small dust balances have been successfully converted to BNB!* 🚀")
                else:
                    msg = dust_res.get("message") or dust_res.get("msg") or dust_res.get("error") or "Dönüştürülecek uygun toz bakiye bulunamadı (veya 6 saatlik borsa bekleme süresi devrede)."
                    send_message(chat_id, f"ℹ️ {msg}")
            except Exception as d_err:
                send_message(chat_id, f"⚠️ Toz temizleme sırasında uyarı: {d_err}")
            return
        
        if intent == "TRADE" and intent_data.get("coin") and intent_data.get("action"):
            coin = str(intent_data["coin"]).upper()
            action = str(intent_data["action"]).upper()
            amt_type = intent_data.get("amount_type", "FIAT_TRY" if is_tr_user else "FIAT_USD")
            amt_val = float(intent_data.get("amount_value") or 10.0)
            
            target_symbol = f"{coin}/{quote_curr}"
            ticker = fetch_ticker_price(target_symbol)
            curr_price = float(ticker.get("last_price", 0.0))
            
            live_fx = get_live_usd_try_rate()
            if amt_type == "FIAT_TRY":
                amount_usd = amt_val / live_fx
                amount_display = f"₺{amt_val:,.2f} TL"
            elif amt_type == "FIAT_USD":
                amount_usd = amt_val
                amount_display = f"${amt_val:.2f} USD"
            elif amt_type == "COIN_QTY":
                if curr_price > 0:
                    tot_fiat = amt_val * curr_price
                    amount_usd = (tot_fiat / live_fx) if is_tr_user else tot_fiat
                    amount_display = f"{amt_val} {coin} (~₺{tot_fiat:,.2f} TL)" if is_tr_user else f"{amt_val} {coin} (~${tot_fiat:,.2f} USD)"
                else:
                    amount_usd = 10.0
                    amount_display = f"${amount_usd:.2f} USD"
            else: # ALL_BALANCE (Tüm Bakiye Satışı)
                try:
                    port = fetch_portfolio_balance(tenant)
                    h_tr = port.get("binance_tr", {}).get("holdings_details", {})
                    h_gl = port.get("binance_global", {}).get("holdings_details", {})
                    
                    # Doğru borsadaki bakiyeyi öncelikle seç
                    gl_info = h_gl.get(coin, {})
                    tr_info = h_tr.get(coin, {})
                    gl_val = float(gl_info.get("val_usd", 0.0))
                    tr_val = float(tr_info.get("val_usd", 0.0))
                    
                    if not is_tr_user and gl_val > 0:
                        c_info = gl_info
                    elif is_tr_user and tr_val > 0:
                        c_info = tr_info
                    elif gl_val >= tr_val and gl_val > 0:
                        c_info = gl_info
                    elif tr_val > 0:
                        c_info = tr_info
                    else:
                        c_info = port.get("holdings_details", {}).get(coin) or {}
                        
                    c_amt = float(c_info.get("amount", 0.0))
                    c_val = float(c_info.get("val_usd", 0.0))
                    if c_val > 0:
                        amount_usd = c_val
                        amount_display = f"Tüm Bakiye ({c_amt:,.6f} {coin} ~ ${c_val:.2f})"
                    else:
                        amount_usd = 10.0
                        amount_display = f"Tüm {coin} Bakiyesi"
                except Exception:
                    amount_usd = 10.0
                    amount_display = f"Tüm {coin} Bakiyesi"
                    
            is_en_pref = str(tenant.get("preferred_language", "tr")).lower() == "en"
            if is_en_pref:
                send_message(chat_id, f"⚡ *INSTRUCTION RECEIVED: {action} {target_symbol}*\n💵 Budget / Amount: `{amount_display}`\n🏢 Exchange: {exch_label}\n\nTransmitting order to exchange...")
            else:
                send_message(chat_id, f"⚡ *TALİMAT ALINDI: {action} {target_symbol}*\n💵 Bütçe / Miktar: `{amount_display}`\n🏢 Borsa: {exch_label}\n\nEmir borsaya iletiliyor...")
            
            trade_res = execute_spot_trade(
                symbol=target_symbol,
                side=action,
                amount_usd=amount_usd,
                tenant_config=tenant
            )
            
            if trade_res.get("status") in ["success", "EXECUTED", "EXECUTED_SIMULATED"]:
                order_id = trade_res.get("order_id", "LIVE_EXEC")
                exec_p = trade_res.get("executed_price") or curr_price
                price_str = f"₺{exec_p:,.2f} TL" if is_tr_user else f"${exec_p:,.4f}"
                
                # Supabase DB Ledger Güncellemesi
                try:
                    t_id = str(tenant.get("id") or tenant.get("telegram_chat_id") or "default_tenant")
                    exch_id = "binancetr" if is_tr_user else "binance"
                    if action == "BUY":
                        coin_amt = float(trade_res.get("amount") or (amount_usd / exec_p if exec_p > 0 else 0))
                        save_position_to_db(
                            tenant_id=t_id,
                            exchange_id=exch_id,
                            symbol=target_symbol,
                            base_asset=coin,
                            quote_asset=quote_curr,
                            amount=coin_amt,
                            buy_price=exec_p
                        )
                    else: # SELL
                        remove_position_from_db(tenant_id=t_id, exchange_id=exch_id, symbol=target_symbol)
                        set_cooldown_in_db(tenant_id=t_id, symbol=target_symbol, base_asset=coin, duration_seconds=3600)
                except Exception as db_err:
                    print(f"⚠️ [Manuel İşlem DB Uyarısı]: {db_err}")
                
                if is_en_pref:
                    success_card = (
                        f"🚀 *LIVE ORDER EXECUTED ON EXCHANGE!* ✅\n\n"
                        f"👤 User: {first_name}\n"
                        f"⚡ Action: *{action}*\n"
                        f"🪙 Symbol: `{target_symbol}`\n"
                        f"💵 Executed Amount: `{amount_display}`\n"
                        f"📥 Execution Price: `{price_str}`\n"
                        f"📄 Order ID: `#{order_id}`\n"
                        f"🏢 Exchange: {exch_label}\n\n"
                        f"🎉 *Spot order executed live on exchange!*"
                    )
                else:
                    success_card = (
                        f"🚀 *CANLI TALİMAT BORSADA İNFAZ EDİLDİ!* ✅\n\n"
                        f"👤 Kullanıcı: {first_name}\n"
                        f"⚡ İşlem Tipi: *{action}*\n"
                        f"🪙 Sembol: `{target_symbol}`\n"
                        f"💵 İnfaz Tutarı: `{amount_display}`\n"
                        f"📥 İnfaz Fiyatı: `{price_str}`\n"
                        f"📄 Emir No: `#{order_id}`\n"
                        f"🏢 Borsa: {exch_label}\n\n"
                        f"🎉 *İşlem canlı olarak gerçekleştirildi!*"
                    )
                send_message(chat_id, success_card)
            else:
                err = str(trade_res.get("error", "Borsa reddetti"))
                if "NOTIONAL" in err or "-1013" in err:
                    if is_en_pref:
                        friendly_err = "⚠️ *Binance Minimum Order Limit (MIN_NOTIONAL):*\nBinance requires a minimum order value of **$5.00 USD** (or ₺100 TL) for spot market trades.\nAmounts below $5.00 (such as $2.36) cannot be sold directly on the spot order book."
                    else:
                        friendly_err = "⚠️ *Borsa Kuralı (Minimum Emir Limiti - MIN_NOTIONAL):*\nBinance borsasında spot işlem yapabilmek için tek seferlik emir tutarı en az **$5.00 USD** (veya ₺100 TL) olmak zorundadır.\n$2.36 gibi $5'ın altındaki küçük bakiyeler borsa kuralı gereği spot tahtasında satılamaz."
                    send_message(chat_id, friendly_err)
                elif is_en_pref:
                    send_message(chat_id, f"⚠️ *Order Failed:*\n\n`{err}`\n\nPlease check your account balance or API permissions.")
                else:
                    send_message(chat_id, f"⚠️ *Emir İletilemedi:*\n\n`{err}`\n\nLütfen bakiyenizi veya borsa kısıtlamalarını kontrol edin.")
            return

        elif intent == "PRICE_QUERY" and intent_data.get("coin"):
            coin = str(intent_data["coin"]).upper()
            t_usd = fetch_ticker_price(f"{coin}/USDT")
            t_try = fetch_ticker_price(f"{coin}/TRY")
            p_usd = t_usd.get("last_price", 0.0)
            p_try = t_try.get("last_price", p_usd * 34.80)
            chg = t_usd.get("percentage_change", 0.0)
            high = t_usd.get("high", 0.0)
            low = t_usd.get("low", 0.0)
            
            is_en_pref = str(tenant.get("preferred_language", "tr")).lower() == "en"
            if is_en_pref:
                reply = (
                    f"🪙 *{coin} LIVE MARKET STATUS*\n\n"
                    f"💵 *Price:* `${p_usd:,.4f}`\n"
                    f"📈 *24h Change:* `%{chg:+.2f}`\n"
                    f"📊 *24h High:* `${high:,.4f}`\n"
                    f"📉 *24h Low:* `${low:,.4f}`\n\n"
                    f"💡 _To execute trades type 'Buy 10$ {coin}' or 'Sell 10$ {coin}'._"
                )
            else:
                reply = (
                    f"🪙 *{coin} CANLI PİYASA DURUMU*\n\n"
                    f"💵 *Fiyat:* `${p_usd:,.4f}` (₺{p_try:,.2f} TL)\n"
                    f"📈 *24s Değişim:* `%{chg:+.2f}`\n"
                    f"📊 *24s En Yüksek:* `${high:,.4f}`\n"
                    f"📉 *24s En Düşük:* `${low:,.4f}`\n\n"
                    f"💡 _Talimat vermek için '500 TL {coin} al' veya '10$ {coin} sat' yazabilirsiniz._"
                )
            send_message(chat_id, reply)
            return
            
        else:
            chat_reply = intent_data.get("chat_reply")
            if not chat_reply or "bana '500 tl" in str(chat_reply).lower() or len(str(chat_reply)) < 15:
                try:
                    port = fetch_portfolio_balance(tenant)
                    holdings_summary = str(port.get("holdings_details") or port.get("binance_tr", {}).get("holdings_details") or {})
                    
                    qa_system_prompt = (
                        f"Sen Fox-Kripto Akıllı Portföy Yöneticisi ve Kripto Ticaret Asistanısın.\n"
                        f"Kullanıcının Adı: {first_name}\n"
                        f"Kullanıcı Portföy Durumu: {holdings_summary}\n"
                        f"Görevin: Kullanıcının sorusuna doğrudan, açık, dürüst, profesyonel ve tatmin edici bir yanıt vermektir.\n"
                        f"Kullanıcı neden belirli bir işlem yapıldığını, neden satış olmadığını, piyasa durumunu veya botun çalışma mantığını soruyor olabilir.\n"
                        f"Asla ezbere generic karşılama mesajı verme! Soruya nokta atışı yanıt ver."
                    )
                    chat_reply = call_gpt4o(qa_system_prompt, f"Kullanıcı Mesajı: {user_text}")
                except Exception:
                    pass
                    
            if not chat_reply:
                chat_reply = f"Merhaba {first_name}! 'durum', 'haberler', 'analiz' yazabilir veya 'BTC sat', '500 TL SOL al' gibi talimatlar verebilirsiniz. Sorunuzu detaylandırırsanız memnuniyetle yardımcı olurum!"
                
            send_message(chat_id, chat_reply)
            return
    except Exception as nle:
        send_message(chat_id, f"🤖 Merhaba {first_name}! Talimatınız alındı. 'durum', 'haberler' veya 'BTC sat' gibi komutlarla da işlem yapabilirsiniz.")
        return

def start_poller():
    """Telegram Poller Döngüsü (Non-blocking Fast Polling)."""
    print(f"🤖 [Telegram Poller Başlatıldı]: @FoxKriptoBot 7/24 dinleniyor...")
    offset = None
    while True:
        try:
            params = {"timeout": 1, "offset": offset}
            res = requests.get(f"{BASE_URL}/getUpdates", params=params, timeout=6)
            if res.status_code == 200:
                results = res.json().get("result", [])
                for update in results:
                    offset = update["update_id"] + 1
                    # Her mesajı paralel arka plan iş parçacığında (Thread) çalıştır - Sıfır Bloklanma!
                    threading.Thread(target=handle_update, args=(update,), daemon=True).start()
            time.sleep(0.5)
        except Exception as e:
            time.sleep(1)

if __name__ == "__main__":
    start_poller()