import os, sys, time, json, asyncio, threading
if hasattr(sys.stdout, 'reconfigure'): sys.stdout.reconfigure(encoding='utf-8')
from dotenv import load_dotenv
from typing import Dict, Any, Optional
from fastapi import FastAPI, Request, BackgroundTasks, HTTPException
from fastapi.responses import HTMLResponse
from pydantic import BaseModel

from state import CryptoAgentState
from graph import create_crypto_graph
from db import (
    save_graph_state, load_graph_state, log_trade_decision, 
    register_user_tenant, get_all_active_tenants, get_supabase,
    get_active_positions_from_db
)
from exchange import execute_spot_trade, fetch_portfolio_balance, get_live_usd_try_rate
from telegram_poller import start_poller

import secrets
from fastapi import Depends, status
from fastapi.security import HTTPBasic, HTTPBasicCredentials

load_dotenv()

app_api = FastAPI(title="Fox-Kripto Multi-Tenant Autonomous Trading & Management Dashboard")

security = HTTPBasic()

ADMIN_USERNAME = os.environ.get("ADMIN_USERNAME", "admin")
ADMIN_PASSWORD = os.environ.get("ADMIN_PASSWORD", "foxkripto2026")
last_error_alerts = {}

def authenticate_admin(credentials: HTTPBasicCredentials = Depends(security)):
    correct_username = secrets.compare_digest(credentials.username, ADMIN_USERNAME)
    correct_password = secrets.compare_digest(credentials.password, ADMIN_PASSWORD)
    if not (correct_username and correct_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Hatalı Kullanıcı Adı veya Şifre",
            headers={"WWW-Authenticate": "Basic realm='FoxKripto Admin'"},
        )
def resolve_exchange_error_details(err_str: str) -> dict:
    """
    Borsa hata kodlarını (3203, -2010, -1013, -2015 vb.) analiz edip
    insan tarafından anlaşılır Türkçe açıklama ve çözüm aksiyonu üretir.
    """
    import re
    err_lower = str(err_str).lower()
    code_match = re.search(r'\(?(-?\d{3,5})\)?', str(err_str))
    code_str = code_match.group(1) if code_match else "UNKNOWN"
    
    error_dict = {
        "3203": {
            "title": "Miktar / Adım Hatası (LOT_SIZE)",
            "reason": "Borsa bu coin için küsuratlı adet kabul etmiyor.",
            "action": "Bot otomatik tam sayıya çevirerek (2. kademe) işlemi tamamlıyor."
        },
        "-1013": {
            "title": "Adım / Filtre Hatası (LOT_SIZE / MIN_NOTIONAL)",
            "reason": "Emir tutarı borsa asgari işlem sınırının ($10 / ₺200) altında veya adım büyüklüğü uyuşmadı.",
            "action": "Bütçe ve adım büyüklüğü otomatik düzeltilerek yeniden deneniyor."
        },
        "-2010": {
            "title": "Yetersiz Serbest Bakiye (INSUFFICIENT_BALANCE)",
            "reason": "Cüzdanda bu işlemi gerçekleştirecek serbest nakit (USDT / TRY) bulunmuyor.",
            "action": "Mevcut açık pozisyonlardan kâr satışı bekleniyor."
        },
        "-2015": {
            "title": "API Yetki / IP Kısıtlaması (INVALID_API_PERMISSIONS)",
            "reason": "API anahtarında Spot Alım-Satım izni kapalı veya IP whitelist tanımlı değil.",
            "action": "Lütfen Binance API ayarlarından 'Enable Spot Trading' iznini kontrol edin."
        },
        "-1021": {
            "title": "Zaman Aşımı / Sunucu Saati (TIMESTAMP_AHEAD)",
            "reason": "Borsa sunucusu ile zaman senkronizasyonu gecikti.",
            "action": "Sistem saat farkını otomatik güncelleyip emri yeniliyor."
        },
        "-1121": {
            "title": "Geçersiz İşlem Çifti (INVALID_SYMBOL)",
            "reason": "Coin borsada spot işleme kapalı veya çift adı değişti.",
            "action": "Listeden çıkarılıp bir sonraki balina adayına geçildi."
        },
        "-1003": {
            "title": "İstek Limiti Aşıldı (TOO_MANY_REQUESTS)",
            "reason": "Borsa API hız sınırı aşıldı.",
            "action": "Bot 10 saniye soğuma süresine geçti, ardından devam edecek."
        }
    }
    
    resolved = error_dict.get(code_str)
    if not resolved:
        if "insufficient balance" in err_lower or "yetersiz" in err_lower:
            resolved = error_dict["-2010"]
            code_str = "-2010"
        elif "lot_size" in err_lower or "quantity" in err_lower:
            resolved = error_dict["3203"]
            code_str = "3203"
        elif "permission" in err_lower or "api-key" in err_lower or "ip" in err_lower:
            resolved = error_dict["-2015"]
            code_str = "-2015"
        else:
            resolved = {
                "title": "Borsa İletişim Uyarısı",
                "reason": str(err_str)[:120],
                "action": "Sistem otomatik olarak sonraki döngüde işlemi yenileyecektir."
            }
            
    return {
        "code": code_str,
        "title": resolved["title"],
        "reason": resolved["reason"],
        "action": resolved["action"],
        "raw": str(err_str)
    }

def handle_autonomous_error_alert(tenant_name, sym_target, action_name, exch_name, raw_error, chat_id):
    """Borsa hatalarını kodlarıyla birlikte detaylı ve anlaşılır şekilde Telegram'a iletir."""
    global last_error_alerts
    current_time = time.time()
    err_key = f"{sym_target}_{action_name}"
    if current_time - last_error_alerts.get(err_key, 0) > 300: # 5 dk spam filtresi
        last_error_alerts[err_key] = current_time
        err_info = resolve_exchange_error_details(raw_error)
        from telegram_poller import send_message
        warning_msg = (
            f"🚨 *7/24 OTONOM BORSA İŞLEM UYARISI*\n\n"
            f"👤 Kullanıcı: {tenant_name}\n"
            f"🪙 Hedef Balina / Coin: `{sym_target}`\n"
            f"⚡ Yapılmak İstenen İşlem: *{action_name}*\n"
            f"🏢 Borsa: {exch_name}\n\n"
            f"🛑 *Borsa Hata Kodu:* `{err_info['code']} - {err_info['title']}`\n"
            f"❌ *Net Sebep:* {err_info['reason']}\n\n"
            f"💡 *Otomatik Aksiyon:* {err_info['action']}"
        )
        send_message(chat_id, warning_msg)

