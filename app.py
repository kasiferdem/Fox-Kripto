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

load_dotenv()

app_api = FastAPI(title="Fox-Kripto Multi-Tenant Autonomous Trading & Management Dashboard")

# -----------------------------------------
# OTOMATİK 7/24 TELEGRAM DİNLEYİCİ DÖNGÜSÜ
# -----------------------------------------
@app_api.on_event("startup")
def startup_event():
    """Uygulama ayağa kalktığında Telegram Poller'ı tek konteyner içinde arka planda başlatır."""
    print("🚀 [FastAPI Startup]: Telegram Poller 7/24 Arka Plan Süreci Başlatılıyor...")
    poller_thread = threading.Thread(target=start_poller, daemon=True)
    poller_thread.start()

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
    """DigitalOcean sunucusundan ham Binance bakiye yanıtını kontrol eder."""
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
    url = f"https://api.binance.com/api/v3/account?{query}&signature={sig}"
    headers = {"X-MBX-APIKEY": api_key}
    try:
        res = requests.get(url, headers=headers, timeout=10)
        data = res.json()
        if "balances" in data:
            non_zero = [b for b in data["balances"] if float(b["free"]) > 0 or float(b["locked"]) > 0]
            return {"status": res.status_code, "non_zero_balances": non_zero, "accountType": data.get("accountType")}
        return {"status": res.status_code, "raw_binance_response": data}
    except Exception as e:
        return {"error": str(e)}

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
    """Canlı Supabase işlem kararlarını ve loglarını listeler."""
    client = get_supabase()
    if not client: return {"logs": []}
    try:
        res = client.table("crypto_trade_logs").select("*").order("created_at", desc=True).limit(20).execute()
        return {"logs": res.data or []}
    except Exception as e:
        return {"logs": [], "error": str(e)}

@app_api.post("/run-graph")
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
@app_api.get("/", response_class=HTMLResponse)
@app_api.get("/dashboard", response_class=HTMLResponse)
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
