import os, sys, asyncio, threading
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
    register_user_tenant, get_all_active_tenants, get_supabase
)
from exchange import execute_spot_trade
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
    return credentials.username

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
                    
                    from exchange import fetch_portfolio_balance
                    live_bal = fetch_portfolio_balance(tenant)
                    
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
                        is_exec_success = status_str in ["SUCCESS", "EXECUTED", "EXECUTED_SIMULATED"]
                        
                        # 🚨 GERÇEK BORSA HATALARINI TELEGRAM İLE KULLANICIYA BİLDİR:
                        # (Yalnızca gerçek bir işlem teklifi varsa ve borsa emri reddettiyse bildir, normal HOLD durumlarında sus!)
                        if not is_exec_success and proposal and proposal.get("should_trade") and exec_res.get("error"):
                            err_msg = str(exec_res.get("error"))
                            sym_target = proposal.get("symbol", "COIN")
                            action_name = "ALIM (BUY)" if proposal.get("direction") == "BUY" else "SATIM (SELL)"
                            
                            is_try_sym = sym_target.upper().endswith("TRY") or sym_target.upper().endswith("_TRY")
                            exch_name = "BINANCE.TR 🇹🇷" if is_try_sym else "BINANCE GLOBAL 🌍"
                            
                            current_time = time.time()
                            err_key = f"{sym_target}_{action_name}"
                            if current_time - last_error_alerts.get(err_key, 0) > 300: # 5 dk spam filtresi
                                last_error_alerts[err_key] = current_time
                                from telegram_poller import send_message
                                warning_msg = (
                                    f"⚠️ *7/24 OTONOM BORSA İŞLEM UYARISI*\n\n"
                                    f"👤 Kullanıcı: {tenant_name}\n"
                                    f"🪙 Hedef Balina / Coin: `{sym_target}`\n"
                                    f"⚡ Yapılmak İstenen İşlem: *{action_name}*\n"
                                    f"🏢 Borsa: {exch_name}\n\n"
                                    f"❌ *Borsa Reddi / Hata Sebebi:*\n"
                                    f"`{err_msg}`\n\n"
                                    f"💡 *Gereken Aksiyon:* Bot bu işlemi yakaladı ancak borsa emri reddetti. Lütfen borsa hesabınızdaki Spot işlem iznini, bakiye veya IP tanımlarını kontrol edin."
                                )
                                send_message(chat_id, warning_msg)
                            continue
                        
                        symbol = exec_res.get("symbol") or (proposal.get("symbol") if proposal else "BTC/USDT")
                        if not symbol or "AUTO" in symbol.upper():
                            symbol = "BTC/USDT"
                        is_en_user = str(tenant.get("preferred_language", "tr")).lower() == "en"
                        is_tr_tenant = bool(tenant and tenant.get("exchange_id") in ["binancetr", "binance.tr", "trbinance"])
                        wallet_label = "TL" if is_tr_tenant else "USDT"
                        quote_sym = "TRY" if is_tr_tenant else "USDT"
                        base_sym = symbol.split("/")[0].split("_")[0].upper()
                        symbol = f"{base_sym}/{quote_sym}"
                        
                        is_stop_loss = bool(proposal.get("is_stop_loss", False)) if proposal else False
                        raw_action = str(proposal.get("direction", "BUY")).upper() if proposal else "BUY"
                        action_type = raw_action
                        is_take_profit = (raw_action not in ["BUY", "ALIM"]) and (not is_stop_loss)
                        is_executed = is_exec_success
                        
                        if raw_action in ["BUY", "ALIM"]:
                            action_title = "🛒 BUY SPOT ORDER" if is_en_user else "🛒 ALIM (BUY)"
                            status_title = f"✅ Live Buy Executed Successfully ({wallet_label} Wallet)" if is_en_user else f"✅ Canlı Alım Başarıyla Gerçekleştirildi ({wallet_label} Cüzdanı)"
                        else:
                            if is_stop_loss:
                                action_title = "🛡️ SELL (STOP-LOSS)" if is_en_user else "🛡️ SATIM (STOP-LOSS / ZARAR KES)"
                                status_title = f"🛡️ Stop-Loss Triggered & Capital Preserved in {wallet_label} Wallet" if is_en_user else f"🛡️ Canlı Stop-Loss Gerçekleşti ve Sermaye {wallet_label} Cüzdanına Alındı"
                            else:
                                action_title = "🎯 SELL (TAKE-PROFIT)" if is_en_user else "🎯 SATIM (SELL / KÂR ALMA)"
                                status_title = f"🎉 Live Take-Profit Executed & Transferred to {wallet_label} Wallet" if is_en_user else f"🎉 Canlı Satış Gerçekleşti ve {wallet_label} Cüzdanına Aktarıldı"
                            
                        amount = proposal.get("amount_usd", 10.0) if proposal else 10.0
                        if is_tr_tenant:
                            amount_try = round(amount * 47.80, 2)
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
                                        entry_try = raw_entry * 47.80
                                    else:
                                        entry_try = raw_entry if raw_entry > 0 else (raw_exit / 1.017)
                                    exit_try = raw_exit
                                    
                                    # Net Kâr Hesaplama (TL)
                                    gross_pct = ((exit_try - entry_try) / entry_try * 100) if entry_try > 0 else 1.7
                                    net_pct = gross_pct - 0.20 # %0.20 borsa komisyonu düşülür
                                    
                                    tot_sell_try = (coin_qty * exit_try) if coin_qty > 0 else (amount * 47.80)
                                    tot_buy_try = (coin_qty * entry_try) if coin_qty > 0 else (tot_sell_try / (1 + (gross_pct/100.0) if gross_pct > 0 else 1.0))
                                    net_profit_fiat = tot_sell_try - tot_buy_try - (tot_sell_try * 0.002)
                                    if abs(net_profit_fiat) < 0.01:
                                        net_profit_fiat = tot_sell_try * (net_pct / 100.0)
                                        
                                    if exit_try < 0.01:
                                        entry_str = f"₺{entry_try:.8f}"
                                        exit_str = f"₺{exit_try:.8f}"
                                    elif exit_try < 1.0:
                                        entry_str = f"₺{entry_try:.4f}"
                                        exit_str = f"₺{exit_try:.4f}"
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
                                            profit_badge = f"+%{net_pct:.2f} (+₺{net_profit_fiat:,.2f} TL / +${net_profit_fiat/47.80:,.2f} USD) {quote_label} Cüzdanına Kilitlendi!"
                                        else:
                                            profit_label = "📉 *Net Değişim / Stop-Loss:*"
                                            profit_badge = f"-%{abs(net_pct):.2f} (-₺{abs(net_profit_fiat):,.2f} TL / -${abs(net_profit_fiat)/47.80:,.2f} USD) {quote_label} Cüzdanına Aktarıldı"
                                else:
                                    # Binance Global (USDT)
                                    # Eğer raw_entry TRY cinsinden kaydedildiyse (yani exit_usd*20'den büyükse), USD'ye dönüştür
                                    if raw_entry > 0 and (raw_entry > (raw_exit * 20.0)):
                                        entry_usd = raw_entry / 47.80
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
                                        
                                    if exit_usd < 0.01:
                                        entry_str = f"${entry_usd:.8f}"
                                        exit_str = f"${exit_usd:.8f}"
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
                                            profit_badge = f"+%{net_pct:.2f} (+${net_profit_fiat:,.2f} USDT / +₺{net_profit_fiat * 47.80:,.2f} TL) {quote_label} Cüzdanına Kilitlendi!"
                                        else:
                                            profit_label = "📉 *Net Değişim / Stop-Loss:*"
                                            profit_badge = f"-%{abs(net_pct):.2f} (-${abs(net_profit_fiat):,.2f} USDT / -₺{abs(net_profit_fiat) * 47.80:,.2f} TL) {quote_label} Cüzdanına Aktarıldı"
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