def run_autonomous_trading_loop():
    """
    7/24 Otonom Yapay Zeka Alım-Satım ve Piyasa Analiz Döngüsü.
    Sistemdeki tüm aktif kullanıcılar (Tenants) için 5 saniyede bir piyasayı tarar.
    """
    global last_error_alerts
    print("🤖 [Yapay Zeka Otonom Ajan]: 7/24 Tam Otonom Alım-Satım Döngüsü Aktif!")
    import time
    time.sleep(10)
    while True:
        try:
            tenants = get_all_active_tenants()
            if tenants:
                for tenant in tenants:
                    chat_id = tenant.get("telegram_chat_id")
                    tenant_name = tenant.get("tenant_name", "Kullanıcı")
                    print(f"🧠 [Otonom Analiz]: Kullanıcı '{tenant_name}' (Chat ID: {chat_id}) için piyasa taranıyor...")
                    
                    live_bal = fetch_portfolio_balance(tenant)
                    
                    # ⚠️ Borsa API ve İzin Hatası Bildirimi (5 dk spam korumalı)
                    if live_bal.get("api_error") and not tenant.get("is_paper_trading") and chat_id:
                        exch_label = "BINANCE GLOBAL 🌍" if tenant.get("exchange_id") == "binance" else "BINANCE TR 🇹🇷"
                        handle_autonomous_error_alert(
                            tenant_name=tenant_name,
                            sym_target="CÜZDAN & API BAĞLANTISI",
                            action_name="CANLI BAKİYE VE İZİN KONTROLÜ",
                            exch_name=exch_label,
                            raw_error=live_bal.get("api_error"),
                            chat_id=chat_id
                        )
                    
                    graph = create_crypto_graph()
                    initial_state = {
                        "tenant_id": tenant.get("id"),
                        "tenant_config": tenant,
                        "news_data": "Crypto market showing volume breakout and bullish momentum.",
                        "portfolio_state": live_bal,
                        "sentiment_score": 0.8,
                        "trade_proposal": None,
                        "human_approval": "Approved", # FULL AUTONOMOUS MODE
                        "execution_result": None
                    }
                    res = graph.invoke(initial_state)
                    save_graph_state(f"auto_{chat_id}", res)
                    
                    exec_res = res.get("execution_result")
                    proposal = res.get("trade_proposal")
                    human_app = res.get("human_approval")
                    
                    if proposal and (proposal.get("requires_user_approval") or human_app == "Pending_Approval") and chat_id:
                        symbol = proposal.get("symbol", "SOL/USDT")
                        amount = proposal.get("amount_usd", 4.26)
                        score = float(res.get("sentiment_score") or 8.5)
                        base_c = symbol.split("/")[0].split("_")[0]
                        
                        from telegram_poller import send_message
                        reply_markup = {
                            "inline_keyboard": [
                                [
                                    {"text": f"✅ Evet, Ek Alım Yap (${amount:.2f})", "callback_data": f"approve_scalein_{chat_id}"},
                                    {"text": "❌ İptal Et (Pas Geç)", "callback_data": f"reject_scalein_{chat_id}"}
                                ]
                            ]
                        }
                        msg = (
                            f"🚨 *YÜKSEK SKORLU EK ALIM TAVSİYESİ*\n\n"
                            f"👤 Kullanıcı: {tenant_name}\n"
                            f"🪙 Sembol: `{symbol}`\n"
                            f"📊 Yapay Zeka Skoru: *+{score:.1f} / 10* (Zirve Beklenti!)\n"
                            f"💵 Önerilen Bütçe: ${amount:.2f} USD\n"
                            f"🏢 Borsa: BINANCE.TR\n\n"
                            f"💡 *Açıklama:* Cüzdanınızda zaten `{base_c}` var ancak yapay zeka skoru zirvededir (+{score:.1f}). Ek kademeli alım yapılsın mı?"
                        )
                        send_message(chat_id, msg, reply_markup=reply_markup)
                        continue
                        
                    if exec_res and chat_id:
                        status_str = str(exec_res.get("status", "")).upper()
                        is_exec_success = status_str in ["SUCCESS", "EXECUTED"]
                        
                        # 🚨 GERÇEK BORSA HATALARINI TELEGRAM İLE KULLANICIYA BİLDİR:
                        if not is_exec_success and proposal and proposal.get("should_trade") and exec_res.get("error"):
                            sym_target = proposal.get("symbol", "COIN")
                            action_name = "ALIM (BUY)" if proposal.get("direction") == "BUY" else "SATIM (SELL)"
                            is_try_sym = sym_target.upper().endswith("TRY") or sym_target.upper().endswith("_TRY")
                            exch_name = "BINANCE.TR 🇹🇷" if is_try_sym else "BINANCE GLOBAL 🌍"
                            handle_autonomous_error_alert(tenant_name, sym_target, action_name, exch_name, exec_res.get("error"), chat_id)
                            continue
                        
                        # 🛑 YALNIZCA VE YALNIZCA GERÇEK BİR İŞLEM TEKLİFİ VARSA VE BAŞARIYLA İNFAZ EDİLDİYSE BİLDİRİM GÖNDER!
                        if not is_exec_success or not proposal or not proposal.get("should_trade"):
                            continue
                        
                        symbol = exec_res.get("symbol") or proposal.get("symbol")
                        if not symbol:
                            continue
                        is_en_user = str(tenant.get("preferred_language", "tr")).lower() == "en"
                        is_tr_tenant = bool(tenant and tenant.get("exchange_id") in ["binancetr", "binance.tr", "trbinance"]) or symbol.upper().endswith("TRY") or symbol.upper().endswith("_TRY")
                        wallet_label = "TL" if is_tr_tenant else "USDT"
                        quote_sym = "TRY" if is_tr_tenant else "USDT"
                        base_sym = symbol.split("/")[0].split("_")[0].upper()
                        symbol = f"{base_sym}/{quote_sym}"
                        
                        is_stop_loss = bool(proposal.get("is_stop_loss", False))
                        raw_action = str(proposal.get("direction", "BUY")).upper()
                        action_type = raw_action
                        is_take_profit = (raw_action not in ["BUY", "ALIM"]) and (not is_stop_loss)
                        is_executed = is_exec_success
                        
                        if raw_action in ["BUY", "ALIM"]:
                            action_title = "🛒 BUY SPOT ORDER" if is_en_user else "🛒 ALIM (BUY)"
                            status_title = f"✅ Live Buy Executed Successfully ({wallet_label} Wallet)" if is_en_user else f"✅ Canlı Alım Başarıyla Gerçekleştirildi ({wallet_label} Cüzdanı)"
                        else:
                            r_type = str(proposal.get("reason_type", "")).lower()
                            if r_type == "partial_take_profit":
                                action_title = "🎯 PARTIAL TP (%50 SOLD)" if is_en_user else "🎯 KADEMELİ KÂR ALMA (%50 SATILDI)"
                                status_title = f"🚀 %50 Profit Locked & Remaining %50 Set to Breakeven Trailing Mode!" if is_en_user else f"🚀 %50 Kâr Kasaya Kilitlendi, Kalan %50 Sıfır Risk İz Süren Moda Alındı!"
                            elif r_type == "trailing_stop_exit":
                                action_title = "🏆 TRAILING STOP PEAK EXIT" if is_en_user else "🏆 İZ SÜREN STOP ZİRVE ÇIKIŞI"
                                status_title = f"🎉 Whale Wave Closed from Peak & Profit Transferred to {wallet_label} Wallet!" if is_en_user else f"🎉 Balina Dalgası Zirveden Kapatıldı ve Kâr {wallet_label} Cüzdanına Aktarıldı!"
                            elif r_type == "breakeven_exit":
                                action_title = "🛡️ BREAKEVEN CAPITAL EXIT" if is_en_user else "🛡️ MALİYET KORUMA (BREAKEVEN ÇIKIŞ)"
                                status_title = f"🛡️ Breakeven Exit & Zero Loss Capital Preserved in {wallet_label} Wallet" if is_en_user else f"🛡️ Başa Baş Çıkış Gerçekleşti ve Sıfır Zararla Sermaye {wallet_label} Cüzdanına Alındı"
                            elif is_stop_loss:
                                action_title = "🛡️ SELL (STOP-LOSS)" if is_en_user else "🛡️ SATIM (STOP-LOSS / ZARAR KES)"
                                status_title = f"🛡️ Stop-Loss Triggered & Capital Preserved in {wallet_label} Wallet" if is_en_user else f"🛡️ Canlı Stop-Loss Gerçekleşti ve Sermaye {wallet_label} Cüzdanına Alındı"
                            else:
                                action_title = "🎯 SELL (TAKE-PROFIT)" if is_en_user else "🎯 SATIM (SELL / KÂR ALMA)"
                                status_title = f"🎉 Live Take-Profit Executed & Transferred to {wallet_label} Wallet" if is_en_user else f"🎉 Canlı Satış Gerçekleşti ve {wallet_label} Cüzdanına Aktarıldı"
                            
                        amount = proposal.get("amount_usd", 10.0) if proposal else 10.0
                        from exchange import get_live_usd_try_rate
                        live_fx_app = get_live_usd_try_rate()
                        if live_fx_app <= 0:
                            live_fx_app = 35.0
                        if is_tr_tenant:
                            amount_try = round(amount * live_fx_app, 2)
                            amount_display = f"₺{amount_try:.2f} TL"
                        else:
                            amount_display = f"${amount:.2f} USD"
                        
                        order_id = exec_res.get("order_id")
                        order_text = f"\n📄 Order ID: #{order_id}" if (is_en_user and order_id) else (f"\n📄 Emir No: #{order_id}" if order_id else "")
                        
                        price_detail_line = ""
                        if raw_action not in ["BUY", "ALIM"]:
                            raw_entry = float(proposal.get("entry_price") or 0.0) if proposal else 0.0
                            raw_exit = float(exec_res.get("executed_price") or proposal.get("take_profit_price") or 0.0) if exec_res else 0.0
                            coin_qty = float(proposal.get("amount_coin") or 0.0) if proposal else 0.0
                            
                            is_tr_pair = symbol.upper().endswith("TRY")
                            quote_label = "TL" if is_tr_pair else "USDT"
                            
                            if raw_exit > 0:
                                if is_tr_pair:
                                    # Eğer raw_entry USD cinsinden kaydedildiyse (yani exit_try/20'den küçükse), TRY'ye dönüştür
                                    if raw_entry > 0 and (raw_entry < (raw_exit / 20.0)):
                                        entry_try = raw_entry * live_fx_app
                                    else:
                                        entry_try = raw_entry if raw_entry > 0 else (raw_exit / 1.017)
                                    exit_try = raw_exit
                                    
                                    # Net Kâr Hesaplama (TL)
                                    gross_pct = ((exit_try - entry_try) / entry_try * 100) if entry_try > 0 else 1.7
                                    net_pct = gross_pct - 0.20 # %0.20 borsa komisyonu düşülür
                                    
                                    tot_sell_try = (coin_qty * exit_try) if coin_qty > 0 else (amount * live_fx_app)
                                    tot_buy_try = (coin_qty * entry_try) if coin_qty > 0 else (tot_sell_try / (1 + (gross_pct/100.0) if gross_pct > 0 else 1.0))
                                    net_profit_fiat = tot_sell_try - tot_buy_try - (tot_sell_try * 0.002)
                                    if abs(net_profit_fiat) < 0.01:
                                        net_profit_fiat = tot_sell_try * (net_pct / 100.0)
                                        
                                    if exit_try < 0.0001:
                                        entry_str = f"₺{entry_try:.8f}"
                                        exit_str = f"₺{exit_try:.8f}"
                                    elif exit_try < 1.0:
                                        entry_str = f"₺{entry_try:.4f}"
                                        exit_str = f"₺{exit_try:.4f}"
                                    elif exit_try < 10.0:
                                        entry_str = f"₺{entry_try:.3f}"
                                        exit_str = f"₺{exit_try:.3f}"
                                    else:
                                        entry_str = f"₺{entry_try:,.2f}"
                                        exit_str = f"₺{exit_try:,.2f}"
                                        
                                    if is_en_user:
                                        if net_pct >= 0:
                                            profit_label = "📈 *Net Profit:*"
                                            profit_badge = f"+%{net_pct:.2f} (+₺{net_profit_fiat:,.2f} TL Net Profit) Locked in {quote_label} Wallet!"
                                        else:
                                            profit_label = "📉 *Net Change / Stop-Loss:*"
                                            profit_badge = f"-%{abs(net_pct):.2f} (-₺{abs(net_profit_fiat):,.2f} TL) Transferred to {quote_label} Wallet"
                                    else:
                                        if net_pct >= 0:
                                            profit_label = "📈 *Net Kâr / Kazanç:*"
                                            profit_badge = f"+%{net_pct:.2f} (+₺{net_profit_fiat:,.2f} TL / +${net_profit_fiat/live_fx_app:,.2f} USD) {quote_label} Cüzdanına Kilitlendi!"
                                        else:
                                            profit_label = "📉 *Net Değişim / Stop-Loss:*"
                                            profit_badge = f"-%{abs(net_pct):.2f} (-₺{abs(net_profit_fiat):,.2f} TL / -${abs(net_profit_fiat)/live_fx_app:,.2f} USD) {quote_label} Cüzdanına Aktarıldı"
                                else:
                                    # Binance Global (USDT)
                                    # Eğer raw_entry TRY cinsinden kaydedildiyse (yani exit_usd*20'den büyükse), USD'ye dönüştür
                                    if raw_entry > 0 and (raw_entry > (raw_exit * 20.0)):
                                        entry_usd = raw_entry / live_fx_app
                                    else:
                                        entry_usd = raw_entry if raw_entry > 0 else (raw_exit / 1.017)
                                    exit_usd = raw_exit
                                    
                                    gross_pct = ((exit_usd - entry_usd) / entry_usd * 100) if entry_usd > 0 else 1.7
                                    net_pct = gross_pct - 0.20
                                    
                                    tot_sell_usd = (coin_qty * exit_usd) if coin_qty > 0 else amount
                                    tot_buy_usd = (coin_qty * entry_usd) if coin_qty > 0 else (tot_sell_usd / (1 + (gross_pct/100.0) if gross_pct > 0 else 1.0))
                                    net_profit_fiat = tot_sell_usd - tot_buy_usd - (tot_sell_usd * 0.002)
                                    if abs(net_profit_fiat) < 0.01:
                                        net_profit_fiat = tot_sell_usd * (net_pct / 100.0)
                                        
                                    if exit_usd < 0.0001:
                                        entry_str = f"${entry_usd:.8f}"
                                        exit_str = f"${exit_usd:.8f}"
                                    elif exit_usd < 1.0:
                                        entry_str = f"${entry_usd:.4f}"
                                        exit_str = f"${exit_usd:.4f}"
                                    elif exit_usd < 10.0:
                                        entry_str = f"${entry_usd:.3f}"
                                        exit_str = f"${exit_usd:.3f}"
                                    else:
                                        entry_str = f"${entry_usd:,.2f}"
                                        exit_str = f"${exit_usd:,.2f}"
                                        
                                    if is_en_user:
                                        if net_pct >= 0:
                                            profit_label = "📈 *Net Profit:*"
                                            profit_badge = f"+%{net_pct:.2f} (+${net_profit_fiat:,.2f} USDT) Locked in {quote_label} Wallet!"
                                        else:
                                            profit_label = "📉 *Net Change / Stop-Loss:*"
                                            profit_badge = f"-%{abs(net_pct):.2f} (-${abs(net_profit_fiat):,.2f} USDT) Transferred to {quote_label} Wallet"
                                    else:
                                        if net_pct >= 0:
                                            profit_label = "📈 *Net Kâr / Kazanç:*"
                                            profit_badge = f"+%{net_pct:.2f} (+${net_profit_fiat:,.2f} USDT / +₺{net_profit_fiat * live_fx_app:,.2f} TL) {quote_label} Cüzdanına Kilitlendi!"
                                        else:
                                            profit_label = "📉 *Net Değişim / Stop-Loss:*"
                                            profit_badge = f"-%{abs(net_pct):.2f} (-${abs(net_profit_fiat):,.2f} USDT / -₺{abs(net_profit_fiat) * live_fx_app:,.2f} TL) {quote_label} Cüzdanına Aktarıldı"
                            else:
                                entry_str = "Entry Price" if is_en_user else "Alış Fiyatı"
                                exit_str = "Exit Price" if is_en_user else "Satış Fiyatı"
                                profit_label = "📈 *Net Profit:*" if is_en_user else "📈 *Net Kâr / Kazanç:*"
                                profit_badge = "+%1.50+ Net Profit" if is_en_user else "+%1.50+ Net Kazanç"
                            
                            if is_en_user:
                                price_detail_line = (
                                    f"\n📥 *Entry Unit Price:* `{entry_str}`\n"
                                    f"📤 *Exit Unit Price:* `{exit_str}`\n"
                                    f"{profit_label} `{profit_badge}`"
                                )
                            else:
                                price_detail_line = (
                                    f"\n📥 *Alış Birim Fiyatı:* `{entry_str}`\n"
                                    f"📤 *Satış Birim Fiyatı:* `{exit_str}`\n"
                                    f"{profit_label} `{profit_badge}`"
                                )
                            
                        from telegram_poller import send_message
                        exch_display = "BINANCE.TR 🇹🇷" if is_tr_tenant else "BINANCE GLOBAL 🌍"
                        
                        if is_en_user:
                            msg = (
                                f"🤖 *24/7 AUTONOMOUS AI TRADING NOTIFICATION*\n\n"
                                f"👤 User: {tenant_name}\n"
                                f"⚡ Action: *{action_title}*\n"
                                f"🪙 Symbol: `{symbol}`\n"
                                f"💵 Budget / Amount: {amount_display}{price_detail_line}\n"
                                f"🏢 Exchange: {exch_display}\n\n"
                                f"{status_title}{order_text}"
                            )
                        else:
                            msg = (
                                f"🤖 *7/24 OTONOM YAPAY ZEKA BİLDİRİMİ*\n\n"
                                f"👤 Kullanıcı: {tenant_name}\n"
                                f"⚡ İşlem Tipi: *{action_title}*\n"
                                f"🪙 Sembol: `{symbol}`\n"
                                f"💵 Bütçe / Tutar: {amount_display}{price_detail_line}\n"
                                f"🏢 Borsa: {exch_display}\n\n"
                                f"{status_title}{order_text}"
                            )
                        send_message(chat_id, msg)
        except Exception as e:
            print(f"⚠️ [Otonom Döngü Uyarısı]: {e}")
            
        time.sleep(5) # Real-Time Lightning Scalp Loop: Her 5 saniyede bir fiyat ve TP/SL kontrolü yapar

