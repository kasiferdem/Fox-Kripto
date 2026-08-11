import os, sys, requests
if hasattr(sys.stdout, 'reconfigure'): sys.stdout.reconfigure(encoding='utf-8')
from typing import Dict, Any, Optional
from dotenv import load_dotenv

load_dotenv()

TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID", "")

def send_telegram_message(text: str, reply_markup: Optional[Dict[str, Any]] = None) -> bool:
    """Telegram Bot API üzerinden mesaj ve buton gönderir."""
    if not TELEGRAM_BOT_TOKEN or TELEGRAM_BOT_TOKEN.startswith("your_"):
        print(f"   [Telegram Simulation]: {text}")
        return True
        
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {
        "chat_id": TELEGRAM_CHAT_ID,
        "text": text,
        "parse_mode": "Markdown",
        "reply_markup": reply_markup
    }
    try:
        res = requests.post(url, json=payload, timeout=10)
        return res.status_code == 200
    except Exception as e:
        print(f"❌ Telegram Mesaj Hatası: {e}")
        return False

def send_telegram_trade_approval(
    proposal: Dict[str, Any],
    sentiment_score: float,
    analysis_summary: str,
    session_id: str = "session_001"
) -> bool:
    """
    Human-in-the-Loop (HITL): Kullanıcıya formatlı onay kartı ve Onay/Ret butonları gönderir.
    """
    coin = proposal.get("symbol", "BTC/USDT")
    direction = proposal.get("direction", "BUY")
    amount = proposal.get("amount_usd", 100.0)
    entry = proposal.get("entry_price", 0.0)
    sl_pct = proposal.get("stop_loss_percent", 4.0)
    sl_price = proposal.get("stop_loss_price", 0.0)
    tp_price = proposal.get("take_profit_price", 0.0)

    text = (
        f"🚨 *FOX-KRİPTO İŞLEM TEKLİFİ (HUMAN-IN-THE-LOOP)*\n\n"
        f"📊 *Parite:* `{coin}` ({direction})\n"
        f"💵 *Tahsis Edilen Bütçe:* `${amount} USD` (%10 Limiti)\n"
        f"🎯 *Giriş Fiyatı:* `${entry:,.2f}`\n"
        f"🛑 *Stop-Loss (%{sl_pct}):* `${sl_price:,.2f}`\n"
        f"📈 *Kar Al (TP):* `${tp_price:,.2f}`\n"
        f"🧠 *Haber Duyarlılık Skoru:* `{sentiment_score}` (+10/-10)\n"
        f"📝 *Ajan Özeti:* _{analysis_summary}_\n\n"
        f"⚠️ *İşlemi onaylıyor musunuz?* (Onay vermeden borsaya emir iletilmez)."
    )

    # Telegram Inline Keyboard Buttons
    reply_markup = {
        "inline_keyboard": [
            [
                {"text": "✅ İŞLEMİ ONAYLA", "callback_data": f"approve_{session_id}"},
                {"text": "❌ REDDET", "callback_data": f"reject_{session_id}"}
            ]
        ]
    }

    print(f"📱 [Telegram Bot]: Onay Kartı Gönderiliyor -> {coin} ${amount} USD")
    return send_telegram_message(text, reply_markup)

if __name__ == "__main__":
    print("🚀 Telegram Bot Modülü Test Ediliyor...")
    mock_proposal = {
        "symbol": "BTC/USDT",
        "direction": "BUY",
        "amount_usd": 100.0,
        "entry_price": 64400.0,
        "stop_loss_percent": 4.0,
        "stop_loss_price": 61824.0,
        "take_profit_price": 68264.0
    }
    send_telegram_trade_approval(mock_proposal, 7.5, "Kurumsal girişler pozitif boğa görünümünü destekliyor.")