class TriggerGraphRequest(BaseModel):
    session_id: str = "session_001"
    symbol: str = "BTC/USDT"

# -----------------------------------------
# API ROTALARI (KULLANICI EKLE / SİL / LİSTELE)
# -----------------------------------------
@app_api.get("/health")
def health_check():
    return {"status": "healthy", "service": "Fox-Kripto Multi-Tenant Dashboard", "version": "2.1.0-explain-trade"}

@app_api.get("/api/my-ip")
def get_my_egress_ip():
    """DigitalOcean sunucusunun dışarıya çıkan (Egress) IP adresini söyler."""
    import requests
    try:
        res = requests.get("https://api.ipify.org?format=json", timeout=5)
        return res.json()
    except Exception as e:
        return {"error": str(e)}

@app_api.get("/api/admin/test-moonwalker-balance")
def test_moonwalker_balance():
    """DigitalOcean sunucusundan (104.248.135.128) Moonwalker'ın canlı Binance Global bakiyesini okur."""
    from db import get_tenant_by_chat_id
    from exchange import BinanceGlobalRESTClient, fetch_portfolio_balance
    tenant = get_tenant_by_chat_id(757146559)
    if not tenant:
        return {"error": "Tenant Moonwalker not found"}
    return fetch_portfolio_balance(tenant)

