import os, sys, time, requests
if hasattr(sys.stdout, 'reconfigure'): sys.stdout.reconfigure(encoding='utf-8')
from dotenv import load_dotenv
from db import register_user_tenant, get_tenant_by_chat_id, get_supabase, log_trade_decision, save_graph_state, load_graph_state
from exchange import fetch_portfolio_balance, execute_spot_trade

load_dotenv()

TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "8938326996:AAFLmy3S4uAb_GbF8TotsdL0CgWq4jGCFik")
BASE_URL = f"https://api.telegram.org/bot{TOKEN}"

# Kullanıcı oturum durumları (Registration Wizards)
user_states = {}

def send_message(chat_id: int, text: str, reply_markup=None):
    payload = {"chat_id": chat_id, "text": text, "parse_mode": "Markdown", "reply_markup": reply_markup}
    try:
        requests.post(f"{BASE_URL}/sendMessage", json=payload, timeout=10)
    except Exception as e:
        print(f"❌ Telegram Send Error: {e}")

def handle_update(update: dict):
    # 1. Buton Tıklamaları (Callback Query - ONAL / REDDET)
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
            send_message(chat_id, f"✅ *İŞLEM ONAYLANDI!* Borsaya emir iletiliyor...\n`{proposal['symbol']} - ${proposal['amount_usd']} USD`")
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
            
            send_message(chat_id, f"🚀 *İŞLEM BORSADA GERÇEKLEŞTİ!*\nEmir No: `{result.get('order_id')}`\nİnfaz Fiyatı: `${result.get('executed_price')}`")
        else:
            send_message(chat_id, "❌ *İŞLEM REDDEDİLDİ VEYA İPTAL EDİLDİ.*")
        return

    # 2. Normal Mesajlar ve Komutlar
    message = update.get("message")
    if not message: return
    
    chat_id = message["chat"]["id"]
    text = (message.get("text") or "").strip()
    first_name = message["chat"].get("first_name", "Kullanıcı")

    # Komut İşleme
    if text in ["/start", "/help"]:
        tenant = get_tenant_by_chat_id(chat_id)
        if tenant:
            send_message(chat_id, f"👋 *Merhaba {first_name}!*\n\nSistemde **{tenant['tenant_name']}** olarak kayıtlısınız! ✅\n\n📌 *Kullanabileceğiniz Komutlar:*\n• `/durum` veya `/bakiye` - Canlı portföyünüzü görün.\n• `/bagla` - Borsa API anahtarlarınızı güncelleyin.")
        else:
            send_message(chat_id, f"👋 *Merhaba {first_name}!* Fox-Kripto Otonom Ajan Sistemine Hoş Geldiniz!\n\nBinance hesabınızı bağlamak için `/bagla` komutunu yazabilirsiniz.")
        return

    if text in ["/durum", "/bakiye"]:
        tenant = get_tenant_by_chat_id(chat_id)
        balance = fetch_portfolio_balance(tenant)
        send_message(chat_id, f"📊 *CANLI PORTFÖY DURUMUNUZ*\n\n💵 *Serbest USDT:* `${balance['free_usdt']:,.2f}`\n💰 *Toplam Değer:* `${balance['total_usdt']:,.2f}`\n🏢 *Borsa:* `{balance['exchange'].upper()}`\n🧪 *Mod:* `{'Paper Trading' if balance['is_paper_trading'] else 'GERÇEK HESAP CANLI ✅'}`")
        return

    if text == "/bagla":
        user_states[chat_id] = "AWAITING_API_KEY"
        send_message(chat_id, "🔐 *Borsa Bağlantı Sihirbazı*\n\nLütfen **Binance API Key** bilginizi bu sobete mesaj olarak atın:")
        return

    # Çok Adımlı Kayıt Sihirbazı
    state = user_states.get(chat_id)
    if state == "AWAITING_API_KEY":
        user_states[chat_id] = {"step": "AWAITING_SECRET_KEY", "api_key": text}
        send_message(chat_id, "✅ API Key alındı!\n\nŞimdi lütfen **Binance Secret Key** bilginizi mesaj olarak atın:")
        return
    elif isinstance(state, dict) and state.get("step") == "AWAITING_SECRET_KEY":
        api_key = state["api_key"]
        secret_key = text
        del user_states[chat_id]
        
        # Veritabanına kaydet
        res = register_user_tenant(
            tenant_name=first_name,
            telegram_chat_id=chat_id,
            exchange_api_key=api_key,
            exchange_secret_key=secret_key
        )
        if res:
            send_message(chat_id, f"🎉 *TEBRİKLER {first_name.upper()}!*\n\nBinance hesabınız başarıyla bağlandı! Artık otonom yapay zeka sinyalleri bu sohbet üzerinden onayınıza sunulacak. 🚀")
        else:
            send_message(chat_id, "❌ Bağlantı sırasında bir hata oluştu. Lütfen tekrar deneyin.")
        return

def start_poller():
    """Telegram Poller Döngüsü (Long-Polling)."""
    print(f"🤖 [Telegram Poller Başlatıldı]: @FoxKriptoBot 7/24 dinleniyor...")
    offset = None
    while True:
        try:
            params = {"timeout": 10, "offset": offset}
            res = requests.get(f"{BASE_URL}/getUpdates", params=params, timeout=15)
            if res.status_code == 200:
                results = res.json().get("result", [])
                for update in results:
                    offset = update["update_id"] + 1
                    handle_update(update)
        except Exception as e:
            time.sleep(2)

if __name__ == "__main__":
    start_poller()
