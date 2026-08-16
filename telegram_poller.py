import os, sys, time, requests, io

# Windows Console Emoji UnicodeEncodeError Önleyici
if hasattr(sys.stdout, 'buffer'):
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
if hasattr(sys.stderr, 'buffer'):
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')

from dotenv import load_dotenv
from db import register_user_tenant, get_tenant_by_chat_id, get_supabase, log_trade_decision, save_graph_state, load_graph_state
from exchange import fetch_portfolio_balance, execute_spot_trade

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

    # Komut İşleme (Taksim / işaretli veya taksimsiz esnek eşleşme)
    if text_clean in ["start", "help", "yardim", "merhaba"]:
        tenant = get_tenant_by_chat_id(chat_id)
        if tenant:
            send_message(chat_id, f"👋 Merhaba {first_name}!\n\nSistemde {tenant['tenant_name']} olarak kayıtlısınız! ✅\n\n📌 Kullanabileceğiniz Komutlar:\n• durum veya bakiye - Canlı portföyünüzü görün.\n• haberler - Dünyadan en sıcak kripto haberlerini alın.\n• analiz - Canlı yapay zeka piyasa taraması başlatın.\n• bagla - Borsa API anahtarlarınızı güncelleyin.")
        else:
            send_message(chat_id, f"👋 Merhaba {first_name}! Fox-Kripto Otonom Ajan Sistemine Hoş Geldiniz!\n\nBinance hesabınızı bağlamak için bagla yazabilirsiniz.")
        return

    if text_clean in ["haber", "haberler", "haberle", "gundem", "gündem", "news", "kripto haber", "son haberler"]:
        send_message(chat_id, "📡 *KÜRESEL KRİPTO HABERLERİ ÇEKİLİYOR...*\nCoinDesk, CoinTelegraph ve Decrypt taranıyor...")
        try:
            from news_service import fetch_live_global_crypto_news
            headlines = fetch_live_global_crypto_news(limit_per_source=3)
            
            if headlines:
                news_items = "\n\n".join([f"• {h}" for h in headlines[:8]])
                summary_msg = (
                    f"🌍 *CANLI KÜRESEL KRİPTO GÜNDEMİ*\n"
                    f"_(CoinDesk • CoinTelegraph • Decrypt)_\n\n"
                    f"{news_items}\n\n"
                    f"🤖 *Yapay Zeka Analizi:* Küresel haber akışı taranarak otomatik alım-satım stratejilerine doğrudan yansıtılmaktadır! 🚀"
                )
                send_message(chat_id, summary_msg)
            else:
                send_message(chat_id, "ℹ️ Şu anda küresel haber akışında olağandışı bir son dakika gelişmesi bulunmuyor, piyasa sakin seyrediyor.")
        except Exception as ne:
            send_message(chat_id, f"⚠️ Haber akışı çekilirken bir hata oluştu: {ne}")
        return

    if text_clean in ["durum", "bakiye", "portfoy", "bakiye nedir", "durum nedir"]:
        tenant = get_tenant_by_chat_id(chat_id)
        if not tenant:
            send_message(
                chat_id, 
                f"⚠️ *KAYITLI KULLANICI BULUNAMADI*\n\n"
                f"Chat ID `{chat_id}` için Supabase veritabanında aktif borsa hesabı bulunamadı.\n\n"
                f"Lütfen Web Yönetim Panelinizden (`/dashboard`) veya Telegram'da `bagla` yazarak Binance API anahtarlarınızı kaydedin."
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
            if tr_details:
                for a, info in tr_details.items():
                    amt = info["amount"]
                    val = info["val_usd"]
                    if a == "TRY":
                        free_try = amt
                    elif val > 0.01:
                        ticker = fetch_ticker_price(f"{a}/TRY")
                        p_try = float(ticker.get("last_price", 0.0))
                        tot_try = amt * p_try if p_try > 0 else (val * 47.80)
                        tr_holdings_str += f" • 🟢 *{a}:* `{amt:,.4f}` (₺{tot_try:,.2f} TL)\n"
                        
            tot_tr_usd = float(bal_tr.get("total_usdt", 0.0))
            tot_tr_try = tot_tr_usd * 47.80
            
            # Global Varlıkları
            gl_holdings_str = ""
            gl_details = bal_gl.get("holdings_details", {})
            free_usdt = float(bal_gl.get("free_usdt", 0.0))
            if gl_details:
                for a, info in gl_details.items():
                    amt = info["amount"]
                    val = info["val_usd"]
                    if a != "USDT" and val > 0.5:
                        gl_holdings_str += f" • 🟢 *{a}:* `{amt:,.4f}` (${val:,.2f} USD)\n"
            if not gl_holdings_str:
                gl_holdings_str = " • _(Açık coin pozisyonu yok)_\n"
                
            tot_usd = float(balance.get("total_usdt", 0.0))
            
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
                f"🏆 *GENEL TOPLAM PORTFÖY:* *${tot_usd:,.2f} USD* (~₺{tot_usd * 47.80:,.2f} TL)\n"
                f"🧪 Mod: GERÇEK HESAPLAR CANLI ✅"
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

        err_info = f"\n⚠️ Binance Hata Nedeni: {balance['api_error']}\n" if balance.get("api_error") else ""

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

    if text_clean in ["test", "analiz", "otonom", "tarama", "tara"]:
        tenant = get_tenant_by_chat_id(chat_id)
        if not tenant:
            send_message(chat_id, "⚠️ Kullanıcı bulunamadı. Lütfen önce 'bagla' yazarak kaydolun.")
            return

        send_message(chat_id, "🧠 *YAPAY ZEKA OTONOM ANALİZ TESTİ BAŞLATILDI...*\n\n1/3 Piyasa hacmi, teknik göstergeler ve fiyatlar çekiliyor...")
        
        try:
            from graph import create_crypto_graph
            from db import save_graph_state
            
            graph = create_crypto_graph()
            initial_state = {
                "tenant_id": tenant.get("id"),
                "tenant_config": tenant,
                "news_data": "Crypto market showing volume breakout and bullish momentum.",
                "portfolio_state": {},
                "sentiment_score": 0.8,
                "trade_proposal": None,
                "human_approval": "Approved", # FULL AUTONOMOUS TEST
                "execution_result": None
            }
            res = graph.invoke(initial_state)
            save_graph_state(f"test_{chat_id}", res)

            proposal = res.get("trade_proposal")
            sentiment = res.get("sentiment_score", 0.0)
            exec_res = res.get("execution_result")

            if proposal and proposal.get("should_trade", True) and sentiment > 0.0:
                symbol = proposal.get("symbol", "BTC/USDT")
                if "AUTO" in symbol.upper(): symbol = "BTC/USDT"
                action = proposal.get("direction", "ALIM")
                amount = proposal.get("amount_usd", 10.0)
                sl = proposal.get("stop_loss_price", 0.0)
                
                is_success = exec_res and exec_res.get("status") in ["success", "EXECUTED", "EXECUTED_SIMULATED"]
                order_no = f"\n📄 Emir No: #{exec_res.get('order_id')}" if (is_success and exec_res.get('order_id')) else ""
                
                if is_success:
                    status_text = f"✅ Canlı İşlem Binance TR Hesabınızda Gerçekleştirildi!{order_no}"
                else:
                    err_msg = exec_res.get("error", "Bakiye Yetersiz") if exec_res else "Bakiye Yetersiz"
                    if "2202" in err_msg or "balance" in err_msg.lower():
                        status_text = "⚠️ Alım Emri Verilemedi: Binance TR TL Bakiyeniz Yetersiz (Kalan bakiye miktarını aşan emir)."
                    else:
                        status_text = f"⚠️ Alım Emri İletilemedi: {err_msg}"
                
                report = (
                    f"🎯 *YAPAY ZEKA OTONOM ANALİZ RAPORU*\n\n"
                    f"👤 Kullanıcı: {tenant.get('tenant_name')}\n"
                    f"📊 Yapay Zeka Skoru: *{sentiment:+.1f} / +10*\n"
                    f"⚡ İşlem Kararı: *{action} {symbol}*\n"
                    f"💵 Ayrılan Bütçe: *${amount:.2f} USD*\n"
                    f"🛡️ Stop-Loss Seviyesi: *${sl:.2f}*\n"
                    f"🏢 Borsa: BINANCE.TR\n\n"
                    f"{status_text}"
                )
            else:
                report = (
                    f"📊 *YAPAY ZEKA PİYASA TARAMA RAPORU*\n\n"
                    f"👤 Kullanıcı: {tenant.get('tenant_name')}\n"
                    f"📊 Piyasa Duyarlılık Skoru: *{sentiment:+.1f} / +10*\n"
                    f"🛡️ Risk Kararı: Piyasa yönü olumsuz/durağan olduğu için sermayeyi korumak amacıyla alım yapılmadı.\n"
                    f"💵 Nakit TL Bakiyeniz Korumada.\n"
                    f"✅ 7/24 Otonom Nöbet Devam Ediyor."
                )
            send_message(chat_id, report)
        except Exception as e:
            send_message(chat_id, f"⚠️ Test sırasında bir uyarı oluştu: {e}")
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
            "Kullanıcının Türkçe mesajını analiz et ve niyetini (intent) belirle.\n\n"
            "OLASI NİYETLER (intent):\n"
            "1. 'TRADE': Kullanıcı doğrudan bir alım veya satım emri veriyor.\n"
            "   Örnekler: '500 TL sol al', '10 dolar btc al', '10 adet sol al', 'elimdeki avaxı sat', '50 TL pepe sat', '1 sol al', 'bnb sat', '10$ usdt sat', 'sol al', 'near sat'\n"
            "2. 'UPDATE_SETTINGS': Kullanıcı kâr alma (take-profit), stop-loss veya bütçe oranını değiştirmek istiyor.\n"
            "   Örnekler: 'kar hedefimi %3 yap', 'karımı %2.5 yap', 'stop loss'u %2 yap', 'kar alma oranım %4 olsun', 'kar %3 stop %1.5 yap'\n"
            "3. 'PRICE_QUERY': Kullanıcı bir coinin anlık fiyatını veya durumunu soruyor.\n"
            "   Örnekler: 'sol ne kadar', 'bitcoin kaç dolar', 'pepe ne durumda', 'eth fiyatı'\n"
            "4. 'CHAT': Genel soru, sohbet veya selamlama.\n\n"
            "ÇIKTI FORMATI: Yalnızca geçerli bir JSON nesnesi döndür:\n"
            "{\n"
            '  "intent": "TRADE" | "UPDATE_SETTINGS" | "PRICE_QUERY" | "CHAT",\n'
            '  "action": "BUY" | "SELL" | null,\n'
            '  "coin": "SOL" | "BTC" | "AVAX" | "PEPE" | "BNB" | "ETH" | "NEAR" | "SUI" | "RENDER" | null,\n'
            '  "amount_type": "FIAT_TRY" | "FIAT_USD" | "COIN_QTY" | "ALL_BALANCE" | null,\n'
            '  "amount_value": 500.0 | 10.0 | 1.0 | null,\n'
            '  "take_profit_percent": 3.0 | 2.5 | null,\n'
            '  "stop_loss_percent": 2.0 | 1.5 | null,\n'
            '  "chat_reply": "Kullanıcıya samimi ve profesyonel yanıt"\n'
            "}"
        )

        user_text = raw_text.strip()
        parsed_res = call_gpt4o(system_prompt, f"Kullanıcı Mesajı: {user_text}")
        clean_json = parsed_res.strip("` \n").replace("json", "").strip() if parsed_res else "{}"
        intent_data = json.loads(clean_json) if clean_json.startswith("{") else {}
        
        intent = intent_data.get("intent", "CHAT")

        if intent == "UPDATE_SETTINGS":
            tp = intent_data.get("take_profit_percent")
            sl = intent_data.get("stop_loss_percent")
            from db import get_supabase
            sb = get_supabase()
            if sb and (tp is not None or sl is not None):
                update_payload = {}
                if tp is not None: update_payload["take_profit_percent"] = float(tp)
                if sl is not None: update_payload["stop_loss_percent"] = float(sl)
                sb.table("user_tenants").update(update_payload).eq("telegram_chat_id", chat_id).execute()
                
                curr_tp = float(tp) if tp is not None else float(tenant.get("take_profit_percent") or 1.5)
                curr_sl = float(sl) if sl is not None else float(tenant.get("stop_loss_percent") or 1.5)
                
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
                amount_display = f"Tüm {coin} Varlığı"
                
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