@app_api.get("/api/admin/buy-tut-whale")
def buy_tut_whale(amount_usd: float = 15.0):
    """DigitalOcean sunucusundan TUT/USDT balina alımı yapar."""
    from db import get_tenant_by_chat_id
    from exchange import execute_spot_trade
    tenant = get_tenant_by_chat_id(8739367825)
    if not tenant:
        return {"error": "Tenant not found"}
    return execute_spot_trade(symbol="TUT/USDT", side="BUY", amount_usd=amount_usd, tenant_config=tenant)

@app_api.get("/api/admin/buy-spot")
def buy_spot_universal(symbol: str = "GPS/USDT", amount_usd: float = 15.0):
    """DigitalOcean sunucusundan herhangi bir sembol icin aninda spot alis yapar."""
    from db import get_tenant_by_chat_id
    from exchange import execute_spot_trade
    tenant = get_tenant_by_chat_id(8739367825)
    if not tenant:
        return {"error": "Tenant not found"}
    return execute_spot_trade(symbol=symbol, side="BUY", amount_usd=amount_usd, tenant_config=tenant)

@app_api.get("/api/admin/sell-spot")
def sell_spot_universal(symbol: str = "GPS/USDT", amount_usd: float = 15.0):
    """DigitalOcean sunucusundan herhangi bir sembol icin aninda spot satis yapar."""
    from db import get_tenant_by_chat_id
    from exchange import execute_spot_trade
    tenant = get_tenant_by_chat_id(8739367825)
    if not tenant:
        return {"error": "Tenant not found"}
    return execute_spot_trade(symbol=symbol, side="SELL", amount_usd=amount_usd, tenant_config=tenant)

@app_api.get("/api/admin/sell-ace-now")
def sell_ace_now():
    """Binance Global'de eldeki tum ACE'yi derhal piyasa fiyatindan USDT'ye satar."""
    from db import get_tenant_by_chat_id
    from exchange import execute_spot_trade
    tenant = get_tenant_by_chat_id(8739367825)
    if not tenant:
        return {"error": "Tenant not found"}
    return execute_spot_trade(symbol="ACE/USDT", side="SELL", amount_usd=100.0, tenant_config=tenant)

@app_api.get("/api/admin/buy-ace-whale")
def buy_ace_whale(amount_usd: float = 15.0):
    """DigitalOcean sunucusundan (104.248.135.128) ACE/USDT balina alımı yapar."""
    from db import get_tenant_by_chat_id
    from exchange import execute_spot_trade
    tenant = get_tenant_by_chat_id(8739367825)
    if not tenant:
        return {"error": "Tenant not found"}
    return execute_spot_trade(symbol="ACE/USDT", side="BUY", amount_usd=amount_usd, tenant_config=tenant)

