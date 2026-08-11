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
    Markdown formatı hata verirse otomatik olarak sade metin olarak tekrar dener.
    """
    payload = {"chat_id": chat_id, "text": text, "parse_mode": "Markdown", "reply_markup": reply_markup}
    try:
        res = requests.post(f"{BASE_URL}/sendMessage", json=payload, timeout=10)
        if res.status_code != 200:
            # Fallback: Markdown formatı olmadan tekrar dene
            payload.pop("parse_mode", None)
            res_retry = requests.post(f"{BASE_URL}/sendMessage", json=payload, timeout=10)
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
        
        action = "Approved" if "approve" in cb_data else "Rejected"
        session_id = cb_data.split("_")[-1] if "_" in cb_data else "session_001"
        
        print(f"🎯 [Telegram Poller Buton Tıklandı]: Chat ID={chat_id}, Action={action}")
        
        tenant = get_tenant_by_chat_id(chat_id)
        saved_state = load_graph_state(session_id) or {}
        proposal = saved_state.get("trade_proposal")
        
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
                **proposal, "sentiment_score": saved_state.get("sentiment_score"),
                "human_approval": "Approved", "status": result.get("status", "EXECUTED"),
                "order_id": result.get("order_id"), "execution_details": result
            }, tenant_id=tenant.get("id") if tenant else None)
            
            send_message(chat_id, f"🚀 İŞLEM BORSADA GERÇEKLEŞTİ!\nEmir No: {result.get('order_id')}\nİnfaz Fiyatı: ${result.get('executed_price')}")
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
            send_message(chat_id, f"👋 Merhaba {first_name}!\n\nSistemde {tenant['tenant_name']} olarak kayıtlısınız! ✅\n\n📌 Kullanabileceğiniz Komutlar:\n• durum veya bakiye - Canlı portföyünüzü görün.\n• bagla - Borsa API anahtarlarınızı güncelleyin.")
        else:
            send_message(chat_id, f"👋 Merhaba {first_name}! Fox-Kripto Otonom Ajan Sistemine Hoş Geldiniz!\n\nBinance hesabınızı bağlamak için bagla yazabilirsiniz.")
        return

    if text_clean in ["durum", "bakiye", "portfoy", "bakiye nedir", "durum nedir"]:
        tenant = get_tenant_by_chat_id(chat_id)
        balance = fetch_portfolio_balance(tenant)
        msg_text = (
            f"📊 CANLI PORTFÖY DURUMUNUZ\n\n"
            f"💵 Serbest USDT: ${balance['free_usdt']:,.2f}\n"
            f"💰 Toplam Değer: ${balance['total_usdt']:,.2f}\n"
            f"🏢 Borsa: {balance['exchange'].upper()}\n"
            f"🧪 Mod: {'Paper Trading' if balance['is_paper_trading'] else 'GERÇEK HESAP CANLI ✅'}"
        )
        send_message(chat_id, msg_text)
        return

    if text_clean in ["bagla", "register", "kayit"]:
        user_states[chat_id] = "AWAITING_API_KEY"
        send_message(chat_id, "🔐 Borsa Bağlantı Sihirbazı\n\nLütfen Binance API Key bilginizi bu sohbete mesaj olarak atın:")
        return

    # Çok Adımlı Kayıt Sihirbazı
    state = user_states.get(chat_id)
    if state == "AWAITING_API_KEY":
        user_states[chat_id] = {"step": "AWAITING_SECRET_KEY", "api_key": raw_text}
        send_message(chat_id, "✅ API Key alındı!\n\nŞimdi lütfen Binance Secret Key bilginizi mesaj olarak atın:")
        return
    elif isinstance(state, dict) and state.get("step") == "AWAITING_SECRET_KEY":
        api_key = state["api_key"]
        secret_key = raw_text
        del user_states[chat_id]
        
        # Veritabanına kaydet
        res = register_user_tenant(
            tenant_name=first_name,
            telegram_chat_id=chat_id,
            exchange_api_key=api_key,
            exchange_secret_key=secret_key
        )
        if res:
            send_message(chat_id, f"🎉 TEBRİKLER {first_name.upper()}!\n\nBinance hesabınız başarıyla bağlandı! Artık otonom yapay zeka sinyalleri bu sohbet üzerinden onayınıza sunulacak. 🚀")
        else:
            send_message(chat_id, "❌ Bağlantı sırasında bir hata oluştu. Lütfen tekrar deneyin.")
        return

def start_poller():
    """Telegram Poller Döngüsü (Non-blocking Fast Polling)."""
    print(f"🤖 [Telegram Poller Başlatıldı]: @FoxKriptoBot 7/24 dinleniyor...")
    offset = None
    while True:
        try:
            params = {"timeout": 0, "offset": offset}
            res = requests.get(f"{BASE_URL}/getUpdates", params=params, timeout=5)
            if res.status_code == 200:
                results = res.json().get("result", [])
                for update in results:
                    offset = update["update_id"] + 1
                    try:
                        handle_update(update)
                    except Exception as err:
                        print(f"⚠️ [Poller Update Hatası]: {err}")
            time.sleep(1)
        except Exception as e:
            time.sleep(2)

if __name__ == "__main__":
    start_poller()
