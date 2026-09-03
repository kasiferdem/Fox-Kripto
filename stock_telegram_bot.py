"""
Fox-Borsa: Bağımsız Telegram Bildirim ve Kontrol Botu (@FoxBorsaBot)
Telif Hakkı (c) 2026 Fox-Kripto / Fox-Borsa Quant Ekibi.

ABD Hisse Senedi (Alpaca) alım-satım, Take-Profit, Stop-Loss ve portföy
bildirimlerini bağımsız olarak kullanıcılara iletir.
"""

import os
import time
import requests
from typing import Optional, Dict, Any

STOCK_TELEGRAM_BOT_TOKEN = os.environ.get("STOCK_TELEGRAM_BOT_TOKEN", "8729610871:AAFGM3TOm7ZGXLVpG1m8sGSwk4l5L7zBsdg")

def send_stock_telegram_message(
    chat_id: int,
    text: str,
    reply_markup: Optional[Dict[str, Any]] = None,
    parse_mode: str = "Markdown"
) -> bool:
    """Fox Borsa Telegram Botu üzerinden mesaj gönderir."""
    if not chat_id or not text:
        return False
    url = f"https://api.telegram.org/bot{STOCK_TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {
        "chat_id": chat_id,
        "text": text,
        "parse_mode": parse_mode,
        "disable_web_page_preview": True
    }
    if reply_markup:
        payload["reply_markup"] = reply_markup
    try:
        r = requests.post(url, json=payload, timeout=8)
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
        extra = f"🎯 *Hedef TP:* +%3.00 | *Stop-Loss:* -%1.50"
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