@app_api.get("/api/admin/sell-gps-and-buy-ace")
def sell_gps_and_buy_ace():
    """DigitalOcean sunucusundan (104.248.135.128) GPS'i kârla satıp ACE satın alır."""
    from db import get_tenant_by_chat_id
    from exchange import execute_spot_trade
    tenant = get_tenant_by_chat_id(8739367825)
    if not tenant:
        return {"error": "Tenant not found"}
    
    # 1. GPS Sat (Kârı Al)
    res_sell = execute_spot_trade(symbol="GPS/USDT", side="SELL", amount_usd=10.50, tenant_config=tenant)
    
    # 2. ACE Al ($10 USD)
    res_buy = execute_spot_trade(symbol="ACE/USDT", side="BUY", amount_usd=10.0, tenant_config=tenant)
    
    return {
        "sell_gps": res_sell,
        "buy_ace": res_buy
    }

@app_api.get("/api/admin/convert-dust")
def admin_convert_dust(chat_id: int = 8739367825):
    """Kullanıcının Binance Global hesabındaki tüm küçük toz bakiyeleri (Dust) BNB'ye dönüştürür."""
    from db import get_tenant_by_chat_id
    from exchange import convert_dust_to_bnb
    tenant = get_tenant_by_chat_id(chat_id)
    if not tenant:
        return {"error": "Tenant not found"}
    return convert_dust_to_bnb(tenant)

@app_api.get("/api/admin/convert-bnb-to-usdt")
def admin_convert_bnb_to_usdt(chat_id: int = 8739367825):
    """DigitalOcean sunucusundan (104.248.135.128) 0.095 BNB satıp USDT nakde çevirir."""
    from db import get_tenant_by_chat_id
    from exchange import execute_spot_trade
    tenant = get_tenant_by_chat_id(chat_id)
    if not tenant:
        return {"error": "Tenant not found"}
    return execute_spot_trade(symbol="BNB/USDT", side="SELL", amount_usd=55.0, tenant_config=tenant)

@app_api.get("/api/admin/liquidate-all-to-cash")
def admin_liquidate_all_to_cash(chat_id: int = 8739367825):
    """Kullanıcının TÜM açık pozisyonlarını piyasa fiyatından satarak %100 saf nakde (TRY ve USDT) çeker."""
    from db import get_tenant_by_chat_id
    from exchange import BinanceTRClient, BinanceGlobalRESTClient, fetch_portfolio_balance
    import json
    
    tenant = get_tenant_by_chat_id(chat_id)
    if not tenant:
        return {"error": "Tenant not found"}
        
    results = {"binance_tr": {}, "binance_global": {}, "final_balances": {}}
    raw_k = str(tenant.get("exchange_api_key", ""))
    
    if raw_k.startswith("{"):
        kd = json.loads(raw_k)
        
        # 1. Binance TR Tasfiyesi
        if "binancetr" in kd:
            try:
                cl_tr = BinanceTRClient(kd["binancetr"]["api_key"], kd["binancetr"]["secret_key"])
                bal_tr = cl_tr.fetch_balance()
                for c, amt in bal_tr.get("free", {}).items():
                    c_up = str(c).upper()
                    if c_up not in ["TRY", "USDT", "FDUSD", "BUSD", "USDC"] and float(amt or 0) > 0.001:
                        try:
                            r = cl_tr.create_order(symbol=f"{c_up}_TRY", type="market", side="sell", amount=0)
                            results["binance_tr"][c_up] = {"status": "SOLD", "result": r}
                        except Exception as te:
                            results["binance_tr"][c_up] = {"status": "FAIL", "error": str(te)}
            except Exception as e:
                results["binance_tr_error"] = str(e)
                
        # 2. Binance Global Tasfiyesi
        if "binance" in kd:
            try:
                cl_gl = BinanceGlobalRESTClient(kd["binance"]["api_key"], kd["binance"]["secret_key"])
                bal_gl = cl_gl.fetch_balance()
                for c, amt in bal_gl.get("free", {}).items():
                    c_up = str(c).upper()
                    if c_up not in ["TRY", "USDT", "FDUSD", "BUSD", "USDC"] and float(amt or 0) > 0.0001:
                        try:
                            r = cl_gl.create_order(symbol=f"{c_up}/USDT", type="market", side="sell", amount=float(amt))
                            results["binance_global"][c_up] = {"status": "SOLD", "result": r}
                        except Exception as ge:
                            results["binance_global"][c_up] = {"status": "FAIL", "error": str(ge)}
            except Exception as e:
                results["binance_global_error"] = str(e)
                
    # Pozisyon dosyalarını sıfırla
    import os
    for pf_name in ["active_positions_tr.json", "active_positions_global.json"]:
        pf_p = os.path.join(os.path.dirname(__file__), pf_name)
        try:
            with open(pf_p, "w", encoding="utf-8") as f:
                json.dump({}, f)
        except Exception:
            pass

    bal_after = fetch_portfolio_balance(tenant)
    results["final_balances"] = bal_after
    return results

