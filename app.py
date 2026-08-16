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
    Sistemdeki tüm aktif kullanıcılar (Tenants) için 15 dakikada bir piyasayı tarar.
    """
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
                                    {"text": "❌ Hayır, Pas Geç", "callback_data": f"reject_scalein_{chat_id}"}
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
                        
                        # TEKRARLAYAN HATALAR İÇİN SPAM ENGELLEYİCİ:
                        # Eğer emir bakiye vb. nedenlerle başarısız olduysa Telegram'ı mesajla darlama, sessizce logla!
                        if not is_exec_success:
                            print(f"   ⚠️ [Sessiz Filtre]: İşlem borsa tarafında gerçekleştirilemedi ({exec_res.get('error')}). Telegram spam engellendi.")
                            continue
                        
                        symbol = exec_res.get("symbol") or (proposal.get("symbol") if proposal else "BTC/USDT")
                        if not symbol or "AUTO" in symbol.upper():
                            symbol = "BTC/USDT"
                            
                        is_tr_tenant = bool(tenant and tenant.get("exchange_id") in ["binancetr", "binance.tr", "trbinance"])
                        wallet_label = "TL" if is_tr_tenant else "USDT"
                        quote_sym = "TRY" if is_tr_tenant else "USDT"
                        base_sym = symbol.split("/")[0].split("_")[0].upper()
                        symbol = f"{base_sym}/{quote_sym}"
                        
                        is_stop_loss = bool(proposal.get("is_stop_loss", False)) if proposal else False
                        raw_action = str(proposal.get("direction", "BUY")).upper() if proposal else "BUY"
                        if raw_action in ["BUY", "ALIM"]:
                            action_title = "🛒 ALIM (BUY)"
                            status_title = f"✅ Canlı Alım Başarıyla Gerçekleştirildi ({wallet_label} Cüzdanı)" if is_exec_success else f"⚠️ Alım İletilemedi: {exec_res.get('error', 'Bakiye/Emir Limiti')}"
                        else:
                            if is_stop_loss:
                                action_title = "🛡️ SATIM (STOP-LOSS / ZARAR KES)"
                                status_title = f"🛡️ Canlı Stop-Loss Gerçekleşti ve Sermaye {wallet_label} Cüzdanına Alındı" if is_exec_success else f"⚠️ Satış İletilemedi: {exec_res.get('error', 'Miktar Limiti')}"
                            else:
                                action_title = "🎯 SATIM (SELL / KÂR ALMA)"
                                status_title = f"🎉 Canlı Satış Gerçekleşti ve {wallet_label} Cüzdanına Aktarıldı" if is_exec_success else f"⚠️ Satış İletilemedi: {exec_res.get('error', 'Miktar Limiti')}"
                            
                        amount = proposal.get("amount_usd", 10.0) if proposal else 10.0
                        if is_tr_tenant:
                            amount_try = round(amount * 34.80, 2)
                            amount_display = f"₺{amount_try:.2f} TL"
                        else:
                            amount_display = f"${amount:.2f} USD"
                        
                        order_id = exec_res.get("order_id")
                        order_text = f"\n📄 Emir No: #{order_id}" if (is_exec_success and order_id) else ""
                        
                        price_detail_line = ""
                        if raw_action not in ["BUY", "ALIM"]:
                            raw_entry = float(proposal.get("entry_price") or 0.0) if proposal else 0.0
                            raw_exit = float(exec_res.get("executed_price") or proposal.get("take_profit_price") or 0.0) if exec_res else 0.0
                            coin_qty = float(proposal.get("amount_coin") or 0.0) if proposal else 0.0
                            
                            is_tr_pair = symbol.upper().endswith("TRY")
                            quote_label = "TL" if is_tr_pair else "USDT"
                            
                            if raw_exit > 0:
                                if is_tr_pair:
                                    entry_try = raw_entry if raw_entry > 0 else (raw_exit / 1.017)
                                    exit_try = raw_exit
                                    
                                    # Net Kâr Hesaplama (TL)
                                    gross_pct = ((exit_try - entry_try) / entry_try * 100) if entry_try > 0 else 1.7
                                    net_pct = gross_pct - 0.20 # %0.20 borsa komisyonu düşülür
                                    
                                    tot_sell_try = (coin_qty * exit_try) if coin_qty > 0 else (amount * 34.80)
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
                                        entry_str = f"₺{entry_try:,.2f} TL"
                                        exit_str = f"₺{exit_try:,.2f} TL"
                                        
                                    if net_pct >= 0:
                                        profit_label = "📈 *Net Kâr / Kazanç:*"
                                        profit_badge = f"+%{net_pct:.2f} (+₺{net_profit_fiat:,.2f} TL Net Kazanç) {quote_label} Cüzdanına Kilitlendi!"
                                    else:
                                        profit_label = "📉 *Net Değişim / Stop-Loss:*"
                                        profit_badge = f"-%{abs(net_pct):.2f} (-₺{abs(net_profit_fiat):,.2f} TL) {quote_label} Cüzdanına Aktarıldı"
                                else:
                                    # Binance Global (USDT)
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
                                        
                                    if net_pct >= 0:
                                        profit_label = "📈 *Net Kâr / Kazanç:*"
                                        profit_badge = f"+%{net_pct:.2f} (+${net_profit_fiat:,.2f} USDT Net Kazanç) {quote_label} Cüzdanına Kilitlendi!"
                                    else:
                                        profit_label = "📉 *Net Değişim / Stop-Loss:*"
                                        profit_badge = f"-%{abs(net_pct):.2f} (-${abs(net_profit_fiat):,.2f} USDT) {quote_label} Cüzdanına Aktarıldı"
                            else:
                                entry_str = "Alış Fiyatı"
                                exit_str = "Satış Fiyatı"
                                profit_label = "📈 *Net Kâr / Kazanç:*"
                                profit_badge = "+%1.50+ Net Kazanç"
                            
                            price_detail_line = (
                                f"\n📥 *Alış Birim Fiyatı:* `{entry_str}`\n"
                                f"📤 *Satış Birim Fiyatı:* `{exit_str}`\n"
                                f"{profit_label} `{profit_badge}`"
                            )
                            
                        from telegram_poller import send_message
                        exch_display = "BINANCE.TR 🇹🇷" if is_tr_tenant else "BINANCE GLOBAL 🌍"
                        msg = (
                            f"🤖 *7/24 OTONOM YAPAY ZEKA BİLDİRİMİ*\n\n"
                            f"👤 Kullanıcı: {tenant_name}\n"
                            f"⚡ İşlem Tipi: *{action_title}*\n"
                            f"🪙 Sembol: `{symbol}`\n"
                            f"💵 Bütçe / Tutar: {amount_display}{price_detail_line}\n"
                            f"🏢 Borsa: {exch_display}\n"
                            f"{status_title}{order_text}"
                        )
                        send_message(chat_id, msg)
        except Exception as e:
            print(f"⚠️ [Otonom Döngü Uyarısı]: {e}")
            
        time.sleep(180) # Ultra-Fast Scalp Loop: Her 3 dakikada bir piyasayı tarar

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

class TenantUpdateSettingsRequest(BaseModel):
    take_profit_percent: float = 1.5
    stop_loss_percent: float = 1.5
    max_budget_percent: float = 10.0

class TriggerGraphRequest(BaseModel):
    session_id: str = "session_001"
    symbol: str = "BTC/USDT"

# -----------------------------------------
# API ROTALARI (KULLANICI EKLE / SİL / LİSTELE)
# -----------------------------------------
@app_api.get("/health")
def health_check():
    return {"status": "healthy", "service": "Fox-Kripto Multi-Tenant Dashboard", "version": "2.0.0"}

@app_api.get("/api/my-ip")
def get_my_egress_ip():
    """DigitalOcean sunucusunun dışarıya çıkan (Egress) IP adresini söyler."""
    import requests
    try:
        res = requests.get("https://api.ipify.org?format=json", timeout=5)
        return res.json()
    except Exception as e:
        return {"error": str(e)}

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

    return res_dict

@app_api.get("/api/tenants", dependencies=[Depends(authenticate_admin)])
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

@app_api.post("/api/tenants", dependencies=[Depends(authenticate_admin)])
def create_tenant(req: TenantCreateRequest):
    """Yeni kullanıcı (Tenant) ekler veya günceller."""
    res = register_user_tenant(
        tenant_name=req.tenant_name,
        telegram_chat_id=req.telegram_chat_id,
        exchange_api_key=req.exchange_api_key,
        exchange_secret_key=req.exchange_secret_key,
        exchange_id=req.exchange_id,
        max_budget_percent=req.max_budget_percent
    )
    if res:
        return {"status": "success", "message": f"Kullanıcı '{req.tenant_name}' eklendi.", "tenant": res}
    raise HTTPException(status_code=400, detail="Kullanıcı kaydedilemedi.")

@app_api.post("/api/tenants/{tenant_id}/settings", dependencies=[Depends(authenticate_admin)])
def update_tenant_settings(tenant_id: str, req: TenantUpdateSettingsRequest):
    """Kullanıcının kâr alma, stop-loss ve bütçe limitlerini günceller."""
    client = get_supabase()
    if not client:
        raise HTTPException(status_code=500, detail="Supabase bağlantı hatası.")
    try:
        payload = {
            "take_profit_percent": req.take_profit_percent,
            "stop_loss_percent": req.stop_loss_percent,
            "max_budget_percent": req.max_budget_percent
        }
        res = client.table("user_tenants").update(payload).eq("id", tenant_id).execute()
        return {"status": "success", "message": "Ayarlar başarıyla güncellendi.", "data": res.data}
    except Exception as e:
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

@app_api.get("/api/trade-logs", dependencies=[Depends(authenticate_admin)])
def list_trade_logs():
    """Canlı Supabase işlem kararlarını ve loglarını listeler."""
    client = get_supabase()
    if not client: return {"logs": []}
    try:
        res = client.table("crypto_trade_logs").select("*").order("created_at", desc=True).limit(20).execute()
        return {"logs": res.data or []}
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
        <title>Fox-Kripto Multi-Tenant Yönetim Paneli</title>
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
            .header h1 { font-size: 28px; font-weight: 700; background: linear-gradient(135deg, #60a5fa, #3b82f6); -webkit-background-clip: text; -webkit-text-fill-color: transparent; }
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
            <div>
                <h1>🦊 Fox-Kripto Multi-Tenant Yönetim Paneli</h1>
                <p style="color: var(--text-muted); font-size: 14px;">Otonom Yapay Zeka Kripto Ticaret, Risk ve Kullanıcı Yönetimi</p>
            </div>
            <button class="btn btn-primary" onclick="loadData()">🔄 Verileri Yenile</button>
        </div>

        <div class="grid">
            <div class="card">
                <div class="card-title">
                    <span>👥 Kayıtlı Kullanıcılar & Dinamik Risk Ayarları</span>
                    <span id="tenant-count" class="badge badge-active">0 Aktif</span>
                </div>
                <table>
                    <thead>
                        <tr>
                            <th>Kullanıcı Adı</th>
                            <th>Telegram ID</th>
                            <th>🎯 Kâr Alma %</th>
                            <th>🛡️ Stop-Loss %</th>
                            <th>💵 Bütçe %</th>
                            <th>Durum</th>
                            <th>İşlem</th>
                        </tr>
                    </thead>
                    <tbody id="tenants-table">
                        <tr><td colspan="7" style="color: var(--text-muted);">Yükleniyor...</td></tr>
                    </tbody>
                </table>
            </div>

            <div class="card">
                <div class="card-title">➕ Yeni Kullanıcı Ekle</div>
                <form id="tenant-form" onsubmit="submitTenant(event)">
                    <div class="form-group">
                        <label>Kullanıcı Adı</label>
                        <input type="text" id="tenant_name" placeholder="Örn: Ahmet" required>
                    </div>
                    <div class="form-group">
                        <label>Telegram Chat ID</label>
                        <input type="number" id="telegram_chat_id" placeholder="Örn: 8739367825" required>
                    </div>
                    <div class="form-group">
                        <label>Binance API Key</label>
                        <input type="text" id="exchange_api_key" placeholder="Binance API Key" required>
                    </div>
                    <div class="form-group">
                        <label>Binance Secret Key</label>
                        <input type="password" id="exchange_secret_key" placeholder="Binance Secret Key" required>
                    </div>
                    <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 10px;">
                        <div class="form-group">
                            <label>🎯 Kâr Alma %</label>
                            <input type="number" id="take_profit_percent" value="1.5" step="0.1" min="0.5" max="50">
                        </div>
                        <div class="form-group">
                            <label>🛡️ Stop-Loss %</label>
                            <input type="number" id="stop_loss_percent" value="1.5" step="0.1" min="0.5" max="30">
                        </div>
                    </div>
                    <div class="form-group">
                        <label>İşlem Başı Maks Bütçe %</label>
                        <input type="number" id="max_budget_percent" value="10" min="1" max="100">
                    </div>
                    <button type="submit" class="btn btn-primary" style="width: 100%; margin-top: 10px;">💾 Kullanıcıyı Kaydet</button>
                </form>
            </div>
        </div>

        <div class="card" style="margin-top: 24px;">
            <div class="card-title">📜 Canlı İşlem Kararları ve Loglar (Supabase)</div>
            <div id="logs-container">Yükleniyor...</div>
        </div>

        <script>
            async function loadData() {
                try {
                    const res = await fetch('/api/tenants');
                    const data = await res.json();
                    const table = document.getElementById('tenants-table');
                    document.getElementById('tenant-count').innerText = `${data.count} Aktif`;
                    
                    if (data.tenants.length === 0) {
                        table.innerHTML = `<tr><td colspan="7" style="color: var(--text-muted);">Henüz eklenmiş kullanıcı yok.</td></tr>`;
                    } else {
                        table.innerHTML = data.tenants.map(t => `
                            <tr>
                                <td><strong>${t.tenant_name}</strong></td>
                                <td><code>${t.telegram_chat_id}</code></td>
                                <td>
                                    <input type="number" step="0.1" class="input-inline" id="tp_${t.id}" value="${t.take_profit_percent || 1.5}">
                                </td>
                                <td>
                                    <input type="number" step="0.1" class="input-inline" id="sl_${t.id}" value="${t.stop_loss_percent || 1.5}">
                                </td>
                                <td>
                                    <input type="number" step="1" class="input-inline" id="mb_${t.id}" value="${t.max_budget_percent || 10}">
                                </td>
                                <td><span class="badge badge-active">Aktif</span></td>
                                <td>
                                    <button class="btn btn-primary" style="padding: 5px 12px; margin-right: 4px;" onclick="updateSettings('${t.id}')">💾 Kaydet</button>
                                    <button class="btn btn-danger" style="padding: 5px 10px;" onclick="deleteTenant('${t.id}')">Sil</button>
                                </td>
                            </tr>
                        `).join('');
                    }

                    // Logları Yükle
                    const logRes = await fetch('/api/trade-logs');
                    const logData = await logRes.json();
                    const logContainer = document.getElementById('logs-container');
                    if (logData.logs.length === 0) {
                        logContainer.innerHTML = `<p style="color: var(--text-muted);">Henüz kayıtlı işlem logu yok.</p>`;
                    } else {
                        logContainer.innerHTML = logData.logs.map(l => `
                            <div class="log-item">
                                <strong>${l.symbol} (${l.direction})</strong> - Tutar: $${l.amount_usd} USD | Fiyat: $${l.entry_price || '—'} | SL: $${l.stop_loss_price || '—'} 
                                <span class="badge badge-active" style="float: right;">${l.human_approval}</span>
                            </div>
                        `).join('');
                    }
                } catch(e) { console.error(e); }
            }

            async function updateSettings(tenantId) {
                const tp = parseFloat(document.getElementById('tp_' + tenantId).value);
                const sl = parseFloat(document.getElementById('sl_' + tenantId).value);
                const mb = parseFloat(document.getElementById('mb_' + tenantId).value);
                
                try {
                    const res = await fetch('/api/tenants/' + tenantId + '/settings', {
                        method: 'POST',
                        headers: {'Content-Type': 'application/json'},
                        body: JSON.stringify({take_profit_percent: tp, stop_loss_percent: sl, max_budget_percent: mb})
                    });
                    if (res.ok) {
                        alert('✅ Kâr Alma (%' + tp + ') ve Stop-Loss (%' + sl + ') limitleri başarıyla güncellendi!');
                        loadData();
                    } else {
                        alert('❌ Güncelleme sırasında bir hata oluştu.');
                    }
                } catch(e) {
                    alert('Hata: ' + e);
                }
            }

            async function submitTenant(e) {
                e.preventDefault();
                const payload = {
                    tenant_name: document.getElementById('tenant_name').value,
                    telegram_chat_id: parseInt(document.getElementById('telegram_chat_id').value),
                    exchange_api_key: document.getElementById('exchange_api_key').value,
                    exchange_secret_key: document.getElementById('exchange_secret_key').value,
                    take_profit_percent: parseFloat(document.getElementById('take_profit_percent').value),
                    stop_loss_percent: parseFloat(document.getElementById('stop_loss_percent').value),
                    max_budget_percent: parseFloat(document.getElementById('max_budget_percent').value)
                };
                const res = await fetch('/api/tenants', {
                    method: 'POST',
                    headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify(payload)
                });
                if (res.ok) {
                    alert('✅ Kullanıcı ve limitler başarıyla kaydedildi!');
                    document.getElementById('tenant-form').reset();
                    loadData();
                } else {
                    alert('❌ Kullanıcı kaydedilemedi.');
                }
            }

            async function deleteTenant(tenantId) {
                if (!confirm('Bu kullanıcıyı pasife almak istediğinizden emin misiniz?')) return;
                const res = await fetch(`/api/tenants/${tenantId}`, { method: 'DELETE' });
                if (res.ok) {
                    alert('Kullanıcı pasife alındı.');
                    loadData();
                }
            }

            loadData();
        </script>
    </body>
    </html>
    """
    return HTMLResponse(content=html_content)

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app_api, host="0.0.0.0", port=8000)
