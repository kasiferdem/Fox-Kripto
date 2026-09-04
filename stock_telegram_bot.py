"""
Fox-Borsa: Bağımsız Telegram Bildirim ve Kontrol Botu (@FoxBorsaBot)
Telif Hakkı (c) 2026 Fox-Kripto / Fox-Borsa Quant Ekibi.

ABD Hisse Senedi (Alpaca) alım-satım, Take-Profit, Stop-Loss ve portföy
bildirimlerini bağımsız olarak kullanıcılara iletir.
Ayrıca /start, /bakiye, /pozisyonlar, /hisseler, /seans komutlarına canlı yanıt verir.
"""

import os
import sys
import time
import threading
import requests
from typing import Optional, Dict, Any, List
from alpaca_client import AlpacaClient

STOCK_TELEGRAM_BOT_TOKEN = os.environ.get("STOCK_TELEGRAM_BOT_TOKEN", "8729610871:AAFGM3TOm7ZGXLVpG1m8sGSwk4l5L7zBsdg")
BASE_URL = f"https://api.telegram.org/bot{STOCK_TELEGRAM_BOT_TOKEN}"

# Ana Klavye Butonları
MAIN_KEYBOARD = {
    "keyboard": [
        [{"text": "💼 Bakiye & Cüzdan"}, {"text": "📊 Açık Pozisyonlar"}],
        [{"text": "🔍 Canlı Hisse Fiyatları"}, {"text": "⏰ Seans Durumu"}],
        [{"text": "🌐 Borsa Dashboard Paneli"}]
    ],
    "resize_keyboard": True,
    "persistent": True
}

def send_stock_telegram_message(
    chat_id: int,
    text: str,
    reply_markup: Optional[Dict[str, Any]] = None,
    parse_mode: str = "Markdown"
) -> bool:
    """Fox Borsa Telegram Botu üzerinden mesaj gönderir."""
    if not chat_id or not text:
        return False
    url = f"{BASE_URL}/sendMessage"
    payload = {
        "chat_id": chat_id,
        "text": text,
        "parse_mode": parse_mode,
        "disable_web_page_preview": True
    }
    if reply_markup is not None:
        payload["reply_markup"] = reply_markup
    else:
        payload["reply_markup"] = MAIN_KEYBOARD

    try:
        r = requests.post(url, json=payload, timeout=8)
        if r.status_code != 200:
            # Markdown fallback
            payload.pop("parse_mode", None)
            requests.post(url, json=payload, timeout=8)
        return r.status_code == 200
    except Exception as e:
        print(f"⚠️ [Stock Telegram Hatası]: {e}")
        return False

def notify_stock_trade(
    chat_id: int,
    action: str,  # "BUY", "SELL", "TP", "SL"
    symbol: str,
    qty: float,
    price: float,
    amount_usd: float,
    pnl_pct: Optional[float] = None,
    pnl_usd: Optional[float] = None,
    order_id: Optional[str] = None
) -> bool:
    """ABD Hisse Senedi Alım/Satım bildirimini şık formatta Telegram'a gönderir."""
    if action.upper() in ["BUY", "ALIM"]:
        title = "🛒 FOX-BORSA: CANLI HİSSE ALIMI (BUY)"
        icon = "🟢"
        extra = "🎯 *Hedef TP:* +%3.00 | *Stop-Loss:* -%1.50"
    elif action.upper() in ["TP", "TAKE_PROFIT", "KAR"]:
        title = "🎯 FOX-BORSA: KÂR ALMA (TAKE-PROFIT)"
        icon = "🎉"
        extra = f"📈 *Net Kâr:* +%{pnl_pct:.2f} (+${pnl_usd:.2f} USD)"
    elif action.upper() in ["SL", "STOP_LOSS", "ZARAR"]:
        title = "🛡️ FOX-BORSA: STOP-LOSS (SERMAYE KORUMA)"
        icon = "🛑"
        extra = f"📉 *Net Değişim:* %{pnl_pct:.2f} (-${abs(pnl_usd or 0):.2f} USD)"
    else:
        title = "📄 FOX-BORSA: İŞLEM BİLDİRİMİ"
        icon = "⚡"
        extra = ""

    msg = (
        f"{icon} *{title}*\n\n"
        f"🏛️ *Piyasa:* ABD BORSALARI (NASDAQ / NYSE)\n"
        f"🪙 *Hisse / Sembol:* `{symbol.upper()}`\n"
        f"📊 *Adet:* `{qty:.4f}` hisse\n"
        f"📥 *Birim Fiyat:* `${price:.2f} USD`\n"
        f"💵 *Toplam Tutar:* `${amount_usd:.2f} USD`\n"
        f"{extra}\n"
        f"🏢 *Aracı Kurum:* ALPACA SECURITIES LLC\n"
        f"📄 *Emir No:* `#{order_id or 'ALPACAX'}`\n\n"
        f"🤖 _Fox-Borsa Wall Street Quant Engine Tarafından Otonom İnfaz Edildi._"
    )
    return send_stock_telegram_message(chat_id, msg)