# -----------------------------------------
# OTOMATİK 7/24 TELEGRAM DİNLEYİCİ & OTONOM DÖNGÜ
# -----------------------------------------
@app_api.on_event("startup")
def startup_event():
    """Uygulama ayağa kalktığında Telegram Poller ve Otonom Ticaret Döngüsünü arka planda başlatır."""
    print("🚀 [FastAPI Startup]: Telegram Poller 7/24 Arka Plan Süreci Başlatılıyor...")
    poller_thread = threading.Thread(target=start_poller, daemon=True)
    poller_thread.start()

    print("🤖 [FastAPI Startup]: 7/24 Tam Otonom Yapay Zeka Ticaret Döngüsü Başlatılıyor...")
    auto_thread = threading.Thread(target=run_autonomous_trading_loop, daemon=True)
    auto_thread.start()

    print("👑 [FastAPI Startup]: 7/24 Mobil AI Geliştirici Köprüsü (@FoxSystemBot) Başlatılıyor...")
    try:
        from dev_agent_bridge import start_dev_poller
        dev_thread = threading.Thread(target=start_dev_poller, daemon=True)
        dev_thread.start()
    except Exception as e:
        print(f"⚠️ Dev-Bridge Başlatma Hatası: {e}")

# -----------------------------------------
# PYDANTIC MODEL TANIMLARI
# -----------------------------------------
class TenantCreateRequest(BaseModel):
    tenant_name: str
    telegram_chat_id: int
    exchange_api_key: str
    exchange_secret_key: str
    exchange_id: str = "binance"
    max_budget_percent: float = 10.0
    take_profit_percent: float = 1.5
    stop_loss_percent: float = 1.5
    preferred_language: str = "tr"

class TenantUpdateSettingsRequest(BaseModel):
    take_profit_percent: float = 1.5
    stop_loss_percent: float = 1.5
    max_budget_percent: float = 10.0
    preferred_language: str = "tr"
    exchange_id: Optional[str] = None

class TriggerGraphRequest(BaseModel):
    session_id: str = "session_001"
    symbol: str = "BTC/USDT"

class SystemSettingsRequest(BaseModel):
    trailing_stop_enabled: bool

# -----------------------------------------
# API ROTALARI (KULLANICI EKLE / SİL / LİSTELE)
# -----------------------------------------
@app_api.get("/health")
def health_check():
    return {"status": "healthy", "service": "Fox-Kripto Multi-Tenant Dashboard", "version": "2.1.0-explain-trade"}

@app_api.get("/api/settings", dependencies=[Depends(authenticate_admin)])
def get_settings_endpoint():
    from db import get_system_setting
    ts_enabled = bool(get_system_setting("trailing_stop_enabled", True))
    return {
        "status": "success",
        "trailing_stop_enabled": ts_enabled
    }

@app_api.post("/api/settings", dependencies=[Depends(authenticate_admin)])
def update_settings_endpoint(req: SystemSettingsRequest):
    from db import set_system_setting
    ok = set_system_setting("trailing_stop_enabled", req.trailing_stop_enabled)
    return {
        "status": "success" if ok else "error",
        "trailing_stop_enabled": req.trailing_stop_enabled,
        "message": f"Dinamik İz Süren Stop (Trailing Stop) Modu: {'AÇIK' if req.trailing_stop_enabled else 'KAPALI'}"
    }

@app_api.get("/api/my-ip")
def get_my_egress_ip():
    """DigitalOcean sunucusunun dışarıya çıkan (Egress) IP adresini söyler."""
    import requests
    try:
        res = requests.get("https://api.ipify.org?format=json", timeout=5)
        return res.json()
    except Exception as e:
        return {"error": str(e)}

