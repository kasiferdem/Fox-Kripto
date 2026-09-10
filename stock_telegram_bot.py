"""
Fox-Borsa: Bağımsız Telegram Bildirim ve Kontrol Botu (@FoxBorsaBot)
Telif Hakkı (c) 2026 Fox-Kripto / Fox-Borsa Quant Ekibi.

ABD Hisse Senedi (Alpaca) alım-satım, Take-Profit, Stop-Loss ve portföy
bildirimlerini bağımsız olarak kullanıcılara iletir.
Ayrıca /start, /bakiye, /pozisyonlar, /hisseler, /seans komutlarına canlı yanıt verir.
"""

import os
import sys
import io
import time
import threading
import requests
from typing import Optional, Dict, Any, List
from alpaca_client import AlpacaClient



try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

DEFAULT_STOCK_BOT_TOKEN = ""

def _get_base_url() -> str:
    token = os.environ.get("STOCK_TELEGRAM_BOT_TOKEN", "").strip()
    return f"https://api.telegram.org/bot{token}"

# Ana Klavye Butonları (Sabit ve Sürekli Görünür)
MAIN_KEYBOARD = {
    "keyboard": [
        [{"text": "💼 Bakiye & Cüzdan"}, {"text": "📊 Açık Pozisyonlar"}],
        [{"text": "🔍 Canlı Hisse Fiyatları"}, {"text": "🌍 Küresel Piyasa Radarı"}],
        [{"text": "⏰ Seans Durumu"}, {"text": "🌐 Borsa Dashboard Paneli"}]
    ],
    "resize_keyboard": True,
    "is_persistent": True,
    "one_time_keyboard": False
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
    base_url = _get_base_url()
    url = f"{base_url}/sendMessage"
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
            port_val = float(acc.get("portfolio_value", 100000.0) or 100000.0)
            cash_val = float(acc.get("cash", 100000.0) or 100000.0)
            power_val = float(acc.get("buying_power", 400000.0) or 400000.0)
            is_p = acc.get("is_paper", True)
            
            raw_acc = acc.get("raw") or {}
            last_equity = float(raw_acc.get("last_equity") or 100000.0)
            daily_diff_usd = port_val - last_equity
            daily_diff_pct = ((port_val - last_equity) / last_equity * 100.0) if last_equity > 0 else 0.0
            
            # Açık pozisyonlar ve anlık kâr/zarar toplamı
            positions = alpaca.get_positions()
            open_pos_count = len(positions)
            unrealized_total_usd = sum(float(p.get("unrealized_pl", 0.0) or 0.0) for p in positions)
            
            rate_try = 48.0
            try:
                from exchange import get_live_usd_try_rate
                live_r = get_live_usd_try_rate()
                if live_r > 0: rate_try = live_r
            except Exception:
                pass
                
            tot_try = port_val * rate_try
            daily_diff_try = daily_diff_usd * rate_try
            
            pnl_sign = "+" if daily_diff_usd >= 0 else ""
            pnl_emoji = "🟢" if daily_diff_usd >= 0 else "🔴"
            
            unreal_sign = "+" if unrealized_total_usd >= 0 else ""
            unreal_emoji = "📈" if unrealized_total_usd >= 0 else "📉"
            
            bal_msg = (
                "💼 *ALPACA HESAP VE PORTFÖY DURUMU*\n\n"
                f"💵 *Toplam Portföy Değeri:* `${port_val:,.2f} USD` (~₺{tot_try:,.2f} TL)\n"
                f"🟢 *Kullanılabilir Serbest Nakit:* `${cash_val:,.2f} USD`\n"
                f"🚀 *Gün İçi Alım Gücü (4x):* `${power_val:,.2f} USD`\n\n"
                f"━━━━━━━━━━━━━━━━━━━━\n"
                f"{pnl_emoji} *GÜNLÜK NET KÂR / ZARAR (PnL):*\n"
                f"• Net Değişim: *{pnl_sign}${daily_diff_usd:,.2f} USD* ({pnl_sign}₺{daily_diff_try:,.2f} TL)\n"
                f"• Getiri Oranı: *{pnl_sign}%{daily_diff_pct:.2f}*\n"
                f"━━━━━━━━━━━━━━━━━━━━\n"
                f"{unreal_emoji} *AÇIK POZİSYONLAR DURUMU ({open_pos_count} Hisse):*\n"
                f"• Canlı Açık Kâr/Zarar: *{unreal_sign}${unrealized_total_usd:,.2f} USD*\n"
                f"━━━━━━━━━━━━━━━━━━━━\n"
                f"🏢 *Aracı Kurum:* Alpaca Securities LLC\n"
                f"🧪 *Hesap Modu:* `{'Paper Sandbox ($100K)' if is_p else 'Live Real Trading'}`\n"
                f"🟢 *Hesap Durumu:* `ACTIVE (İşleme Açık)` ✅"
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

    # 5. Küresel Piyasa Radarı
    elif "küresel" in text_lower or "radar" in text_lower or text_lower == "/kuresel":
        from global_market_radar import GlobalMarketRadar
        radar = GlobalMarketRadar(alpaca)
        g = radar.evaluate_global_sentiment()
        d = g.get("details", {})
        asia = d.get("asia", {})
        europe = d.get("europe", {})
        us = d.get("us_futures", {})
        
        radar_msg = (
            "🌍 *KÜRESEL PİYASA VE ÖNCÜ SEANS RADARI*\n\n"
            f"🧭 *Küresel Makro Skor:* `{g.get('global_macro_score')}/10`\n"
            f"📊 *Piyasa Rejimi:* {g.get('badge')}\n\n"
            f"🇯🇵 *1. Asya Seansı (Tokyo & TSMC):* {asia.get('status')}\n"
            f"  • Nikkei (EWJ): `${asia.get('ewj_price', 0):.2f}` ({asia.get('ewj_change_pct', 0):+.2f}%)\n"
            f"  • TSMC Çip (TSM): `${asia.get('tsm_price', 0):.2f}` ({asia.get('tsm_change_pct', 0):+.2f}%)\n\n"
            f"🇬🇧 *2. Avrupa Seansı (DAX & FTSE):* {europe.get('status')}\n"
            f"  • Almanya DAX (EWG): `${europe.get('ewg_price', 0):.2f}` ({europe.get('ewg_change_pct', 0):+.2f}%)\n"
            f"  • Londra FTSE (EWU): `${europe.get('ewu_price', 0):.2f}` ({europe.get('ewu_change_pct', 0):+.2f}%)\n\n"
            f"🇺🇸 *3. ABD Ön Piyasa (Futures):* {us.get('status')}\n"
            f"  • S&P 500 (SPY): `${us.get('spy_price', 0):.2f}` ({us.get('spy_change_pct', 0):+.2f}%)\n"
            f"  • Nasdaq 100 (QQQ): `${us.get('qqq_price', 0):.2f}` ({us.get('qqq_change_pct', 0):+.2f}%)\n\n"
            f"💡 *Tavsiye:* _{g.get('advice')}_"
        )
        send_stock_telegram_message(chat_id, radar_msg)

    # 6. Seans Durumu
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

    # 7. Panel Linki
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
    print("[@FoxBorsaBot]: Telegram Dinleyicisi Aktif Edildi!", flush=True)
    while _poller_running:
        try:
            base_url = _get_base_url()
            if not base_url or "bot" == base_url.split("/")[-1]:
                time.sleep(5)
                continue
            url = f"{base_url}/getUpdates?offset={offset}&timeout=10"
            res = requests.get(url, timeout=15)
            if res.status_code == 200:
                data = res.json()
                updates = data.get("result", [])
                for u in updates:
                    offset = u["update_id"] + 1
                    msg = u.get("message")
                    if msg:
                        try:
                            handle_stock_message(msg)
                        except Exception as msg_err:
                            pass
            elif res.status_code == 409:
                time.sleep(5)
            else:
                time.sleep(2)
        except Exception:
            time.sleep(3)

def start_stock_telegram_poller():
    """Fox Borsa Telegram Poller dongusunu arka planda baslatir."""
    global _poller_thread, _poller_running
    if _poller_thread and _poller_thread.is_alive():
        return
    _poller_running = True
    _poller_thread = threading.Thread(target=_run_stock_poller_loop, daemon=True)
    _poller_thread.start()

if __name__ == "__main__":
    print("[@FoxBorsaBot]: Standalone Poller Baslatiliyor...", flush=True)
    _poller_running = True
    _run_stock_poller_loop()