# -------------------------------------------------------------
# 🤖 ETKİLEŞİMLİ KOMUT DİNLEYİCİSİ (INTERACTIVE COMMAND HANDLER)
# -------------------------------------------------------------

def handle_stock_message(msg: Dict[str, Any]):
    chat = msg.get("chat", {})
    chat_id = chat.get("id")
    text = (msg.get("text") or "").strip()
    if not chat_id or not text:
        return

    text_lower = text.lower()
    alpaca = AlpacaClient()

    # 1. /start ve Yardım
    if text_lower in ["/start", "start", "merhaba", "selam", "yardım", "/help"]:
        welcome_text = (
            "🏛️ *Fox-Borsa (@FoxBorsaBot) Wall Street Quant Sistemine Hoş Geldiniz!*\n\n"
            "Bu bot, **Alpaca Securities LLC** üzerinden ABD Hisse Senedi Piyasalarında (NASDAQ / NYSE) 16:30 - 23:00 seanslarında 2. Dalga Retest stratejisiyle otonom işlem ve anlık bildirim sağlar.\n\n"
            "📌 *Kullanabileceğiniz Hızlı İşlemler:*\n"
            "• 💼 *Bakiye & Cüzdan:* Alpaca nakit ve portföy durumunuz\n"
            "• 📊 *Açık Pozisyonlar:* Canlı hisse pozisyonları ve kâr/zarar\n"
            "• 🔍 *Canlı Hisse Fiyatları:* NVDA, TSLA, AAPL, SPY anlık verileri\n"
            "• ⏰ *Seans Durumu:* ABD borsa açılış/kapanış saatleri\n"
            "• 🌐 *Borsa Dashboard:* Web yönetim paneli linki\n\n"
            "Aşağıdaki menü butonlarını kullanarak anında sorgulama yapabilirsiniz 👇"
        )
        send_stock_telegram_message(chat_id, welcome_text, reply_markup=MAIN_KEYBOARD)

    # 2. Bakiye & Cüzdan
    elif "bakiye" in text_lower or text_lower == "/bakiye" or "cüzdan" in text_lower:
        acc = alpaca.get_account()
        if acc.get("status") == "success":
            port_val = acc.get("portfolio_value", 100000.0)
            cash_val = acc.get("cash", 100000.0)
            power_val = acc.get("buying_power", 400000.0)
            is_p = acc.get("is_paper", True)
            
            bal_msg = (
                "💼 *ALPACA HESAP VE PORTFÖY DURUMU*\n\n"
                f"💵 *Toplam Portföy Değeri:* `${port_val:,.2f} USD`\n"
                f"🟢 *Kullanılabilir Serbest Nakit:* `${cash_val:,.2f} USD`\n"
                f"🚀 *Gün İçi Alım Gücü (4x Margin):* `${power_val:,.2f} USD`\n"
                f"🏢 *Aracı Kurum:* Alpaca Securities LLC\n"
                f"🧪 *Hesap Modu:* `{'Paper Sandbox ($100K)' if is_p else 'Live Real Trading'}`\n"
                f"🟢 *Hesap Durumu:* `ACTIVE (İşleme Açık)`"
            )
        else:
            bal_msg = f"⚠️ Bakiye sorgulanamadı: {acc.get('error')}"
        send_stock_telegram_message(chat_id, bal_msg)

    # 3. Açık Pozisyonlar
    elif "pozisyon" in text_lower or text_lower == "/pozisyonlar":
        positions = alpaca.get_positions()
        if not positions:
            pos_msg = "💼 *Şu an açık hisse senedi pozisyonunuz bulunmuyor (Kasa %100 Nakitte).* 🛡️"
        else:
            pos_msg = f"📊 *AÇIK HİSSE SENEDİ POZİSYONLARI ({len(positions)})*\n\n"
            for p in positions:
                sym = p.get("symbol")
                qty = p.get("qty")
                cur = p.get("current_price")
                entry = p.get("avg_entry_price")
                pl = p.get("unrealized_pl", 0.0)
                plpc = p.get("unrealized_plpc", 0.0)
                icon = "🟢" if pl >= 0 else "🔴"
                pos_msg += (
                    f"🪙 *{sym}* ({qty} adet)\n"
                    f"  • Giriş: `${entry:.2f}` | Anlık: `${cur:.2f}`\n"
                    f"  • {icon} Kâr/Zarar: `{'+' if pl>=0 else ''}${pl:.2f} ({'+' if plpc>=0 else ''}{plpc:.2f}%)`\n\n"
                )
        send_stock_telegram_message(chat_id, pos_msg)

    # 4. Canlı Hisse Fiyatları
    elif "hisse" in text_lower or "fiyat" in text_lower or text_lower == "/hisseler":
        symbols = ["NVDA", "TSLA", "AAPL", "MSFT", "SPY", "QQQ", "PLTR", "COIN"]
        bars = alpaca.get_latest_bars(symbols)
        if not bars:
            price_msg = "⚠️ Hisse fiyatları anlık olarak okunamadı."
        else:
            price_msg = "🔍 *CANLI ABD HİSSE SENEDİ VE ETF FİYATLARI*\n\n"
            for s, b in bars.items():
                p_val = b.get("price", 0.0)
                price_msg += f"• *{s}:* `${p_val:.2f} USD`\n"
            price_msg += "\n🏛️ _Veriler Alpaca Market Data üzerinden anlık olarak çekilmektedir._"
        send_stock_telegram_message(chat_id, price_msg)

    # 5. Seans Durumu
    elif "seans" in text_lower or text_lower == "/seans" or "piyasa" in text_lower:
        clock = alpaca.get_market_clock()
        is_open = clock.get("is_open", False)
        if is_open:
            seans_msg = (
                "🟢 *ABD BORSALARI SEANSI AÇIK! (NYSE & NASDAQ)*\n\n"
                "• İşlemler ve algoritmik 2. Dalga Retest taraması aktiftir.\n"
                "• Seans Kapanışı: 23:00 TSI (16:00 EST)"
            )
        else:
            seans_msg = (
                "🔴 *ABD BORSALARI ŞU AN KAPALI*\n\n"
                "• Seans Saatleri: Hafta içi 16:30 - 23:00 TSI (09:30 - 16:00 EST)\n"
                "• Sistem açılış seansını pusuya yatarak beklemektedir."
            )
        send_stock_telegram_message(chat_id, seans_msg)

    # 6. Panel Linki
    elif "panel" in text_lower or text_lower == "/panel" or "dashboard" in text_lower:
        panel_msg = (
            "🌐 *FOX-BORSA YÖNETİM PANELİ*\n\n"
            "Aşağıdaki link üzerinden Alpaca borsa panelinize ulaşabilirsiniz:\n"
            "👉 `https://fox-kripto-m7n46.ondigitalocean.app/borsa/dashboard`\n\n"
            "_(Kullanıcı yönetimi, hisse tarayıcısı ve tek tıkla alım yapabilirsiniz.)_"
        )
        send_stock_telegram_message(chat_id, panel_msg)

    else:
        send_stock_telegram_message(
            chat_id,
            "🤖 Komut anlaşılamadı. Lütfen aşağıdaki menü butonlarını kullanınız veya `/start` yazınız.",
            reply_markup=MAIN_KEYBOARD
        )

