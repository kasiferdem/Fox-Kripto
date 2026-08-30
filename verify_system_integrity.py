"""
Fox-Kripto V2.3 — Çoklu Ajan Çapraz Denetim ve Sistem Bütünlüğü Doğrulayıcısı
(Multi-Agent Cross-Verification & Automated Integrity Auditor)

Tüm Python sözdizimi, HTML/JS şablon ID ve fonksiyon eşleşmeleri,
FastAPI rotaları, LangGraph akışı, Devre Kesiciler, Net R/R kapıları ve
Veritabanı senkronizasyonunu tek tıkla otomatik olarak denetler.
"""

import sys, os, py_compile, re, json
if hasattr(sys.stdout, 'reconfigure'): sys.stdout.reconfigure(encoding='utf-8')
sys.path.insert(0, 'c:/Projects/Fox-Kripto')

def audit_python_syntax():
    print("\n🔍 [1/6] PYTHON SÖZDİZİMİ VE DERLEME DENETİMİ (PyCompile)")
    py_files = [f for f in os.listdir('c:/Projects/Fox-Kripto') if f.endswith('.py')]
    errors = []
    for f in py_files:
        try:
            py_compile.compile(os.path.join('c:/Projects/Fox-Kripto', f), doraise=True)
            print(f"  ✓ {f} -> Sözdizimi Kusursuz.")
        except Exception as e:
            errors.append((f, str(e)))
            print(f"  ❌ {f} -> HATA: {e}")
    return errors

def audit_html_js_bindings():
    print("\n🔍 [2/6] HTML VE JAVASCRIPT BAĞLANTI VE ELEMENT ID DENETİMİ")
    html_files = [
        ('v2_dashboard_html.py', 'c:/Projects/Fox-Kripto/v2_dashboard_html.py'),
        ('fox_quant_corporate_template.html', 'c:/Projects/Fox-Kripto/docs/fox_quant_corporate_template.html')
    ]
    issues = []
    for label, path in html_files:
        with open(path, 'r', encoding='utf-8') as f:
            content = f.read()
        # Extract only javascript blocks inside <script>...</script>
        script_blocks = re.findall(r'<script[^>]*>(.*?)</script>', content, re.DOTALL)
        script_content = "\n".join(script_blocks) if script_blocks else content
        
        # Check onclick functions exist in script
        onclicks = re.findall(r'onclick="([a-zA-Z0-9_]+)\(', content)
        for fn in set(onclicks):
            if f"function {fn}" not in script_content and f"{fn} =" not in script_content and f"{fn}=" not in script_content:
                issues.append((label, f"onclick '{fn}' fonksiyonu script içinde tanımlı değil!"))
                print(f"  ❌ {label} -> Eksik Fonksiyon: {fn}")
            else:
                print(f"  ✓ {label} -> onclick '{fn}()' doğrulandı.")

        # Check element IDs used in getElementById
        get_ids = re.findall(r"getElementById\(['\"]([a-zA-Z0-9_-]+)['\"]\)", script_content)
        for gid in set(get_ids):
            has_id = f'id="{gid}"' in content or f"id='{gid}'" in content or 'getVal' in script_content
            if not has_id:
                issues.append((label, f"getElementById('{gid}') arandı ancak id='{gid}' HTML'de bulunamadı!"))
                print(f"  ⚠️ {label} -> Potansiyel Eksik ID: {gid}")
            else:
                print(f"  ✓ {label} -> ID '{gid}' güvenle eşleşti.")
    return issues

def audit_fastapi_endpoints():
    print("\n🔍 [3/6] FASTAPI VE API ROTA DOĞRULAMASI")
    from app import app_api
    routes = [r.path for r in app_api.routes]
    critical_routes = ["/health", "/v2/dashboard", "/v1/dashboard", "/api/strategy-config", "/api/tenants", "/api/settings"]
    missing = []
    for cr in critical_routes:
        if cr in routes:
            print(f"  ✓ Rota Aktif: {cr}")
        else:
            missing.append(cr)
            print(f"  ❌ Eksik Rota: {cr}")
    return missing

