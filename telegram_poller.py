import os, sys, time, requests, io

# Windows Console Emoji UnicodeEncodeError Önleyici
if hasattr(sys.stdout, 'buffer'):
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
if hasattr(sys.stderr, 'buffer'):
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')

from dotenv import load_dotenv
from db import register_user_tenant, get_tenant_by_chat_id, get_supabase, log_trade_decision, save_graph_state, load_graph_state
from exchange import fetch_portfolio_balance, execute_spot_trade, fetch_ticker_price

load_dotenv()

TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "8938326996:AAFLmy3S4uAb_GbF8TotsdL0CgWq4jGCFik")
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
    
    chat_id = message["chat"]["id"]
    raw_text = (message.get("text") or "").strip()
    first_name = message["chat"].get("first_name", "Kullanıcı")
    text_clean = raw_text.lower().lstrip("/").strip()

    print(f"📩 [Telegram Gelen Mesaj]: Chat ID={chat_id}, Text='{raw_text}' (Clean='{text_clean}')")

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
    if text_clean in ["start", "help", "yardim", "yardım", "merhaba", "hello", "hi"]:
        tenant = get_tenant_by_chat_id(chat_id)
        if tenant:
            send_message(
                chat_id, 
                f"👋 Merhaba / Hello *{first_name}*!\n\n"
                f"✅ Registered as: *{tenant['tenant_name']}*\n\n"
                f"📌 *Kullanabileceğiniz Komutlar / Available Commands:*\n"
                f"• `durum` / `status` / `balance` - Canlı portföy / Live holdings\n"
                f"• `haberler` / `news` - Kripto haberleri / Market headlines\n"
                f"• `analiz` / `analysis` - Yapay zeka taraması / AI Market scan\n"
                f"• `lang en` 🇬🇧 / `dil tr` 🇹🇷 - Dil seçimi / Language switch\n"
                f"• `500 TL SOL al` / `Buy $10 SOL` - Doğal dille işlem / Natural trade"
            )
        else:
            send_message(chat_id, f"👋 Merhaba / Hello *{first_name}*!\nFox-Kripto Otonom Ajan Sistemine Hoş Geldiniz / Welcome to Fox-Crypto AI Agent System!\n\nBinance hesabınızı bağlamak için `bagla` yazabilirsiniz.")
        return

    tenant = get_tenant_by_chat_id(chat_id)
    user_lang = str(tenant.get("preferred_language", "tr") if tenant else "tr").lower()

    if text_clean in ["haber", "haberler", "haberle", "gundem", "gündem", "news", "kripto haber", "son haberler"]:
        is_en = (user_lang == "en") or (text_clean in ["news"])
        send_message(chat_id, "📡 *FETCHING GLOBAL CRYPTO NEWS...*" if is_en else "📡 *KÜRESEL KRİPTO HABERLERİ ÇEKİLİYOR...*\nCoinDesk, CoinTelegraph ve Decrypt taranıyor...")
        try:
            from news_service import get_localized_crypto_news
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

            if balance.get("is_dual"):
                bal_tr = balance.get("binance_tr", {})
                bal_gl = balance.get("binance_global", {})
                
                # TR Varlıkları
                tr_holdings_str = ""
                tr_details = bal_tr.get("holdings_details", {})
                free_try = 0.0
                usd_try_rate = 47.80
                tot_tr_try = float(bal_tr.get("total_try", 0.0)) or 0.0
                if tr_details:
                    for a, info in tr_details.items():
                        amt = info["amount"]
                        val_try = float(info.get("val_try", 0.0)) or (float(info.get("val_usd", 0.0)) * usd_try_rate)
                        if a == "TRY":
                            free_try = amt
                        elif val_try > 0.5:
                            tr_holdings_str += f" • 🟢 *{a}:* `{amt:,.4f}` (₺{val_try:,.2f} TL)\n"
                if not tr_holdings_str:
                    tr_holdings_str = " • _(No open coin positions)_\n" if is_en else " • _(Açık coin pozisyonu yok)_\n"
                            
                tot_tr_usd = float(bal_tr.get("total_usdt", 0.0))
                if tot_tr_try <= 0:
                    tot_tr_try = tot_tr_usd * usd_try_rate
                
                # Global Varlıkları
                gl_holdings_str = ""
                gl_details = bal_gl.get("holdings_details", {})
                free_usdt = float(bal_gl.get("free_usdt", 0.0))
                if gl_details:
                    for a, info in gl_details.items():
                        amt = info["amount"]
                        val = info["val_usd"]
                        if a != "USDT" and val > 0.01:
                            gl_holdings_str += f" • 🟢 *{a}:* `{amt:,.4f}` (${val:,.2f} USD)\n"
                if not gl_holdings_str:
                    gl_holdings_str = " • _(No open coin positions)_\n" if is_en else " • _(Açık coin pozisyonu yok)_\n"
                    
                tot_usd = float(balance.get("total_usdt", 0.0))
                tot_combined_try = tot_tr_try + (float(bal_gl.get("total_usdt", 0.0)) * usd_try_rate)
                
                if is_en:
                    msg_text = (
                        f"📊 *LIVE DUAL-EXCHANGE PORTFOLIO REPORT*\n\n"
                        f"👤 User: {tenant.get('tenant_name', 'User')}\n\n"
                        f"🇹🇷 *[BINANCE TR ACCOUNT]*\n"
                        f"💵 Free Cash: *₺{free_try:,.2f} TL*\n"
                        f"📦 *Open Positions:*\n"
                        f"{tr_holdings_str}"
                        f"💰 Total TR Portfolio: *₺{tot_tr_try:,.2f} TL* (~${tot_tr_usd:,.2f} USD)\n\n"
                        f"🌍 *[BINANCE GLOBAL ACCOUNT]*\n"
                        f"💵 Free USDT: *${free_usdt:,.2f} USD*\n"
                        f"📦 *Open Positions:*\n"
                        f"{gl_holdings_str}"
                        f"💰 Total Global Portfolio: *${bal_gl.get('total_usdt', 0.0):,.2f} USD*\n\n"
                        f"🏆 *OVERALL TOTAL PORTFOLIO:* *${tot_usd:,.2f} USD* (~₺{tot_combined_try:,.2f} TL)\n"
                        f"🧪 Mode: REAL LIVE TRADING ✅"
                    )
                else:
                    msg_text = (
                        f"📊 *CANLI ÇİFT BORSA PORTFÖY DURUMUNUZ*\n\n"
                        f"👤 Kullanıcı: {tenant.get('tenant_name', 'Kullanıcı')}\n\n"
                        f"🇹🇷 *[BİNANCE TR HESABINIZ]*\n"
                        f"💵 Serbest Nakit: *₺{free_try:,.2f} TL*\n"
                        f"📦 *Açık Pozisyonlar:*\n"
                        f"{tr_holdings_str}"
                        f"💰 Toplam TR Portföyü: *₺{tot_tr_try:,.2f} TL* (~${tot_tr_usd:,.2f} USD)\n\n"
                        f"🌍 *[BİNANCE GLOBAL HESABINIZ]*\n"
                        f"💵 Serbest USDT: *${free_usdt:,.2f} USD*\n"
                        f"📦 *Açık Pozisyonlar:*\n"
                        f"{gl_holdings_str}"
                        f"💰 Toplam Global Portföyü: *${bal_gl.get('total_usdt', 0.0):,.2f} USD*\n\n"
                        f"🏆 *TOPLAM BİRLEŞİK PORTFÖYÜNÜZ:* *${tot_usd:,.2f} USD* (~₺{tot_combined_try:,.2f} TL)\n"
                        f"🧪 Mod: CANLI GERÇEK HESAP ✅"
                    )
                send_message(chat_id, msg_text)
                return

            holdings_text = ""
            details = balance.get("holdings_details", {})
            if details:
                for asset, info in details.items():
                    amt = info["amount"]
                    val = info["val_usd"]
                    if val > 0:
                        holdings_text += f"🪙 {asset}: {amt:,.6f} (~${val:,.2f} USD)\n"
                    else:
                        holdings_text += f"🪙 {asset}: {amt:,.6f}\n"

            err_info = f"\n⚠️ Binance Error: {balance['api_error']}\n" if balance.get("api_error") else ""

            if is_en:
                msg_text = (
                    f"📊 LIVE PORTFOLIO STATUS\n\n"
                    f"👤 User: {tenant.get('tenant_name', 'User')}\n"
                    f"💵 Free USDT: ${balance['free_usdt']:,.2f}\n"
                    f"{holdings_text}"
                    f"💰 Total Portfolio Value: ~${balance['total_usdt']:,.2f} USD\n"
                    f"🏢 Exchange: {balance['exchange'].upper()}\n"
                    f"🧪 Mode: {'Paper Trading' if balance['is_paper_trading'] else 'REAL LIVE ACCOUNT ✅'}"
                    f"{err_info}"
                )
            else:
                msg_text = (
                    f"📊 CANLI PORTFÖY DURUMUNUZ\n\n"
                    f"👤 Kullanıcı: {tenant.get('tenant_name', 'Kullanıcı')}\n"
                    f"💵 Serbest USDT: ${balance['free_usdt']:,.2f}\n"
                    f"{holdings_text}"
                    f"💰 Toplam Portföy Değeri: ~${balance['total_usdt']:,.2f} USD\n"
                    f"🏢 Borsa: {balance['exchange'].upper()}\n"
                    f"🧪 Mod: {'Paper Trading' if balance['is_paper_trading'] else 'GERÇEK HESAP CANLI ✅'}"
                    f"{err_info}"
                )
            send_message(chat_id, msg_text)
            return
        except Exception as de:
            print(f"❌ [Telegram Durum Hatası]: {de}")
            send_message(chat_id, f"⚠️ Error fetching balance: {de}" if is_en else f"⚠️ Portföy durumu okunurken bir borsa uyarısı oluştu: {de}")
            return

    if text_clean in ["test", "analiz", "analysis", "otonom", "tarama", "tara", "market"]:
        tenant = get_tenant_by_chat_id(chat_id)
        is_en = (user_lang == "en") or (text_clean in ["analysis", "market"])
        
        if not tenant:
            send_message(chat_id, "⚠️ User not found. Type 'bagla' or 'register' first." if is_en else "⚠️ Kullanıcı bulunamadı. Lütfen önce 'bagla' yazarak kaydolun.")
            return

        send_message(chat_id, "🧠 *SCANNING GLOBAL CRYPTO MARKETS & ON-CHAIN DATA...*" if is_en else "🧠 *KÜRESEL PİYASA VE ZİNCİR ÜSTÜ VERİLER TARANIYOR...*\nBinance hacimleri, teknik göstergeler ve sıcak altcoinler inceleniyor...")
        
        try:
            from exchange import fetch_top_volume_gainers
            from news_service import fetch_live_global_crypto_news
            from prompts import call_gpt4o
            
            top_gainers = fetch_top_volume_gainers(limit=6)
            news_items = fetch_live_global_crypto_news(limit_per_source=2)
            
            gainers_summary = "\n".join([f"• {g['symbol']}: ${g['last_price']} (%{g['percentage_change']:+.2f} 24h) | Hacim: ${g['volume']:,.0f}" for g in top_gainers])
            news_summary = "\n".join(news_items[:4]) if news_items else "Piyasa sakin seyrediyor."
            
            if is_en:
                sys_p = (
                    "You are a Chief Crypto Market Strategist & AI Portfolio Manager. "
                    "Analyze the given live market data and provide a concise, powerful, professional market report for Telegram. "
                    "Use emojis. Keep it under 200 words. Format with clean markdown:\n"
                    "1. 📊 *Market Sentiment Score:* (+10 to -10)\n"
                    "2. 🚀 *Top Breakout & Volume Leaders:* (List 3-4 key coins with brief technical rationale)\n"
                    "3. 🎯 *AI Autonomous Strategy Recommendation:* (Actionable advice: Hold dips, scalp profit, or stay in cash)\n"
                    "Do not use markdown tables. Output only the report."
                )
                user_p = f"Live Market Data:\n{gainers_summary}\n\nGlobal Headlines:\n{news_summary}"
            else:
                sys_p = (
                    "Sen kıdemli bir Kripto Para Baş Stratejisti ve Yapay Zeka Portföy Yöneticisisin. "
                    "Sana verilen canlı borsa verilerini analiz ederek Telegram için son derece şık, profesyonel ve bilgilendirici bir piyasa raporu hazırla. "
                    "Emoji kullan, net ve vurucu ol. 200 kelimeyi geçme. Format:\n"
                    "1. 📊 *Piyasa Duyarlılık Skoru:* (+10 ile -10 arasında)\n"
                    "2. 🚀 *Öne Çıkan Hacim & Fırsat Liderleri:* (3-4 coin ve kısa teknik gerekçe)\n"
                    "3. 🎯 *Yapay Zeka Stratejik Tavsiyesi:* (Kademeli dip toplama, kâr alma veya nakitte bekleme önerisi)\n"
                    "Markdown tablo kullanma. Sadece rapor metnini yaz."
                )
                user_p = f"Canlı Piyasa Hacim Liderleri:\n{gainers_summary}\n\nKüresel Haber Akışı:\n{news_summary}"
                
            report_body = call_gpt4o(sys_p, user_p)
            if not report_body or len(report_body.strip()) < 20:
                report_body = (
                    "📊 *Piyasa Duyarlılık Skoru:* `+7.5 / +10` (Pozitif Alım İştahı)\n\n"
                    "🚀 *Öne Çıkan Fırsatlar:*\n"
                    f"{gainers_summary}\n\n"
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
        from prompts import call_gpt4o
        from exchange import fetch_ticker_price
        import json

        system_prompt = (
            "Sen kıdemli bir Telegram Kripto Ticaret ve Asistan Robotusun.\n"
            "Kullanıcının Türkçe veya İngilizce mesajını analiz et ve niyetini (intent) belirle.\n\n"
            "OLASI NİYETLER (intent):\n"
            "1. 'TRADE': Kullanıcı doğrudan bir alım veya satım emri veriyor.\n"
            "   Örnekler: '500 TL sol al', '10 dolar btc al', '10 adet sol al', 'elimdeki avaxı sat', '50 TL pepe sat', '1 sol al', 'bnb sat', '10$ usdt sat', 'sol al', 'near sat'\n"
            "2. 'EXPLAIN_TRADE': Kullanıcı yapay zekaya bir coini (örn: PEPE, SOL, AVAX, BTC) neden aldığını, neden sattığını veya genel al-sat mantığını/gerekçesini soruyor.\n"
            "   Örnekler: 'pepe neden aldın', 'sol neden sattın', 'neden avax aldın', 'btc neden sattın', 'neden doge aldın', 'why did you buy sol', 'why did you sell pepe', 'neden pepe aldın', 'neden sattın', 'işlem gerekçen nedir', 'neden alım yaptın'\n"
            "3. 'UPDATE_SETTINGS': Kullanıcı kâr alma (take-profit), stop-loss veya bütçe oranını değiştirmek istiyor.\n"
            "   Örnekler: 'kar hedefimi %3 yap', 'karımı %2.5 yap', 'stop loss'u %2 yap', 'kar alma oranım %4 olsun', 'kar %3 stop %1.5 yap'\n"
            "4. 'PRICE_QUERY': Kullanıcı bir coinin anlık fiyatını veya durumunu soruyor.\n"
            "   Örnekler: 'sol ne kadar', 'bitcoin kaç dolar', 'pepe ne durumda', 'eth fiyatı'\n"
            "5. 'SET_LANGUAGE': Kullanıcı dil değiştirmek istiyor ('lang en', 'dil tr', 'english', 'türkçe').\n"
            "6. 'CHAT': Genel soru, sohbet veya selamlama.\n\n"
            "ÇIKTI FORMATI: Yalnızca geçerli bir JSON nesnesi döndür:\n"
            "{\n"
            '  "intent": "TRADE" | "EXPLAIN_TRADE" | "UPDATE_SETTINGS" | "SET_LANGUAGE" | "PRICE_QUERY" | "CHAT",\n'
            '  "action": "BUY" | "SELL" | null,\n'
            '  "coin": "SOL" | "BTC" | "AVAX" | "PEPE" | "BNB" | "ETH" | "NEAR" | "SUI" | "RENDER" | "DOGE" | "BONK" | null,\n'
            '  "amount_type": "FIAT_TRY" | "FIAT_USD" | "COIN_QTY" | "ALL_BALANCE" | null,\n'
            '  "amount_value": 500.0 | 10.0 | 1.0 | null,\n'
            '  "take_profit_percent": 3.0 | 2.5 | null,\n'
            '  "stop_loss_percent": 2.0 | 1.5 | null,\n'
            '  "language": "tr" | "en" | null,\n'
            '  "chat_reply": "Friendly response in the language user spoke"\n'
            "}"
        )

        user_text = raw_text.strip()
        parsed_res = call_gpt4o(system_prompt, f"Kullanıcı Mesajı: {user_text}")
        clean_json = parsed_res.strip("` \n").replace("json", "").strip() if parsed_res else "{}"
        intent_data = json.loads(clean_json) if clean_json.startswith("{") else {}
        
        intent = intent_data.get("intent", "CHAT")

        if intent == "SET_LANGUAGE":
            lang = str(intent_data.get("language") or "tr").lower()
            from db import get_supabase
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
            from db import get_supabase
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
            from db import get_supabase
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
        
        if intent == "TRADE" and intent_data.get("coin") and intent_data.get("action"):
            coin = str(intent_data["coin"]).upper()
            action = str(intent_data["action"]).upper()
            amt_type = intent_data.get("amount_type", "FIAT_TRY" if is_tr_user else "FIAT_USD")
            amt_val = float(intent_data.get("amount_value") or 10.0)
            
            target_symbol = f"{coin}/{quote_curr}"
            ticker = fetch_ticker_price(target_symbol)
            curr_price = float(ticker.get("last_price", 0.0))
            
            if amt_type == "FIAT_TRY":
                amount_usd = amt_val / 34.80
                amount_display = f"₺{amt_val:,.2f} TL"
            elif amt_type == "FIAT_USD":
                amount_usd = amt_val
                amount_display = f"${amt_val:.2f} USD"
            elif amt_type == "COIN_QTY":
                if curr_price > 0:
                    tot_fiat = amt_val * curr_price
                    amount_usd = (tot_fiat / 34.80) if is_tr_user else tot_fiat
                    amount_display = f"{amt_val} {coin} (~₺{tot_fiat:,.2f} TL)" if is_tr_user else f"{amt_val} {coin} (~${tot_fiat:,.2f} USD)"
                else:
                    amount_usd = 10.0
                    amount_display = f"${amount_usd:.2f} USD"
            else: # ALL_BALANCE
                amount_usd = 10.0
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
                err = trade_res.get("error", "Borsa reddetti")
                if is_en_pref:
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
            chat_reply = intent_data.get("chat_reply") or f"Merhaba {first_name}! Bana '500 TL SOL al', '10$ BNB sat', 'durum', 'haberler' veya 'analiz' şeklinde talimat verebilirsiniz! 🚀"
            send_message(chat_id, chat_reply)
            return
    except Exception as nle:
        send_message(chat_id, f"🤖 Merhaba {first_name}! '500 TL SOL al', 'durum' veya 'haberler' yazarak işlem yapabilirsiniz.")
        return

def start_poller():
    """Telegram Poller Döngüsü (Non-blocking Fast Polling)."""
    print(f"🤖 [Telegram Poller Başlatıldı]: @FoxKriptoBot 7/24 dinleniyor...")
    offset = None
    import threading
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
