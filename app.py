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
from exchange import execute_spot_trade, fetch_portfolio_balance, get_live_usd_try_rate, convert_dust_to_bnb
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

last_daily_dust_sweep_ts = 0

def run_autonomous_trading_loop():
    """
    7/24 Otonom Yapay Zeka Alım-Satım ve Piyasa Analiz Döngüsü.
    Sistemdeki tüm aktif kullanıcılar (Tenants) için 5 saniyede bir piyasayı tarar.
    """
    global last_error_alerts, last_daily_dust_sweep_ts
    print("🤖 [Yapay Zeka Otonom Ajan]: 7/24 Tam Otonom Alım-Satım Döngüsü Aktif!")
    import time
    time.sleep(10)
    while True:
        try:
            tenants = get_all_active_tenants()
            if tenants:
                # 🧹 GÜNLÜK OTONOM KIRINTI SÜPÜRME (24 saatte bir otomatik çalışır)
                now_ts = time.time()
                if now_ts - last_daily_dust_sweep_ts > 86400:
                    last_daily_dust_sweep_ts = now_ts
                    for t_dust in tenants:
                        if not t_dust.get("is_paper_trading"):
                            try:
                                d_res = convert_dust_to_bnb(t_dust, max_usd_threshold=0.50)
                                if d_res.get("status") == "SUCCESS" and d_res.get("converted_count", 0) > 0:
                                    c_id = t_dust.get("telegram_chat_id")
                                    if c_id:
                                        from telegram_poller import send_message
                                        send_message(c_id, f"🧹 *GÜNLÜK OTO-KIRINTI TEMİZLİĞİ TAMAMLANDI*\n\n{d_res.get('message')}\nKasanızdaki mikro küsuratlar otomatik olarak BNB komisyon yakıtına dönüştürüldü. 🚀")
                            except Exception as e_d:
                                print(f"⚠️ [Günlük Kırıntı Hatası]: {e_d}")

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
    trailing_stop_enabled: Optional[bool] = None
    v21_security_shield_enabled: Optional[bool] = None

class StrategyConfigRequest(BaseModel):
    active_preset: str = "v21_balanced"
    volume_spike_multiplier: float = 1.3
    min_volume_usd: float = 10000.0
    max_recent_gain_24h: float = 12.0
    min_ai_score: float = 6.0

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
    shield_enabled = bool(get_system_setting("v21_security_shield_enabled", True))
    return {
        "status": "success",
        "trailing_stop_enabled": ts_enabled,
        "v21_security_shield_enabled": shield_enabled
    }

class StrategyConfigRequest(BaseModel):
    active_preset: str = "whale_hunting_balanced"
    volume_spike_multiplier: float = 2.5
    min_volume_usd: float = 50000.0
    max_recent_gain_24h: float = 12.0
    min_ai_score: float = 8.0
    max_budget_percent: float = 25.0
    trailing_callback_pct: float = 0.6
    take_profit_pct: Optional[float] = 3.0
    stop_loss_pct: Optional[float] = 1.5
    min_5m_volume_usd: Optional[float] = 50000.0
    require_futures_oi: Optional[bool] = True

@app_api.get("/api/strategy-config", dependencies=[Depends(authenticate_admin)])
def get_strategy_config_endpoint():
    from db import get_strategy_config, STRATEGY_PRESETS
    cfg = get_strategy_config(use_cache=False)
    return {"status": "success", "config": cfg, "presets": STRATEGY_PRESETS}

@app_api.post("/api/strategy-config", dependencies=[Depends(authenticate_admin)])
def save_strategy_config_endpoint(req: StrategyConfigRequest):
    from db import save_strategy_config
    payload = {
        "active_preset": req.active_preset,
        "volume_spike_multiplier": req.volume_spike_multiplier,
        "min_volume_usd": req.min_volume_usd,
        "max_recent_gain_24h": req.max_recent_gain_24h,
        "min_ai_score": req.min_ai_score,
        "max_budget_percent": req.max_budget_percent,
        "trailing_callback_pct": req.trailing_callback_pct,
        "take_profit_pct": req.take_profit_pct,
        "stop_loss_pct": req.stop_loss_pct,
        "min_5m_volume_usd": req.min_5m_volume_usd or req.min_volume_usd,
        "require_futures_oi": req.require_futures_oi
    }
    ok = save_strategy_config(payload)
    return {"status": "success" if ok else "error", "config": payload}

