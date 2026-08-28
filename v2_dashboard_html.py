"""
Fox-Kripto V2 Dashboard HTML / CSS / JS Generator
UI/UX Designer Skill Standartlarına göre tasarlanmış Çift Motorlu Yönetim Paneli.
"""

def generate_v2_dashboard_html(
    tenants_ssr_json: str,
    tenants_ssr_html: str,
    logs_ssr_html: str,
    active_engine: str = "WHALE_HUNTING",
    active_risk: str = "BALANCED",
    active_version: str = "V2",
    trailing_checked: str = "checked",
    trailing_status: str = "AÇIK",
    trailing_color: str = "var(--success)",
    shield_checked: str = "checked",
    shield_status: str = "AÇIK",
    shield_color: str = "var(--success)"
) -> str:
    html = f"""<!DOCTYPE html>
<html lang="tr">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Fox-Kripto v2.0 Quant Dashboard | Hacim Scalp & Gerçek Balina Avı</title>
    <!-- Modern Distinctive Typography: Space Grotesk & JetBrains Mono -->
    <link rel="preconnect" href="https://fonts.googleapis.com">
    <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
    <link href="https://fonts.googleapis.com/css2?family=JetBrains+Mono:wght@400;600;700&family=Space+Grotesk:wght@400;500;600;700&display=swap" rel="stylesheet">
    
    <style>
        :root {{
            --bg-base: #090d16;
            --bg-card: rgba(17, 24, 39, 0.85);
            --bg-card-hover: rgba(30, 41, 59, 0.95);
            --border-color: rgba(255, 255, 255, 0.1);
            --border-glow: rgba(6, 182, 212, 0.4);
            
            --scalp-cyan: #06b6d4;
            --scalp-glow: rgba(6, 182, 212, 0.25);
            --whale-gold: #f59e0b;
            --whale-glow: rgba(245, 158, 11, 0.25);
            
            --success: #10b981;
            --danger: #f43f5e;
            --text-main: #f8fafc;
            --text-muted: #94a3b8;
            
            --font-sans: 'Space Grotesk', -apple-system, sans-serif;
            --font-mono: 'JetBrains Mono', monospace;
        }}

        * {{ box-sizing: border-box; margin: 0; padding: 0; font-family: var(--font-sans); }}
        body {{
            background-color: var(--bg-base);
            background-image: 
                radial-gradient(at 0% 0%, rgba(6, 182, 212, 0.08) 0px, transparent 50%),
                radial-gradient(at 100% 0%, rgba(245, 158, 11, 0.08) 0px, transparent 50%),
                radial-gradient(at 50% 100%, rgba(16, 185, 129, 0.05) 0px, transparent 50%);
            background-attachment: fixed;
            color: var(--text-main);
            padding: 24px;
            min-height: 100vh;
        }}

        /* Header Bar */
        .top-header {{
            display: flex;
            justify-content: space-between;
            align-items: center;
            flex-wrap: wrap;
            gap: 16px;
            margin-bottom: 24px;
            padding-bottom: 18px;
            border-bottom: 1px solid var(--border-color);
        }}
        .brand-title h1 {{
            font-size: 26px;
            font-weight: 700;
            letter-spacing: -0.5px;
            background: linear-gradient(135deg, #38bdf8, #818cf8);
            -webkit-background-clip: text;
            -webkit-text-fill-color: transparent;
            display: flex;
            align-items: center;
            gap: 10px;
        }}
        .brand-subtitle {{
            font-size: 13px;
            color: var(--text-muted);
            margin-top: 4px;
        }}

        .header-controls {{
            display: flex;
            align-items: center;
            gap: 12px;
            flex-wrap: wrap;
        }}

        /* Version Card Switcher */
        .version-switcher {{
            display: flex;
            align-items: center;
            background: rgba(15, 23, 42, 0.9);
            border: 1px solid var(--border-color);
            border-radius: 12px;
            padding: 4px;
            gap: 4px;
        }}
        .version-btn {{
            padding: 6px 14px;
            font-size: 13px;
            font-weight: 700;
            border-radius: 8px;
            border: none;
            cursor: pointer;
            text-decoration: none;
            transition: all 0.2s;
            display: flex;
            align-items: center;
            gap: 6px;
        }}
        .version-btn.active {{
            background: linear-gradient(135deg, #0284c7, #2563eb);
            color: white;
            box-shadow: 0 4px 12px rgba(37, 99, 235, 0.35);
        }}
        .version-btn.inactive {{
            background: transparent;
            color: var(--text-muted);
        }}
        .version-btn.inactive:hover {{
            color: var(--text-main);
            background: rgba(255, 255, 255, 0.05);
        }}

        /* Switches & Badges */
        .status-pill {{
            display: flex;
            align-items: center;
            gap: 8px;
            background: rgba(15, 23, 42, 0.85);
            border: 1px solid var(--border-color);
            border-radius: 10px;
            padding: 6px 14px;
            font-size: 13px;
        }}
        .switch {{ position: relative; display: inline-block; width: 40px; height: 22px; margin-bottom: 0; }}
        .switch input {{ opacity: 0; width: 0; height: 0; }}
        .slider {{ position: absolute; cursor: pointer; top: 0; left: 0; right: 0; bottom: 0; background-color: #334155; transition: .2s ease; border-radius: 22px; border: 1px solid var(--border-color); }}
        .slider:before {{ position: absolute; content: ""; height: 16px; width: 16px; left: 2px; bottom: 2px; background-color: white; transition: .2s ease; border-radius: 50%; }}
        input:checked + .slider {{ background-color: var(--success) !important; }}
        input:checked + .slider:before {{ transform: translateX(18px) !important; }}

        /* Engine Hero Card */
        .engine-card {{
            background: var(--bg-card);
            backdrop-filter: blur(16px);
            border: 1px solid rgba(245, 158, 11, 0.3);
            border-radius: 20px;
            padding: 24px;
            box-shadow: 0 12px 36px rgba(0, 0, 0, 0.4);
            margin-bottom: 24px;
            position: relative;
            overflow: hidden;
        }}
        .engine-card::before {{
            content: '';
            position: absolute;
            top: 0; left: 0; right: 0; height: 3px;
            background: linear-gradient(90deg, var(--scalp-cyan), var(--whale-gold));
        }}

        .engine-toggle-group {{
            display: grid;
            grid-template-columns: 1fr 1fr;
            gap: 12px;
            margin-bottom: 20px;
        }}
        .engine-select-btn {{
            padding: 14px 20px;
            border-radius: 14px;
            border: 2px solid var(--border-color);
            background: rgba(15, 23, 42, 0.6);
            color: var(--text-muted);
            font-size: 15px;
            font-weight: 700;
            cursor: pointer;
            display: flex;
            justify-content: space-between;
            align-items: center;
            transition: all 0.25s;
        }}
        .engine-select-btn.active-scalp {{
            border-color: var(--scalp-cyan);
            background: linear-gradient(180deg, rgba(6, 182, 212, 0.15), rgba(6, 182, 212, 0.03));
            color: var(--scalp-cyan);
            box-shadow: 0 0 20px var(--scalp-glow);
        }}
        .engine-select-btn.active-whale {{
            border-color: var(--whale-gold);
            background: linear-gradient(180deg, rgba(245, 158, 11, 0.15), rgba(245, 158, 11, 0.03));
            color: var(--whale-gold);
            box-shadow: 0 0 20px var(--whale-glow);
        }}

        /* Risk Pills */
        .risk-pills-row {{
            display: flex;
            gap: 8px;
            align-items: center;
            flex-wrap: wrap;
            margin-bottom: 20px;
        }}
        .risk-pill {{
            padding: 8px 16px;
            border-radius: 10px;
            border: 1px solid var(--border-color);
            background: rgba(15, 23, 42, 0.7);
            color: var(--text-muted);
            font-size: 13px;
            font-weight: 600;
            cursor: pointer;
            transition: all 0.2s;
        }}
        .risk-pill.active {{
            background: rgba(245, 158, 11, 0.2);
            color: var(--whale-gold);
            border-color: var(--whale-gold);
        }}

        /* 10 Confirmations Matrix */
        .confirmations-matrix {{
            display: grid;
            grid-template-columns: repeat(auto-fill, minmax(220px, 1fr));
            gap: 10px;
            margin-top: 16px;
            padding: 16px;
            background: rgba(10, 15, 29, 0.6);
            border-radius: 14px;
            border: 1px solid var(--border-color);
        }}
        .conf-badge {{
            display: flex;
            align-items: center;
            gap: 8px;
            font-size: 12px;
            color: #cbd5e1;
            padding: 8px 12px;
            background: rgba(15, 23, 42, 0.8);
            border-radius: 8px;
            border-left: 3px solid #64748b;
        }}
        .conf-badge.verified {{
            border-left-color: var(--success);
            color: #a7f3d0;
        }}

        /* Grid Structure */
        .main-grid {{
            display: grid;
            grid-template-columns: 1fr 380px;
            gap: 24px;
        }}
        @media (max-width: 1080px) {{
            .main-grid {{ grid-template-columns: 1fr; }}
        }}

        .card {{
            background: var(--bg-card);
            backdrop-filter: blur(16px);
            border: 1px solid var(--border-color);
            border-radius: 16px;
            padding: 24px;
            box-shadow: 0 8px 24px rgba(0,0,0,0.3);
        }}
        .card-title {{
            font-size: 17px;
            font-weight: 700;
            margin-bottom: 16px;
            display: flex;
            justify-content: space-between;
            align-items: center;
        }}

        /* Buttons */
        .btn {{
            padding: 10px 18px;
            border-radius: 10px;
            border: none;
            font-weight: 700;
            font-size: 13px;
            cursor: pointer;
            transition: all 0.2s;
            display: inline-flex;
            align-items: center;
            gap: 6px;
        }}
        .btn-primary {{
            background: linear-gradient(135deg, #0284c7, #2563eb);
            color: white;
        }}
        .btn-primary:hover {{
            box-shadow: 0 4px 14px rgba(37, 99, 235, 0.4);
            transform: translateY(-1px);
        }}
        .btn-gold {{
            background: linear-gradient(135deg, #f59e0b, #d97706);
            color: white;
        }}
        .btn-danger {{
            background: rgba(244, 63, 94, 0.15);
            color: var(--danger);
            border: 1px solid var(--danger);
        }}

        /* Table */
        .table-responsive {{ overflow-x: auto; }}
        table {{ width: 100%; border-collapse: collapse; margin-top: 10px; }}
        th, td {{ padding: 12px 10px; text-align: left; border-bottom: 1px solid var(--border-color); font-size: 13px; white-space: nowrap; }}
        th {{ color: var(--text-muted); font-weight: 600; }}
        .mono {{ font-family: var(--font-mono); }}
        .input-inline {{ width: 74px; padding: 6px 8px; border-radius: 8px; border: 1px solid var(--border-color); background: rgba(15, 23, 42, 0.85); color: white; text-align: center; font-family: var(--font-mono); font-size: 13px; }}
    </style>
</head>
<body>

    <!-- TOP HEADER BAR -->
    <header class="top-header">
        <div class="brand-title">
            <h1>🦊 Fox-Kripto <span style="font-size: 13px; background: rgba(6, 182, 212, 0.2); color: var(--scalp-cyan); border: 1px solid var(--scalp-cyan); padding: 2px 8px; border-radius: 6px; font-weight: 700;">V2.0 QUANT</span></h1>
            <div class="brand-subtitle">Hacim Scalping & Gerçek Balina Avı | Çok Boyutlu İnfaz ve Risk Yönetimi</div>
        </div>

        <div class="header-controls">
            <!-- V1 / V2 Sürüm Seçici -->
            <div class="version-switcher">
                <a href="/v1/dashboard" class="version-btn inactive">🏛️ V1 Klasik</a>
                <a href="/v2/dashboard" class="version-btn active">⚡ V2 Çift Motor</a>
            </div>

            <!-- Trailing Stop & Güvenlik Zırhı -->
            <div class="status-pill">
                <span style="color: #38bdf8; font-weight: 600;">🚀 Trailing SL:</span>
                <label class="switch">
                    <input type="checkbox" id="trailing-toggle" {trailing_checked} onchange="toggleTrailingStop(this.checked)">
                    <span class="slider"></span>
                </label>
            </div>

            <button class="btn btn-gold" onclick="triggerDustClean()">🧹 Kırıntı Temizle</button>
            <button class="btn btn-primary" onclick="loadData()">🔄 Verileri Yenile</button>
        </div>
    </header>

    <!-- ⚡ V2 ÇİFT MOTOR VE RİSK PROFİLİ SEÇİCİ HERO KART -->
    <section class="engine-card">
        <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 16px; flex-wrap: wrap; gap: 10px;">
            <div>
                <span style="font-size: 12px; color: var(--text-muted); text-transform: uppercase; letter-spacing: 1px; font-weight: 700;">AKTİF STRATEJİ MOTORU</span>
                <h2 id="engine-title" style="font-size: 20px; font-weight: 700; color: #f8fafc; margin-top: 2px;">🐋 Gerçek Balina Avı Motoru (10 Kriterli Teyit)</h2>
            </div>
            <div id="engine-badge" style="background: rgba(245, 158, 11, 0.2); color: var(--whale-gold); border: 1px solid var(--whale-gold); padding: 6px 14px; border-radius: 20px; font-size: 13px; font-weight: 700;">
                🐋 Balina Avı · Dengeli · v2.0 Aktif
            </div>
        </div>

        <!-- Motor Seçim Butonları -->
        <div class="engine-toggle-group">
            <button id="btn-engine-scalp" class="engine-select-btn" onclick="switchEngine('VOLUME_SCALPING')">
                <span>⚡ 1. Hacim Scalping Motoru</span>
                <span style="font-size: 12px; opacity: 0.8;">1m/3m/5m Hızlı Momentum</span>
            </button>
            <button id="btn-engine-whale" class="engine-select-btn active-whale" onclick="switchEngine('WHALE_HUNTING')">
                <span>🐋 2. Gerçek Balina Avı Motoru</span>
                <span style="font-size: 12px; opacity: 0.8;">Spot + Vadeli OI + Duvar Teyidi</span>
            </button>
        </div>

        <!-- Risk Seviyesi Seçici -->
        <div class="risk-pills-row">
            <span style="font-size: 13px; color: var(--text-muted); font-weight: 600; margin-right: 6px;">Hazır Profiller:</span>
            <button id="pill-agg" class="risk-pill" onclick="switchRisk('AGGRESSIVE')">🔥 Agresif</button>
            <button id="pill-bal" class="risk-pill active" onclick="switchRisk('BALANCED')">⚖️ Dengeli (Önerilen)</button>
            <button id="pill-def" class="risk-pill" onclick="switchRisk('DEFENSIVE')">🏰 Defansif</button>
            <button id="pill-cus" class="risk-pill" onclick="switchRisk('CUSTOM')">⚙️ Özel (Custom)</button>
            <button class="btn btn-primary" onclick="saveV2Strategy()" style="margin-left: auto; height: 38px; font-weight: 700;">💾 Parametreleri Kaydet & Canlıya Al</button>
        </div>

        <!-- 🎛️ CANLI PARAMETRE YÖNETİM VE İNCE AYAR MERKEZİ -->
        <div style="margin-top: 16px; padding: 20px; background: rgba(10, 15, 29, 0.75); border-radius: 16px; border: 1px solid var(--border-color);">
            <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 14px;">
                <span style="font-size: 13px; font-weight: 700; color: var(--whale-gold); text-transform: uppercase; letter-spacing: 0.5px;">🎛️ Quant Parametre Yönetim ve İnce Ayar Merkezi</span>
                <span style="font-size: 11px; color: var(--text-muted);">Değerleri dilediğiniz gibi değiştirip canlı motora anında uygulayabilirsiniz.</span>
            </div>
            
            <div style="display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: 14px;">
                <!-- 1. Min 5dk Hacim -->
                <div>
                    <label style="font-size: 11px; color: var(--text-muted); display: block; margin-bottom: 4px; font-weight: 600;">🧱 Min 5dk Hacim ($ USD)</label>
                    <input type="number" id="param_min_volume_usd" value="50000" onchange="markCustom()" style="width: 100%; padding: 8px 12px; border-radius: 8px; background: rgba(15, 23, 42, 0.9); color: #38bdf8; border: 1px solid var(--border-color); font-family: var(--font-mono); font-weight: 600;">
                </div>
                <!-- 2. Hacim Çarpanı -->
                <div>
                    <label style="font-size: 11px; color: var(--text-muted); display: block; margin-bottom: 4px; font-weight: 600;">⚡ Hacim Patlama Çarpanı (x)</label>
                    <input type="number" step="0.1" id="param_volume_spike" value="2.5" onchange="markCustom()" style="width: 100%; padding: 8px 12px; border-radius: 8px; background: rgba(15, 23, 42, 0.9); color: #f59e0b; border: 1px solid var(--border-color); font-family: var(--font-mono); font-weight: 600;">
                </div>
                <!-- 3. Maks 24s Prim -->
                <div>
                    <label style="font-size: 11px; color: var(--text-muted); display: block; margin-bottom: 4px; font-weight: 600;">📈 Maks 24s Prim Limiti (%)</label>
                    <input type="number" step="0.5" id="param_max_gain_24h" value="12.0" onchange="markCustom()" style="width: 100%; padding: 8px 12px; border-radius: 8px; background: rgba(15, 23, 42, 0.9); color: white; border: 1px solid var(--border-color); font-family: var(--font-mono); font-weight: 600;">
                </div>
                <!-- 4. Min AI Skoru -->
                <div>
                    <label style="font-size: 11px; color: var(--text-muted); display: block; margin-bottom: 4px; font-weight: 600;">🧠 Min AI & Teyit Skoru (1-10)</label>
                    <input type="number" step="0.1" id="param_min_ai_score" value="8.0" onchange="markCustom()" style="width: 100%; padding: 8px 12px; border-radius: 8px; background: rgba(15, 23, 42, 0.9); color: var(--success); border: 1px solid var(--border-color); font-family: var(--font-mono); font-weight: 600;">
                </div>
                <!-- 5. Kasa Bütçesi -->
                <div>
                    <label style="font-size: 11px; color: var(--text-muted); display: block; margin-bottom: 4px; font-weight: 600;">💰 İşlem Başı Kasa Bütçesi (%)</label>
                    <input type="number" step="1.0" id="param_max_budget" value="25.0" onchange="markCustom()" style="width: 100%; padding: 8px 12px; border-radius: 8px; background: rgba(15, 23, 42, 0.9); color: white; border: 1px solid var(--border-color); font-family: var(--font-mono); font-weight: 600;">
                </div>
                <!-- 6. Hedef TP -->
                <div>
                    <label style="font-size: 11px; color: var(--text-muted); display: block; margin-bottom: 4px; font-weight: 600;">🎯 Hedef Kâr Al (%)</label>
                    <input type="number" step="0.1" id="param_tp_pct" value="3.0" onchange="markCustom()" style="width: 100%; padding: 8px 12px; border-radius: 8px; background: rgba(15, 23, 42, 0.9); color: var(--success); border: 1px solid var(--border-color); font-family: var(--font-mono); font-weight: 600;">
                </div>
                <!-- 7. Stop-Loss -->
                <div>
                    <label style="font-size: 11px; color: var(--text-muted); display: block; margin-bottom: 4px; font-weight: 600;">🛡️ Zarar Kes Stop-Loss (%)</label>
                    <input type="number" step="0.1" id="param_sl_pct" value="1.5" onchange="markCustom()" style="width: 100%; padding: 8px 12px; border-radius: 8px; background: rgba(15, 23, 42, 0.9); color: var(--danger); border: 1px solid var(--border-color); font-family: var(--font-mono); font-weight: 600;">
                </div>
                <!-- 8. Trailing Callback -->
                <div>
                    <label style="font-size: 11px; color: var(--text-muted); display: block; margin-bottom: 4px; font-weight: 600;">🚀 Trailing Zirve Çekilme (%)</label>
                    <input type="number" step="0.1" id="param_trailing_callback" value="0.6" onchange="markCustom()" style="width: 100%; padding: 8px 12px; border-radius: 8px; background: rgba(15, 23, 42, 0.9); color: #38bdf8; border: 1px solid var(--border-color); font-family: var(--font-mono); font-weight: 600;">
                </div>
            </div>
        </div>

        <!-- 10 Kurumsal Teyit Göstergesi -->
        <div style="margin-top: 14px;">
            <div style="font-size: 12px; color: var(--text-muted); font-weight: 700; display: flex; justify-content: space-between;">
                <span>10 KURUMSAL TEYİT MATRİSİ (WHALE CONFIRMATION MATRIX)</span>
                <span style="color: var(--success); font-family: var(--font-mono);">9 / 10 Teyit Aktif (Skor: 8.7/10)</span>
            </div>
            <div class="confirmations-matrix">
                <div class="conf-badge verified">✅ 1. Spot Hacim Patlaması (>2.5x)</div>
                <div class="conf-badge verified">✅ 2. Vadeli Açık Faiz (OI Artışı)</div>
                <div class="conf-badge verified">✅ 3. Funding Rate Dengesi (<%0.10)</div>
                <div class="conf-badge verified">✅ 4. Alış Duvarı Koruması (>60s)</div>
                <div class="conf-badge verified">✅ 5. Taker Alış Baskısı (>%64)</div>
                <div class="conf-badge verified">✅ 6. 24s Primsiz Giriş (<%12.0)</div>
                <div class="conf-badge verified">✅ 7. VWAP & EMA Retest Desteği</div>
                <div class="conf-badge verified">✅ 8. On-Chain Borsa Çıkışları</div>
                <div class="conf-badge verified">✅ 9. Düşük Spread (<%0.20)</div>
                <div class="conf-badge verified">✅ 10. Sıfır Manipülasyon Riski</div>
            </div>
        </div>
    </section>

    <!-- ANA İÇERİK GRID -->
    <main class="main-grid">
        <!-- SOL: KULLANICILAR VE SİNYAL LOGLARI -->
        <div style="display: flex; flex-direction: column; gap: 24px;">
            <!-- Kayıtlı Kullanıcılar -->
            <div class="card">
                <div class="card-title">
                    <span>👥 Kayıtlı Kullanıcılar & Dinamik Risk Dağılımı</span>
                    <span style="font-size: 12px; color: var(--scalp-cyan); background: rgba(6, 182, 212, 0.15); padding: 4px 10px; border-radius: 12px;">Multi-Tenant V2</span>
                </div>
                <div class="table-responsive">
                    <table>
                        <thead>
                            <tr>
                                <th>Kullanıcı Adı</th>
                                <th>Telegram ID</th>
                                <th>🎯 Kâr Al %</th>
                                <th>🛡️ Stop %</th>
                                <th>💵 Bütçe %</th>
                                <th>🏛️ Borsa</th>
                                <th>🌐 Dil</th>
                                <th>Durum</th>
                                <th>İşlemler</th>
                            </tr>
                        </thead>
                        <tbody id="tenants-tbody">
                            {tenants_ssr_html}
                        </tbody>
                    </table>
                </div>
            </div>

            <!-- Canlı İşlem ve Karar Logları -->
            <div class="card">
                <div class="card-title">
                    <span>📜 Açıklanabilir AI Karar & İşlem Günlüğü (Explainable Logs)</span>
                    <span style="font-size: 12px; color: var(--success);">🟢 Canlı Veritabanı Senkronize</span>
                </div>
                <div id="logs-container">
                    {logs_ssr_html}
                </div>
            </div>
        </div>

        <!-- SAĞ: YENİ KULLANICI EKLEME PANELİ -->
        <div>
            <div class="card" style="position: sticky; top: 24px;">
                <div class="card-title">
                    <span>➕ Yeni Kullanıcı Ekle</span>
                </div>
                <form id="add-user-form" onsubmit="addUser(event)">
                    <div style="margin-bottom: 12px;">
                        <label style="font-size: 12px; color: var(--text-muted); display: block; margin-bottom: 4px;">Kullanıcı Adı</label>
                        <input type="text" id="new_tenant_name" required style="width: 100%; padding: 8px; border-radius: 8px; background: rgba(15, 23, 42, 0.8); color: white; border: 1px solid var(--border-color);">
                    </div>
                    <div style="margin-bottom: 12px;">
                        <label style="font-size: 12px; color: var(--text-muted); display: block; margin-bottom: 4px;">Telegram Chat ID</label>
                        <input type="number" id="new_telegram_chat_id" required style="width: 100%; padding: 8px; border-radius: 8px; background: rgba(15, 23, 42, 0.8); color: white; border: 1px solid var(--border-color);">
                    </div>
                    <div style="margin-bottom: 12px;">
                        <label style="font-size: 12px; color: var(--text-muted); display: block; margin-bottom: 4px;">Binance API Key</label>
                        <input type="text" id="new_api_key" placeholder="API Key" style="width: 100%; padding: 8px; border-radius: 8px; background: rgba(15, 23, 42, 0.8); color: white; border: 1px solid var(--border-color);">
                    </div>
                    <div style="margin-bottom: 12px;">
                        <label style="font-size: 12px; color: var(--text-muted); display: block; margin-bottom: 4px;">Binance Secret Key</label>
                        <input type="password" id="new_secret_key" placeholder="Secret Key" style="width: 100%; padding: 8px; border-radius: 8px; background: rgba(15, 23, 42, 0.8); color: white; border: 1px solid var(--border-color);">
                    </div>
                    <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 8px; margin-bottom: 14px;">
                        <div>
                            <label style="font-size: 12px; color: var(--text-muted); display: block; margin-bottom: 4px;">🎯 Kâr Al %</label>
                            <input type="number" step="0.1" id="new_tp" value="3.0" style="width: 100%; padding: 8px; border-radius: 8px; background: rgba(15, 23, 42, 0.8); color: white; border: 1px solid var(--border-color);">
                        </div>
                        <div>
                            <label style="font-size: 12px; color: var(--text-muted); display: block; margin-bottom: 4px;">🛡️ Stop %</label>
                            <input type="number" step="0.1" id="new_sl" value="1.5" style="width: 100%; padding: 8px; border-radius: 8px; background: rgba(15, 23, 42, 0.8); color: white; border: 1px solid var(--border-color);">
                        </div>
                    </div>
                    <button type="submit" class="btn btn-primary" style="width: 100%; justify-content: center; height: 42px;">💾 Kullanıcıyı Kaydet</button>
                </form>
            </div>
        </div>
    </main>

    <script>
        function getAuthHeaders() {{
            return {{ 'Authorization': 'Basic ' + btoa('admin:foxkripto2026') }};
        }}

        let currentEngine = '{active_engine}';
        let currentRisk = '{active_risk}';

        function switchEngine(engine) {{
            currentEngine = engine;
            const btnScalp = document.getElementById('btn-engine-scalp');
            const btnWhale = document.getElementById('btn-engine-whale');
            const title = document.getElementById('engine-title');
            const badge = document.getElementById('engine-badge');

            if (engine === 'VOLUME_SCALPING') {{
                btnScalp.className = 'engine-select-btn active-scalp';
                btnWhale.className = 'engine-select-btn';
                title.innerHTML = '⚡ Hacim Scalping Motoru (1m/3m/5m İvme)';
                badge.style.borderColor = 'var(--scalp-cyan)';
                badge.style.color = 'var(--scalp-cyan)';
                badge.style.background = 'rgba(6, 182, 212, 0.2)';
                badge.innerText = '⚡ Scalp · ' + currentRisk + ' · v2.0 Aktif';
            }} else {{
                btnWhale.className = 'engine-select-btn active-whale';
                btnScalp.className = 'engine-select-btn';
                title.innerHTML = '🐋 Gerçek Balina Avı Motoru (10 Kriterli Teyit)';
                badge.style.borderColor = 'var(--whale-gold)';
                badge.style.color = 'var(--whale-gold)';
                badge.style.background = 'rgba(245, 158, 11, 0.2)';
                badge.innerText = '🐋 Balina · ' + currentRisk + ' · v2.0 Aktif';
            }}
        }}

        const PRESETS_MAP = {{
            'VOLUME_SCALPING_AGGRESSIVE': {{ min_vol: 35000, spike: 1.5, gain: 15.0, score: 7.2, budget: 35.0, tp: 2.2, sl: 1.2, cb: 0.5 }},
            'VOLUME_SCALPING_BALANCED':   {{ min_vol: 50000, spike: 1.8, gain: 10.0, score: 7.8, budget: 25.0, tp: 3.0, sl: 1.5, cb: 0.6 }},
            'VOLUME_SCALPING_DEFENSIVE':  {{ min_vol: 75000, spike: 2.2, gain: 8.0,  score: 8.5, budget: 15.0, tp: 4.0, sl: 1.8, cb: 0.8 }},
            'WHALE_HUNTING_AGGRESSIVE':   {{ min_vol: 50000, spike: 2.0, gain: 15.0, score: 7.8, budget: 35.0, tp: 4.0, sl: 1.5, cb: 0.6 }},
            'WHALE_HUNTING_BALANCED':     {{ min_vol: 75000, spike: 2.5, gain: 12.0, score: 8.2, budget: 25.0, tp: 5.0, sl: 1.8, cb: 0.7 }},
            'WHALE_HUNTING_DEFENSIVE':    {{ min_vol: 100000, spike: 3.2, gain: 9.0, score: 8.8, budget: 15.0, tp: 6.5, sl: 2.0, cb: 0.9 }}
        }};

        function markCustom() {{
            document.querySelectorAll('.risk-pill').forEach(btn => btn.classList.remove('active'));
            const cusBtn = document.getElementById('pill-cus');
            if (cusBtn) cusBtn.classList.add('active');
            currentRisk = 'CUSTOM';
            const badge = document.getElementById('engine-badge');
            if (badge) badge.innerText = (currentEngine === 'WHALE_HUNTING' ? '🐋 Balina' : '⚡ Scalp') + ' · Özel Ayarlar · v2.0 Aktif';
        }}

        function switchRisk(risk) {{
            currentRisk = risk;
            document.querySelectorAll('.risk-pill').forEach(btn => {{
                btn.classList.toggle('active', btn.innerText.includes(risk));
            }});
            
            const key = currentEngine + '_' + risk;
            const p = PRESETS_MAP[key];
            if (p) {{
                document.getElementById('param_min_volume_usd').value = p.min_vol;
                document.getElementById('param_volume_spike').value = p.spike;
                document.getElementById('param_max_gain_24h').value = p.gain;
                document.getElementById('param_min_ai_score').value = p.score;
                document.getElementById('param_max_budget').value = p.budget;
                document.getElementById('param_tp_pct').value = p.tp;
                document.getElementById('param_sl_pct').value = p.sl;
                document.getElementById('param_trailing_callback').value = p.cb;
            }}
            switchEngine(currentEngine);
        }}

        async function saveV2Strategy() {{
            try {{
                const payload = {{
                    active_preset: currentEngine.toLowerCase() + '_' + currentRisk.toLowerCase(),
                    min_volume_usd: parseFloat(document.getElementById('param_min_volume_usd').value) || 50000,
                    volume_spike_multiplier: parseFloat(document.getElementById('param_volume_spike').value) || 2.5,
                    max_recent_gain_24h: parseFloat(document.getElementById('param_max_gain_24h').value) || 12.0,
                    min_ai_score: parseFloat(document.getElementById('param_min_ai_score').value) || 8.0,
                    max_budget_percent: parseFloat(document.getElementById('param_max_budget').value) || 25.0,
                    take_profit_pct: parseFloat(document.getElementById('param_tp_pct').value) || 3.0,
                    stop_loss_pct: parseFloat(document.getElementById('param_sl_pct').value) || 1.5,
                    trailing_callback_pct: parseFloat(document.getElementById('param_trailing_callback').value) || 0.6,
                    min_5m_volume_usd: parseFloat(document.getElementById('param_min_volume_usd').value) || 50000,
                    require_futures_oi: true
                }};

                const res = await fetch('/api/strategy-config', {{
                    method: 'POST',
                    headers: {{ ...getAuthHeaders(), 'Content-Type': 'application/json' }},
                    body: JSON.stringify(payload)
                }});
                if (res.ok) {{
                    alert('✅ [BAŞARILI]: Tüm Quant Parametreleri Canlı Otonom Motora ve Veritabanına Kaydedildi!\n\n• Min Hacim: $' + payload.min_volume_usd.toLocaleString() + ' USD\n• Hacim Çarpanı: ' + payload.volume_spike_multiplier + 'x\n• Hedef TP: %' + payload.take_profit_pct + ' | SL: %' + payload.stop_loss_pct + '\n• Kasa Bütçesi: %' + payload.max_budget_percent);
                }} else {{
                    alert('❌ Kaydetme hatası: ' + res.statusText);
                }}
            }} catch(e) {{ alert('Ayar kaydetme hatası: ' + e); }}
        }}

        async function triggerDustClean() {{
            try {{
                const res = await fetch('/api/clean-dust', {{ method: 'POST', headers: getAuthHeaders() }});
                const data = await res.json();
                alert('🧹 Kırıntı Temizliği Tamamlandı: ' + JSON.stringify(data.results || data));
            }} catch(e) {{ alert('Hata: ' + e); }}
        }}

        async function toggleTrailingStop(state) {{
            await fetch('/api/settings', {{
                method: 'POST',
                headers: {{ ...getAuthHeaders(), 'Content-Type': 'application/json' }},
                body: JSON.stringify({{ trailing_stop_enabled: state }})
            }});
        }}

        function loadData() {{ window.location.reload(); }}
    </script>
</body>
</html>"""
    return html
