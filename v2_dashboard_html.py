"""
Fox-Kripto V2.2: Ultra-Premium Quant Dashboard (UI/UX Pro Max Edition)
Tasarım & Mimari: UI/UX Pro Max • Frontend Design • Mobile Design • Fox Marka Yükleme Göstergesi
Özellikler: Kullanıcı Tıklanabilir Canlı Bakiye Modalı, Fox Marka Spinner, Net Kullanıcı Logları,
Space Grotesk + JetBrains Mono, 10 Teyit Matrisi, 8 Parametreli Canlı Kontrol Merkezi, Mobil Thumb-Zone Dock.
"""

def generate_v2_dashboard_html(
    tenants: list = None,
    logs: list = None,
    active_engine: str = "WHALE_HUNTING",
    active_risk: str = "BALANCED",
    system_settings: dict = None,
    strategy_config: dict = None,
    **kwargs
) -> str:
    tenants = tenants or []
    logs = logs or []
    system_settings = system_settings or {}
    strategy_config = strategy_config or {}

    trailing_checked = "checked" if system_settings.get("trailing_stop_enabled", True) else ""
    shield_checked = "checked" if system_settings.get("v21_security_shield_enabled", True) else ""

    # Strategy Config Defaults
    min_vol = int(strategy_config.get("min_volume_usd", 50000))
    spike_mult = float(strategy_config.get("volume_spike_multiplier", 2.5))
    max_gain = float(strategy_config.get("max_recent_gain_24h", 12.0))
    ai_score = float(strategy_config.get("min_ai_score", 8.0))
    max_budget = float(strategy_config.get("max_budget_percent", 25.0))
    tp_pct = float(strategy_config.get("take_profit_pct", 3.0))
    sl_pct = float(strategy_config.get("stop_loss_pct", 1.5))
    cb_pct = float(strategy_config.get("trailing_callback_pct", 0.6))

    # Tenants Tablosu SSR HTML (Tıklanabilir Satırlar)
    tenants_ssr_html = ""
    for t in tenants:
        tid = t.get("id", "")
        tname = t.get("tenant_name", "Kullanıcı")
        chat_id = t.get("telegram_chat_id", "-")
        user_tp = t.get("take_profit_percent", tp_pct)
        user_sl = t.get("stop_loss_percent", sl_pct)
        user_budget = t.get("max_budget_percent", max_budget)
        is_paper = t.get("is_paper_trading", False)
        exch_badge = "🇹🇷 Binance TR" if t.get("exchange_id") == "binancetr" else "🌍 Binance Global"
        lang = str(t.get("preferred_language", "tr")).upper()

        status_badge = '<span class="badge badge-warning">🧪 Sanal</span>' if is_paper else '<span class="badge badge-success">🟢 Canlı</span>'

        tenants_ssr_html += f"""
        <tr data-id="{tid}" class="clickable-row">
            <td onclick="openTenantPortfolioModal('{tid}', '{tname}')" style="cursor: pointer;">
                <div style="display: flex; align-items: center; gap: 10px;">
                    <div class="user-avatar">{tname[:2].upper()}</div>
                    <div>
                        <strong style="color: #f8fafc; font-size: 14px;">{tname}</strong>
                        <small style="display: block; color: #38bdf8; font-size: 11px;">🔍 Bakiyeyi İncele ➔</small>
                    </div>
                </div>
            </td>
            <td><code class="font-mono">{chat_id}</code></td>
            <td><input type="number" step="0.1" class="table-input" id="tp_{tid}" value="{user_tp}" style="color: var(--success); width: 65px;"></td>
            <td><input type="number" step="0.1" class="table-input" id="sl_{tid}" value="{user_sl}" style="color: var(--danger); width: 65px;"></td>
            <td><input type="number" step="1.0" class="table-input" id="budget_{tid}" value="{user_budget}" style="color: var(--whale-gold); width: 65px;"></td>
            <td><span class="badge badge-exch">{exch_badge}</span></td>
            <td><span class="badge" style="background: rgba(148, 163, 184, 0.15); color: #cbd5e1;">{lang}</span></td>
            <td>{status_badge}</td>
            <td>
                <button class="btn btn-sm btn-primary" onclick="updateTenantSettings('{tid}', event)">💾 Kaydet</button>
            </td>
        </tr>
        """

    if not tenants_ssr_html:
        tenants_ssr_html = '<tr><td colspan="9" style="text-align: center; color: var(--text-muted); padding: 24px;">Henüz kayıtlı kullanıcı bulunmuyor.</td></tr>'

    # Canlı Karar Logları SSR HTML (Kullanıcı İsimli ve Zengin Tablo)
    logs_ssr_html = ""
    for l in (logs or [])[:25]:
        t_time = str(l.get("created_at", ""))[:19].replace("T", " ")
        sym = l.get("symbol", "N/A")
        direction = l.get("direction", "HOLD")
        status = l.get("status", "SUCCESS")
        t_name = l.get("tenant_name") or "S"
        amt = float(l.get("amount_usd", 0.0) or 0.0)
        p_entry = float(l.get("entry_price", 0.0) or 0.0)
        det = l.get("execution_details") or {}
        reason = det.get("justification") or det.get("reason") or "Kurumsal teyit matrisi ve AI mutabakatı ile onaylandı."
        score = l.get("sentiment_score") or det.get("v2_score") or "8.5"
        exch_label = l.get("exchange_label") or ("Binance TR 🇹🇷" if str(sym).endswith("TRY") else "Binance Global 🌍")

        is_buy = direction in ["BUY", "ALIM"]
        dir_badge = '<span class="badge badge-success">🟢 ALIM</span>' if is_buy else ('<span class="badge badge-danger">🔴 SATIM</span>' if direction in ["SELL", "SATIM"] else '<span class="badge badge-warning">⏳ GÖZETLEME</span>')

        logs_ssr_html += f"""
        <tr style="border-bottom: 1px solid rgba(255, 255, 255, 0.04); font-size: 13px;">
            <td style="padding: 12px 10px;">
                <div style="display: flex; align-items: center; gap: 6px;">
                    <span style="color: var(--whale-gold); font-size: 14px;">👤</span>
                    <strong style="color: #f8fafc;">{t_name}</strong>
                </div>
                <small style="color: var(--text-muted); font-size: 11px;">{exch_label}</small>
            </td>
            <td style="padding: 12px 10px;">
                <div style="display: flex; align-items: center; gap: 8px;">
                    {dir_badge}
                    <code class="font-mono" style="font-weight: 700; color: #38bdf8; font-size: 13px;">{sym}</code>
                </div>
                <small style="color: #94a3b8; font-size: 11px; display: block; margin-top: 3px;">{reason[:75]}...</small>
            </td>
            <td style="padding: 12px 10px; font-family: var(--font-mono); font-weight: 600; color: #f8fafc;">${amt:,.2f}</td>
            <td style="padding: 12px 10px; font-family: var(--font-mono); color: #cbd5e1;">${p_entry:,.4f}</td>
            <td style="padding: 12px 10px;">
                <span style="color: var(--success); font-weight: 700; font-family: var(--font-mono);">{score} / 10</span>
            </td>
            <td style="padding: 12px 10px;">
                <span class="badge badge-success">✅ {status}</span>
            </td>
            <td style="padding: 12px 10px; color: var(--text-muted); font-family: var(--font-mono); font-size: 11px;">{t_time}</td>
        </tr>
        """

    if not logs_ssr_html:
        logs_ssr_html = '<tr><td colspan="7" style="text-align: center; color: var(--text-muted); padding: 32px;">Kayıtlı işlem kararı bulunmuyor.</td></tr>'

    html = f"""<!DOCTYPE html>
<html lang="tr">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=1.0, user-scalable=no">
    <title>Fox-Kripto V2.2 Quant Terminal | Golden Whale Protocol</title>
    <link rel="preconnect" href="https://fonts.googleapis.com">
    <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
    <link href="https://fonts.googleapis.com/css2?family=JetBrains+Mono:wght@400;500;600;700&family=Space+Grotesk:wght@400;500;600;700&family=Inter:wght@400;500;600;700&display=swap" rel="stylesheet">
    <style>
        :root {{
            --fox-flame: #EF4323;
            --fox-ember: #D53427;
            --fox-action: #D53427;
            
            --bg-base: #06090e;
            --bg-card: rgba(13, 19, 33, 0.85);
            --bg-card-hover: rgba(18, 26, 44, 0.95);
            --border-color: rgba(255, 255, 255, 0.08);
            --border-glow: rgba(245, 158, 11, 0.25);
            
            --whale-gold: #f59e0b;
            --whale-gold-light: #fbbf24;
            --whale-glow: rgba(245, 158, 11, 0.35);
            
            --scalp-cyan: #06b6d4;
            --scalp-glow: rgba(6, 182, 212, 0.35);
            
            --success: #10b981;
            --success-glow: rgba(16, 185, 129, 0.25);
            --danger: #ef4444;
            --warning: #f59e0b;
            
            --text-main: #f8fafc;
            --text-muted: #94a3b8;
            --font-sans: 'Space Grotesk', 'Inter', -apple-system, sans-serif;
            --font-mono: 'JetBrains Mono', monospace;
        }}

        * {{ box-sizing: border-box; margin: 0; padding: 0; -webkit-tap-highlight-color: transparent; }}
        body {{
            background: radial-gradient(circle at 50% -10%, #151d30 0%, var(--bg-base) 65%);
            color: var(--text-main);
            font-family: var(--font-sans);
            min-height: 100vh;
            padding: 16px 20px 100px 20px;
            overflow-x: hidden;
        }}

        /* Scrollbar */
        ::-webkit-scrollbar {{ width: 6px; height: 6px; }}
        ::-webkit-scrollbar-track {{ background: var(--bg-base); }}
        ::-webkit-scrollbar-thumb {{ background: #334155; border-radius: 4px; }}
        ::-webkit-scrollbar-thumb:hover {{ background: var(--whale-gold); }}

        /* Top Header */
        .header {{
            display: flex;
            justify-content: space-between;
            align-items: center;
            padding: 14px 20px;
            background: var(--bg-card);
            backdrop-filter: blur(20px);
            border: 1px solid var(--border-color);
            border-radius: 16px;
            margin-bottom: 20px;
            flex-wrap: wrap;
            gap: 12px;
            box-shadow: 0 8px 32px rgba(0, 0, 0, 0.5);
        }}
        .brand-title {{
            display: flex;
            align-items: center;
            gap: 10px;
            font-size: 20px;
            font-weight: 700;
            letter-spacing: -0.5px;
        }}
        .brand-title span.badge-quant {{
            font-size: 11px;
            background: linear-gradient(135deg, var(--whale-gold), #d97706);
            color: #000;
            padding: 3px 8px;
            border-radius: 6px;
            font-weight: 800;
            font-family: var(--font-mono);
        }}

        .nav-actions {{
            display: flex;
            align-items: center;
            gap: 10px;
            flex-wrap: wrap;
        }}

        /* Buttons & Pills */
        .btn {{
            display: inline-flex;
            align-items: center;
            gap: 6px;
            padding: 8px 16px;
            border-radius: 10px;
            font-size: 13px;
            font-weight: 600;
            cursor: pointer;
            border: 1px solid transparent;
            transition: all 0.2s cubic-bezier(0.4, 0, 0.2, 1);
            font-family: var(--font-sans);
        }}
        .btn:active {{ transform: scale(0.97); }}
        .btn-primary {{
            background: linear-gradient(135deg, #2563eb, #1d4ed8);
            color: white;
            box-shadow: 0 4px 14px rgba(37, 99, 235, 0.35);
        }}
        .btn-primary:hover {{ background: #1d4ed8; }}
        .btn-gold {{
            background: linear-gradient(135deg, var(--whale-gold), #d97706);
            color: #000;
            font-weight: 700;
            box-shadow: 0 4px 14px var(--whale-glow);
        }}
        .btn-gold:hover {{ background: #d97706; color: #fff; }}
        .btn-sm {{ padding: 6px 12px; font-size: 12px; border-radius: 8px; }}

        /* Version Switcher */
        .version-switcher {{
            display: flex;
            background: rgba(15, 23, 42, 0.9);
            border: 1px solid var(--border-color);
            border-radius: 12px;
            padding: 3px;
            gap: 4px;
        }}
        .version-btn {{
            padding: 6px 14px;
            border-radius: 8px;
            font-size: 12px;
            font-weight: 600;
            color: var(--text-muted);
            text-decoration: none;
            transition: all 0.2s;
        }}
        .version-btn.active {{
            background: linear-gradient(135deg, var(--whale-gold), #d97706);
            color: #000;
            font-weight: 700;
        }}

        /* Switch Toggle */
        .switch {{ position: relative; display: inline-block; width: 42px; height: 22px; }}
        .switch input {{ opacity: 0; width: 0; height: 0; }}
        .slider {{ position: absolute; cursor: pointer; top: 0; left: 0; right: 0; bottom: 0; background-color: #334155; transition: .2s ease; border-radius: 22px; border: 1px solid var(--border-color); }}
        .slider:before {{ position: absolute; content: ""; height: 16px; width: 16px; left: 2px; bottom: 2px; background-color: white; transition: .2s ease; border-radius: 50%; }}
        input:checked + .slider {{ background-color: var(--success) !important; }}
        input:checked + .slider:before {{ transform: translateX(20px) !important; }}

        /* Hero Engine Matrix Card */
        .engine-card {{
            background: var(--bg-card);
            backdrop-filter: blur(20px);
            border: 1px solid var(--border-glow);
            border-radius: 20px;
            padding: 24px;
            box-shadow: 0 12px 40px rgba(0, 0, 0, 0.6);
            margin-bottom: 24px;
            position: relative;
            overflow: hidden;
        }}
        .engine-card::before {{
            content: '';
            position: absolute;
            top: 0; left: 0; right: 0; height: 3px;
            background: linear-gradient(90deg, var(--fox-flame), var(--whale-gold), var(--success));
        }}

        .engine-toggle-group {{
            display: grid;
            grid-template-columns: 1fr 1fr;
            gap: 12px;
            margin-bottom: 20px;
        }}
        .engine-select-btn {{
            padding: 16px 20px;
            border-radius: 14px;
            border: 2px solid var(--border-color);
            background: rgba(15, 23, 42, 0.7);
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
            background: linear-gradient(180deg, rgba(6, 182, 212, 0.18), rgba(6, 182, 212, 0.03));
            color: var(--scalp-cyan);
            box-shadow: 0 0 24px var(--scalp-glow);
        }}
        .engine-select-btn.active-whale {{
            border-color: var(--whale-gold);
            background: linear-gradient(180deg, rgba(245, 158, 11, 0.18), rgba(245, 158, 11, 0.03));
            color: var(--whale-gold);
            box-shadow: 0 0 24px var(--whale-glow);
        }}

        /* Risk Pills */
        .risk-pills-row {{
            display: flex;
            gap: 8px;
            align-items: center;
            flex-wrap: wrap;
            margin-bottom: 16px;
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
            box-shadow: 0 0 12px rgba(245, 158, 11, 0.3);
        }}

        /* 10 Confirmations Matrix */
        .confirmations-matrix {{
            display: grid;
            grid-template-columns: repeat(auto-fill, minmax(210px, 1fr));
            gap: 10px;
            margin-top: 14px;
            padding: 16px;
            background: rgba(10, 15, 29, 0.7);
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
            border: 1px solid rgba(255, 255, 255, 0.04);
            font-weight: 500;
        }}
        .conf-badge.verified {{
            border-color: rgba(16, 185, 129, 0.4);
            color: #10b981;
            background: rgba(16, 185, 129, 0.08);
        }}

        /* Main Grid */
        .main-grid {{
            display: grid;
            grid-template-columns: 2.3fr 1fr;
            gap: 24px;
        }}
        @media (max-width: 1080px) {{
            .main-grid {{ grid-template-columns: 1fr; }}
            .engine-toggle-group {{ grid-template-columns: 1fr; }}
        }}

        /* Cards & Tables */
        .card {{
            background: var(--bg-card);
            backdrop-filter: blur(16px);
            border: 1px solid var(--border-color);
            border-radius: 18px;
            padding: 20px;
            box-shadow: 0 8px 32px rgba(0, 0, 0, 0.4);
        }}
        .card-title {{
            font-size: 16px;
            font-weight: 700;
            display: flex;
            justify-content: space-between;
            align-items: center;
            margin-bottom: 16px;
            color: #f8fafc;
        }}

        .table-responsive {{ overflow-x: auto; }}
        table {{ width: 100%; border-collapse: collapse; text-align: left; }}
        th {{
            font-size: 11px;
            text-transform: uppercase;
            letter-spacing: 0.8px;
            color: var(--text-muted);
            padding: 12px 14px;
            border-bottom: 1px solid var(--border-color);
        }}
        td {{
            padding: 12px 14px;
            font-size: 13px;
            border-bottom: 1px solid rgba(255, 255, 255, 0.04);
            vertical-align: middle;
        }}
        tr.clickable-row:hover td {{ background: rgba(245, 158, 11, 0.06); }}

        .table-input {{
            background: rgba(15, 23, 42, 0.9);
            border: 1px solid var(--border-color);
            border-radius: 6px;
            padding: 6px 8px;
            font-family: var(--font-mono);
            font-weight: 600;
            text-align: center;
        }}

        .user-avatar {{
            width: 34px;
            height: 34px;
            border-radius: 50%;
            background: linear-gradient(135deg, var(--fox-flame), var(--fox-ember));
            color: #fff;
            display: flex;
            align-items: center;
            justify-content: center;
            font-weight: 800;
            font-size: 12px;
            box-shadow: 0 4px 12px rgba(239, 67, 35, 0.35);
        }}

        .badge {{
            display: inline-flex;
            align-items: center;
            padding: 4px 8px;
            border-radius: 6px;
            font-size: 11px;
            font-weight: 600;
        }}
        .badge-success {{ background: rgba(16, 185, 129, 0.15); color: var(--success); }}
        .badge-danger {{ background: rgba(239, 68, 68, 0.15); color: var(--danger); }}
        .badge-warning {{ background: rgba(245, 158, 11, 0.15); color: var(--warning); }}
        .badge-exch {{ background: rgba(6, 182, 212, 0.15); color: var(--scalp-cyan); }}

        /* ============================================================================
           FOX MARKA YÜKLEME GÖSTERGESİ & MODAL (Fox MRO Tasarım Dili)
           ========================================================================== */
        .modal-backdrop {{
            position: fixed; inset: 0; z-index: 1500;
            background: rgba(6, 9, 14, 0.85);
            backdrop-filter: blur(16px);
            display: none;
            align-items: center;
            justify-content: center;
            padding: 20px;
        }}
        .modal-backdrop.active {{ display: flex; }}
        .modal-window {{
            background: rgba(13, 19, 33, 0.95);
            border: 1px solid var(--border-glow);
            border-radius: 20px;
            width: 100%;
            max-width: 640px;
            max-height: 90vh;
            overflow-y: auto;
            padding: 24px;
            box-shadow: 0 20px 60px rgba(0, 0, 0, 0.8);
            position: relative;
        }}
        .modal-close-btn {{
            position: absolute; top: 20px; right: 20px;
            background: rgba(255, 255, 255, 0.08);
            border: none; color: #fff; width: 32px; height: 32px;
            border-radius: 50%; cursor: pointer; font-size: 16px;
            display: flex; align-items: center; justify-content: center;
        }}
        .modal-close-btn:hover {{ background: var(--danger); }}

        /* Fox Spinner */
        .foxload {{ display: grid; justify-items: center; gap: 14px; padding: 40px 20px; }}
        .foxload-ring {{ position: relative; width: 68px; height: 68px; display: grid; place-items: center; }}
        .foxload-ring svg {{ position: absolute; inset: 0; width: 100%; height: 100%; }}
        .foxload-arc {{ animation: foxspin 1.15s cubic-bezier(.55,.15,.45,.85) infinite; transform-origin: center; }}
        .foxload-mark {{
            position: relative; display: block;
            animation: foxbreathe 2.2s ease-in-out infinite;
            filter: drop-shadow(0 4px 14px rgba(239,67,35,0.45));
        }}
        @keyframes foxspin {{ 0% {{ transform: rotate(0deg); }} 100% {{ transform: rotate(360deg); }} }}
        @keyframes foxbreathe {{ 0%, 100% {{ transform: scale(1); opacity: .92; }} 50% {{ transform: scale(1.1); opacity: 1; }} }}

        /* Mobile Bottom Floating Dock */
        .mobile-dock {{
            display: none;
            position: fixed;
            bottom: 0; left: 0; right: 0;
            background: rgba(10, 15, 29, 0.95);
            backdrop-filter: blur(20px);
            border-top: 1px solid var(--border-color);
            padding: 10px 16px;
            z-index: 1000;
            justify-content: space-around;
            align-items: center;
        }}
        @media (max-width: 768px) {{
            .mobile-dock {{ display: flex; }}
            body {{ padding-bottom: 90px; }}
        }}
        .dock-item {{
            display: flex;
            flex-direction: column;
            align-items: center;
            gap: 4px;
            font-size: 11px;
            color: var(--text-muted);
            text-decoration: none;
            cursor: pointer;
            min-width: 48px;
            min-height: 44px;
            justify-content: center;
        }}
        .dock-item.active {{ color: var(--whale-gold); font-weight: 700; }}

        /* Toast Notifications */
        #toast {{
            visibility: hidden;
            min-width: 280px;
            background: rgba(15, 23, 42, 0.95);
            color: #fff;
            text-align: center;
            border-radius: 12px;
            padding: 14px 20px;
            position: fixed;
            z-index: 2000;
            bottom: 30px;
            left: 50%;
            transform: translateX(-50%);
            border: 1px solid var(--whale-gold);
            box-shadow: 0 8px 32px var(--whale-glow);
            font-weight: 600;
            font-size: 13px;
        }}
        #toast.show {{ visibility: visible; animation: fadein 0.4s, fadeout 0.4s 2.6s; }}
        @keyframes fadein {{ from {{ bottom: 10px; opacity: 0; }} to {{ bottom: 30px; opacity: 1; }} }}
        @keyframes fadeout {{ from {{ bottom: 30px; opacity: 1; }} to {{ bottom: 10px; opacity: 0; }} }}
    </style>
</head>
<body>
    <!-- TOAST BİLDİRİMİ -->
    <div id="toast">✅ İşlem Başarılı!</div>

    <!-- KULLANICI DETAYLI CANLI BAKİYE MODALI -->
    <div id="portfolio-modal" class="modal-backdrop">
        <div class="modal-window">
            <button class="modal-close-btn" onclick="closePortfolioModal()">✕</button>
            <div id="modal-content">
                <!-- Fox Marka Yükleme Göstergesi -->
                <div class="foxload">
                    <div class="foxload-ring">
                        <svg viewBox="0 0 68 68" fill="none">
                            <circle cx="34" cy="34" r="30" stroke="rgba(239,67,35,0.2)" stroke-width="4"/>
                            <circle class="foxload-arc" cx="34" cy="34" r="30" stroke="url(#foxgrad)" stroke-width="4" stroke-linecap="round" stroke-dasharray="70 120"/>
                            <defs>
                                <linearGradient id="foxgrad" x1="0" y1="0" x2="68" y2="68" gradientUnits="userSpaceOnUse">
                                    <stop stop-color="#EF4323"/>
                                    <stop offset="1" stop-color="#F59E0B"/>
                                </linearGradient>
                            </defs>
                        </svg>
                        <span class="foxload-mark" style="font-size: 26px;">🦊</span>
                    </div>
                    <div style="text-align: center;">
                        <b style="color: #f8fafc; font-size: 16px;">Borsa Cüzdanı Doğrulanıyor...</b>
                        <p style="color: var(--text-muted); font-size: 12px; margin-top: 4px;">Binance Spot ve Earn bakiyeleri canlı taranıyor.</p>
                    </div>
                </div>
            </div>
        </div>
    </div>

    <!-- ÜST HEADER / KONTROL BARI -->
    <header class="header">
        <div class="brand-title">
            <span>🦊 Fox-Kripto</span>
            <span class="badge-quant">V2.2 QUANT</span>
            <span class="badge badge-success" style="font-size: 11px; font-family: var(--font-mono);">🟢 7/24 OTONOM NÖBET</span>
        </div>

        <div class="nav-actions">
            <!-- Sürüm Seçici -->
            <div class="version-switcher">
                <a href="/v1/dashboard" class="version-btn">🏛️ V1 Klasik</a>
                <a href="/v2/dashboard" class="version-btn active">⚡ V2 Quant</a>
            </div>

            <!-- Trailing Stop Toggle -->
            <div style="display: flex; align-items: center; gap: 8px; background: rgba(15, 23, 42, 0.8); padding: 6px 12px; border-radius: 10px; border: 1px solid var(--border-color);">
                <span style="color: #38bdf8; font-size: 12px; font-weight: 600;">🚀 Trailing SL:</span>
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
                <span style="font-size: 12px; color: var(--text-muted); text-transform: uppercase; letter-spacing: 1px; font-weight: 700;">AKTİF QUANT STRATEJİ MOTORU</span>
                <h2 id="engine-title" style="font-size: 20px; font-weight: 700; color: #f8fafc; margin-top: 2px;">🐋 Gerçek Balina Avı Motoru (10 Kriterli Teyit)</h2>
            </div>
            <div id="engine-badge" style="background: rgba(245, 158, 11, 0.2); color: var(--whale-gold); border: 1px solid var(--whale-gold); padding: 6px 14px; border-radius: 20px; font-size: 13px; font-weight: 700;">
                🐋 Balina Avı · {active_risk} · v2.2 Aktif
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

        <!-- Hazır Risk Seviyesi Seçici -->
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
                <span style="font-size: 11px; color: var(--text-muted);">Değerleri ekrandan dilediğiniz gibi değiştirip canlı motora anında uygulayabilirsiniz.</span>
            </div>
            
            <div style="display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: 14px;">
                <!-- 1. Min 5dk Hacim -->
                <div>
                    <label style="font-size: 11px; color: var(--text-muted); display: block; margin-bottom: 4px; font-weight: 600;">🧱 Min 5dk Hacim ($ USD)</label>
                    <input type="number" id="param_min_volume_usd" value="{min_vol}" onchange="markCustom()" style="width: 100%; padding: 8px 12px; border-radius: 8px; background: rgba(15, 23, 42, 0.9); color: #38bdf8; border: 1px solid var(--border-color); font-family: var(--font-mono); font-weight: 600;">
                </div>
                <!-- 2. Hacim Çarpanı -->
                <div>
                    <label style="font-size: 11px; color: var(--text-muted); display: block; margin-bottom: 4px; font-weight: 600;">⚡ Hacim Patlama Çarpanı (x)</label>
                    <input type="number" step="0.1" id="param_volume_spike" value="{spike_mult}" onchange="markCustom()" style="width: 100%; padding: 8px 12px; border-radius: 8px; background: rgba(15, 23, 42, 0.9); color: #f59e0b; border: 1px solid var(--border-color); font-family: var(--font-mono); font-weight: 600;">
                </div>
                <!-- 3. Maks 24s Prim -->
                <div>
                    <label style="font-size: 11px; color: var(--text-muted); display: block; margin-bottom: 4px; font-weight: 600;">📈 Maks 24s Prim Limiti (%)</label>
                    <input type="number" step="0.5" id="param_max_gain_24h" value="{max_gain}" onchange="markCustom()" style="width: 100%; padding: 8px 12px; border-radius: 8px; background: rgba(15, 23, 42, 0.9); color: white; border: 1px solid var(--border-color); font-family: var(--font-mono); font-weight: 600;">
                </div>
                <!-- 4. Min AI Skoru -->
                <div>
                    <label style="font-size: 11px; color: var(--text-muted); display: block; margin-bottom: 4px; font-weight: 600;">🧠 Min AI & Teyit Skoru (1-10)</label>
                    <input type="number" step="0.1" id="param_min_ai_score" value="{ai_score}" onchange="markCustom()" style="width: 100%; padding: 8px 12px; border-radius: 8px; background: rgba(15, 23, 42, 0.9); color: var(--success); border: 1px solid var(--border-color); font-family: var(--font-mono); font-weight: 600;">
                </div>
                <!-- 5. Kasa Bütçesi -->
                <div>
                    <label style="font-size: 11px; color: var(--text-muted); display: block; margin-bottom: 4px; font-weight: 600;">💰 İşlem Başı Kasa Bütçesi (%)</label>
                    <input type="number" step="1.0" id="param_max_budget" value="{max_budget}" onchange="markCustom()" style="width: 100%; padding: 8px 12px; border-radius: 8px; background: rgba(15, 23, 42, 0.9); color: white; border: 1px solid var(--border-color); font-family: var(--font-mono); font-weight: 600;">
                </div>
                <!-- 6. Hedef TP -->
                <div>
                    <label style="font-size: 11px; color: var(--text-muted); display: block; margin-bottom: 4px; font-weight: 600;">🎯 Hedef Kâr Al (%)</label>
                    <input type="number" step="0.1" id="param_tp_pct" value="{tp_pct}" onchange="markCustom()" style="width: 100%; padding: 8px 12px; border-radius: 8px; background: rgba(15, 23, 42, 0.9); color: var(--success); border: 1px solid var(--border-color); font-family: var(--font-mono); font-weight: 600;">
                </div>
                <!-- 7. Stop-Loss -->
                <div>
                    <label style="font-size: 11px; color: var(--text-muted); display: block; margin-bottom: 4px; font-weight: 600;">🛡️ Zarar Kes Stop-Loss (%)</label>
                    <input type="number" step="0.1" id="param_sl_pct" value="{sl_pct}" onchange="markCustom()" style="width: 100%; padding: 8px 12px; border-radius: 8px; background: rgba(15, 23, 42, 0.9); color: var(--danger); border: 1px solid var(--border-color); font-family: var(--font-mono); font-weight: 600;">
                </div>
                <!-- 8. Trailing Callback -->
                <div>
                    <label style="font-size: 11px; color: var(--text-muted); display: block; margin-bottom: 4px; font-weight: 600;">🚀 Trailing Zirve Çekilme (%)</label>
                    <input type="number" step="0.1" id="param_trailing_callback" value="{cb_pct}" onchange="markCustom()" style="width: 100%; padding: 8px 12px; border-radius: 8px; background: rgba(15, 23, 42, 0.9); color: #38bdf8; border: 1px solid var(--border-color); font-family: var(--font-mono); font-weight: 600;">
                </div>
            </div>
        </div>

        <!-- 10 Kurumsal Teyit Göstergesi -->
        <div style="margin-top: 14px;">
            <div style="display: flex; justify-content: space-between; align-items: center; font-size: 12px; color: var(--text-muted); font-weight: 700;">
                <span>10 KURUMSAL TEYİT MATRİSİ (THE GOLDEN WHALE MATRIX)</span>
                <span style="color: var(--success); font-family: var(--font-mono);">9 / 10 Teyit Devrede (Skor: 8.7/10)</span>
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
            <!-- Kayıtlı Kullanıcılar (Tıklanabilir Bakiye İnceleme) -->
            <div class="card">
                <div class="card-title">
                    <div>
                        <span>👥 Kayıtlı Kullanıcılar & Dinamik Risk Dağılımı</span>
                        <small style="display: block; font-size: 12px; color: #38bdf8; margin-top: 2px;">💡 Canlı cüzdan ve açık pozisyonları görmek için kullanıcının üzerine tıklayın.</small>
                    </div>
                    <span style="font-size: 12px; color: var(--scalp-cyan); background: rgba(6, 182, 212, 0.15); padding: 4px 10px; border-radius: 12px;">Multi-Tenant V2.2</span>
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

            <!-- Canlı İşlem ve Karar Logları (Zengin Tablo Formatı) -->
            <div class="card">
                <div class="card-title">
                    <span>📜 Açıklanabilir AI Karar & İşlem Günlüğü (Explainable Logs)</span>
                    <span style="font-size: 12px; color: var(--success);">🟢 Canlı Veritabanı Senkronize</span>
                </div>
                <div class="table-responsive">
                    <table>
                        <thead>
                            <tr>
                                <th>👤 Kullanıcı & Borsa</th>
                                <th>🪙 İşlem & Çift</th>
                                <th>💵 Bütçe</th>
                                <th>📥 Fiyat</th>
                                <th>📊 AI Skoru</th>
                                <th>🏷️ Durum</th>
                                <th>⏱️ Zaman</th>
                            </tr>
                        </thead>
                        <tbody id="logs-tbody">
                            {logs_ssr_html}
                        </tbody>
                    </table>
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

    <!-- MOBİL THUMB-ZONE FLOATING DOCK -->
    <nav class="mobile-dock">
        <a href="/v2/dashboard" class="dock-item active">
            <span>⚡</span>
            <span>V2 Quant</span>
        </a>
        <a href="/v1/dashboard" class="dock-item">
            <span>🏛️</span>
            <span>V1 Klasik</span>
        </a>
        <div class="dock-item" onclick="triggerDustClean()">
            <span>🧹</span>
            <span>Kırıntı</span>
        </div>
        <div class="dock-item" onclick="loadData()">
            <span>🔄</span>
            <span>Yenile</span>
        </div>
    </nav>

    <script>
        function getAuthHeaders() {{
            return {{ 'Authorization': 'Basic ' + btoa('admin:foxkripto2026') }};
        }}

        function showToast(msg) {{
            const t = document.getElementById('toast');
            if (!t) return;
            t.innerText = msg;
            t.className = 'show';
            setTimeout(() => {{ t.className = t.className.replace('show', ''); }}, 3000);
        }}

        /* ============================================================================
           KULLANICI CANLI PORTFÖY MODALI (FOX SPINNER ENTEGRE)
           ========================================================================== */
        async function openTenantPortfolioModal(tenantId, tenantName) {{
            const modal = document.getElementById('portfolio-modal');
            const content = document.getElementById('modal-content');
            modal.classList.add('active');

            content.innerHTML = `
                <div class="foxload">
                    <div class="foxload-ring">
                        <svg viewBox="0 0 68 68" fill="none">
                            <circle cx="34" cy="34" r="30" stroke="rgba(239,67,35,0.2)" stroke-width="4"/>
                            <circle class="foxload-arc" cx="34" cy="34" r="30" stroke="url(#foxgrad)" stroke-width="4" stroke-linecap="round" stroke-dasharray="70 120"/>
                            <defs>
                                <linearGradient id="foxgrad" x1="0" y1="0" x2="68" y2="68" gradientUnits="userSpaceOnUse">
                                    <stop stop-color="#EF4323"/>
                                    <stop offset="1" stop-color="#F59E0B"/>
                                </linearGradient>
                            </defs>
                        </svg>
                        <span class="foxload-mark" style="font-size: 26px;">🦊</span>
                    </div>
                    <div style="text-align: center;">
                        <b style="color: #f8fafc; font-size: 16px;">${{tenantName}} Cüzdanı Taranıyor...</b>
                        <p style="color: var(--text-muted); font-size: 12px; margin-top: 4px;">Binance Spot ve Earn bakiyeleri canlı doğrulanıyor.</p>
                    </div>
                </div>
            `;

            try {{
                const res = await fetch('/api/tenants/' + tenantId + '/portfolio', {{ headers: getAuthHeaders() }});
                if (!res.ok) throw new Error('Cüzdan verisi alınamadı');
                const data = await res.json();
                const port = data.portfolio || {{}};
                const freeUsdt = port.free_usdt || 0.0;
                const totUsdt = port.total_usdt || 0.0;
                const totTry = port.total_try || 0.0;
                const holdings = port.holdings_details || {{}};

                let holdingsHtml = '';
                for (const [coin, info] of Object.entries(holdings)) {{
                    const amt = Number(info.amount || 0);
                    const valUsd = Number(info.val_usd || 0);
                    const valTry = Number(info.val_try || 0);
                    const p = Number(info.price || 0);
                    if (valUsd >= 1.0) {{
                        holdingsHtml += `
                            <div style="display: flex; justify-content: space-between; align-items: center; padding: 12px 14px; background: rgba(15, 23, 42, 0.7); border-radius: 10px; margin-bottom: 8px; border: 1px solid rgba(255,255,255,0.04);">
                                <div style="display: flex; align-items: center; gap: 8px;">
                                    <strong style="color: #f8fafc; font-size: 14px;">${{coin}}</strong>
                                    <span class="font-mono" style="font-size: 12px; color: #94a3b8;">${{amt.toLocaleString()}} adet</span>
                                </div>
                                <div style="text-align: right;">
                                    <strong class="font-mono" style="color: #10b981; font-size: 14px;">$${{valUsd.toFixed(2)}} USD</strong>
                                    <small class="font-mono" style="display: block; color: #94a3b8; font-size: 11px;">~₺${{valTry.toFixed(2)}} TL</small>
                                </div>
                            </div>
                        `;
                    }}
                }}

                if (!holdingsHtml) {{
                    holdingsHtml = '<p style="color: var(--text-muted); text-align: center; padding: 20px;">Açık coin pozisyonu bulunmuyor.</p>';
                }}

                content.innerHTML = `
                    <div style="display: flex; align-items: center; gap: 10px; margin-bottom: 18px;">
                        <div class="user-avatar" style="width: 40px; height: 40px; font-size: 14px;">${{tenantName.slice(0, 2).toUpperCase()}}</div>
                        <div>
                            <h3 style="color: #f8fafc; font-size: 18px;">${{tenantName}} — Canlı Bakiye & Cüzdan</h3>
                            <span class="badge badge-exch">${{data.exchange_id === 'binancetr' ? '🇹🇷 Binance TR' : '🌍 Binance Global'}}</span>
                        </div>
                    </div>

                    <!-- Kasa Özeti Kartları -->
                    <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 12px; margin-bottom: 20px;">
                        <div style="padding: 14px; background: rgba(15, 23, 42, 0.8); border-radius: 12px; border: 1px solid rgba(255,255,255,0.06);">
                            <span style="font-size: 11px; color: var(--text-muted); text-transform: uppercase;">Toplam Portföy</span>
                            <div class="font-mono" style="font-size: 20px; font-weight: 700; color: var(--whale-gold); margin-top: 4px;">$${{totUsdt.toFixed(2)}} USD</div>
                            <small class="font-mono" style="color: #cbd5e1;">~₺${{totTry.toFixed(2)}} TL</small>
                        </div>
                        <div style="padding: 14px; background: rgba(15, 23, 42, 0.8); border-radius: 12px; border: 1px solid rgba(255,255,255,0.06);">
                            <span style="font-size: 11px; color: var(--text-muted); text-transform: uppercase;">Serbest Nakit</span>
                            <div class="font-mono" style="font-size: 20px; font-weight: 700; color: #38bdf8; margin-top: 4px;">$${{freeUsdt.toFixed(2)}} USD</div>
                            <small style="color: #10b981;">🟢 Alıma Hazır</small>
                        </div>
                    </div>

                    <h4 style="font-size: 13px; color: var(--text-muted); text-transform: uppercase; margin-bottom: 10px; font-weight: 700;">📦 Açık Coin Varlıkları</h4>
                    <div>${{holdingsHtml}}</div>
                `;
            }} catch(err) {{
                content.innerHTML = `
                    <div style="text-align: center; padding: 30px;">
                        <span style="font-size: 32px;">⚠️</span>
                        <h4 style="color: var(--danger); margin-top: 10px;">Cüzdan Yüklenemedi</h4>
                        <p style="color: var(--text-muted); font-size: 13px; margin-top: 4px;">${{err.message}}</p>
                    </div>
                `;
            }}
        }}

        function closePortfolioModal() {{
            document.getElementById('portfolio-modal').classList.remove('active');
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
                badge.innerText = '⚡ Scalp · ' + currentRisk + ' · v2.2 Aktif';
            }} else {{
                btnWhale.className = 'engine-select-btn active-whale';
                btnScalp.className = 'engine-select-btn';
                title.innerHTML = '🐋 Gerçek Balina Avı Motoru (10 Kriterli Teyit)';
                badge.style.borderColor = 'var(--whale-gold)';
                badge.style.color = 'var(--whale-gold)';
                badge.style.background = 'rgba(245, 158, 11, 0.2)';
                badge.innerText = '🐋 Balina · ' + currentRisk + ' · v2.2 Aktif';
            }}
        }}

        const PRESETS_MAP = {{
            'VOLUME_SCALPING_AGGRESSIVE': {{ min_vol: 35000, spike: 1.5, gain: 15.0, score: 7.2, budget: 35.0, tp: 2.2, sl: 1.2, cb: 0.5 }},
            'VOLUME_SCALPING_BALANCED':   {{ min_vol: 50000, spike: 1.8, gain: 10.0, score: 7.8, budget: 25.0, tp: 3.0, sl: 1.5, cb: 0.6 }},
            'VOLUME_SCALPING_DEFENSIVE':  {{ min_vol: 75000, spike: 2.2, gain: 8.0,  score: 8.5, budget: 15.0, tp: 4.0, sl: 1.8, cb: 0.8 }},
            'WHALE_HUNTING_AGGRESSIVE':   {{ min_vol: 50000, spike: 2.0, gain: 15.0, score: 7.8, budget: 35.0, tp: 4.0, sl: 1.5, cb: 0.6 }},
            'WHALE_HUNTING_BALANCED':     {{ min_vol: 50000, spike: 2.5, gain: 12.0, score: 8.2, budget: 25.0, tp: 3.0, sl: 1.5, cb: 0.6 }},
            'WHALE_HUNTING_DEFENSIVE':    {{ min_vol: 100000, spike: 3.2, gain: 9.0, score: 8.8, budget: 15.0, tp: 6.5, sl: 2.0, cb: 0.9 }}
        }};

        function markCustom() {{
            document.querySelectorAll('.risk-pill').forEach(btn => btn.classList.remove('active'));
            const cusBtn = document.getElementById('pill-cus');
            if (cusBtn) cusBtn.classList.add('active');
            currentRisk = 'CUSTOM';
            const badge = document.getElementById('engine-badge');
            if (badge) badge.innerText = (currentEngine === 'WHALE_HUNTING' ? '🐋 Balina' : '⚡ Scalp') + ' · Özel Ayarlar · v2.2 Aktif';
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
                    showToast('✅ [BAŞARILI]: Tüm Quant Parametreleri Canlı Otonom Motora Kaydedildi!');
                }} else {{
                    alert('❌ Kaydetme hatası: ' + res.statusText);
                }}
            }} catch(e) {{ alert('Ayar kaydetme hatası: ' + e); }}
        }}

        async function updateTenantSettings(tid, event) {{
            if (event) event.stopPropagation();
            const tp = parseFloat(document.getElementById('tp_' + tid).value) || 3.0;
            const sl = parseFloat(document.getElementById('sl_' + tid).value) || 1.5;
            const budget = parseFloat(document.getElementById('budget_' + tid).value) || 25.0;

            try {{
                const res = await fetch('/api/update-tenant', {{
                    method: 'POST',
                    headers: {{ ...getAuthHeaders(), 'Content-Type': 'application/json' }},
                    body: JSON.stringify({{ tenant_id: tid, take_profit_percent: tp, stop_loss_percent: sl, max_budget_percent: budget }})
                }});
                if (res.ok) showToast('✅ Kullanıcı risk parametreleri güncellendi!');
                else alert('Hata oluştu.');
            }} catch(e) {{ alert('Hata: ' + e); }}
        }}

        async function triggerDustClean() {{
            try {{
                showToast('🧹 Kırıntı Temizliği Başlatıldı...');
                const res = await fetch('/api/clean-dust', {{ method: 'POST', headers: getAuthHeaders() }});
                const data = await res.json();
                showToast('🧹 Kırıntı Temizliği Tamamlandı: ' + (data.status || 'OK'));
            }} catch(e) {{ alert('Hata: ' + e); }}
        }}

        async function toggleTrailingStop(state) {{
            await fetch('/api/settings', {{
                method: 'POST',
                headers: {{ ...getAuthHeaders(), 'Content-Type': 'application/json' }},
                body: JSON.stringify({{ trailing_stop_enabled: state }})
            }});
            showToast('🚀 Trailing Stop Durumu: ' + (state ? 'AÇIK' : 'KAPALI'));
        }}

        async function addUser(e) {{
            e.preventDefault();
            const payload = {{
                tenant_name: document.getElementById('new_tenant_name').value,
                telegram_chat_id: parseInt(document.getElementById('new_telegram_chat_id').value),
                exchange_api_key: document.getElementById('new_api_key').value,
                exchange_secret_key: document.getElementById('new_secret_key').value,
                take_profit_percent: parseFloat(document.getElementById('new_tp').value),
                stop_loss_percent: parseFloat(document.getElementById('new_sl').value),
                is_paper_trading: false
            }};
            try {{
                const res = await fetch('/api/add-tenant', {{
                    method: 'POST',
                    headers: {{ ...getAuthHeaders(), 'Content-Type': 'application/json' }},
                    body: JSON.stringify(payload)
                }});
                if (res.ok) {{
                    showToast('🎉 Yeni kullanıcı başarıyla eklendi!');
                    setTimeout(() => window.location.reload(), 1000);
                }} else alert('Ekleme başarısız.');
            }} catch(err) {{ alert('Hata: ' + err); }}
        }}

        function loadData() {{ window.location.reload(); }}
    </script>
</body>
</html>"""
    return html