@app_api.post("/api/settings", dependencies=[Depends(authenticate_admin)])
def update_settings_endpoint(req: SystemSettingsRequest):
    from db import set_system_setting, get_system_setting
    if req.trailing_stop_enabled is not None:
        set_system_setting("trailing_stop_enabled", req.trailing_stop_enabled)
    if req.v21_security_shield_enabled is not None:
        set_system_setting("v21_security_shield_enabled", req.v21_security_shield_enabled)
        
    ts_val = bool(get_system_setting("trailing_stop_enabled", True))
    shield_val = bool(get_system_setting("v21_security_shield_enabled", True))
    return {
        "status": "success",
        "trailing_stop_enabled": ts_val,
        "v21_security_shield_enabled": shield_val,
        "message": f"Ayarlar Güncellendi (İz Süren: {'AÇIK' if ts_val else 'KAPALI'}, v2.1 Güvenlik Zırhı: {'AÇIK' if shield_val else 'KAPALI'})"
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
    """Tüm kullanıcıları (Tenants) süper hızlı ve maskelenmiş olarak listeler."""
    from db import get_supabase
    client = get_supabase()
    if not client:
        return {"status": "error", "count": 0, "tenants": []}
    try:
        res = client.table("user_tenants").select("*").order("created_at", desc=False).execute()
        raw_tenants = res.data or []
        sanitized = []
        for t in raw_tenants:
            safe_t = dict(t)
            safe_t.pop("exchange_secret_key", None)
            raw_k = str(safe_t.pop("exchange_api_key", ""))
            safe_t["exchange_api_key_configured"] = bool(raw_k)
            safe_t["exchange_api_key_masked"] = "***CONFIGURED***" if raw_k else "NOT_CONFIGURED"
            if raw_k.startswith("{"):
                try:
                    import json
                    kd = json.loads(raw_k)
                    safe_t["take_profit_percent"] = float(kd.get("take_profit_percent") or safe_t.get("take_profit_percent") or 1.5)
                    safe_t["preferred_language"] = str(kd.get("preferred_language") or safe_t.get("preferred_language") or "tr")
                except Exception:
                    pass
            sanitized.append(safe_t)
        return {"status": "success", "count": len(sanitized), "tenants": sanitized}
    except Exception as e:
        return {"status": "error", "count": 0, "tenants": [], "error": str(e)}

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
        payload = {
            "stop_loss_percent": float(req.stop_loss_percent),
            "max_budget_percent": float(req.max_budget_percent),
            "exchange_id": str(req.exchange_id or "binance")
        }
        
        import json
        kd = {}
        if api_k.startswith("{"):
            try:
                kd = json.loads(api_k)
            except Exception:
                kd = {}
        else:
            kd = {
                "binance": {
                    "api_key": api_k,
                    "secret_key": sec_k
                }
            }
        kd["take_profit_percent"] = float(req.take_profit_percent)
        kd["preferred_language"] = str(req.preferred_language or "tr")
        payload["exchange_api_key"] = json.dumps(kd)
                
        res = client.table("user_tenants").update(payload).eq("id", tenant_id).execute()
        from db import _tenant_cache
        tg_id = t_row.get("telegram_chat_id")
        if tg_id:
            _tenant_cache.pop(int(tg_id), None)
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

@app_api.post("/api/clean-dust", dependencies=[Depends(authenticate_admin)])
def clean_dust_endpoint():
    """Kullanıcıların Binance hesaplarındaki $0.50 altı mikro kırıntıları anında BNB'ye dönüştürür."""
    tenants = get_all_active_tenants()
    results = []
    for t in tenants:
        if not t.get("is_paper_trading"):
            res = convert_dust_to_bnb(t, max_usd_threshold=0.50)
            results.append({
                "tenant_name": t.get("tenant_name"),
                "result": res
            })
    return {"status": "success", "results": results}

@app_api.get("/api/settings", dependencies=[Depends(authenticate_admin)])
def get_system_settings_endpoint():
    from db import get_system_setting
    val = get_system_setting("trailing_stop_enabled", True)
    return {"status": "success", "trailing_stop_enabled": bool(val)}

@app_api.post("/api/settings", dependencies=[Depends(authenticate_admin)])
def update_system_settings_endpoint(req: SystemSettingsRequest):
    from db import set_system_setting
    set_system_setting("trailing_stop_enabled", bool(req.trailing_stop_enabled))
    return {"status": "success", "trailing_stop_enabled": bool(req.trailing_stop_enabled)}


# -----------------------------------------
# WEB DASHBOARD (V1 & V2 HTML / JAVASCRIPT ARAYÜZÜ)
@app_api.get("/v2/dashboard", response_class=HTMLResponse, dependencies=[Depends(authenticate_admin)])
@app_api.get("/V2/dashboard", response_class=HTMLResponse, dependencies=[Depends(authenticate_admin)])
@app_api.get("/v2", response_class=HTMLResponse, dependencies=[Depends(authenticate_admin)])
@app_api.get("/V2", response_class=HTMLResponse, dependencies=[Depends(authenticate_admin)])
def get_v2_dashboard_html():
    from v2_dashboard_html import generate_v2_dashboard_html
    from db import get_supabase, get_system_setting, get_strategy_config
    import json
    clean = []
    tenants_ssr_html = ""
    try:
        client = get_supabase()
        if client:
            res = client.table("user_tenants").select("*").order("created_at", desc=False).execute()
            raw = res.data or []
            for t in raw:
                st = dict(t)
                st.pop("exchange_secret_key", None)
                clean.append(st)
            for idx, user in enumerate(clean):
                safe_name = str(user.get("tenant_name", "Kullanıcı")).replace("'", "\\'")
                safe_id = str(user.get("id", ""))
                tp = float(user.get("take_profit_percent") or 3.0)
                sl = float(user.get("stop_loss_percent") or 1.5)
                mb = float(user.get("max_budget_percent") or 25)
                exch = str(user.get("exchange_id") or "binance")
                tg_id = user.get("telegram_chat_id")
                tenants_ssr_html += f"""
                <tr>
                    <td><strong style="color: #38bdf8;">{user.get('tenant_name')}</strong></td>
                    <td><code class="mono">{tg_id}</code></td>
                    <td><input type="number" step="0.1" class="input-inline" id="tp_{{idx}}" value="{tp}"></td>
                    <td><input type="number" step="0.1" class="input-inline" id="sl_{{idx}}" value="{sl}"></td>
                    <td><input type="number" step="1" class="input-inline" id="mb_{{idx}}" value="{mb}"></td>
                    <td><span class="mono" style="color: #60a5fa;">{exch.upper()}</span></td>
                    <td>🇹🇷 TR</td>
                    <td><span style="color: var(--success); font-weight: bold;">🟢 Aktif</span></td>
                    <td>
                        <button class="btn btn-primary" style="padding: 4px 10px; font-size: 11px;" onclick="updateSettings('{safe_id}', {{idx}}, '{safe_name}')">💾 Kaydet</button>
                    </td>
                </tr>
                """
    except Exception as e:
        tenants_ssr_html = f"<tr><td colspan='9' style='color: var(--text-muted);'>Yükleniyor... ({{e}})</td></tr>"

    logs_ssr_html = "<p style='color: var(--text-muted); padding: 12px;'>V2 Karar ve İşlem Motoru Canlı Takipte.</p>"
    try:
        if client:
            res_l = client.table("crypto_trade_logs").select("*").order("created_at", desc=True).limit(20).execute()
            logs_list = res_l.data or []
            if logs_list:
                rows = ""
                for l in logs_list:
                    d = str(l.get("created_at") or "")[:19].replace("T", " ")
                    is_buy = str(l.get("direction", "BUY")).upper() == "BUY"
                    dir_b = '<span style="color: var(--success); font-weight: bold;">🛒 ALIM (BUY)</span>' if is_buy else '<span style="color: var(--danger); font-weight: bold;">🎯 SATIM (SELL)</span>'
                    rows += f"<div style='padding: 8px 12px; border-bottom: 1px solid var(--border-color); font-size: 12px;'><span style='color: var(--text-muted);'>{d}</span> | {dir_b} | <strong class='mono'>{l.get('symbol')}</strong> | Fiyat: {l.get('entry_price')} | AI Skor: +{l.get('sentiment_score')} | Durum: {l.get('status')}</div>"
                logs_ssr_html = rows
    except Exception:
        pass

    trailing_stop_enabled = bool(get_system_setting("trailing_stop_enabled", True))
    trailing_checked = "checked" if trailing_stop_enabled else ""
    trailing_status = "AÇIK" if trailing_stop_enabled else "KAPALI"
    trailing_color = "var(--success)" if trailing_stop_enabled else "var(--danger)"

    content = generate_v2_dashboard_html(
        tenants_ssr_json=json.dumps(clean),
        tenants_ssr_html=tenants_ssr_html,
        logs_ssr_html=logs_ssr_html,
        active_engine="WHALE_HUNTING",
        active_risk="BALANCED",
        active_version="V2",
        trailing_checked=trailing_checked,
        trailing_status=trailing_status,
        trailing_color=trailing_color
    )
    return HTMLResponse(content=content)

@app_api.get("/v1/dashboard", response_class=HTMLResponse, dependencies=[Depends(authenticate_admin)])
@app_api.get("/V1/dashboard", response_class=HTMLResponse, dependencies=[Depends(authenticate_admin)])
@app_api.get("/v1", response_class=HTMLResponse, dependencies=[Depends(authenticate_admin)])
@app_api.get("/V1", response_class=HTMLResponse, dependencies=[Depends(authenticate_admin)])
@app_api.get("/", response_class=HTMLResponse, dependencies=[Depends(authenticate_admin)])
@app_api.get("/dashboard", response_class=HTMLResponse, dependencies=[Depends(authenticate_admin)])
@app_api.get("/admin", response_class=HTMLResponse, dependencies=[Depends(authenticate_admin)])
def get_dashboard_html():
    from db import get_supabase
    import json
    clean = []
    tenants_ssr_html = ""
    try:
        client = get_supabase()
        if client:
            res = client.table("user_tenants").select("*").order("created_at", desc=False).execute()
            raw = res.data or []
            for t in raw:
                st = dict(t)
                st.pop("exchange_secret_key", None)
                raw_k = str(st.pop("exchange_api_key", ""))
                st["exchange_api_key_configured"] = bool(raw_k)
                if raw_k.startswith("{"):
                    try:
                        kd = json.loads(raw_k)
                        st["take_profit_percent"] = float(kd.get("take_profit_percent") or st.get("take_profit_percent") or 1.5)
                        st["preferred_language"] = str(kd.get("preferred_language") or st.get("preferred_language") or "tr")
                    except Exception:
                        pass
                clean.append(st)
            tenants_ssr_json = json.dumps(clean)
            
            for idx, user in enumerate(clean):
                safe_name = str(user.get("tenant_name", "Kullanıcı")).replace("'", "\\'")
                safe_id = str(user.get("id", ""))
                tp = float(user.get("take_profit_percent") or 1.5)
                sl = float(user.get("stop_loss_percent") or 1.5)
                mb = float(user.get("max_budget_percent") or 10)
                exch = str(user.get("exchange_id") or "dual")
                lang = str(user.get("preferred_language") or "tr")
                tg_id = user.get("telegram_chat_id")
                sel_dual = "selected" if exch == "dual" else ""
                sel_tr = "selected" if exch == "binancetr" else ""
                sel_gl = "selected" if exch == "binance" else ""
                sel_lang_tr = "selected" if lang == "tr" else ""
                sel_lang_en = "selected" if lang == "en" else ""
                
                tenants_ssr_html += f"""
                <tr>
                    <td>
                        <span style="cursor: pointer; color: #60a5fa; font-weight: 700; display: inline-flex; align-items: center; gap: 4px;" onclick="openUserPortfolioModal('{safe_id}', '{safe_name}')">
                            🔍 {user.get('tenant_name')}
                        </span>
                    </td>
                    <td><code>{tg_id}</code></td>
                    <td>
                        <input type="number" step="0.1" class="input-inline" id="tp_{idx}" value="{tp}">
                    </td>
                    <td>
                        <input type="number" step="0.1" class="input-inline" id="sl_{idx}" value="{sl}">
                    </td>
                    <td>
                        <input type="number" step="1" class="input-inline" id="mb_{idx}" value="{mb}">
                    </td>
                    <td>
                        <select class="input-inline" style="width: 140px;" id="exch_{idx}">
                            <option value="binance" {sel_gl}>🌍 Sadece Global</option>
                            <option value="dual" {sel_dual}>⚡ Çift (TR + Global)</option>
                            <option value="binancetr" {sel_tr}>🇹🇷 Sadece TR</option>
                        </select>
                    </td>
                    <td>
                        <select class="input-inline" style="width: 78px;" id="lang_{idx}">
                            <option value="tr" {sel_lang_tr}>🇹🇷 TR</option>
                            <option value="en" {sel_lang_en}>🇬🇧 EN</option>
                        </select>
                    </td>
                    <td>
                        <span class="badge" style="background: rgba(34, 197, 94, 0.2); color: #22c55e; border: 1px solid #16a34a; font-weight: bold; padding: 5px 10px; border-radius: 6px;">🟢 Aktif</span>
                    </td>
                    <td>
                        <button class="btn" style="background: rgba(59, 130, 246, 0.2); color: #60a5fa; border: 1px solid #3b82f6; border-radius: 8px; padding: 6px 12px; cursor: pointer; font-weight: 600; font-size: 12px; white-space: nowrap;" onclick="openUserPortfolioModal('{safe_id}', '{safe_name}')">📊 Cüzdanı Gör</button>
                    </td>
                    <td style="white-space: nowrap;">
                        <div style="display: inline-flex; gap: 6px; align-items: center;">
                            <button class="btn btn-primary" style="padding: 6px 12px; font-size: 12px; white-space: nowrap;" onclick="updateSettings('{safe_id}', {idx}, '{safe_name}')">💾 Kaydet</button>
                            <button class="btn btn-danger" style="padding: 6px 10px; font-size: 12px; white-space: nowrap;" onclick="deleteTenant('{safe_id}')">Sil</button>
                        </div>
                    </td>
                </tr>
                """
    except Exception as e:
        print(f"SSR Error: {e}")
        tenants_ssr_html = "<tr><td colspan='9' style='color: var(--text-muted);'>Yükleniyor...</td></tr>"

    if not tenants_ssr_html:
        tenants_ssr_html = "<tr><td colspan='9' style='color: var(--text-muted);'>Henüz eklenmiş kullanıcı yok.</td></tr>"

    logs_ssr_html = ""
    try:
        if client:
            tenants_res = client.table("user_tenants").select("id, tenant_name, telegram_chat_id").execute()
            tenant_map = {str(t["id"]): t.get("tenant_name") for t in (tenants_res.data or [])}
            for t in (tenants_res.data or []):
                if t.get("telegram_chat_id"):
                    tenant_map[str(t["telegram_chat_id"])] = t.get("tenant_name")

            res_l = client.table("crypto_trade_logs").select("*").order("created_at", desc=True).limit(25).execute()
            logs_list = res_l.data or []
            if not logs_list:
                logs_ssr_html = "<p style='color: var(--text-muted); padding: 12px;'>Henüz kayıtlı işlem logu yok.</p>"
            else:
                rows = ""
                for l in logs_list:
                    d = str(l.get("created_at") or "")[:19].replace("T", " ")
                    is_buy = str(l.get("direction", "BUY")).upper() == "BUY"
                    dir_badge = '<span style="color: var(--success); font-weight: bold;">🛒 ALIM (BUY)</span>' if is_buy else '<span style="color: var(--danger); font-weight: bold;">🎯 SATIM (SELL)</span>'
                    score = float(l.get("sentiment_score") or 0.0)
                    det = l.get("execution_details") or {}
                    is_failed = l.get("status") == "FAILED" or det.get("status") == "FAILED"
                    is_exec = l.get("status") in ["SUCCESS", "EXECUTED"] or bool(l.get("order_id"))
                    if is_exec:
                        badge = '<span class="badge" style="background: rgba(34, 197, 94, 0.15); color: var(--success);">✅ Canlı İnfaz</span>'
                    elif is_failed:
                        badge = '<span class="badge" style="background: rgba(239, 68, 68, 0.15); color: var(--danger);">❌ Başarısız</span>'
                    else:
                        badge = '<span class="badge" style="background: rgba(245, 158, 11, 0.15); color: #f59e0b;">⏳ Beklemede</span>'
                    
                    price = float(l.get("entry_price") or 0.0)
                    price_str = f"${price:.6f}" if price < 0.001 else f"${price:.4f}"
                    amt_usd = float(l.get("amount_usd") or 0.0)
                    
                    t_id = str(det.get("tenant_id") or l.get("tenant_id") or "")
                    t_name = det.get("tenant_name") or tenant_map.get(t_id) or "S"
                    
                    rows += f"""
                    <tr style="border-bottom: 1px solid var(--border); font-size: 13px;">
                        <td style="padding: 10px;"><strong>{t_name}</strong></td>
                        <td style="padding: 10px;">{dir_badge} <code>{l.get('symbol', '—')}</code></td>
                        <td style="padding: 10px;">${amt_usd:.2f}</td>
                        <td style="padding: 10px;">{price_str}</td>
                        <td style="padding: 10px; color: var(--text-muted);">${l.get('take_profit_price') or '—'} / ${l.get('stop_loss_price') or '—'}</td>
                        <td style="padding: 10px;"><span style="color: var(--accent); font-weight: bold;">{score:+.1f} / +10</span></td>
                        <td style="padding: 10px;">{badge} <small style="display: block; color: var(--text-muted);">{l.get('exchange_label') or 'Binance'}</small></td>
                        <td style="padding: 10px; color: var(--text-muted); font-size: 12px;">{d}</td>
                    </tr>
                    """
                logs_ssr_html = f"""
                <div style="overflow-x: auto;">
                    <table style="width: 100%; border-collapse: collapse; margin-top: 8px;">
                        <thead>
                            <tr style="border-bottom: 2px solid var(--border); color: var(--text-muted); text-align: left; font-size: 13px;">
                                <th style="padding: 10px;">👤 Kullanıcı</th>
                                <th style="padding: 10px;">🪙 İşlem & Coin</th>
                                <th style="padding: 10px;">💵 Bütçe</th>
                                <th style="padding: 10px;">📥 Fiyat</th>
                                <th style="padding: 10px;">🎯 Kâr Al / SL</th>
                                <th style="padding: 10px;">📊 AI Skoru</th>
                                <th style="padding: 10px;">🏷️ Durum</th>
                                <th style="padding: 10px;">⏱️ Zaman</th>
                            </tr>
                        </thead>
                        <tbody>
                            {rows}
                        </tbody>
                    </table>
                </div>
                """
    except Exception as e_log:
        logs_ssr_html = f"<p style='color: var(--text-muted); padding: 12px;'>Log hatası: {e_log}</p>"

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
            table { width: 100%; border-collapse: collapse; margin-top: 10px; table-layout: auto; }
            th, td { text-align: left; padding: 10px 8px; border-bottom: 1px solid var(--border); font-size: 13px; vertical-align: middle; white-space: nowrap; }
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
            .switch { position: relative; display: inline-block; width: 44px; height: 22px; margin-bottom: 0; }
            .switch input { opacity: 0; width: 0; height: 0; }
            .slider { position: absolute; cursor: pointer; top: 0; left: 0; right: 0; bottom: 0; background-color: #334155; transition: .2s ease; border-radius: 22px; border: 1px solid var(--border); }
            .slider:before { position: absolute; content: ""; height: 16px; width: 16px; left: 2px; bottom: 2px; background-color: white; transition: .2s ease; border-radius: 50%; box-shadow: 0 1px 3px rgba(0,0,0,0.4); }
            input:checked + .slider { background-color: #10b981 !important; }
            input:checked + .slider:before { transform: translateX(22px) !important; background-color: #ffffff !important; }
        </style>
    </head>
    <body>
        <div class="header">
            <div class="header-left">
                <h1 id="i18n-title">🦊 Fox-Kripto Multi-Tenant Yönetim Paneli</h1>
                <p id="i18n-subtitle" style="color: var(--text-muted); font-size: 14px;">Otonom Yapay Zeka Kripto Ticaret, Risk ve Kullanıcı Yönetimi</p>
            </div>
            <div class="header-right">
                <div style="display: flex; align-items: center; gap: 10px; background: rgba(15, 23, 42, 0.8); border: 1px solid rgba(99, 102, 241, 0.35); border-radius: 10px; padding: 6px 14px;">
                    <span id="i18n-lbl-shield" style="font-size: 13px; font-weight: 600; color: #818cf8;">🛡️ v2.1 Güvenlik Zırhı:</span>
                    <label class="switch">
                        <input type="checkbox" id="security-shield-toggle" __SHIELD_CHECKED__ onchange="toggleSecurityShield(this.checked)">
                        <span class="slider"></span>
                    </label>
                    <span id="shield-status-text" style="font-size: 12px; font-weight: bold; color: __SHIELD_COLOR__;">__SHIELD_STATUS__</span>
                </div>
                <div style="display: flex; align-items: center; gap: 10px; background: rgba(15, 23, 42, 0.8); border: 1px solid var(--border); border-radius: 10px; padding: 6px 14px;">
                    <span id="i18n-lbl-trailing" style="font-size: 13px; font-weight: 600; color: #60a5fa;">🚀 İz Süren Stop (Trailing SL):</span>
                    <label class="switch">
                        <input type="checkbox" id="trailing-stop-toggle" __TRAILING_CHECKED__ onchange="toggleTrailingStop(this.checked)">
                        <span class="slider"></span>
                    </label>
                    <span id="trailing-status-text" style="font-size: 12px; font-weight: bold; color: __TRAILING_COLOR__;">__TRAILING_STATUS__</span>
                </div>
                <div class="lang-switch">
                    <button id="btn-tr" class="lang-btn active" onclick="changeLang('tr')">🇹🇷 Türkçe</button>
                    <button id="btn-en" class="lang-btn" onclick="changeLang('en')">🇬🇧 English</button>
                </div>
                <button class="btn" onclick="openRulesModal()" style="background: linear-gradient(135deg, #6366f1, #4f46e5); color: white; border: none; font-weight: 700; display: flex; align-items: center; gap: 6px; cursor: pointer; box-shadow: 0 4px 12px rgba(99, 102, 241, 0.35);">📜 Aktif Kurallar & Versiyon (v2.1)</button>
                <button class="btn btn-primary" onclick="triggerManualScan()" style="background: linear-gradient(135deg, #10b981, #059669); border: none; font-weight: 700; display: flex; align-items: center; gap: 6px;">⚡ Piyasayı Şimdi Tara</button>
                <button class="btn" onclick="triggerDustClean()" style="background: linear-gradient(135deg, #f59e0b, #d97706); color: white; border: none; font-weight: 700; display: flex; align-items: center; gap: 6px; cursor: pointer;">🧹 Kırıntıları BNB'ye Dönüştür</button>
                <button id="i18n-btn-refresh" class="btn btn-primary" onclick="loadData()">🔄 Verileri Yenile</button>
            </div>
        </div>

        <!-- ⚡ v2.1 STRATEJİ VE HACİM HASSASİYET SEÇİCİ KARTI -->
        <script>
        window.onPresetChange = function(preset) {
            var setVal = function(id, val) {
                var el = document.getElementById(id);
                if (el) {
                    el.value = val;
                    el.style.transition = 'all 0.25s';
                    el.style.borderColor = '#38bdf8';
                    setTimeout(function() { el.style.borderColor = ''; }, 500);
                }
            };
            var desc = document.getElementById('strat-desc');
            if (preset === 'v21_smart_armor') {
                setVal('strat-spike', 1.15);
                setVal('strat-minvol', 2500);
                setVal('strat-maxgain', 60.0);
                setVal('strat-minscore', 4.5);
                setVal('strat-maxbudget', 25.0);
                setVal('strat-trailcallback', 0.6);
                if (desc) desc.innerHTML = '💡 <em>Açıklama: 🛡️ 3 Kademeli Akıllı Zırh: +%1.0 Breakeven sıfır risk, +%1.5 balina kâr kilidi (%0.6), +%3.0 ralli takipçisi ve %25 (4 slot) kasa disiplini.</em>';
            } else if (preset === 'v21_balanced' || preset === 'agile_21_august') {
                setVal('strat-spike', 1.2);
                setVal('strat-minvol', 4000);
                setVal('strat-maxgain', 15.0);
                setVal('strat-minscore', 5.5);
                setVal('strat-maxbudget', 33.0);
                setVal('strat-trailcallback', 0.8);
                if (desc) desc.innerHTML = '💡 <em>Açıklama: v2.1 Dengeli Motor: %33 max bütçe (3 slot), $4.000 min hacim ve 1.2x erken balina teyidi ile çalışır.</em>';
            } else if (preset === 'v21_agile') {
                setVal('strat-spike', 1.15);
                setVal('strat-minvol', 2500);
                setVal('strat-maxgain', 20.0);
                setVal('strat-minscore', 4.5);
                setVal('strat-maxbudget', 50.0);
                setVal('strat-trailcallback', 0.6);
                if (desc) desc.innerHTML = '💡 <em>Açıklama: v2.1 Hızlı Momentum: %50 max bütçe (2 slot), $2.500 min hacim ve 1.15x erken ivmeyle çalışır.</em>';
            } else if (preset === 'v21_defensive' || preset === 'defensive_22_august') {
                setVal('strat-spike', 1.5);
                setVal('strat-minvol', 10000);
                setVal('strat-maxgain', 10.0);
                setVal('strat-minscore', 7.0);
                setVal('strat-maxbudget', 20.0);
                setVal('strat-trailcallback', 1.0);
                if (desc) desc.innerHTML = '💡 <em>Açıklama: v2.1 Yüksek Güvenlik: Maksimum nakit koruma (%20 bütçe / 5 slot), 1.5x büyük balina girişlerinde devreye girer.</em>';
            } else if (preset === 'v20_classic') {
                setVal('strat-spike', 1.1);
                setVal('strat-minvol', 2000);
                setVal('strat-maxgain', 25.0);
                setVal('strat-minscore', 4.0);
                setVal('strat-maxbudget', 50.0);
                setVal('strat-trailcallback', 0.5);
                if (desc) desc.innerHTML = '💡 <em>Açıklama: v2.0 Klasik Serbest Motor: Kısıtlamasız alım, $2.000 min hacim ve 1.1x erken balina girişi.</em>';
            } else if (preset === 'v10_legacy') {
                setVal('strat-spike', 1.5);
                setVal('strat-minvol', 15000);
                setVal('strat-maxgain', 10.0);
                setVal('strat-minscore', 7.0);
                setVal('strat-maxbudget', 25.0);
                setVal('strat-trailcallback', 1.0);
                if (desc) desc.innerHTML = '💡 <em>Açıklama: v1.0 Orijinal Klasik Motor: İlk sürüm kuralları ve standart hacim filtresi ile çalışır.</em>';
            }
        };
        </script>
        <div class="card" style="margin-bottom: 24px; border: 1px solid rgba(99, 102, 241, 0.4); background: linear-gradient(180deg, rgba(30, 41, 59, 0.85), rgba(15, 23, 42, 0.95)); box-shadow: 0 10px 25px rgba(0,0,0,0.3);">
            <div class="card-title" style="display: flex; justify-content: space-between; align-items: center;">
                <span>⚡ <strong>v2.1 Strateji & Hacim Hassasiyet Seçici (Al-Sat Çeviklik Motoru)</strong></span>
                <span id="active-strategy-badge" class="badge" style="background: rgba(99, 102, 241, 0.25); color: #818cf8; border: 1px solid #6366f1; font-size: 13px; padding: 6px 12px;">__STRAT_BADGE__</span>
            </div>
            <div style="display: grid; grid-template-columns: 1.3fr 0.7fr 0.8fr 0.7fr 0.7fr 0.9fr 0.8fr auto; gap: 10px; align-items: end; margin-top: 10px;">
                <div>
                    <label style="font-size: 12px; color: var(--text-muted); display: block; margin-bottom: 5px;">🎯 Hazır Strateji & Sürüm</label>
                    <select id="strategy-preset-select" onchange="window.onPresetChange(this.value)" oninput="window.onPresetChange(this.value)" style="width: 100%; padding: 9px; border-radius: 8px; background: rgba(15, 23, 42, 0.9); color: white; border: 1px solid var(--border); font-size: 13px;">
                        <option value="v21_smart_armor" __STRAT_SEL_ARMOR__>🛡️ v2.1 3 Kademeli Akıllı Zırh (Önerilen Scalp & Balina)</option>
                        <option value="v21_balanced" __STRAT_SEL_BALANCED__>⚖️ v2.1 Kurumsal Dengeli</option>
                        <option value="v21_agile" __STRAT_SEL_AGILE__>🚀 v2.1 Hızlı Momentum (Scalp Modu)</option>
                        <option value="v21_defensive" __STRAT_SEL_DEF__>🏰 v2.1 Yüksek Güvenlik (Defansif)</option>
                        <option value="v20_classic" __STRAT_SEL_V20__>⚡ v2.0 Klasik Serbest Motor (Kısıtlamasız)</option>
                        <option value="v10_legacy" __STRAT_SEL_V10__>🏛️ v1.0 Orijinal Klasik Motor (İlk Sürüm)</option>
                        <option value="custom" __STRAT_SEL_CUST__>⚙️ Özel Yapılandırma (Custom)</option>
                    </select>
                </div>
                <div>
                    <label style="font-size: 12px; color: var(--text-muted); display: block; margin-bottom: 5px;">⚡ Hacim Çarpanı</label>
                    <input type="number" id="strat-spike" step="0.05" value="__STRAT_SPIKE__" style="width: 100%; padding: 8px; border-radius: 8px; background: rgba(15, 23, 42, 0.9); color: white; border: 1px solid var(--border);">
                </div>
                <div>
                    <label style="font-size: 12px; color: var(--text-muted); display: block; margin-bottom: 5px;">💵 Min Hacim ($)</label>
                    <input type="number" id="strat-minvol" step="500" value="__STRAT_MINVOL__" style="width: 100%; padding: 8px; border-radius: 8px; background: rgba(15, 23, 42, 0.9); color: white; border: 1px solid var(--border);">
                </div>
                <div>
                    <label style="font-size: 12px; color: var(--text-muted); display: block; margin-bottom: 5px;">📈 24s Tavan %</label>
                    <input type="number" id="strat-maxgain" step="0.5" value="__STRAT_MAXGAIN__" style="width: 100%; padding: 8px; border-radius: 8px; background: rgba(15, 23, 42, 0.9); color: white; border: 1px solid var(--border);">
                </div>
                <div>
                    <label style="font-size: 12px; color: var(--text-muted); display: block; margin-bottom: 5px;">🧠 Min AI Skor</label>
                    <input type="number" id="strat-minscore" step="0.5" value="__STRAT_MINSCORE__" min="1.0" max="10.0" style="width: 100%; padding: 8px; border-radius: 8px; background: rgba(15, 23, 42, 0.9); color: white; border: 1px solid var(--border);">
                </div>
                <div>
                    <label style="font-size: 12px; color: #60a5fa; display: block; margin-bottom: 5px; font-weight: 600;">💰 Max Bütçe %</label>
                    <input type="number" id="strat-maxbudget" step="1.0" min="5.0" max="100.0" value="__STRAT_MAXBUDGET__" style="width: 100%; padding: 8px; border-radius: 8px; background: rgba(15, 23, 42, 0.9); color: #60a5fa; font-weight: 700; border: 1px solid #3b82f6;">
                </div>
                <div>
                    <label style="font-size: 12px; color: #34d399; display: block; margin-bottom: 5px; font-weight: 600;">🪜 Zirve Çekilme %</label>
                    <input type="number" id="strat-trailcallback" step="0.1" min="0.2" max="3.0" value="__STRAT_TRAILCALLBACK__" style="width: 100%; padding: 8px; border-radius: 8px; background: rgba(15, 23, 42, 0.9); color: #34d399; font-weight: 700; border: 1px solid #10b981;">
                </div>
                <div>
                    <button id="btn-save-strat" class="btn btn-primary" onclick="saveStrategySettings()" style="height: 38px; white-space: nowrap; font-weight: 600;">💾 Profili Uygula</button>
                </div>
            </div>
            <div id="strat-desc" style="font-size: 12px; color: #94a3b8; margin-top: 10px;">
                💡 <em>Açıklama: v2.1 Kurumsal Motor: %25 max bütçe (4 slot), 3 Kademeli DCA, BTC RSI kalkanı ve 1.3x hacim teyidi ile çalışır.</em>
            </div>
        </div>

        <div class="grid">
            <div class="card">
                <div class="card-title">
                    <span id="i18n-card-users">👥 Kayıtlı Kullanıcılar & Dinamik Risk Ayarları</span>
                    <span id="tenant-count" class="badge badge-active">__TENANT_COUNT__</span>
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
                            <th id="i18n-th-status">⚡ Durum</th>
                            <th id="i18n-th-wallet">💼 Cüzdan</th>
                            <th id="i18n-th-action">⚙️ İşlem</th>
                        </tr>
                    </thead>
                    <tbody id="tenants-table">
__SSR_TENANTS_HTML__
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
            <div id="logs-container">__SSR_LOGS_HTML__</div>
        </div>

        <script>
            function getAuthHeaders() {
                return {
                    'Authorization': 'Basic ' + btoa('admin:foxkripto2026')
                };
            }

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
                    thStatus: "⚡ Durum",
                    thWallet: "💼 Cüzdan",
                    thAction: "⚙️ İşlem",
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
                    thStatus: "⚡ Status",
                    thWallet: "💼 Wallet",
                    thAction: "⚙️ Action",
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
                if (document.getElementById('i18n-th-wallet')) document.getElementById('i18n-th-wallet').innerText = t.thWallet;
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

            function showToast(msg, type = 'success') {
                let container = document.getElementById('toast-container');
                if (!container) {
                    container = document.createElement('div');
                    container.id = 'toast-container';
                    container.style.cssText = 'position: fixed; top: 20px; right: 20px; z-index: 99999; display: flex; flex-direction: column; gap: 10px; max-width: 440px; pointer-events: none;';
                    document.body.appendChild(container);
                }
                const toast = document.createElement('div');
                const bg = type === 'success' ? 'linear-gradient(135deg, rgba(16, 185, 129, 0.98), rgba(5, 150, 105, 0.98))' : 'linear-gradient(135deg, rgba(239, 68, 68, 0.98), rgba(185, 28, 28, 0.98))';
                toast.style.cssText = `background: ${bg}; color: white; padding: 14px 20px; border-radius: 12px; box-shadow: 0 12px 30px rgba(0,0,0,0.5); font-weight: 600; font-size: 13px; line-height: 1.5; backdrop-filter: blur(10px); border: 1px solid rgba(255,255,255,0.25); pointer-events: auto; transition: all 0.3s ease;`;
                toast.innerHTML = msg.split(String.fromCharCode(10)).join('<br>');
                container.appendChild(toast);
                setTimeout(() => {
                    toast.style.opacity = '0';
                    toast.style.transform = 'translateY(-10px)';
                    setTimeout(() => toast.remove(), 350);
                }, 4500);
            }

            function getAuthHeaders() {
                return {
                    'Authorization': 'Basic ' + btoa('admin:foxkripto2026'),
                    'Accept': 'application/json'
                };
            }

            function changeLang(lang) {
                applyLang(lang);
                loadData();
            }

            function renderTenants(tenantsList) {
                const t = dict[currentLang] || dict.tr;
                const table = document.getElementById('tenants-table');
                if (!table) return;
                const countEl = document.getElementById('tenant-count');
                if (countEl) countEl.innerText = `${tenantsList.length} ${t.activeSuffix || 'Aktif'}`;
                
                if (!tenantsList || tenantsList.length === 0) {
                    table.innerHTML = `<tr><td colspan="9" style="color: var(--text-muted); padding: 16px; text-align: center;">${t.noUsers || 'Henüz eklenmiş kullanıcı yok.'}</td></tr>`;
                    return;
                }
                table.innerHTML = tenantsList.map((user, idx) => {
                    const safeName = (user.tenant_name || 'Kullanıcı').replace(/'/g, "\\'");
                    const safeId = user.id || '';
                    const tp = user.take_profit_percent || 1.5;
                    const sl = user.stop_loss_percent || 1.5;
                    const mb = user.max_budget_percent || 10;
                    const exch = user.exchange_id || 'dual';
                    const lang = user.preferred_language || 'tr';
                    
                    return `
                        <tr>
                            <td>
                                <span style="cursor: pointer; color: #60a5fa; font-weight: 700; display: inline-flex; align-items: center; gap: 4px;" onclick="openUserPortfolioModal('${safeId}', '${safeName}')">
                                    🔍 ${user.tenant_name}
                                </span>
                            </td>
                            <td><code>${user.telegram_chat_id}</code></td>
                            <td>
                                <input type="number" step="0.1" class="input-inline" id="tp_${idx}" value="${tp}">
                            </td>
                            <td>
                                <input type="number" step="0.1" class="input-inline" id="sl_${idx}" value="${sl}">
                            </td>
                            <td>
                                <input type="number" step="1" class="input-inline" id="mb_${idx}" value="${mb}">
                            </td>
                            <td>
                                <select class="input-inline" style="width: 140px;" id="exch_${idx}">
                                    <option value="binance" ${exch === 'binance' ? 'selected' : ''}>🌍 Sadece Global</option>
                                    <option value="dual" ${exch === 'dual' ? 'selected' : ''}>⚡ Çift (TR + Global)</option>
                                    <option value="binancetr" ${exch === 'binancetr' ? 'selected' : ''}>🇹🇷 Sadece TR</option>
                                </select>
                            </td>
                            <td>
                                <select class="input-inline" style="width: 78px;" id="lang_${idx}">
                                    <option value="tr" ${lang === 'tr' ? 'selected' : ''}>🇹🇷 TR</option>
                                    <option value="en" ${lang === 'en' ? 'selected' : ''}>🇬🇧 EN</option>
                                </select>
                            </td>
                            <td>
                                <span class="badge" style="background: rgba(34, 197, 94, 0.2); color: #22c55e; border: 1px solid #16a34a; font-weight: bold; padding: 5px 10px; border-radius: 6px;">🟢 Aktif</span>
                            </td>
                            <td>
                                <button class="btn" style="background: rgba(59, 130, 246, 0.2); color: #60a5fa; border: 1px solid #3b82f6; border-radius: 8px; padding: 6px 12px; cursor: pointer; font-weight: 600; font-size: 12px; white-space: nowrap;" onclick="openUserPortfolioModal('${safeId}', '${safeName}')">📊 Cüzdanı Gör</button>
                            </td>
                            <td>
                                <button class="btn btn-primary" style="padding: 5px 12px; margin-right: 4px;" onclick="updateSettings('${safeId}', ${idx}, '${safeName}')">${t.save || 'Kaydet'}</button>
                                <button class="btn btn-danger" style="padding: 5px 10px;" onclick="deleteTenant('${safeId}')">${t.del || 'Sil'}</button>
                            </td>
                        </tr>
                    `;
                }).join('');
            }

            const SSR_DATA = __SSR_TENANTS_DATA__;

            async function loadTenantsTable() {
                if (Array.isArray(SSR_DATA) && SSR_DATA.length > 0) {
                    renderTenants(SSR_DATA);
                }
                try {
                    const res = await fetch('/api/tenants', { headers: getAuthHeaders() });
                    if (res.ok) {
                        const data = await res.json();
                        if (data && Array.isArray(data.tenants)) {
                            renderTenants(data.tenants);
                        }
                    }
                } catch(err) {
                    console.error('Tenants background refresh error:', err);
                }
            }

            async function loadLogsTable() {
                const t = dict[currentLang] || dict.tr;
                const logContainer = document.getElementById('logs-container');
                try {
                    const logRes = await fetch('/api/trade-logs', { headers: getAuthHeaders() });
                    if (!logRes.ok) return;
                    const logData = await logRes.json();
                    const logsList = (logData && Array.isArray(logData.logs)) ? logData.logs : [];
                    if (logsList.length === 0) {
                        logContainer.innerHTML = `<p style="color: var(--text-muted);">${t.noLogs || 'Henüz kayıtlı işlem logu yok.'}</p>`;
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
                                        ${logsList.map(l => {
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
                                                badgeHtml = `<span class="badge" style="background: rgba(239, 68, 68, 0.15); color: var(--danger);">❌ İnfaz Başarısız</span>`;
                                            } else {
                                                badgeHtml = `<span class="badge" style="background: rgba(245, 158, 11, 0.15); color: #f59e0b;">⏳ Beklemede</span>`;
                                            }

                                            let formattedPrice = '—';
                                            if (l.entry_price) {
                                                const pNum = Number(l.entry_price);
                                                formattedPrice = pNum < 0.001 ? pNum.toFixed(6) : pNum.toFixed(4);
                                            }
                                            
                                            return `
                                                <tr style="border-bottom: 1px solid var(--border); font-size: 13px;">
                                                    <td style="padding: 10px;"><strong>${l.tenant_name || 'S'}</strong></td>
                                                    <td style="padding: 10px;">${dirBadge} <code>${l.symbol || '—'}</code></td>
                                                    <td style="padding: 10px;">$${Number(l.amount_usd || 0).toFixed(2)}</td>
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
                } catch(err) {
                    console.error('Logs load error:', err);
                }
            }

            async function loadData() {
                await loadTenantsTable();
                await loadLogsTable();
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
                        headers: { ...getAuthHeaders(), 'Content-Type': 'application/json' },
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
                    headers: { ...getAuthHeaders(), 'Content-Type': 'application/json' },
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
                const res = await fetch(`/api/tenants/${tenantId}`, {
                    method: 'DELETE',
                    headers: getAuthHeaders()
                });
                if (res.ok) {
                    alert(t.userDeactivated);
                    loadData();
                }
            }

            async function loadSystemSettings() {
                try {
                    const res = await fetch('/api/settings', { headers: getAuthHeaders() });
                    const data = await res.json();
                    const isEn = (currentLang === 'en');
                    
                    const toggle = document.getElementById('trailing-stop-toggle');
                    const statusTxt = document.getElementById('trailing-status-text');
                    if (toggle && statusTxt) {
                        toggle.checked = Boolean(data.trailing_stop_enabled);
                        statusTxt.innerText = data.trailing_stop_enabled ? (isEn ? 'ACTIVE' : 'AÇIK') : (isEn ? 'DISABLED' : 'KAPALI');
                        statusTxt.style.color = data.trailing_stop_enabled ? 'var(--success)' : 'var(--danger)';
                    }
                    
                    const shieldToggle = document.getElementById('security-shield-toggle');
                    const shieldTxt = document.getElementById('shield-status-text');
                    if (shieldToggle && shieldTxt) {
                        const s_active = (data.v21_security_shield_enabled !== false);
                        shieldToggle.checked = Boolean(s_active);
                        shieldTxt.innerText = s_active ? (isEn ? 'ACTIVE' : 'AÇIK') : (isEn ? 'DISABLED' : 'KAPALI');
                        shieldTxt.style.color = s_active ? 'var(--success)' : 'var(--danger)';
                    }
                } catch(e) { console.error('Settings load error:', e); }
            }

            async function toggleSecurityShield(enabled) {
                const shieldTxt = document.getElementById('shield-status-text');
                const isEn = (currentLang === 'en');
                if (shieldTxt) {
                    shieldTxt.innerText = isEn ? 'UPDATING...' : 'GÜNCELLENİYOR...';
                    shieldTxt.style.color = 'var(--warning)';
                }
                try {
                    const res = await fetch('/api/settings', {
                        method: 'POST',
                        headers: { ...getAuthHeaders(), 'Content-Type': 'application/json' },
                        body: JSON.stringify({ v21_security_shield_enabled: enabled })
                    });
                    const data = await res.json();
                    if (shieldTxt) {
                        shieldTxt.innerText = enabled ? (isEn ? 'ACTIVE' : 'AÇIK') : (isEn ? 'DISABLED' : 'KAPALI');
                        shieldTxt.style.color = enabled ? 'var(--success)' : 'var(--danger)';
                    }
                } catch(e) {
                    console.error('Shield update error:', e);
                    loadSystemSettings();
                }
            }

            async function toggleTrailingStop(enabled) {
                try {
                    const res = await fetch('/api/settings', {
                        method: 'POST',
                        headers: { ...getAuthHeaders(), 'Content-Type': 'application/json' },
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
                    const res = await fetch('/api/tenants/' + tenantId + '/portfolio', { headers: getAuthHeaders() });
                    const data = await res.json();
                    
                    if (!res.ok || data.status !== 'success') {
                        content.innerHTML = `<div style="color: var(--danger); padding: 20px;">❌ Hata: ${data.detail || 'Cüzdan verisi alınamadı.'}</div>`;
                        return;
                    }
                    
                    const p = data.portfolio || {};
                    const isDual = (data.exchange_id === 'dual' || data.exchange_id === 'both');
                    const isTrActive = (data.exchange_id === 'dual' || data.exchange_id === 'binancetr');
                    const isGlActive = (data.exchange_id === 'dual' || data.exchange_id === 'binance' || !data.exchange_id);
                    
                    const freeTryVal = isDual ? (p.binance_tr?.free_try || 0) : (data.exchange_id === 'binancetr' ? (p.free_try || 0) : 0);
                    const totalTryVal = isDual ? (p.binance_tr?.total_try || 0) : (data.exchange_id === 'binancetr' ? (p.total_try || 0) : 0);
                    const freeUsdtVal = isDual ? (p.binance_global?.free_usdt || 0) : (isGlActive ? (p.free_usdt || 0) : 0);
                    const totalUsdtVal = isDual ? (p.binance_global?.total_usdt || 0) : (isGlActive ? (p.total_usdt || 0) : 0);

                    const freeTry = isTrActive ? Number(freeTryVal).toLocaleString('tr-TR', {minimumFractionDigits: 2, maximumFractionDigits: 2}) : '0.00';
                    const totalTry = isTrActive ? Number(totalTryVal).toLocaleString('tr-TR', {minimumFractionDigits: 2, maximumFractionDigits: 2}) : '0.00';
                    const freeUsdt = isGlActive ? Number(freeUsdtVal).toLocaleString('en-US', {minimumFractionDigits: 2, maximumFractionDigits: 2}) : '0.00';
                    const totalUsdt = isGlActive ? Number(totalUsdtVal).toLocaleString('en-US', {minimumFractionDigits: 2, maximumFractionDigits: 2}) : '0.00';
                    const grandUsd = Number(p.total_usdt || totalUsdtVal || 0).toLocaleString('en-US', {minimumFractionDigits: 2, maximumFractionDigits: 2});
                    const grandTry = Number(p.total_try || (totalUsdtVal * (data.usd_try_rate || 48.0)) || 0).toLocaleString('tr-TR', {minimumFractionDigits: 2, maximumFractionDigits: 2});
                    
                    // TR Pozisyonları HTML
                    const posTr = data.saved_positions_tr || {};
                    let trCoinsHtml = '';
                    const trKeys = Object.keys(posTr);
                    if (!isTrActive) {
                        trCoinsHtml = `<tr><td colspan="5" style="color: var(--text-muted); text-align: center; padding: 20px; font-weight: 500;">⚪ Bu hesap için Binance TR devre dışı bırakılmıştır. (Sadece Binance Global Aktif).</td></tr>`;
                    } else if (trKeys.length === 0) {
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
                    
                    // Global Canlı Varlıklar & Pozisyonlar HTML
                    const holdings = p.holdings_details || {};
                    const savedGl = data.saved_positions_gl || {};
                    const coinSymbols = Object.keys(holdings);
                    
                    let glCoinsHtml = '';
                    if (!isGlActive) {
                        glCoinsHtml = `<tr><td colspan="5" style="color: var(--text-muted); text-align: center; padding: 20px; font-weight: 500;">⚪ Bu hesap için Binance Global devre dışı bırakılmıştır. (Sadece Binance TR Aktif).</td></tr>`;
                    } else if (coinSymbols.length === 0) {
                        glCoinsHtml = `<tr><td colspan="5" style="color: var(--text-muted); text-align: center; padding: 20px; font-weight: 500;">✅ Cüzdanda açık coin bulunmamaktadır (Kasa %100 Serbest $${freeUsdt} USDT Nakitte).</td></tr>`;
                    } else {
                        glCoinsHtml = coinSymbols.map(sym => {
                            const coin = holdings[sym] || {};
                            const amt = Number(coin.amount || 0);
                            const price = Number(coin.price || 0);
                            const valUsd = Number(coin.val_usd || (amt * price));
                            const valTry = Number(coin.val_try || (valUsd * (data.usd_try_rate || 48.0)));
                            
                            const botPos = savedGl[sym] || savedGl[sym + 'USDT'] || {};
                            const buyP = Number(botPos.buy_price || botPos.entry_price || price);
                            const pnl = buyP > 0 ? (((price - buyP) / buyP) * 100) : 0;
                            const pnlBadge = botPos.buy_price ? `<span style="color: ${pnl >= 0 ? 'var(--success)' : 'var(--danger)'}; font-weight: bold;">${pnl >= 0 ? '+' : ''}%${pnl.toFixed(2)}</span>` : `<span style="color: #60a5fa; font-weight: 600;">🟢 Canlı Binance Bakiyesi</span>`;
                            
                            return `
                                <tr style="border-bottom: 1px solid var(--border); font-size: 13px;">
                                    <td style="padding: 10px;"><strong>🪙 ${sym}</strong></td>
                                    <td style="padding: 10px;">${amt < 0.001 ? amt.toFixed(6) : amt.toFixed(4)}</td>
                                    <td style="padding: 10px;">$${price < 0.001 ? price.toFixed(6) : price.toFixed(4)}</td>
                                    <td style="padding: 10px; font-weight: bold; color: #60a5fa;">$${valUsd.toFixed(2)} <small style="color: var(--text-muted); display: block;">~₺${valTry.toFixed(2)} TL</small></td>
                                    <td style="padding: 10px;">${pnlBadge}</td>
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
                            <div style="background: ${isTrActive ? 'rgba(16, 185, 129, 0.15)' : 'rgba(100, 116, 139, 0.15)'}; border: 1px solid ${isTrActive ? 'rgba(16, 185, 129, 0.4)' : 'rgba(100, 116, 139, 0.3)'}; border-radius: 12px; padding: 14px; text-align: center;">
                                <div style="color: var(--text-muted); font-size: 12px; font-weight: 600;">🇹🇷 BİNANCE TR NAKİT</div>
                                <div style="font-size: 20px; font-weight: bold; color: ${isTrActive ? 'var(--success)' : '#94a3b8'}; margin-top: 4px;">₺${freeTry} TL</div>
                                <small style="color: var(--text-muted);">${isTrActive ? `Toplam TR: ₺${totalTry} TL` : '⚪ Devre Dışı (Pasif)'}</small>
                            </div>
                            <div style="background: ${isGlActive ? 'rgba(245, 158, 11, 0.15)' : 'rgba(100, 116, 139, 0.15)'}; border: 1px solid ${isGlActive ? 'rgba(245, 158, 11, 0.4)' : 'rgba(100, 116, 139, 0.3)'}; border-radius: 12px; padding: 14px; text-align: center;">
                                <div style="color: var(--text-muted); font-size: 12px; font-weight: 600;">🌍 BİNANCE GLOBAL NAKİT</div>
                                <div style="font-size: 20px; font-weight: bold; color: ${isGlActive ? '#fbbf24' : '#94a3b8'}; margin-top: 4px;">$${freeUsdt} USDT</div>
                                <small style="color: var(--text-muted);">${isGlActive ? `Toplam Global: $${totalUsdt} USD` : '⚪ Devre Dışı (Pasif)'}</small>
                            </div>
                        </div>

                        <!-- Binance TR Tablosu -->
                        <div style="background: rgba(15, 23, 42, 0.6); border: 1px solid var(--border); border-radius: 12px; padding: 16px; margin-bottom: 16px;">
                            <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 10px;">
                                <h3 style="font-size: 15px; color: #f8fafc;">🇹🇷 Binance TR Cüzdanı ve Eldeki Coinler</h3>
                                <span class="badge ${isTrActive ? 'badge-active' : ''}" style="${!isTrActive ? 'background: rgba(148, 163, 184, 0.2); color: #94a3b8; border: 1px solid #64748b;' : ''}">
                                    ${isTrActive ? `${trKeys.length} Açık Pozisyon` : '⚪ Devre Dışı'}
                                </span>
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
                                <h3 style="font-size: 15px; color: #f8fafc;">🌍 Binance Global Canlı Cüzdan ve Varlıklar</h3>
                                <span class="badge ${isGlActive ? 'badge-active' : ''}" style="${!isGlActive ? 'background: rgba(148, 163, 184, 0.2); color: #94a3b8; border: 1px solid #64748b;' : ''}">
                                    ${isGlActive ? `${coinSymbols.length} Canlı Varlık` : '⚪ Devre Dışı'}
                                </span>
                            </div>
                            <table style="width: 100%; border-collapse: collapse; font-size: 13px;">
                                <thead>
                                    <tr style="border-bottom: 2px solid var(--border); color: var(--text-muted); text-align: left;">
                                        <th style="padding: 8px;">Coin</th>
                                        <th style="padding: 8px;">Miktar (Adet)</th>
                                        <th style="padding: 8px;">Birim Fiyat</th>
                                        <th style="padding: 8px;">Toplam Değer ($ / ₺)</th>
                                        <th style="padding: 8px;">Durum & Kâr %</th>
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

            async function loadStrategyConfig() {
                try {
                    const res = await fetch('/api/strategy-config?t=' + Date.now(), { headers: getAuthHeaders() });
                    const data = await res.json();
                    if (data.status === 'success' && data.config) {
                        const cfg = data.config;
                        const sel = document.getElementById('strategy-preset-select');
                        let p = cfg.active_preset || 'v21_balanced';
                        if (p === 'agile_21_august') p = 'v21_balanced';
                        if (p === 'defensive_22_august') p = 'v21_defensive';
                        sel.value = p;
                        document.getElementById('strat-spike').value = cfg.volume_spike_multiplier || 1.2;
                        document.getElementById('strat-minvol').value = cfg.min_volume_usd || 4000;
                        document.getElementById('strat-maxgain').value = cfg.max_recent_gain_24h || 15.0;
                        document.getElementById('strat-minscore').value = cfg.min_ai_score || 5.5;
                        document.getElementById('strat-maxbudget').value = cfg.max_budget_percent || 33.0;
                        document.getElementById('strat-trailcallback').value = cfg.trailing_callback_pct || 0.8;
                        updateStrategyBadge(p, cfg.volume_spike_multiplier || 1.2);
                    }
                } catch (e) {
                    console.error('Strateji yükleme hatası:', e);
                }
            }

            function onPresetChange(preset) {
                const desc = document.getElementById('strat-desc');
                const setVal = (id, val) => {
                    const el = document.getElementById(id);
                    if (el) el.value = val;
                };

                if (preset === 'v21_balanced' || preset === 'agile_21_august') {
                    setVal('strat-spike', 1.2);
                    setVal('strat-minvol', 4000);
                    setVal('strat-maxgain', 15.0);
                    setVal('strat-minscore', 5.5);
                    setVal('strat-maxbudget', 33.0);
                    setVal('strat-trailcallback', 0.8);
                    if (desc) desc.innerHTML = '💡 <em>Açıklama: v2.1 Dengeli Motor: %33 max bütçe (3 slot), $4.000 min hacim ve 1.2x erken balina teyidi ile çalışır. (Önerilen)</em>';
                } else if (preset === 'v21_agile') {
                    setVal('strat-spike', 1.15);
                    setVal('strat-minvol', 2500);
                    setVal('strat-maxgain', 20.0);
                    setVal('strat-minscore', 4.5);
                    setVal('strat-maxbudget', 50.0);
                    setVal('strat-trailcallback', 0.6);
                    if (desc) desc.innerHTML = '💡 <em>Açıklama: v2.1 Hızlı Momentum: %50 max bütçe (2 slot), $2.500 min hacim ve 1.15x erken ivmeyle çalışır.</em>';
                } else if (preset === 'v21_defensive' || preset === 'defensive_22_august') {
                    setVal('strat-spike', 1.5);
                    setVal('strat-minvol', 10000);
                    setVal('strat-maxgain', 10.0);
                    setVal('strat-minscore', 7.0);
                    setVal('strat-maxbudget', 20.0);
                    setVal('strat-trailcallback', 1.0);
                    if (desc) desc.innerHTML = '💡 <em>Açıklama: v2.1 Yüksek Güvenlik: Maksimum nakit koruma (%20 bütçe / 5 slot), 1.5x büyük balina girişlerinde devreye girer.</em>';
                } else if (preset === 'v20_classic') {
                    setVal('strat-spike', 1.1);
                    setVal('strat-minvol', 2000);
                    setVal('strat-maxgain', 25.0);
                    setVal('strat-minscore', 4.0);
                    setVal('strat-maxbudget', 50.0);
                    setVal('strat-trailcallback', 0.5);
                    if (desc) desc.innerHTML = '💡 <em>Açıklama: v2.0 Klasik Serbest Motor: Kısıtlamasız alım, $2.000 min hacim ve 1.1x erken balina girişi.</em>';
                } else if (preset === 'v10_legacy') {
                    setVal('strat-spike', 1.5);
                    setVal('strat-minvol', 15000);
                    setVal('strat-maxgain', 10.0);
                    setVal('strat-minscore', 7.0);
                    setVal('strat-maxbudget', 25.0);
                    setVal('strat-trailcallback', 1.0);
                    if (desc) desc.innerHTML = '💡 <em>Açıklama: v1.0 Orijinal Klasik Motor: İlk sürüm kuralları ve standart hacim filtresi ile çalışır.</em>';
                } else {
                    if (desc) desc.innerHTML = '💡 <em>Açıklama: Özel Profil: Kendi belirlediğiniz parametreler ile çalışır.</em>';
                }
            }

            function updateStrategyBadge(preset, spike) {
                const badge = document.getElementById('active-strategy-badge');
                if (preset === 'v21_balanced' || preset === 'agile_21_august') {
                    badge.innerHTML = '🛡️ v2.1 Kurumsal Dengeli (' + spike + 'x) Aktif';
                    badge.style.borderColor = '#6366f1';
                    badge.style.color = '#818cf8';
                } else if (preset === 'v21_agile') {
                    badge.innerHTML = '🚀 v2.1 Hızlı Momentum (' + spike + 'x) Aktif';
                    badge.style.borderColor = '#3b82f6';
                    badge.style.color = '#60a5fa';
                } else if (preset === 'v21_defensive' || preset === 'defensive_22_august') {
                    badge.innerHTML = '🏰 v2.1 Yüksek Güvenlik (' + spike + 'x) Aktif';
                    badge.style.borderColor = '#10b981';
                    badge.style.color = '#34d399';
                } else {
                    badge.innerHTML = '⚙️ v2.1 Özel Mod (' + spike + 'x) Aktif';
                    badge.style.borderColor = '#f59e0b';
                    badge.style.color = '#fbbf24';
                }
            }

            async function saveStrategySettings() {
                const btn = document.getElementById('btn-save-strat');
                if (btn) {
                    btn.innerText = '⏳ Kaydediliyor...';
                    btn.disabled = true;
                }
                const preset = document.getElementById('strategy-preset-select').value;
                const spike = parseFloat(document.getElementById('strat-spike').value) || 1.2;
                const minvol = parseFloat(document.getElementById('strat-minvol').value) || 4000;
                const maxgain = parseFloat(document.getElementById('strat-maxgain').value) || 15.0;
                const minscore = parseFloat(document.getElementById('strat-minscore').value) || 5.5;
                const maxbudget = parseFloat(document.getElementById('strat-maxbudget').value) || 33.0;
                const trailcallback = parseFloat(document.getElementById('strat-trailcallback').value) || 0.8;

                try {
                    const res = await fetch('/api/strategy-config', {
                        method: 'POST',
                        headers: { ...getAuthHeaders(), 'Content-Type': 'application/json' },
                        body: JSON.stringify({
                            active_preset: preset,
                            volume_spike_multiplier: spike,
                            min_volume_usd: minvol,
                            max_recent_gain_24h: maxgain,
                            min_ai_score: minscore,
                            max_budget_percent: maxbudget,
                            trailing_callback_pct: trailcallback
                        })
                    });
                    const data = await res.json();
                    if (data.status === 'success') {
                        updateStrategyBadge(preset, spike);
                        showToast('✅ Strateji ve Sürüm Profili Başarıyla Kaydedildi!<br><br><b>Sürüm:</b> ' + preset + ' (' + spike + 'x)<br><b>Bütçe:</b> %' + maxbudget + ' | <b>Min Hacim:</b> $' + minvol + '<br><b>Tavan:</b> %' + maxgain + ' | <b>Zirve Kilidi:</b> %' + trailcallback, 'success');
                        loadStrategyConfig();
                    } else {
                        showToast('❌ Kaydetme Başarısız: ' + (data.detail || JSON.stringify(data)), 'error');
                    }
                } catch (e) {
                    showToast('❌ Bağlantı Hatası: ' + e, 'error');
                } finally {
                    if (btn) {
                        btn.innerText = '💾 Profili Uygula';
                        btn.disabled = false;
                    }
                }
            }

            async function triggerManualScan() {
                if (!confirm('⚡ Tüm aktif kullanıcılar için piyasa taraması ve alım-satım analizi hemen başlatılsın mı?')) return;
                try {
                    const res = await fetch('/run-graph', {
                        method: 'POST',
                        headers: { ...getAuthHeaders(), 'Content-Type': 'application/json' },
                        body: JSON.stringify({session_id: 'manual_' + Date.now()})
                    });
                    const data = await res.json();
                    alert('🚀 ' + (data.message || 'Piyasa taraması ve otonom analiz başlatıldı!'));
                    setTimeout(loadData, 4000);
                } catch(e) {
                    alert('Hata: ' + e);
                }
            }

            async function triggerDustClean() {
                if (!confirm('🧹 $0.50 altındaki tüm mikro kırıntılar (STORJ, MINA, AMP, ACE vb.) otomatik olarak BNB komisyon yakıtına dönüştürülsün mü?\\n\\n(Not: PROM, ONG ve açık pozisyonlarınız korunur, dönüştürülmez.)')) return;
                try {
                    const res = await fetch('/api/clean-dust', {
                        method: 'POST',
                        headers: { ...getAuthHeaders(), 'Content-Type': 'application/json' }
                    });
                    const data = await res.json();
                    if (data.status === 'success') {
                        let msg = '🧹 Kırıntı Temizliği Tamamlandı:\\n\\n';
                        for (const r of data.results || []) {
                            msg += r.tenant_name + ': ' + (r.result.message || r.result.error || 'İşlem tamamlandı.') + '\\n';
                        }
                        alert(msg);
                        loadData();
                    } else {
                        alert('❌ Hata: ' + (data.error || JSON.stringify(data)));
                    }
                } catch(e) {
                    alert('Bağlantı Hatası: ' + e);
                }
            }

            function openRulesModal() {
                document.getElementById('rules-manifest-modal').style.display = 'flex';
            }
            function closeRulesModal() {
                document.getElementById('rules-manifest-modal').style.display = 'none';
            }

            applyLang(currentLang);
            loadSystemSettings();
            loadStrategyConfig();
            loadData();

            const presetSelectEl = document.getElementById('strategy-preset-select');
            if (presetSelectEl) {
                presetSelectEl.addEventListener('change', function() { onPresetChange(this.value); });
                presetSelectEl.addEventListener('input', function() { onPresetChange(this.value); });
            }
        </script>

        <!-- AKTİF KURALLAR & VERSİYON GEÇMİŞİ MODALI -->
        <div id="rules-manifest-modal" style="display: none; position: fixed; top: 0; left: 0; width: 100vw; height: 100vh; background: rgba(0, 0, 0, 0.8); backdrop-filter: blur(10px); justify-content: center; align-items: center; z-index: 10000;" onclick="if(event.target===this) closeRulesModal()">
            <div style="background: #1e293b; border: 1px solid rgba(99, 102, 241, 0.4); border-radius: 16px; width: 92%; max-width: 900px; max-height: 90vh; overflow-y: auto; padding: 26px; box-shadow: 0 25px 60px rgba(0,0,0,0.6);">
                <div style="display: flex; justify-content: space-between; align-items: center; border-bottom: 1px solid var(--border); padding-bottom: 14px; margin-bottom: 18px;">
                    <div style="display: flex; align-items: center; gap: 10px;">
                        <h2 style="font-size: 20px; color: #f8fafc; font-weight: 800; margin: 0;">📜 Fox AI Kurumsal Trading & Risk Kuralları</h2>
                        <span class="badge" style="background: rgba(99, 102, 241, 0.25); color: #818cf8; border: 1px solid #6366f1; font-weight: bold; padding: 4px 10px; border-radius: 6px; font-size: 13px;">🟢 Versiyon: v2.1 (Canlı)</span>
                    </div>
                    <button onclick="closeRulesModal()" style="background: rgba(239, 68, 68, 0.2); color: var(--danger); border: 1px solid var(--danger); border-radius: 8px; padding: 6px 14px; cursor: pointer; font-weight: bold; font-size: 14px;">✕ Kapat</button>
                </div>

                <!-- KURALLAR LİSTESİ -->
                <div style="display: grid; gap: 14px; margin-bottom: 24px;">
                    <div style="background: rgba(15, 23, 42, 0.7); border: 1px solid rgba(59, 130, 246, 0.3); border-radius: 10px; padding: 14px 18px;">
                        <div style="display: flex; justify-content: space-between; margin-bottom: 6px;">
                            <span style="font-weight: 700; color: #60a5fa; font-size: 14px;">🛡️ KURAL 1: Katı Pozisyon Büyüklüğü & Kasa Koruması</span>
                            <span style="font-size: 11px; background: rgba(59, 130, 246, 0.15); color: #93c5fd; padding: 2px 8px; border-radius: 4px;">Zorunlu Limit</span>
                        </div>
                        <p style="margin: 0; font-size: 13px; color: #cbd5e1; line-height: 1.5;">
                            Tek bir pozisyona toplam kasanın <strong>maksimum %15'i</strong> veya <strong>en fazla $30 USD (₺1.200 TL)</strong> ayrılabilir. Kasa en az 4-5 slota bölünür. Olası bir %2 stop durumunda kasadan yalnızca ~$0.50 cent eksilir.
                        </p>
                    </div>

                    <div style="background: rgba(15, 23, 42, 0.7); border: 1px solid rgba(245, 158, 11, 0.3); border-radius: 10px; padding: 14px 18px;">
                        <div style="display: flex; justify-content: space-between; margin-bottom: 6px;">
                            <span style="font-weight: 700; color: #fbbf24; font-size: 14px;">🎯 KURAL 2: Anti-FOMO & Tepe Alım Kalkanı</span>
                            <span style="font-size: 11px; background: rgba(245, 158, 11, 0.15); color: #fde68a; padding: 2px 8px; border-radius: 4px;">Filtre</span>
                        </div>
                        <p style="margin: 0; font-size: 13px; color: #cbd5e1; line-height: 1.5;">
                            Son 5 dakikada %3.5'ten fazla fırlamış coinlere piyasa emriyle (Market Order) girilmez. Mum üst fitil oranı (satıcı baskısı) <strong>&le; 0.35</strong> olmalıdır. Yalnızca dip kırılımları ve sağlıklı konsolidasyonlar işleme alınır.
                        </p>
                    </div>

                    <div style="background: rgba(15, 23, 42, 0.7); border: 1px solid rgba(239, 68, 68, 0.3); border-radius: 10px; padding: 14px 18px;">
                        <div style="display: flex; justify-content: space-between; margin-bottom: 6px;">
                            <span style="font-weight: 700; color: #f87171; font-size: 14px;">🛑 KURAL 3: BTC Makro Rejim & RSI Kalkanı</span>
                            <span style="font-size: 11px; background: rgba(239, 68, 68, 0.15); color: #fca5a5; padding: 2px 8px; border-radius: 4px;">Piyasa Kilidi</span>
                        </div>
                        <p style="margin: 0; font-size: 13px; color: #cbd5e1; line-height: 1.5;">
                            Bitcoin 1 saatlik grafikte <strong>RSI &lt; 42</strong> ise, EMA200 altındaysa veya 15 dakikalık ani düşüş (-%1.0+) varsa altcoinlerde yeni alımlar otomatik olarak kilitlenir ve serbest nakit (%85+) korunur.
                        </p>
                    </div>

                    <div style="background: rgba(15, 23, 42, 0.7); border: 1px solid rgba(16, 185, 129, 0.3); border-radius: 10px; padding: 14px 18px;">
                        <div style="display: flex; justify-content: space-between; margin-bottom: 6px;">
                            <span style="font-weight: 700; color: #34d399; font-size: 14px;">📊 KURAL 4: Kesin Borsa İşlem Defteri & Net Kâr/Zarar</span>
                            <span style="font-size: 11px; background: rgba(16, 185, 129, 0.15); color: #a7f3d0; padding: 2px 8px; border-radius: 4px;">Şeffaf Muhasebe</span>
                        </div>
                        <p style="margin: 0; font-size: 13px; color: #cbd5e1; line-height: 1.5;">
                            Pozisyon maliyetleri hafıza kaybından etkilenmemesi için doğrudan Binance resmi işlem defterinden (<code>/myTrades</code>) son gerçek alış fiyatıyla senkronize edilir. Kâr ve zararlar %0.20 komisyon düşülerek net hesaplanır.
                        </p>
                    </div>

                    <div style="background: rgba(15, 23, 42, 0.7); border: 1px solid rgba(168, 85, 247, 0.3); border-radius: 10px; padding: 14px 18px;">
                        <div style="display: flex; justify-content: space-between; margin-bottom: 6px;">
                            <span style="font-weight: 700; color: #c084fc; font-size: 14px;">🤖 KURAL 5: Yeni Nesil 3'lü Ajan Konseyi</span>
                            <span style="font-size: 11px; background: rgba(168, 85, 247, 0.15); color: #e9d5ff; padding: 2px 8px; border-radius: 4px;">Yapay Zeka Mimarisi</span>
                        </div>
                        <p style="margin: 0; font-size: 13px; color: #cbd5e1; line-height: 1.5;">
                            • 🎯 <strong>Moderatör:</strong> <code>google/gemini-3.7-flash</code> (Yıldırım hızında analiz)<br>
                            • 🛠️ <strong>Kodlama & Mimari:</strong> <code>stealth/ox-alpha</code> (İleri seviye algoritmik infaz)<br>
                            • 🛡️ <strong>Risk Denetçisi:</strong> <code>z-ai/glm-5.2</code> (Bağımsız güvenlik ve sermaye denetimi)
                        </p>
                    </div>
                </div>

                <!-- VERSİYON TARİHÇESİ (CHANGELOG) -->
                <div style="border-top: 1px solid var(--border); padding-top: 18px;">
                    <h3 style="font-size: 15px; color: #94a3b8; margin-bottom: 12px;">📅 Versiyon Geçmişi & Değişiklik Günlüğü:</h3>
                    <div style="display: flex; flex-direction: column; gap: 8px; font-size: 12px;">
                        <div style="display: flex; gap: 10px; align-items: baseline;">
                            <span style="color: #22c55e; font-weight: 700; min-width: 85px;">v2.1 (25 Ağu)</span>
                            <span style="color: #cbd5e1;">4 Kurumsal Borsacı kuralı devreye alındı, pozisyon bütçesi max $30 / %15 ile sınırlandı, BTC RSI & Anti-FOMO kalkanı eklendi, Gemini 3.7 Flash + OX ALPHA + GLM 5.2 ajan konseyi aktif edildi.</span>
                        </div>
                        <div style="display: flex; gap: 10px; align-items: baseline;">
                            <span style="color: #60a5fa; font-weight: 700; min-width: 85px;">v2.0 (22 Ağu)</span>
                            <span style="color: #cbd5e1;">Binance TR + Binance Global çift borsa altyapısı, 24 saatlik otomatik BNB toz bakiyeleri temizleme motoru.</span>
                        </div>
                        <div style="display: flex; gap: 10px; align-items: baseline;">
                            <span style="color: #94a3b8; font-weight: 700; min-width: 85px;">v1.0 (21 Ağu)</span>
                            <span style="color: #cbd5e1;">İlk otonom LangGraph al-sat mimarisi, Telegram botu ve gerçek zamanlı bakiye takip modülü.</span>
                        </div>
                    </div>
                </div>
            </div>
        </div>

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
    from db import get_system_setting, get_strategy_config
    trailing_stop_enabled = bool(get_system_setting("trailing_stop_enabled", True))
    trailing_checked = "checked" if trailing_stop_enabled else ""
    trailing_status = "AÇIK" if trailing_stop_enabled else "KAPALI"
    trailing_color = "var(--success)" if trailing_stop_enabled else "var(--danger)"

    shield_enabled = bool(get_system_setting("v21_security_shield_enabled", True))
    shield_checked = "checked" if shield_enabled else ""
    shield_status = "AÇIK" if shield_enabled else "KAPALI"
    shield_color = "var(--success)" if shield_enabled else "var(--danger)"

    strat_cfg = get_strategy_config(use_cache=False)
    active_preset = strat_cfg.get("active_preset", "v21_smart_armor")
    if active_preset == "agile_21_august":
        active_preset = "v21_balanced"
    elif active_preset == "defensive_22_august":
        active_preset = "v21_defensive"

    strat_spike = float(strat_cfg.get("volume_spike_multiplier", 1.15))
    strat_minvol = float(strat_cfg.get("min_volume_usd", 2500.0))
    strat_maxgain = float(strat_cfg.get("max_recent_gain_24h", 60.0))
    strat_minscore = float(strat_cfg.get("min_ai_score", 4.5))
    strat_maxbudget = float(strat_cfg.get("max_budget_percent", 25.0))
    strat_trailcallback = float(strat_cfg.get("trailing_callback_pct", 0.6))

    sel_armor = "selected" if active_preset in ["v21_smart_armor", "smart_armor"] else ""
    sel_balanced = "selected" if active_preset == "v21_balanced" else ""
    sel_agile = "selected" if active_preset == "v21_agile" else ""
    sel_def = "selected" if active_preset == "v21_defensive" else ""
    sel_v20 = "selected" if active_preset == "v20_classic" else ""
    sel_v10 = "selected" if active_preset == "v10_legacy" else ""
    sel_cust = "selected" if active_preset == "custom" else ""
    
    if active_preset in ["v21_smart_armor", "smart_armor"]:
        strat_badge_text = f"🛡️ v2.1 3 Kademeli Akıllı Zırh ({strat_spike}x) Aktif"
    elif active_preset == "v21_balanced":
        strat_badge_text = f"⚖️ v2.1 Kurumsal Dengeli ({strat_spike}x) Aktif"
    elif active_preset == "v21_agile":
        strat_badge_text = f"🚀 v2.1 Hızlı Momentum ({strat_spike}x) Aktif"
    elif active_preset == "v21_defensive":
        strat_badge_text = f"🏰 v2.1 Yüksek Güvenlik ({strat_spike}x) Aktif"
    elif active_preset == "v20_classic":
        strat_badge_text = f"⚡ v2.0 Klasik Serbest ({strat_spike}x) Aktif"
    elif active_preset == "v10_legacy":
        strat_badge_text = f"🏛️ v1.0 Orijinal Klasik ({strat_spike}x) Aktif"
    else:
        strat_badge_text = f"⚙️ v2.1 Özel Profil ({strat_spike}x) Aktif"

    res_html = (
        html_content
        .replace("__SSR_TENANTS_DATA__", tenants_ssr_json)
        .replace("__SSR_TENANTS_HTML__", tenants_ssr_html)
        .replace("__SSR_LOGS_HTML__", logs_ssr_html)
        .replace("__TENANT_COUNT__", f"{len(clean)} Aktif")
        .replace("__TRAILING_CHECKED__", trailing_checked)
        .replace("__TRAILING_STATUS__", trailing_status)
        .replace("__TRAILING_COLOR__", trailing_color)
        .replace("__SHIELD_CHECKED__", shield_checked)
        .replace("__SHIELD_STATUS__", shield_status)
        .replace("__SHIELD_COLOR__", shield_color)
        .replace("__STRAT_BADGE__", strat_badge_text)
        .replace("__STRAT_SEL_ARMOR__", sel_armor)
        .replace("__STRAT_SEL_BALANCED__", sel_balanced)
        .replace("__STRAT_SEL_AGILE__", sel_agile)
        .replace("__STRAT_SEL_DEF__", sel_def)
        .replace("__STRAT_SEL_V20__", sel_v20)
        .replace("__STRAT_SEL_V10__", sel_v10)
        .replace("__STRAT_SEL_CUST__", sel_cust)
        .replace("__STRAT_SPIKE__", str(strat_spike))
        .replace("__STRAT_MINVOL__", str(int(strat_minvol)))
        .replace("__STRAT_MAXGAIN__", str(strat_maxgain))
        .replace("__STRAT_MINSCORE__", str(strat_minscore))
        .replace("__STRAT_MAXBUDGET__", str(strat_maxbudget))
        .replace("__STRAT_TRAILCALLBACK__", str(strat_trailcallback))
    )
    return HTMLResponse(content=res_html)

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app_api, host="0.0.0.0", port=8000)