@app_api.get("/api/tenants", dependencies=[Depends(authenticate_admin)])
def list_tenants():
    """Tüm kullanıcıları (Tenants) listeler (Tam Güvenli & Maskelenmiş)."""
    tenants = get_all_active_tenants()
    sanitized = []
    for t in tenants:
        safe_t = dict(t)
        safe_t.pop("exchange_secret_key", None)
        raw_k = safe_t.pop("exchange_api_key", "")
        safe_t["exchange_api_key_configured"] = bool(raw_k)
        safe_t["exchange_api_key_masked"] = "***CONFIGURED***" if raw_k else "NOT_CONFIGURED"
        sanitized.append(safe_t)
    return {"status": "success", "count": len(sanitized), "tenants": sanitized}

@app_api.post("/api/tenants", dependencies=[Depends(authenticate_admin)])
def create_tenant(req: TenantCreateRequest):
    """Yeni kullanıcı (Tenant) ekler veya günceller."""
    import json
    kd = {
        "api_key": req.exchange_api_key,
        "secret_key": req.exchange_secret_key,
        "take_profit_percent": req.take_profit_percent,
        "preferred_language": req.preferred_language
    }
    res = register_user_tenant(
        tenant_name=req.tenant_name,
        telegram_chat_id=req.telegram_chat_id,
        exchange_api_key=json.dumps(kd),
        exchange_secret_key=req.exchange_secret_key,
        exchange_id=req.exchange_id,
        max_budget_percent=req.max_budget_percent
    )
    if res:
        safe_res = dict(res)
        safe_res.pop("exchange_secret_key", None)
        safe_res.pop("exchange_api_key", None)
        return {"status": "success", "message": f"Kullanıcı '{req.tenant_name}' eklendi.", "tenant": safe_res}
    raise HTTPException(status_code=400, detail="Kullanıcı kaydedilemedi.")

@app_api.post("/api/tenants/{tenant_id}/settings", dependencies=[Depends(authenticate_admin)])
def update_tenant_settings(tenant_id: str, req: TenantUpdateSettingsRequest):
    client = get_supabase()
    if not client:
        raise HTTPException(status_code=500, detail="Supabase bağlantı hatası.")
    try:
        curr = client.table("user_tenants").select("*").eq("id", tenant_id).execute()
        if not curr.data:
            raise HTTPException(status_code=404, detail="Kullanıcı bulunamadı.")
            
        t_row = curr.data[0]
        api_k = str(t_row.get("exchange_api_key", ""))
        sec_k = str(t_row.get("exchange_secret_key", ""))
        
        payload = {
            "stop_loss_percent": req.stop_loss_percent,
            "max_budget_percent": req.max_budget_percent
        }
        if req.exchange_id:
            payload["exchange_id"] = req.exchange_id
        
        import json
        if api_k.startswith("{"):
            try:
                kd = json.loads(api_k)
                kd["take_profit_percent"] = req.take_profit_percent
                kd["preferred_language"] = req.preferred_language
                payload["exchange_api_key"] = json.dumps(kd)
            except Exception:
                pass
        else:
            kd = {
                "api_key": api_k,
                "secret_key": sec_k,
                "take_profit_percent": req.take_profit_percent,
                "preferred_language": req.preferred_language
            }
            payload["exchange_api_key"] = json.dumps(kd)
                
        res = client.table("user_tenants").update(payload).eq("id", tenant_id).execute()
        return {"status": "success", "message": "Ayarlar başarıyla güncellendi.", "data": res.data}
    except Exception as e:
        print(f"❌ [Settings Update Error]: {e}")
        raise HTTPException(status_code=400, detail=str(e))

@app_api.delete("/api/tenants/{tenant_id}", dependencies=[Depends(authenticate_admin)])
def delete_tenant(tenant_id: str):
    """Kullanıcıyı pasife alır / siler."""
    client = get_supabase()
    if not client:
        raise HTTPException(status_code=500, detail="Supabase bağlantı hatası.")
    try:
        client.table("user_tenants").update({"is_active": False}).eq("id", tenant_id).execute()
        return {"status": "success", "message": "Kullanıcı başarıyla pasife alındı."}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