# -------------------------------------------------------------
# 🔄 7/24 ARKA PLAN POLLER DÖNGÜSÜ (BACKGROUND POLLER)
# -------------------------------------------------------------

_poller_thread = None
_poller_running = False

def _run_stock_poller_loop():
    global _poller_running
    offset = 0
    print("🚀 [@FoxBorsaBot]: Telegram Dinleyicisi Başlatıldı!")
    while _poller_running:
        try:
            url = f"{BASE_URL}/getUpdates?offset={offset}&timeout=15"
            res = requests.get(url, timeout=20)
            if res.status_code == 200:
                data = res.json()
                updates = data.get("result", [])
                for u in updates:
                    offset = u["update_id"] + 1
                    msg = u.get("message")
                    if msg:
                        handle_stock_message(msg)
            elif res.status_code == 409:
                time.sleep(5)
            else:
                time.sleep(2)
        except Exception as e:
            time.sleep(3)

def start_stock_telegram_poller():
    """Fox Borsa Telegram Poller döngüsünü arka planda başlatır."""
    global _poller_thread, _poller_running
    if _poller_thread and _poller_thread.is_alive():
        return
    _poller_running = True
    _poller_thread = threading.Thread(target=_run_stock_poller_loop, daemon=True)
    _poller_thread.start()