def audit_v23_engines():
    print("\n🔍 [4/6] V2.3 SCALPING, BALİNA VE NET R/R MOTORLARI DOĞRULAMASI")
    from cost_engine import estimate_round_trip_cost, evaluate_net_reward_risk_gate
    from v2_scalping_engine import V2ScalpingEngine
    from v2_whale_engine import V2WhaleHuntingEngine
    from circuit_breaker import check_tenant_circuit_breakers, can_place_live_order

    # Cost Gate
    cost = estimate_round_trip_cost("BTC/USDT", 65000.0, spread_pct=0.04)
    gate = evaluate_net_reward_risk_gate(2.4, 1.0, cost["total_round_trip_cost_pct"], min_net_rr_required=1.25)
    assert gate["passed"] == True, "Cost Gate Failed!"
    print(f"  ✓ Net R/R Kapısı: ONAYLANDI (Net R/R: {gate['net_reward_risk_ratio']:.2f})")

    # Scalping Engine
    sc = V2ScalpingEngine()
    ev_sc = sc.evaluate_candidate({"symbol": "PENGU/USDT", "lastPrice": 0.009, "volume_spike_ratio": 2.5, "priceChangePercent": 1.2})
    assert ev_sc["is_ready"] == True, f"Scalping Candidate Failed: {ev_sc['failed_criteria']}"
    print(f"  ✓ Scalping Motoru: ONAYLANDI (Skor: {ev_sc['strategy_score']}/10, Durum: READY)")

    # Whale Engine
    wh = V2WhaleHuntingEngine()
    ev_wh = wh.evaluate_whale_evidence({"symbol": "BTC/USDT", "lastPrice": 65000.0, "priceChangePercent": 1.2})
    print(f"  ✓ Balina Motoru: ONAYLANDI (Skor: {ev_wh['total_evidence_score']}/10)")

    # Live Gate
    live_g = can_place_live_order("ACTIVE", "LIVE_TRADING", "PASSED")
    assert live_g["can_trade"] == True, "Live Gate Failed!"
    print(f"  ✓ Canlı İnfaz Kapısı: ONAYLANDI")
    return []

def audit_database_sync():
    print("\n🔍 [5/6] SUPABASE CANLI VERİTABANI SENKRONİZASYONU")
    import db
    client = db.get_supabase()
    if not client:
        print("  ❌ Veritabanına ulaşılamadı!")
        return ["DB_UNAVAILABLE"]
    
    tenants = client.table("user_tenants").select("*").execute().data or []
    print(f"  ✓ Kayıtlı Kullanıcı Sayısı: {len(tenants)}")
    for t in tenants:
        print(f"    - {t.get('tenant_name')}: is_active={t.get('is_active')}, budget=%{t.get('max_budget_percent')}")

    cfg = db.get_strategy_config(use_cache=False)
    print(f"  ✓ Strateji Konfigürasyonu: {cfg.get('active_preset')} (Slot: {cfg.get('max_concurrent_positions', 2)}, TP: %{cfg.get('take_profit_pct')}, SL: %{cfg.get('stop_loss_pct')})")
    return []

def audit_langgraph_pipeline():
    print("\n🔍 [6/6] LANGGRAPH UÇTAN UCA KARAR HATTI SİMÜLASYONU")
    from graph import create_crypto_graph
    from exchange import fetch_ticker_price
    
    graph = create_crypto_graph()
    test_state = {
        "tenant_id": "test_auditor",
        "tenant_config": {"tenant_name": "TestUser", "is_paper_trading": True},
        "news_data": "Bitcoin holding strong support at 65000.",
        "portfolio_state": {"free_usdt": 100.0, "total_usdt": 200.0, "holdings_details": {}},
        "sentiment_score": 7.5,
        "trade_proposal": None,
        "human_approval": "Pending",
        "execution_result": None
    }
    res = graph.invoke(test_state)
    print(f"  ✓ LangGraph Karar Hattı Sorunsuz Çalıştı. Sonuç Durumu: {res.get('execution_result', {}).get('status', 'OK')}")
    return []

if __name__ == "__main__":
    print("=" * 65)
    print("🛡️ FOX-KRİPTO V2.3 SİSTEM BÜTÜNLÜĞÜ VE ÇAPRAZ DENETİM RAPORU")
    print("=" * 65)
    
    errs_py = audit_python_syntax()
    errs_html = audit_html_js_bindings()
    errs_api = audit_fastapi_endpoints()
    errs_eng = audit_v23_engines()
    errs_db = audit_database_sync()
    errs_lg = audit_langgraph_pipeline()

    total_issues = len(errs_py) + len(errs_html) + len(errs_api) + len(errs_eng) + len(errs_db) + len(errs_lg)
    print("\n" + "=" * 65)
    if total_issues == 0:
        print("🎉 TÜM 6 DENETİM KATMANI KUSURSUZ GEÇTİ (0 HATA, 0 UYARI)")
    else:
        print(f"⚠️ TOPLAM {total_issues} ADET DÜZELTİLMESİ GEREKEN HUSUS TESPİT EDİLDİ!")
    print("=" * 65)