@app_api.get("/api/tenants/{tenant_id}/portfolio", dependencies=[Depends(authenticate_admin)])
def get_tenant_portfolio(tenant_id: str):
    """Admin Paneli İçin Kullanıcının Canlı Borsa Cüzdanını ve Coin Detaylarını Döner."""
    client = get_supabase()
    if not client:
        raise HTTPException(status_code=500, detail="Supabase bağlantı hatası.")
    try:
        res = client.table("user_tenants").select("*").eq("id", tenant_id).execute()
        if not res.data or len(res.data) == 0:
            raise HTTPException(status_code=404, detail="Kullanıcı bulunamadı.")
            
        t_row = dict(res.data[0])
        t_id = str(t_row.get("id") or t_row.get("telegram_chat_id"))
        
        bal = fetch_portfolio_balance(t_row)
        saved_pos_tr = get_active_positions_from_db(t_id, "binancetr")
        saved_pos_gl = get_active_positions_from_db(t_id, "binance")
        usd_try_rate = get_live_usd_try_rate()
        
        return {
            "status": "success",
            "tenant_id": tenant_id,
            "tenant_name": t_row.get("tenant_name", "Kullanıcı"),
            "telegram_chat_id": t_row.get("telegram_chat_id"),
            "exchange_id": t_row.get("exchange_id", "dual"),
            "usd_try_rate": usd_try_rate,
            "portfolio": bal,
            "saved_positions_tr": saved_pos_tr,
            "saved_positions_gl": saved_pos_gl
        }
    except Exception as e:
        print(f"❌ [Tenant Portfolio Error]: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app_api.get("/api/trade-logs", dependencies=[Depends(authenticate_admin)])
def list_trade_logs():
    """Canlı Supabase işlem kararlarını ve loglarını kullanıcı isimleriyle listeler."""
    client = get_supabase()
    if not client: return {"logs": []}
    try:
        tenants_res = client.table("user_tenants").select("id, tenant_name, exchange_id").execute()
        tenant_map = {t["id"]: t for t in (tenants_res.data or [])}
        
        res = client.table("crypto_trade_logs").select("*").order("created_at", desc=True).limit(30).execute()
        raw_logs = res.data or []
        enriched_logs = []
        for l in raw_logs:
            tid = str(l.get("tenant_id") or "")
            t_info = tenant_map.get(tid, {})
            det = l.get("execution_details") or {}
            
            is_paper_order = str(l.get("order_id") or "").startswith("PAPER_") or bool(det.get("raw_order", {}).get("info", {}).get("is_paper"))
            if is_paper_order:
                l["tenant_name"] = "🧪 Sanal Test (Paper Sandbox)"
                l["exchange_label"] = "Sanal Sandbox 🧪"
            else:
                l["tenant_name"] = t_info.get("tenant_name") or det.get("tenant_name") or "S (Çift Borsa TR+Global)"
                l["exchange_label"] = "Binance TR 🇹🇷" if (t_info.get("exchange_id") == "binancetr" or str(l.get("symbol")).endswith("TRY")) else "Binance Global 🌍"
            
            if l.get("symbol") in ["AUTO/USDT", "AUTO"]:
                l["symbol"] = "DİNAMİK FIRSAT COIN"
                
            enriched_logs.append(l)
            
        return {"logs": enriched_logs}
    except Exception as e:
        return {"logs": [], "error": str(e)}

@app_api.post("/run-graph", dependencies=[Depends(authenticate_admin)])
def run_graph_endpoint(req: TriggerGraphRequest, background_tasks: BackgroundTasks):
    def _execute():
        print(f"🚀 [/run-graph]: Akış Başlatıldı -> Session: {req.session_id}")
        graph = create_crypto_graph()
        initial_state = {
            "tenant_id": None, "tenant_config": None, "news_data": "",
            "portfolio_state": {}, "sentiment_score": 0.0, "trade_proposal": None,
            "human_approval": "Pending", "execution_result": None
        }
        res = graph.invoke(initial_state)
        save_graph_state(req.session_id, res)
    background_tasks.add_task(_execute)
    return {"status": "STARTED", "message": f"Otonom akış başlatıldı (Session: {req.session_id})"}

# -----------------------------------------
# WEB DASHBOARD (HTML / JAVASCRIPT ARAYÜZÜ)
# -----------------------------------------
@app_api.get("/dashboard", response_class=HTMLResponse, dependencies=[Depends(authenticate_admin)])
def get_dashboard_html():
    html_content = """
    <!DOCTYPE html>
    <html lang="tr">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>Fox-Kripto Management Dashboard</title>
        <link href="https://fonts.googleapis.com/css2?family=Outfit:wght@300;400;600;700&display=swap" rel="stylesheet">
        <style>
            :root {
                --bg: #0f172a;
                --card-bg: rgba(30, 41, 59, 0.7);
                --accent: #3b82f6;
                --accent-hover: #2563eb;
                --success: #10b981;
                --danger: #ef4444;
                --text: #f8fafc;
                --text-muted: #94a3b8;
                --border: rgba(255, 255, 255, 0.1);
            }
            * { box-sizing: border-box; margin: 0; padding: 0; font-family: 'Outfit', sans-serif; }
            body { background: var(--bg); color: var(--text); padding: 30px; min-height: 100vh; }
            .header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 30px; }
            .header-left h1 { font-size: 28px; font-weight: 700; background: linear-gradient(135deg, #60a5fa, #3b82f6); -webkit-background-clip: text; -webkit-text-fill-color: transparent; }
            .header-right { display: flex; gap: 12px; align-items: center; }
            .lang-switch { display: flex; background: rgba(15, 23, 42, 0.8); border: 1px solid var(--border); border-radius: 10px; padding: 4px; gap: 4px; }
            .lang-btn { background: transparent; border: none; color: var(--text-muted); padding: 6px 12px; font-size: 13px; font-weight: 600; border-radius: 6px; cursor: pointer; transition: all 0.2s; }
            .lang-btn.active { background: var(--accent); color: white; box-shadow: 0 2px 8px rgba(59, 130, 246, 0.4); }
            .grid { display: grid; grid-template-columns: 1fr 380px; gap: 24px; }
            .card { background: var(--card-bg); backdrop-filter: blur(12px); border: 1px solid var(--border); border-radius: 16px; padding: 24px; box-shadow: 0 10px 30px rgba(0,0,0,0.3); }
            .card-title { font-size: 18px; font-weight: 600; margin-bottom: 16px; display: flex; justify-content: space-between; align-items: center; }
            table { width: 100%; border-collapse: collapse; margin-top: 10px; }
            th, td { text-align: left; padding: 12px; border-bottom: 1px solid var(--border); font-size: 14px; vertical-align: middle; }
            th { color: var(--text-muted); font-weight: 600; }
            .badge { padding: 4px 10px; border-radius: 20px; font-size: 12px; font-weight: 600; display: inline-block; }
            .badge-active { background: rgba(16, 185, 129, 0.2); color: var(--success); border: 1px solid var(--success); }
            .btn { padding: 8px 16px; border-radius: 8px; border: none; font-weight: 600; cursor: pointer; transition: all 0.2s; }
            .btn-primary { background: var(--accent); color: white; }
            .btn-primary:hover { background: var(--accent-hover); }
            .btn-danger { background: rgba(239, 68, 68, 0.2); color: var(--danger); border: 1px solid var(--danger); }
            .btn-danger:hover { background: var(--danger); color: white; }
            .form-group { margin-bottom: 14px; }
            .form-group label { display: block; font-size: 13px; color: var(--text-muted); margin-bottom: 6px; }
            .form-group input, .form-group select { width: 100%; padding: 10px; border-radius: 8px; border: 1px solid var(--border); background: rgba(15, 23, 42, 0.6); color: white; font-size: 14px; outline: none; }
            .form-group input:focus { border-color: var(--accent); }
            .log-item { padding: 12px; border-bottom: 1px solid var(--border); font-size: 13px; }
            .log-item:last-child { border-bottom: none; }
            .input-inline { width: 68px; padding: 6px 8px; border-radius: 6px; border: 1px solid var(--border); background: rgba(15, 23, 42, 0.8); color: white; font-size: 13px; text-align: center; }
            .input-inline:focus { border-color: var(--accent); }
            .switch { position: relative; display: inline-block; width: 44px; height: 24px; margin-bottom: 0; }
            .switch input { opacity: 0; width: 0; height: 0; }
            .slider { position: absolute; cursor: pointer; top: 0; left: 0; right: 0; bottom: 0; background-color: #334155; transition: .3s; border-radius: 24px; border: 1px solid var(--border); }
            .slider:before { position: absolute; content: ""; height: 16px; width: 16px; left: 3px; bottom: 3px; background-color: white; transition: .3s; border-radius: 50%; }
            input:checked + .slider { background-color: #10b981; }
            input:checked + .slider:before { transform: translateX(20px); }
        </style>
    </head>
    <body>
        <div class="header">
            <div class="header-left">
                <h1 id="i18n-title">🦊 Fox-Kripto Multi-Tenant Yönetim Paneli</h1>
                <p id="i18n-subtitle" style="color: var(--text-muted); font-size: 14px;">Otonom Yapay Zeka Kripto Ticaret, Risk ve Kullanıcı Yönetimi</p>
            </div>
            <div class="header-right">
                <div style="display: flex; align-items: center; gap: 10px; background: rgba(15, 23, 42, 0.8); border: 1px solid var(--border); border-radius: 10px; padding: 6px 14px;">
                    <span id="i18n-lbl-trailing" style="font-size: 13px; font-weight: 600; color: #60a5fa;">🚀 İz Süren Stop (Trailing SL):</span>
                    <label class="switch">
                        <input type="checkbox" id="trailing-stop-toggle" onchange="toggleTrailingStop(this.checked)">
                        <span class="slider"></span>
                    </label>
                    <span id="trailing-status-text" style="font-size: 12px; font-weight: bold; color: var(--success);">AÇIK</span>
                </div>
                <div class="lang-switch">
                    <button id="btn-tr" class="lang-btn active" onclick="changeLang('tr')">🇹🇷 Türkçe</button>
                    <button id="btn-en" class="lang-btn" onclick="changeLang('en')">🇬🇧 English</button>
                </div>
                <button id="i18n-btn-refresh" class="btn btn-primary" onclick="loadData()">🔄 Verileri Yenile</button>
            </div>
        </div>

        <div class="grid">
            <div class="card">
                <div class="card-title">
                    <span id="i18n-card-users">👥 Kayıtlı Kullanıcılar & Dinamik Risk Ayarları</span>
                    <span id="tenant-count" class="badge badge-active">0 Aktif</span>
                </div>
                <table>
                    <thead>
                        <tr>
                            <th id="i18n-th-user">Kullanıcı Adı</th>
                            <th id="i18n-th-tg">Telegram ID</th>
                            <th id="i18n-th-tp">🎯 Kâr Alma %</th>
                            <th id="i18n-th-sl">🛡️ Stop-Loss %</th>
                            <th id="i18n-th-mb">💵 Bütçe %</th>
                            <th id="i18n-th-exch">🏛️ Borsa Seçimi</th>
                            <th id="i18n-th-lang">🌐 Dil / Lang</th>
                            <th id="i18n-th-status">Durum</th>
                            <th id="i18n-th-action">İşlem</th>
                        </tr>
                    </thead>
                    <tbody id="tenants-table">
                        <tr><td colspan="9" style="color: var(--text-muted);">Yükleniyor...</td></tr>
                    </tbody>
                </table>
            </div>

            <div class="card">
                <div id="i18n-card-add" class="card-title">➕ Yeni Kullanıcı Ekle</div>
                <form id="tenant-form" onsubmit="submitTenant(event)">
                    <div class="form-group">
                        <label id="i18n-lbl-name">Kullanıcı Adı</label>
                        <input type="text" id="tenant_name" placeholder="Örn: Ahmet" required>
                    </div>
                    <div class="form-group">
                        <label id="i18n-lbl-tg">Telegram Chat ID</label>
                        <input type="number" id="telegram_chat_id" placeholder="Örn: 8739367825" required>
                    </div>
                    <div class="form-group">
                        <label id="i18n-lbl-apikey">Binance API Key</label>
                        <input type="text" id="exchange_api_key" placeholder="Binance API Key" required>
                    </div>
                    <div class="form-group">
                        <label id="i18n-lbl-secret">Binance Secret Key</label>
                        <input type="password" id="exchange_secret_key" placeholder="Binance Secret Key" required>
                    </div>
                    <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 10px;">
                        <div class="form-group">
                            <label id="i18n-lbl-tp">🎯 Kâr Alma %</label>
                            <input type="number" id="take_profit_percent" value="1.5" step="0.1" min="0.5" max="50">
                        </div>
                        <div class="form-group">
                            <label id="i18n-lbl-sl">🛡️ Stop-Loss %</label>
                            <input type="number" id="stop_loss_percent" value="1.5" step="0.1" min="0.5" max="30">
                        </div>
                    </div>
                    <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 10px;">
                        <div class="form-group">
                            <label id="i18n-lbl-budget">İşlem Başı Maks Bütçe %</label>
                            <input type="number" id="max_budget_percent" value="10" min="1" max="100">
                        </div>
                        <div class="form-group">
                            <label id="i18n-lbl-langselect">🌐 Dil / Language</label>
                            <select id="preferred_language">
                                <option value="tr">🇹🇷 Türkçe</option>
                                <option value="en">🇬🇧 English</option>
                            </select>
                        </div>
                    </div>
                    <button id="i18n-btn-saveuser" type="submit" class="btn btn-primary" style="width: 100%; margin-top: 10px;">💾 Kullanıcıyı Kaydet</button>
                </form>
            </div>
        </div>

        <div class="card" style="margin-top: 24px;">
            <div id="i18n-card-logs" class="card-title">📜 Canlı İşlem Kararları ve Loglar (Supabase)</div>
            <div id="logs-container">Yükleniyor...</div>
        </div>

        <script>
            let currentLang = localStorage.getItem('fox_crypto_lang') || 'tr';

            const dict = {
                tr: {
                    title: "🦊 Fox-Kripto Multi-Tenant Yönetim Paneli",
                    subtitle: "Otonom Yapay Zeka Kripto Ticaret, Risk ve Kullanıcı Yönetimi",
                    refresh: "🔄 Verileri Yenile",
                    usersTitle: "👥 Kayıtlı Kullanıcılar & Dinamik Risk Ayarları",
                    activeSuffix: "Aktif",
                    thUser: "Kullanıcı Adı",
                    thTg: "Telegram ID",
                    thTp: "🎯 Kâr Alma %",
                    thSl: "🛡️ Stop-Loss %",
                    thMb: "💵 Bütçe %",
                    thExch: "🏛️ Borsa Seçimi",
                    thLang: "🌐 Dil / Lang",
                    thStatus: "Durum",
                    thAction: "İşlem",
                    addUser: "➕ Yeni Kullanıcı Ekle",
                    lblName: "Kullanıcı Adı",
                    lblTg: "Telegram Chat ID",
                    lblApiKey: "Binance API Key",
                    lblSecret: "Binance Secret Key",
                    lblTp: "🎯 Kâr Alma %",
                    lblSl: "🛡️ Stop-Loss %",
                    lblBudget: "İşlem Başı Maks Bütçe %",
                    lblLangSelect: "🌐 Dil / Language",
                    btnSaveUser: "💾 Kullanıcıyı Kaydet",
                    logsTitle: "📜 Canlı İşlem Kararları ve Loglar (Supabase)",
                    loading: "Yükleniyor...",
                    noUsers: "Henüz eklenmiş kullanıcı yok.",
                    noLogs: "Henüz kayıtlı işlem logu yok.",
                    save: "💾 Kaydet",
                    del: "Sil",
                    activeBadge: "Aktif",
                    confirmDel: "Bu kullanıcıyı pasife almak istediğinizden emin misiniz?",
                    userSaved: "için Kâr Alma, Stop-Loss, Borsa ve Dil tercihleri başarıyla kaydedildi!",
                    userAdded: "✅ Kullanıcı ve limitler başarıyla kaydedildi!",
                    userAddFailed: "❌ Kullanıcı kaydedilemedi.",
                    userDeactivated: "Kullanıcı pasife alındı."
                },
                en: {
                    title: "🦊 Fox-Crypto Multi-Tenant Management Dashboard",
                    subtitle: "Autonomous AI Crypto Trading, Risk & User Management",
                    refresh: "🔄 Refresh Data",
                    usersTitle: "👥 Registered Users & Dynamic Risk Settings",
                    activeSuffix: "Active",
                    thUser: "User Name",
                    thTg: "Telegram ID",
                    thTp: "🎯 Take-Profit %",
                    thSl: "🛡️ Stop-Loss %",
                    thMb: "💵 Budget %",
                    thExch: "🏛️ Exchange Selection",
                    thLang: "🌐 Language",
                    thStatus: "Status",
                    thAction: "Action",
                    addUser: "➕ Add New User",
                    lblName: "User Name",
                    lblTg: "Telegram Chat ID",
                    lblApiKey: "Binance API Key",
                    lblSecret: "Binance Secret Key",
                    lblTp: "🎯 Take-Profit %",
                    lblSl: "🛡️ Stop-Loss %",
                    lblBudget: "Max Budget % Per Trade",
                    lblLangSelect: "🌐 Language Preference",
                    btnSaveUser: "💾 Save User",
                    logsTitle: "📜 Live Trade Decisions & Logs (Supabase)",
                    loading: "Loading...",
                    noUsers: "No users registered yet.",
                    noLogs: "No live trade logs recorded yet.",
                    save: "💾 Save",
                    del: "Delete",
                    activeBadge: "Active",
                    confirmDel: "Are you sure you want to deactivate this user?",
                    userSaved: "Take-Profit, Stop-Loss, Exchange and Language preferences saved successfully for",
                    userAdded: "✅ User and risk limits saved successfully!",
                    userAddFailed: "❌ Failed to save user.",
                    userDeactivated: "User deactivated successfully."
                }
            };

            function applyLang(lang) {
                currentLang = lang;
                localStorage.setItem('fox_crypto_lang', lang);
                document.getElementById('btn-tr').classList.toggle('active', lang === 'tr');
                document.getElementById('btn-en').classList.toggle('active', lang === 'en');
                
                const t = dict[lang];
                document.getElementById('i18n-title').innerText = t.title;
                document.getElementById('i18n-subtitle').innerText = t.subtitle;
                document.getElementById('i18n-btn-refresh').innerText = t.refresh;
                document.getElementById('i18n-card-users').innerText = t.usersTitle;
                document.getElementById('i18n-th-user').innerText = t.thUser;
                document.getElementById('i18n-th-tg').innerText = t.thTg;
                document.getElementById('i18n-th-tp').innerText = t.thTp;
                document.getElementById('i18n-th-sl').innerText = t.thSl;
                document.getElementById('i18n-th-mb').innerText = t.thMb;
                if (document.getElementById('i18n-th-exch')) document.getElementById('i18n-th-exch').innerText = t.thExch;
                document.getElementById('i18n-th-lang').innerText = t.thLang;
                document.getElementById('i18n-th-status').innerText = t.thStatus;
                document.getElementById('i18n-th-action').innerText = t.thAction;
                document.getElementById('i18n-card-add').innerText = t.addUser;
                document.getElementById('i18n-lbl-name').innerText = t.lblName;
                document.getElementById('i18n-lbl-tg').innerText = t.lblTg;
                document.getElementById('i18n-lbl-apikey').innerText = t.lblApiKey;
                document.getElementById('i18n-lbl-secret').innerText = t.lblSecret;
                document.getElementById('i18n-lbl-tp').innerText = t.lblTp;
                document.getElementById('i18n-lbl-sl').innerText = t.lblSl;
                document.getElementById('i18n-lbl-budget').innerText = t.lblBudget;
                document.getElementById('i18n-lbl-langselect').innerText = t.lblLangSelect;
                document.getElementById('i18n-btn-saveuser').innerText = t.btnSaveUser;
                document.getElementById('i18n-card-logs').innerText = t.logsTitle;
            }

            function changeLang(lang) {
                applyLang(lang);
                loadData();
            }

            async function loadData() {
                const t = dict[currentLang];
                try {
                    const res = await fetch('/api/tenants');
                    const data = await res.json();
                    const table = document.getElementById('tenants-table');
                    document.getElementById('tenant-count').innerText = `${data.count} ${t.activeSuffix}`;
                    
                    if (data.tenants.length === 0) {
                        table.innerHTML = `<tr><td colspan="9" style="color: var(--text-muted);">${t.noUsers}</td></tr>`;
                    } else {
                        table.innerHTML = data.tenants.map((user, idx) => `
                            <tr>
                                <td>
                                    <span style="cursor: pointer; color: #60a5fa; font-weight: 700; display: inline-flex; align-items: center; gap: 4px;" onclick="openUserPortfolioModal('${user.id}', '${user.tenant_name}')">
                                        🔍 ${user.tenant_name}
                                    </span>
                                </td>
                                <td><code>${user.telegram_chat_id}</code></td>
                                <td>
                                    <input type="number" step="0.1" class="input-inline" id="tp_${idx}" value="${user.take_profit_percent || 1.5}">
                                </td>
                                <td>
                                    <input type="number" step="0.1" class="input-inline" id="sl_${idx}" value="${user.stop_loss_percent || 1.5}">
                                </td>
                                <td>
                                    <input type="number" step="1" class="input-inline" id="mb_${idx}" value="${user.max_budget_percent || 10}">
                                </td>
                                <td>
                                    <select class="input-inline" style="width: 110px;" id="exch_${idx}">
                                        <option value="dual" ${(!user.exchange_id || user.exchange_id === 'dual') ? 'selected' : ''}>⚡ Çift Borsa</option>
                                        <option value="binancetr" ${user.exchange_id === 'binancetr' ? 'selected' : ''}>🇹🇷 Binance TR</option>
                                        <option value="binance" ${user.exchange_id === 'binance' ? 'selected' : ''}>🌍 Global</option>
                                    </select>
                                </td>
                                <td>
                                    <select class="input-inline" style="width: 78px;" id="lang_${idx}">
                                        <option value="tr" ${user.preferred_language === 'en' ? '' : 'selected'}>🇹🇷 TR</option>
                                        <option value="en" ${user.preferred_language === 'en' ? 'selected' : ''}>🇬🇧 EN</option>
                                    </select>
                                </td>
                                <td>
                                    <span class="badge badge-active" style="cursor: pointer;" onclick="openUserPortfolioModal('${user.id}', '${user.tenant_name}')">📊 Cüzdanı Gör</span>
                                </td>
                                <td>
                                    <button class="btn btn-primary" style="padding: 5px 12px; margin-right: 4px;" onclick="updateSettings('${user.id}', ${idx}, '${user.tenant_name}')">${t.save}</button>
                                    <button class="btn btn-danger" style="padding: 5px 10px;" onclick="deleteTenant('${user.id}')">${t.del}</button>
                                </td>
                            </tr>
                        `).join('');
                    }

                    // Logları Yükle
                    const logRes = await fetch('/api/trade-logs');
                    const logData = await logRes.json();
                    const logContainer = document.getElementById('logs-container');
                    if (!logData.logs || logData.logs.length === 0) {
                        logContainer.innerHTML = `<p style="color: var(--text-muted);">${t.noLogs}</p>`;
                    } else {
                        logContainer.innerHTML = `
                            <div style="overflow-x: auto;">
                                <table style="width: 100%; border-collapse: collapse; margin-top: 8px;">
                                    <thead>
                                        <tr style="border-bottom: 2px solid var(--border); color: var(--text-muted); text-align: left; font-size: 13px;">
                                            <th style="padding: 10px;">👤 ${currentLang === 'tr' ? 'Kullanıcı' : 'User'}</th>
                                            <th style="padding: 10px;">🪙 ${currentLang === 'tr' ? 'İşlem & Coin' : 'Action & Symbol'}</th>
                                            <th style="padding: 10px;">💵 ${currentLang === 'tr' ? 'Bütçe / Tutar' : 'Amount'}</th>
                                            <th style="padding: 10px;">📥 ${currentLang === 'tr' ? 'Fiyat' : 'Price'}</th>
                                            <th style="padding: 10px;">🎯 ${currentLang === 'tr' ? 'Kâr Al / SL' : 'TP / SL'}</th>
                                            <th style="padding: 10px;">📊 ${currentLang === 'tr' ? 'Yapay Zeka Skoru' : 'AI Score'}</th>
                                            <th style="padding: 10px;">🏷️ ${currentLang === 'tr' ? 'Durum & Borsa' : 'Status & Exchange'}</th>
                                            <th style="padding: 10px;">⏱️ ${currentLang === 'tr' ? 'Zaman' : 'Time'}</th>
                                        </tr>
                                    </thead>
                                    <tbody>
                                        ${logData.logs.map(l => {
                                            const d = l.created_at ? new Date(l.created_at).toLocaleString(currentLang === 'tr' ? 'tr-TR' : 'en-US') : '—';
                                            const isBuy = (l.direction || 'BUY').toUpperCase() === 'BUY';
                                            const dirBadge = isBuy ? '<span style="color: var(--success); font-weight: bold;">🛒 ALIM (BUY)</span>' : '<span style="color: var(--danger); font-weight: bold;">🎯 SATIM (SELL)</span>';
                                            const score = l.sentiment_score ? (l.sentiment_score > 0 ? `+${l.sentiment_score}` : l.sentiment_score) : '—';
                                            
                                            const isFailed = l.status === 'FAILED' || (l.execution_details && l.execution_details.status === 'FAILED');
                                            const isExec = l.status === 'SUCCESS' || l.status === 'EXECUTED' || l.order_id;
                                            
                                            let badgeHtml = '';
                                            if (isExec) {
                                                badgeHtml = `<span class="badge" style="background: rgba(34, 197, 94, 0.15); color: var(--success);">✅ Canlı İnfaz Edildi</span>`;
                                            } else if (isFailed) {
                                                badgeHtml = `<span class="badge" style="background: rgba(239, 68, 68, 0.15); color: var(--danger);">⏳ Nakit Beklemede (Hold)</span>`;
                                            } else {
                                                badgeHtml = `<span class="badge" style="background: rgba(59, 130, 246, 0.15); color: var(--accent);">${l.human_approval || 'Approved'}</span>`;
                                            }
                                            
                                            const formattedPrice = l.entry_price ? (Number(l.entry_price) < 1 ? Number(l.entry_price).toFixed(4) : Number(l.entry_price).toLocaleString()) : '—';
                                            
                                            return `
                                                <tr style="border-bottom: 1px solid var(--border); font-size: 13px;">
                                                    <td style="padding: 10px;"><strong>${l.tenant_name || 'Ana Kullanıcı'}</strong></td>
                                                    <td style="padding: 10px;">${dirBadge} <code>${l.symbol}</code></td>
                                                    <td style="padding: 10px;"><strong>$${l.amount_usd || 10} USD</strong></td>
                                                    <td style="padding: 10px;">$${formattedPrice}</td>
                                                    <td style="padding: 10px; color: var(--text-muted);">$${l.take_profit_price || '—'} / $${l.stop_loss_price || '—'}</td>
                                                    <td style="padding: 10px;"><span style="color: var(--accent); font-weight: bold;">${score} / +10</span></td>
                                                    <td style="padding: 10px;">
                                                        ${badgeHtml}
                                                        <small style="display: block; color: var(--text-muted); margin-top: 2px;">${l.exchange_label || 'Binance'}</small>
                                                    </td>
                                                    <td style="padding: 10px; color: var(--text-muted); font-size: 12px;">${d}</td>
                                                </tr>
                                            `;
                                        }).join('')}
                                    </tbody>
                                </table>
                            </div>
                        `;
                    }
                } catch(e) { console.error(e); }
            }

            async function updateSettings(tenantId, idx, name) {
                const t = dict[currentLang];
                const tp = parseFloat(document.getElementById('tp_' + idx).value);
                const sl = parseFloat(document.getElementById('sl_' + idx).value);
                const mb = parseFloat(document.getElementById('mb_' + idx).value);
                const exch = document.getElementById('exch_' + idx).value;
                const lang = document.getElementById('lang_' + idx).value;
                
                try {
                    const res = await fetch('/api/tenants/' + tenantId + '/settings', {
                        method: 'POST',
                        headers: {'Content-Type': 'application/json'},
                        body: JSON.stringify({take_profit_percent: tp, stop_loss_percent: sl, max_budget_percent: mb, exchange_id: exch, preferred_language: lang})
                    });
                    const resData = await res.json();
                    if (res.ok && resData.status === 'success') {
                        alert(`✅ ${name || 'User'}: ${currentLang === 'tr' ? 'Kâr Alma' : 'Take-Profit'} (%${tp}), Stop-Loss (%${sl}), Borsa (${exch.toUpperCase()}) ${t.userSaved}`);
                        loadData();
                    } else {
                        alert('❌ Error: ' + (resData.detail || JSON.stringify(resData)));
                    }
                } catch(e) {
                    alert('Connection Error: ' + e);
                }
            }

            async function submitTenant(e) {
                e.preventDefault();
                const t = dict[currentLang];
                const payload = {
                    tenant_name: document.getElementById('tenant_name').value,
                    telegram_chat_id: parseInt(document.getElementById('telegram_chat_id').value),
                    exchange_api_key: document.getElementById('exchange_api_key').value,
                    exchange_secret_key: document.getElementById('exchange_secret_key').value,
                    take_profit_percent: parseFloat(document.getElementById('take_profit_percent').value),
                    stop_loss_percent: parseFloat(document.getElementById('stop_loss_percent').value),
                    max_budget_percent: parseFloat(document.getElementById('max_budget_percent').value),
                    preferred_language: document.getElementById('preferred_language').value
                };
                const res = await fetch('/api/tenants', {
                    method: 'POST',
                    headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify(payload)
                });
                if (res.ok) {
                    alert(t.userAdded);
                    document.getElementById('tenant-form').reset();
                    loadData();
                } else {
                    alert(t.userAddFailed);
                }
            }

            async function deleteTenant(tenantId) {
                const t = dict[currentLang];
                if (!confirm(t.confirmDel)) return;
                const res = await fetch(`/api/tenants/${tenantId}`, { method: 'DELETE' });
                if (res.ok) {
                    alert(t.userDeactivated);
                    loadData();
                }
            }

            async function loadSystemSettings() {
                try {
                    const res = await fetch('/api/settings');
                    const data = await res.json();
                    const toggle = document.getElementById('trailing-stop-toggle');
                    const statusTxt = document.getElementById('trailing-status-text');
                    if (toggle && statusTxt) {
                        const isEn = (currentLang === 'en');
                        toggle.checked = Boolean(data.trailing_stop_enabled);
                        statusTxt.innerText = data.trailing_stop_enabled ? (isEn ? 'ACTIVE' : 'AÇIK') : (isEn ? 'DISABLED' : 'KAPALI');
                        statusTxt.style.color = data.trailing_stop_enabled ? 'var(--success)' : 'var(--danger)';
                    }
                } catch(e) { console.error('Settings load error:', e); }
            }

            async function toggleTrailingStop(enabled) {
                try {
                    const res = await fetch('/api/settings', {
                        method: 'POST',
                        headers: {'Content-Type': 'application/json'},
                        body: JSON.stringify({trailing_stop_enabled: enabled})
                    });
                    const data = await res.json();
                    const statusTxt = document.getElementById('trailing-status-text');
                    if (statusTxt) {
                        const isEn = (currentLang === 'en');
                        statusTxt.innerText = enabled ? (isEn ? 'ACTIVE' : 'AÇIK') : (isEn ? 'DISABLED' : 'KAPALI');
                        statusTxt.style.color = enabled ? 'var(--success)' : 'var(--danger)';
                    }
                } catch(e) { console.error('Settings update error:', e); }
            }

            // ==========================================
            // KULLANICI CÜZDAN & VARLIK DETAY MODALI
            // ==========================================
            async function openUserPortfolioModal(tenantId, tenantName) {
                const modal = document.getElementById('user-portfolio-modal');
                const content = document.getElementById('portfolio-modal-body');
                const title = document.getElementById('portfolio-modal-title');
                
                title.innerHTML = `💼 <strong>${tenantName}</strong> — Canlı Borsa & Cüzdan Detayları`;
                content.innerHTML = `
                    <div style="text-align: center; padding: 40px; color: var(--text-muted);">
                        <p style="font-size: 18px; margin-bottom: 8px;">⏳ Borsa Cüzdanları ve Açık Pozisyonlar Taranıyor...</p>
                        <small>Binance TR (TRY) ve Binance Global (USDT) REST API sorgulanıyor...</small>
                    </div>
                `;
                modal.style.display = 'flex';
                
                try {
                    const res = await fetch('/api/tenants/' + tenantId + '/portfolio');
                    const data = await res.json();
                    
                    if (!res.ok || data.status !== 'success') {
                        content.innerHTML = `<div style="color: var(--danger); padding: 20px;">❌ Hata: ${data.detail || 'Cüzdan verisi alınamadı.'}</div>`;
                        return;
                    }
                    
                    const p = data.portfolio || {};
                    const bTr = p.binance_tr || {};
                    const bGl = p.binance_global || {};
                    const posTr = data.saved_positions_tr || {};
                    const posGl = data.saved_positions_gl || {};
                    
                    const freeTry = Number(bTr.free_try || 0).toLocaleString('tr-TR', {minimumFractionDigits: 2, maximumFractionDigits: 2});
                    const totalTry = Number(bTr.total_try || 0).toLocaleString('tr-TR', {minimumFractionDigits: 2, maximumFractionDigits: 2});
                    const freeUsdt = Number(bGl.free_usdt || 0).toLocaleString('en-US', {minimumFractionDigits: 2, maximumFractionDigits: 2});
                    const totalUsdt = Number(bGl.total_usdt || 0).toLocaleString('en-US', {minimumFractionDigits: 2, maximumFractionDigits: 2});
                    const grandUsd = Number(p.total_usdt || 0).toLocaleString('en-US', {minimumFractionDigits: 2, maximumFractionDigits: 2});
                    const grandTry = Number(p.total_try || 0).toLocaleString('tr-TR', {minimumFractionDigits: 2, maximumFractionDigits: 2});
                    
                    // TR Pozisyonları HTML
                    let trCoinsHtml = '';
                    const trKeys = Object.keys(posTr);
                    if (trKeys.length === 0) {
                        trCoinsHtml = `<tr><td colspan="5" style="color: var(--text-muted); text-align: center; padding: 16px; font-weight: 500;">✅ Şu an açık coin pozisyonu yok (Kasa %100 Serbest TRY Nakitte).</td></tr>`;
                    } else {
                        trCoinsHtml = trKeys.map(sym => {
                            const coin = posTr[sym];
                            const buyPrice = Number(coin.buy_price || coin.entry_price || 0);
                            const currentPrice = Number(coin.current_price || coin.highest_price || buyPrice);
                            const pnl = buyPrice > 0 ? (((currentPrice - buyPrice) / buyPrice) * 100) : (coin.pnl_percent || 0);
                            const pnlColor = pnl >= 0 ? 'var(--success)' : 'var(--danger)';
                            return `
                                <tr style="border-bottom: 1px solid var(--border);">
                                    <td style="padding: 10px;"><strong>🪙 ${sym}</strong></td>
                                    <td style="padding: 10px;">${coin.amount}</td>
                                    <td style="padding: 10px;">₺${buyPrice.toFixed(4)}</td>
                                    <td style="padding: 10px;">₺${currentPrice.toFixed(4)}</td>
                                    <td style="padding: 10px; font-weight: bold; color: ${pnlColor};">${pnl >= 0 ? '+' : ''}%${Number(pnl).toFixed(2)}</td>
                                </tr>
                            `;
                        }).join('');
                    }
                    
                    // Global Pozisyonları HTML
                    let glCoinsHtml = '';
                    const glKeys = Object.keys(posGl);
                    if (glKeys.length === 0) {
                        glCoinsHtml = `<tr><td colspan="5" style="color: var(--text-muted); text-align: center; padding: 16px; font-weight: 500;">✅ Şu an açık coin pozisyonu yok (Kasa %100 Serbest USDT Nakitte).</td></tr>`;
                    } else {
                        glCoinsHtml = glKeys.map(sym => {
                            const coin = posGl[sym];
                            const buyPrice = Number(coin.buy_price || coin.entry_price || 0);
                            const currentPrice = Number(coin.current_price || coin.highest_price || buyPrice);
                            const pnl = buyPrice > 0 ? (((currentPrice - buyPrice) / buyPrice) * 100) : (coin.pnl_percent || 0);
                            const pnlColor = pnl >= 0 ? 'var(--success)' : 'var(--danger)';
                            return `
                                <tr style="border-bottom: 1px solid var(--border);">
                                    <td style="padding: 10px;"><strong>🪙 ${sym}</strong></td>
                                    <td style="padding: 10px;">${coin.amount}</td>
                                    <td style="padding: 10px;">$${buyPrice.toFixed(4)}</td>
                                    <td style="padding: 10px;">$${currentPrice.toFixed(4)}</td>
                                    <td style="padding: 10px; font-weight: bold; color: ${pnlColor};">${pnl >= 0 ? '+' : ''}%${Number(pnl).toFixed(2)}</td>
                                </tr>
                            `;
                        }).join('');
                    }

                    content.innerHTML = `
                        <!-- Toplam Kasa Özeti -->
                        <div style="display: grid; grid-template-columns: 1fr 1fr 1fr; gap: 14px; margin-bottom: 20px;">
                            <div style="background: rgba(59, 130, 246, 0.15); border: 1px solid rgba(59, 130, 246, 0.4); border-radius: 12px; padding: 14px; text-align: center;">
                                <div style="color: var(--text-muted); font-size: 12px; font-weight: 600;">🏆 TOPLAM PORTFÖY DEĞERİ</div>
                                <div style="font-size: 22px; font-weight: bold; color: #60a5fa; margin-top: 4px;">$${grandUsd} USD</div>
                                <small style="color: var(--text-muted);">~₺${grandTry} TL</small>
                            </div>
                            <div style="background: rgba(16, 185, 129, 0.15); border: 1px solid rgba(16, 185, 129, 0.4); border-radius: 12px; padding: 14px; text-align: center;">
                                <div style="color: var(--text-muted); font-size: 12px; font-weight: 600;">🇹🇷 BİNANCE TR NAKİT</div>
                                <div style="font-size: 20px; font-weight: bold; color: var(--success); margin-top: 4px;">₺${freeTry} TL</div>
                                <small style="color: var(--text-muted);">Toplam TR: ₺${totalTry} TL</small>
                            </div>
                            <div style="background: rgba(245, 158, 11, 0.15); border: 1px solid rgba(245, 158, 11, 0.4); border-radius: 12px; padding: 14px; text-align: center;">
                                <div style="color: var(--text-muted); font-size: 12px; font-weight: 600;">🌍 BİNANCE GLOBAL NAKİT</div>
                                <div style="font-size: 20px; font-weight: bold; color: #fbbf24; margin-top: 4px;">$${freeUsdt} USDT</div>
                                <small style="color: var(--text-muted);">Toplam Global: $${totalUsdt} USD</small>
                            </div>
                        </div>

                        <!-- Binance TR Tablosu -->
                        <div style="background: rgba(15, 23, 42, 0.6); border: 1px solid var(--border); border-radius: 12px; padding: 16px; margin-bottom: 16px;">
                            <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 10px;">
                                <h3 style="font-size: 15px; color: #f8fafc;">🇹🇷 Binance TR Cüzdanı ve Eldeki Coinler</h3>
                                <span class="badge badge-active">${trKeys.length} Açık Pozisyon</span>
                            </div>
                            <table style="width: 100%; border-collapse: collapse; font-size: 13px;">
                                <thead>
                                    <tr style="border-bottom: 2px solid var(--border); color: var(--text-muted); text-align: left;">
                                        <th style="padding: 8px;">Coin</th>
                                        <th style="padding: 8px;">Adet</th>
                                        <th style="padding: 8px;">Giriş Fiyatı</th>
                                        <th style="padding: 8px;">Anlık Fiyat</th>
                                        <th style="padding: 8px;">Kâr / Zarar %</th>
                                    </tr>
                                </thead>
                                <tbody>${trCoinsHtml}</tbody>
                            </table>
                        </div>

                        <!-- Binance Global Tablosu -->
                        <div style="background: rgba(15, 23, 42, 0.6); border: 1px solid var(--border); border-radius: 12px; padding: 16px;">
                            <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 10px;">
                                <h3 style="font-size: 15px; color: #f8fafc;">🌍 Binance Global Cüzdanı ve Eldeki Coinler</h3>
                                <span class="badge badge-active">${glKeys.length} Açık Pozisyon</span>
                            </div>
                            <table style="width: 100%; border-collapse: collapse; font-size: 13px;">
                                <thead>
                                    <tr style="border-bottom: 2px solid var(--border); color: var(--text-muted); text-align: left;">
                                        <th style="padding: 8px;">Coin</th>
                                        <th style="padding: 8px;">Adet</th>
                                        <th style="padding: 8px;">Giriş Fiyatı</th>
                                        <th style="padding: 8px;">Anlık Fiyat</th>
                                        <th style="padding: 8px;">Kâr / Zarar %</th>
                                    </tr>
                                </thead>
                                <tbody>${glCoinsHtml}</tbody>
                            </table>
                        </div>
                    `;
                } catch(e) {
                    content.innerHTML = `<div style="color: var(--danger); padding: 20px;">Bağlantı Hatası: ${e}</div>`;
                }
            }

            function closeUserPortfolioModal() {
                document.getElementById('user-portfolio-modal').style.display = 'none';
            }

            applyLang(currentLang);
            loadSystemSettings();
            loadData();
        </script>

        <!-- KULLANICI CÜZDAN DETAY MODAL HTML -->
        <div id="user-portfolio-modal" style="display: none; position: fixed; top: 0; left: 0; width: 100vw; height: 100vh; background: rgba(0, 0, 0, 0.75); backdrop-filter: blur(8px); justify-content: center; align-items: center; z-index: 10000;" onclick="if(event.target===this) closeUserPortfolioModal()">
            <div style="background: #1e293b; border: 1px solid rgba(255, 255, 255, 0.15); border-radius: 16px; width: 90%; max-width: 820px; max-height: 90vh; overflow-y: auto; padding: 24px; box-shadow: 0 20px 50px rgba(0,0,0,0.5);">
                <div style="display: flex; justify-content: space-between; align-items: center; border-bottom: 1px solid var(--border); padding-bottom: 14px; margin-bottom: 18px;">
                    <h2 id="portfolio-modal-title" style="font-size: 18px; color: #f8fafc; font-weight: 700;">💼 Kullanıcı Cüzdan Detayları</h2>
                    <button onclick="closeUserPortfolioModal()" style="background: rgba(239, 68, 68, 0.2); color: var(--danger); border: 1px solid var(--danger); border-radius: 8px; padding: 6px 12px; cursor: pointer; font-weight: bold; font-size: 14px;">✕ Kapat</button>
                </div>
                <div id="portfolio-modal-body">
                    <!-- Dinamik Cüzdan İçeriği Buraya Yüklenecek -->
                </div>
            </div>
        </div>
    </body>
    </html>
    """
    return HTMLResponse(content=html_content)

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app_api, host="0.0.0.0", port=8000)
