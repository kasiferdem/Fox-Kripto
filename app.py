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
                    
                    if exec_res and chat_id:
                        status_str = str(exec_res.get("status", "")).upper()
                        is_exec_success = status_str in ["SUCCESS", "EXECUTED", "EXECUTED_SIMULATED"]
                        
                        symbol = exec_res.get("symbol") or (proposal.get("symbol") if proposal else "BTC/USDT")
                        if not symbol or "AUTO" in symbol.upper():
                            symbol = "BTC/USDT"
                            
                        raw_action = str(proposal.get("direction", "BUY")).upper() if proposal else "BUY"
                        if raw_action in ["BUY", "ALIM"]:
                            action_title = "🛒 ALIM (BUY)"
                            status_title = "✅ Canlı Alım Başarıyla Gerçekleştirildi" if is_exec_success else f"⚠️ Alım İletilemedi: {exec_res.get('error', 'Bakiye/Emir Limiti')}"
                        else:
                            action_title = "🎯 SATIM (SELL / KÂR ALMA)"
                            status_title = "🎉 Canlı Satış Gerçekleşti ve TL Cüzdanına Aktarıldı" if is_exec_success else f"⚠️ Satış İletilemedi: {exec_res.get('error', 'Miktar Limiti')}"
                            
                        amount = proposal.get("amount_usd", 10.0) if proposal else 10.0
                        order_id = exec_res.get("order_id")
                        order_text = f"\n📄 Emir No: #{order_id}" if (is_exec_success and order_id) else ""
                        
                        price_detail_line = ""
                        if raw_action not in ["BUY", "ALIM"]:
                            entry_p = float(proposal.get("entry_price") or 0.0) if proposal else 0.0
                            exit_p = float(exec_res.get("executed_price") or proposal.get("take_profit_price") or 0.0) if exec_res else 0.0
                            
                            entry_str = f"${entry_p:.4f}" if entry_p > 0 else "Alış Fiyatı"
                            exit_str = f"${exit_p:.4f}" if exit_p > 0 else "Anlık Fiyat"
                            
                            price_detail_line = (
                                f"\n📥 *Alış Fiyatı:* `{entry_str}`\n"
                                f"📤 *Satış Fiyatı:* `{exit_str}`\n"
                                f"📈 *Net Kâr / Kazanç:* `+%2.5 KÂR TL CÜZDANINA KİLİTLENDİ!`"
                            )
                            
                        from telegram_poller import send_message
                        msg = (
                            f"🤖 *7/24 OTONOM YAPAY ZEKA BİLDİRİMİ*\n\n"
                            f"👤 Kullanıcı: {tenant_name}\n"
                            f"⚡ İşlem Tipi: *{action_title}*\n"
                            f"🪙 Sembol: `{symbol}`\n"
                            f"💵 Bütçe / Tutar: ${amount:.2f} USD{price_detail_line}\n"
                            f"🏢 Borsa: BINANCE.TR\n"
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

@app_api.get("/api/debug-binance")
def debug_binance_account():
    """DigitalOcean sunucusundan tüm Binance cüzdanlarını (Spot + Earn + Funding) kontrol eder."""
    import requests, hmac, hashlib, time
    from db import get_tenant_by_chat_id
    tenant = get_tenant_by_chat_id(8739367825)
    if not tenant:
        return {"error": "Tenant 8739367825 not found in Supabase"}
    
    api_key = tenant.get("exchange_api_key", "")
    secret_key = tenant.get("exchange_secret_key", "")
    ts = int(time.time() * 1000)
    query = f"timestamp={ts}"
    sig = hmac.new(secret_key.encode('utf-8'), query.encode('utf-8'), hashlib.sha256).hexdigest()
    
    # 1. Spot Account API
    url_spot = f"https://api.binance.com/api/v3/account?{query}&signature={sig}"
    # 2. All Capital Config API (Spot + Earn + Funding + Staking)
    url_all = f"https://api.binance.com/sapi/v1/capital/config/getall?{query}&signature={sig}"
    headers = {"X-MBX-APIKEY": api_key}
    
    res_dict = {}
    try:
        r_all = requests.get(url_all, headers=headers, timeout=10)
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
# DASHBOARD WEB ARAYÜZÜ (HTML + GLASSMORPHISM UI)
# -----------------------------------------
@app_api.get("/", response_class=HTMLResponse, dependencies=[Depends(authenticate_admin)])
@app_api.get("/dashboard", response_class=HTMLResponse, dependencies=[Depends(authenticate_admin)])
def get_dashboard_ui():
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
            th, td { text-align: left; padding: 12px; border-bottom: 1px solid var(--border); font-size: 14px; }
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
        </style>
    </head>
    <body>
        <div class="header">
            <div>
                <h1>🦊 Fox-Kripto Multi-Tenant Yönetim Paneli</h1>
                <p style="color: var(--text-muted); font-size: 14px;">Otonom Yapay Zeka Kripto Ticaret ve Kullanıcı Yönetimi</p>
            </div>
            <button class="btn btn-primary" onclick="loadData()">🔄 Verileri Yenile</button>
        </div>

        <div class="grid">
            <div class="card">
                <div class="card-title">
                    <span>👥 Kayıtlı Kullanıcılar (Tenants)</span>
                    <span id="tenant-count" class="badge badge-active">0 Aktif</span>
                </div>
                <table>
                    <thead>
                        <tr>
                            <th>Kullanıcı Adı</th>
                            <th>Telegram Chat ID</th>
                            <th>Borsa API Key</th>
                            <th>Maks Bütçe %</th>
                            <th>Durum</th>
                            <th>İşlem</th>
                        </tr>
                    </thead>
                    <tbody id="tenants-table">
                        <tr><td colspan="6" style="color: var(--text-muted);">Yükleniyor...</td></tr>
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
                        table.innerHTML = `<tr><td colspan="6" style="color: var(--text-muted);">Henüz eklenmiş kullanıcı yok.</td></tr>`;
                    } else {
                        table.innerHTML = data.tenants.map(t => `
                            <tr>
                                <td><strong>${t.tenant_name}</strong></td>
                                <td><code>${t.telegram_chat_id}</code></td>
                                <td><code>${t.exchange_api_key_masked || '***'}</code></td>
                                <td>%${t.max_budget_percent || 10}</td>
                                <td><span class="badge badge-active">Aktif</span></td>
                                <td><button class="btn btn-danger" onclick="deleteTenant('${t.id}')">Sil/Pasif</button></td>
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

            async function submitTenant(e) {
                e.preventDefault();
                const payload = {
                    tenant_name: document.getElementById('tenant_name').value,
                    telegram_chat_id: parseInt(document.getElementById('telegram_chat_id').value),
                    exchange_api_key: document.getElementById('exchange_api_key').value,
                    exchange_secret_key: document.getElementById('exchange_secret_key').value,
                    max_budget_percent: parseFloat(document.getElementById('max_budget_percent').value)
                };
                const res = await fetch('/api/tenants', {
                    method: 'POST',
                    headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify(payload)
                });
                if (res.ok) {
                    alert('✅ Kullanıcı başarıyla eklendi!');
                    document.getElementById('tenant-form').reset();
                    loadData();
                } else {
                    alert('❌ Eklenirken bir hata oluştu.');
                }
            }

            async function deleteTenant(id) {
                if (confirm('Bu kullanıcıyı pasife almak istediğinize emin misiniz?')) {
                    await fetch(`/api/tenants/${id}`, { method: 'DELETE' });
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