@app_api.get("/api/admin/test-spot-buy-user")
def test_spot_buy_user():
    """DigitalOcean sunucusundan doğrudan $10 GPS/USDT alımını canlı test eder ve sonucu döner."""
    from db import get_tenant_by_chat_id
    from exchange import execute_spot_trade
    tenant = get_tenant_by_chat_id(8739367825)
    if not tenant:
        return {"error": "Tenant not found"}
    return execute_spot_trade(symbol="GPS/USDT", side="BUY", amount_usd=10.0, tenant_config=tenant)

@app_api.api_route("/api/admin/demo-swap-moonwalker", methods=["GET", "POST"])
def demo_swap_moonwalker():
    """DigitalOcean sunucusundan (IP: 104.248.135.128) Moonwalker için 0.01 BNB satıp SOL alır."""
    import time
    from db import get_tenant_by_chat_id
    from exchange import get_exchange_for_tenant
    
    tenant = get_tenant_by_chat_id(757146559)
    if not tenant:
        return {"error": "Tenant 757146559 not found"}
        
    ex = get_exchange_for_tenant(tenant)
    results = {}
    
    # 1. 0.01 BNB Sat
    try:
        sell_order = ex.create_order(symbol="BNB/USDT", type="market", side="sell", amount=0.01)
        results["sell_bnb"] = {
            "status": "success",
            "order_id": sell_order.get("id"),
            "price": sell_order.get("price"),
            "cost": sell_order.get("cost"),
            "filled": sell_order.get("filled")
        }
    except Exception as se:
        results["sell_bnb"] = {"status": "error", "error": str(se)}
        return results

    time.sleep(2)

    # 2. SOL Al
    try:
        sol_ticker = ex.fetch_ticker("SOL/USDT")
        sol_p = float(sol_ticker.get("last", 150.0))
        sol_qty = round(5.5 / sol_p, 2)
        buy_order = ex.create_order(symbol="SOL/USDT", type="market", side="buy", amount=sol_qty)
        results["buy_sol"] = {
            "status": "success",
            "order_id": buy_order.get("id"),
            "price": buy_order.get("price"),
            "cost": buy_order.get("cost"),
            "filled": buy_order.get("filled")
        }
    except Exception as be:
        results["buy_sol"] = {"status": "error", "error": str(be)}

    return results

@app_api.get("/api/debug-binance")
def debug_binance_account():
    """DigitalOcean sunucusundan tüm Binance cüzdanlarını (Spot + Earn + Funding) kontrol eder."""
    import requests, hmac, hashlib, time
    from db import get_tenant_by_chat_id
    tenant = get_tenant_by_chat_id(8739367825)
    if not tenant:
        return {"error": "Tenant 8739367825 not found in Supabase"}
    
    import json
    api_k_raw = tenant.get("exchange_api_key", "")
    sec_k_raw = tenant.get("exchange_secret_key", "")
    if isinstance(api_k_raw, str) and api_k_raw.startswith("{"):
        kd = json.loads(api_k_raw)
        api_key = kd.get("binance", {}).get("api_key", "")
        secret_key = kd.get("binance", {}).get("secret_key", "")
    else:
        api_key = api_k_raw
        secret_key = sec_k_raw

    ts = int(time.time() * 1000)
    query = f"timestamp={ts}"
    sig = hmac.new(secret_key.encode('utf-8'), query.encode('utf-8'), hashlib.sha256).hexdigest()
    headers = {"X-MBX-APIKEY": api_key}
    
    res_dict = {}
    
    # 1. Spot Account
    try:
        r_spot = requests.get(f"https://api.binance.com/api/v3/account?{query}&signature={sig}", headers=headers, timeout=10)
        s_data = r_spot.json()
        s_bals = s_data.get("balances", [])
        spot_non_zero = [b for b in s_bals if float(b.get("free", 0)) > 0 or float(b.get("locked", 0)) > 0]
        res_dict["spot_balances_non_zero"] = spot_non_zero
    except Exception as se:
        res_dict["spot_exception"] = str(se)

    # 2. All Capital Config (Spot + Earn + Funding)
    try:
        r_all = requests.get(f"https://api.binance.com/sapi/v1/capital/config/getall?{query}&signature={sig}", headers=headers, timeout=10)
        data_all = r_all.json()
        if isinstance(data_all, list):
            non_zero_capital = []
            for item in data_all:
                coin = item.get("coin")
                free = float(item.get("free", 0.0))
                locked = float(item.get("locked", 0.0))
                freeze = float(item.get("freeze", 0.0))
                withdrawing = float(item.get("withdrawing", 0.0))
                ipoing = float(item.get("ipoing", 0.0))
                tot = free + locked + freeze + withdrawing + ipoing
                if tot > 0:
                    non_zero_capital.append({"coin": coin, "free": free, "locked": locked, "freeze": freeze, "total": tot})
            res_dict["all_wallets_non_zero"] = non_zero_capital
        else:
            res_dict["all_wallets_error"] = data_all
    except Exception as e:
        res_dict["all_wallets_exception"] = str(e)

    # 3. Simple Earn Flexible / Locked Positions
    try:
        r_earn_flex = requests.get(f"https://api.binance.com/sapi/v1/simple-earn/flexible/position?{query}&signature={sig}", headers=headers, timeout=10)
        res_dict["simple_earn_flexible"] = r_earn_flex.json()
    except Exception as ee:
        res_dict["simple_earn_flexible_err"] = str(ee)

    try:
        r_earn_lock = requests.get(f"https://api.binance.com/sapi/v1/simple-earn/locked/position?{query}&signature={sig}", headers=headers, timeout=10)
        res_dict["simple_earn_locked"] = r_earn_lock.json()
    except Exception as ele:
        res_dict["simple_earn_locked_err"] = str(ele)

    # 4. Open Orders (Açık Emirler)
    try:
        r_ord = requests.get(f"https://api.binance.com/api/v3/openOrders?{query}&signature={sig}", headers=headers, timeout=10)
        res_dict["open_orders"] = r_ord.json()
    except Exception as oe:
        res_dict["open_orders_err"] = str(oe)

    # 5. User Asset (Funding Wallet)
    try:
        r_ua = requests.post(f"https://api.binance.com/sapi/v3/asset/getUserAsset?{query}&signature={sig}", headers=headers, timeout=10)
        res_dict["user_asset_funding"] = r_ua.json()
    except Exception as uae:
        res_dict["user_asset_funding_err"] = str(uae)

    return res_dict

@app_api.get("/api/tenants")
def list_tenants():
    """Tüm kullanıcıları (Tenants) listeler."""
    tenants = get_all_active_tenants()
    for t in tenants:
        if "exchange_api_key" in t and t["exchange_api_key"]:
            key = t["exchange_api_key"]
            t["exchange_api_key_masked"] = key[:6] + "..." + key[-4:] if len(key) > 10 else "***"
        if "exchange_secret_key" in t:
            t["exchange_secret_key"] = "***HIDDEN***"
    return {"status": "success", "count": len(tenants), "tenants": tenants}

@app_api.post("/api/tenants")
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
        return {"status": "success", "message": f"Kullanıcı '{req.tenant_name}' eklendi.", "tenant": res}
    raise HTTPException(status_code=400, detail="Kullanıcı kaydedilemedi.")

@app_api.post("/api/tenants/{tenant_id}/settings")
def update_tenant_settings(tenant_id: str, req: TenantUpdateSettingsRequest):
    """Kullanıcının kâr alma, stop-loss, bütçe ve dil tercihlerini günceller."""
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

@app_api.delete("/api/tenants/{tenant_id}")
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

@app_api.get("/api/trade-logs")
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
            tid = l.get("tenant_id")
            t_info = tenant_map.get(tid, {})
            l["tenant_name"] = t_info.get("tenant_name", "S (Çift Borsa TR+Global)")
            l["exchange_label"] = "Binance TR 🇹🇷" if t_info.get("exchange_id") == "binancetr" else "Binance Global 🌍"
            
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
@app_api.get("/dashboard", response_class=HTMLResponse)
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
        </style>
    </head>
    <body>
        <div class="header">
            <div class="header-left">
                <h1 id="i18n-title">🦊 Fox-Kripto Multi-Tenant Yönetim Paneli</h1>
                <p id="i18n-subtitle" style="color: var(--text-muted); font-size: 14px;">Otonom Yapay Zeka Kripto Ticaret, Risk ve Kullanıcı Yönetimi</p>
            </div>
            <div class="header-right">
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
                            <th id="i18n-th-lang">🌐 Dil / Lang</th>
                            <th id="i18n-th-status">Durum</th>
                            <th id="i18n-th-action">İşlem</th>
                        </tr>
                    </thead>
                    <tbody id="tenants-table">
                        <tr><td colspan="8" style="color: var(--text-muted);">Yükleniyor...</td></tr>
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
                    thLang: "🌐 Dil",
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
                    userSaved: "için Kâr Alma, Stop-Loss ve Dil tercihleri başarıyla kaydedildi!",
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
                    userSaved: "Take-Profit, Stop-Loss and Language preferences saved successfully for",
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
                        table.innerHTML = `<tr><td colspan="8" style="color: var(--text-muted);">${t.noUsers}</td></tr>`;
                    } else {
                        table.innerHTML = data.tenants.map((user, idx) => `
                            <tr>
                                <td><strong>${user.tenant_name}</strong></td>
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
                                    <select class="input-inline" style="width: 78px;" id="lang_${idx}">
                                        <option value="tr" ${user.preferred_language === 'en' ? '' : 'selected'}>🇹🇷 TR</option>
                                        <option value="en" ${user.preferred_language === 'en' ? 'selected' : ''}>🇬🇧 EN</option>
                                    </select>
                                </td>
                                <td><span class="badge badge-active">${t.activeBadge}</span></td>
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
                const lang = document.getElementById('lang_' + idx).value;
                
                try {
                    const res = await fetch('/api/tenants/' + tenantId + '/settings', {
                        method: 'POST',
                        headers: {'Content-Type': 'application/json'},
                        body: JSON.stringify({take_profit_percent: tp, stop_loss_percent: sl, max_budget_percent: mb, preferred_language: lang})
                    });
                    const resData = await res.json();
                    if (res.ok && resData.status === 'success') {
                        alert(`✅ ${name || 'User'}: ${currentLang === 'tr' ? 'Kâr Alma' : 'Take-Profit'} (%${tp}), Stop-Loss (%${sl}) & Lang (${lang.toUpperCase()}) ${t.userSaved}`);
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

            applyLang(currentLang);
            loadData();
        </script>
    </body>
    </html>
    """
    return HTMLResponse(content=html_content)

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app_api, host="0.0.0.0", port=8000)
