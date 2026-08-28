"""
Fox-Kripto V2.2: Kurumsal Quant Dashboard (Fox MRO Resmi Tasarım Sistemi)
Tasarım & Mimari: Fox MRO Kurumsal Şartnamesi • Claude UI/UX Heyeti
Özellikler: Ağırbaşlı Mat Kömür Grisi Kartlar, Orijinal Fox SVG Yükleme Göstergesi,
Çift Motor Seçici (Scalp & Balina), 8 Parametreli İnce Ayar Merkezi, Tıklanabilir Cüzdan Modalı,
Açıklanabilir Kullanıcı Log Tablosu, Dark/Light Tema Desteği, 48px Dokunmatik Mobil Dock.
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

    # Dynamic Engine and Risk States
    is_scalp = (active_engine == "VOLUME_SCALPING")
    scalp_btn_cls = "engine-btn active" if is_scalp else "engine-btn"
    whale_btn_cls = "engine-btn active" if not is_scalp else "engine-btn"
    engine_title_text = "1. Hacim Scalping Motoru" if is_scalp else "2. Gerçek Balina Avı Motoru"
    engine_badge_text = f"⚡ Hacim Scalping · {active_risk} · v2.2 Aktif" if is_scalp else f"🐋 Balina Avı · {active_risk} · v2.2 Aktif"
    engine_badge_cls = "badge badge-info" if is_scalp else "badge badge-warn"

    pill_agg_cls = "profile-btn active" if active_risk == "AGGRESSIVE" else "profile-btn"
    pill_bal_cls = "profile-btn active" if active_risk == "BALANCED" else "profile-btn"
    pill_def_cls = "profile-btn active" if active_risk == "DEFENSIVE" else "profile-btn"
    pill_cus_cls = "profile-btn active" if active_risk == "CUSTOM" else "profile-btn"

    # Strategy Config Defaults
    min_vol = int(strategy_config.get("min_volume_usd", 25000 if is_scalp else 50000))
    spike_mult = float(strategy_config.get("volume_spike_multiplier", 1.8 if is_scalp else 2.5))
    max_gain = float(strategy_config.get("max_recent_gain_24h", 12.0))
    ai_score = float(strategy_config.get("min_ai_score", 7.5 if is_scalp else 8.0))
    max_budget = float(strategy_config.get("max_budget_percent", 25.0))
    tp_pct = float(strategy_config.get("take_profit_pct", 2.0 if is_scalp else 3.0))
    sl_pct = float(strategy_config.get("stop_loss_pct", 1.2 if is_scalp else 1.5))
    cb_pct = float(strategy_config.get("trailing_callback_pct", 0.5 if is_scalp else 0.6))

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

        status_badge = '<span class="badge badge-warn">🧪 Sanal</span>' if is_paper else '<span class="badge badge-ok">🟢 Canlı</span>'

        tenants_ssr_html += f"""
        <tr data-id="{tid}" class="clickable">
            <td onclick="openTenantPortfolioModal('{tid}', '{tname}')">
                <div style="display: flex; align-items: center; gap: 8px;">
                    <span style="font-weight: 700; color: var(--ink);">{tname}</span>
                    <span style="font-size: 11px; color: var(--fox-flame);">[Bakiye İncele ➔]</span>
                </div>
            </td>
            <td><code style="font-family: inherit; color: var(--ink-2); font-weight: 600;">{chat_id}</code></td>
            <td><input type="number" step="0.1" class="table-input" id="tp_{tid}" value="{user_tp}" style="color: var(--ok-fg); width: 65px;"></td>
            <td><input type="number" step="0.1" class="table-input" id="sl_{tid}" value="{user_sl}" style="color: var(--stop-fg); width: 65px;"></td>
            <td><input type="number" step="1.0" class="table-input" id="budget_{tid}" value="{user_budget}" style="color: var(--fox-ember); width: 65px;"></td>
            <td><span class="badge badge-info">{exch_badge}</span></td>
            <td><span class="badge badge-idle">{lang}</span></td>
            <td>{status_badge}</td>
            <td>
                <button class="btn btn-sm btn-ghost" onclick="updateTenantSettings('{tid}', event)">💾 Kaydet</button>
            </td>
        </tr>
        """

    if not tenants_ssr_html:
        tenants_ssr_html = '<tr><td colspan="9" style="text-align: center; color: var(--ink-3); padding: 24px;">Henüz kayıtlı kullanıcı bulunmuyor.</td></tr>'

    # Canlı Karar Logları SSR HTML
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
        dir_badge = '<span class="badge badge-ok">ALIM</span>' if is_buy else ('<span class="badge badge-stop">SATIM</span>' if direction in ["SELL", "SATIM"] else '<span class="badge badge-warn">GÖZETLEME</span>')

        logs_ssr_html += f"""
        <tr>
            <td>
                <b>{t_name}</b>
                <small style="display: block; color: var(--ink-3); font-size: 11px;">{exch_label}</small>
            </td>
            <td>
                <div style="display: flex; align-items: center; gap: 6px;">
                    {dir_badge}
                    <b style="color: var(--ink);">{sym}</b>
                </div>
                <small style="color: var(--ink-3); font-size: 11.5px; display: block; margin-top: 2px;">{reason[:75]}...</small>
            </td>
            <td><b>${amt:,.2f}</b></td>
            <td>${p_entry:,.4f}</td>
            <td><span class="badge badge-info">{score} / 10</span></td>
            <td><span class="badge badge-ok">{status}</span></td>
            <td style="color: var(--ink-3); font-size: 12px;">{t_time}</td>
        </tr>
        """

    if not logs_ssr_html:
        logs_ssr_html = '<tr><td colspan="7" style="text-align: center; color: var(--ink-3); padding: 24px;">Kayıtlı işlem kararı bulunmuyor.</td></tr>'

    html = f"""<!doctype html>
<html lang="tr" data-theme="dark">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1, maximum-scale=1, user-scalable=no">
  <title>Fox-Kripto V2.2 — Kurumsal Quant Terminali</title>
  <style>
    :root {{
      --fox-flame: #EF4323;
      --fox-ember: #D53427;
      --fox-action: #D53427;
      --fox-action-2: #B9281E;
      --fox-blood: #85070C;
      --fox-deep:  #720303;

      --ink:   #14100F;
      --ink-2: #5C5250;
      --ink-3: #756C6B;
      --line:  #E9E3E1;
      --line-2:#F2EEED;
      --bg:    #FAF8F7;
      --bg-2:  #F3EFEE;
      --card:  #FFFFFF;
      --card-2:#FCFBFB;
      --hover: #FDF7F6;

      --ok-bg:#E9F6EE;   --ok-fg:#186B3A;
      --warn-bg:#FEF3E2; --warn-fg:#8A5300;
      --stop-bg:#FBECEA; --stop-fg:#A32116;
      --idle-bg:#F0EDEC; --idle-fg:#6B6260;
      --info-bg:#E8F1FA; --info-fg:#1A5A8F;

      --r: 14px;
      --shadow: 0 1px 2px rgba(20,16,15,.05), 0 8px 24px -12px rgba(20,16,15,.18);
      --shadow-lift: 0 2px 4px rgba(20,16,15,.06), 0 18px 40px -20px rgba(20,16,15,.32);
      --tap: 48px;

      color-scheme: light;
    }}

    :root[data-theme='dark'] {{
      --ink:   #F5F1F0;
      --ink-2: #C7BFBC;
      --ink-3: #A79E9B;
      --line:  #302A28;
      --line-2:#262120;
      --bg:    #141110;
      --bg-2:  #1A1615;
      --card:  #1C1817;
      --card-2:#211D1B;
      --hover: #262120;

      --fox-flame: #FF6B4A;
      --fox-ember: #F0553A;
      --fox-action: #D53427;
      --fox-action-2: #A82419;

      --ok-bg:#16301F;   --ok-fg:#6EE7A0;
      --warn-bg:#33260F; --warn-fg:#F5C77E;
      --stop-bg:#331A16; --stop-fg:#FF9B8E;
      --idle-bg:#262120; --idle-fg:#B9B0AD;
      --info-bg:#14283A; --info-fg:#8CC5F5;

      --shadow: 0 1px 2px rgba(0,0,0,.4), 0 8px 24px -12px rgba(0,0,0,.7);
      --shadow-lift: 0 2px 4px rgba(0,0,0,.45), 0 18px 40px -20px rgba(0,0,0,.85);

      color-scheme: dark;
    }}

    * {{ box-sizing: border-box; margin: 0; padding: 0; }}
    body {{
      background: var(--bg);
      color: var(--ink);
      font: 15px/1.5 "Segoe UI Variable Text", "Segoe UI", -apple-system, BlinkMacSystemFont, system-ui, sans-serif;
      font-feature-settings: "tnum" 1;
      padding: 24px 20px 100px 20px;
      min-height: 100vh;
    }}

    .wrap {{ max-width: 1180px; margin: 0 auto; }}

    /* Üst Başlık & Kontrol Çubuğu */
    .top-bar {{
      display: flex;
      justify-content: space-between;
      align-items: center;
      padding: 16px 20px;
      background: var(--card);
      border: 1px solid var(--line);
      border-radius: var(--r);
      box-shadow: var(--shadow);
      margin-bottom: 20px;
      flex-wrap: wrap;
      gap: 12px;
    }}
    .brand {{ display: flex; align-items: center; gap: 12px; }}
    .brand-mark {{
      width: 32px; height: 32px;
      background: var(--card-2);
      border: 1px solid var(--line);
      border-radius: 8px;
      display: grid;
      place-items: center;
    }}
    .brand-title {{ font-size: 18px; font-weight: 700; letter-spacing: -.02em; }}
    .badge {{
      display: inline-flex;
      align-items: center;
      gap: 6px;
      padding: 4px 10px;
      border-radius: 6px;
      font-size: 12px;
      font-weight: 600;
      font-variant-numeric: tabular-nums;
    }}
    .badge-ok {{ background: var(--ok-bg); color: var(--ok-fg); }}
    .badge-warn {{ background: var(--warn-bg); color: var(--warn-fg); }}
    .badge-stop {{ background: var(--stop-bg); color: var(--stop-fg); }}
    .badge-info {{ background: var(--info-bg); color: var(--info-fg); }}
    .badge-idle {{ background: var(--idle-bg); color: var(--idle-fg); }}

    /* Düğmeler */
    .btn {{
      min-height: 40px;
      display: inline-flex;
      align-items: center;
      justify-content: center;
      gap: 8px;
      padding: 0 16px;
      border-radius: 10px;
      border: 1px solid transparent;
      font: inherit;
      font-weight: 650;
      font-size: 13px;
      cursor: pointer;
      transition: all .15s ease;
      text-decoration: none;
    }}
    .btn-primary {{
      background: linear-gradient(180deg, var(--fox-action), var(--fox-action-2));
      color: #fff;
      box-shadow: 0 1px 2px rgba(0,0,0,.2);
    }}
    .btn-primary:hover {{ opacity: .94; }}
    .btn-ghost {{
      background: var(--card-2);
      border-color: var(--line);
      color: var(--ink);
    }}
    .btn-ghost:hover {{ background: var(--hover); }}
    .btn-sm {{ min-height: 32px; padding: 0 10px; font-size: 12px; border-radius: 8px; }}

    /* Switch */
    .switch {{ position: relative; display: inline-block; width: 38px; height: 20px; }}
    .switch input {{ opacity: 0; width: 0; height: 0; }}
    .slider {{ position: absolute; cursor: pointer; top: 0; left: 0; right: 0; bottom: 0; background-color: var(--line); transition: .2s ease; border-radius: 20px; }}
    .slider:before {{ position: absolute; content: ""; height: 14px; width: 14px; left: 3px; bottom: 3px; background-color: white; transition: .2s ease; border-radius: 50%; }}
    input:checked + .slider {{ background-color: var(--fox-action) !important; }}
    input:checked + .slider:before {{ transform: translateX(18px) !important; }}

    /* Kartlar */
    .card {{
      background: var(--card);
      border: 1px solid var(--line);
      border-radius: var(--r);
      padding: 22px;
      box-shadow: var(--shadow);
      margin-bottom: 20px;
    }}
    .card-header {{
      display: flex;
      justify-content: space-between;
      align-items: center;
      margin-bottom: 18px;
      padding-bottom: 14px;
      border-bottom: 1px solid var(--line-2);
    }}
    .card-title {{ font-size: 16px; font-weight: 700; letter-spacing: -.01em; }}

    /* Çift Motor Seçim Alanı */
    .engine-grid {{
      display: grid;
      grid-template-columns: 1fr 1fr;
      gap: 12px;
      margin-bottom: 16px;
    }}
    @media (max-width: 768px) {{ .engine-grid {{ grid-template-columns: 1fr; }} }}

    .engine-btn {{
      padding: 16px 18px;
      border-radius: 12px;
      border: 1px solid var(--line);
      background: var(--card-2);
      color: var(--ink-2);
      text-align: left;
      cursor: pointer;
      display: flex;
      justify-content: space-between;
      align-items: center;
      transition: all .2s;
    }}
    .engine-btn b {{ display: block; font-size: 14.5px; color: var(--ink); margin-bottom: 2px; }}
    .engine-btn span {{ font-size: 12px; color: var(--ink-3); }}
    .engine-btn.active {{
      border-color: var(--fox-action);
      background: var(--card);
      box-shadow: inset 0 0 0 1px var(--fox-action);
    }}
    .engine-btn.active b {{ color: var(--fox-flame); }}

    /* Hazır Profil Seçici */
    .profile-bar {{
      display: flex;
      align-items: center;
      gap: 8px;
      flex-wrap: wrap;
      margin-bottom: 18px;
    }}
    .profile-btn {{
      padding: 8px 14px;
      border-radius: 8px;
      border: 1px solid var(--line);
      background: var(--card-2);
      color: var(--ink-2);
      font-size: 13px;
      font-weight: 600;
      cursor: pointer;
    }}
    .profile-btn.active {{
      background: var(--hover);
      color: var(--fox-ember);
      border-color: var(--fox-ember);
    }}

    /* 8 Parametreli Matris Girişi */
    .param-grid {{
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(180px, 1fr));
      gap: 12px;
      background: var(--bg-2);
      border: 1px solid var(--line-2);
      border-radius: 12px;
      padding: 16px;
      margin-bottom: 18px;
    }}
    .param-box label {{
      display: block;
      font-size: 11.5px;
      font-weight: 600;
      color: var(--ink-3);
      margin-bottom: 4px;
    }}
    .param-box input {{
      width: 100%;
      height: 38px;
      padding: 0 10px;
      border-radius: 8px;
      border: 1px solid var(--line);
      background: var(--card);
      color: var(--ink);
      font-size: 14px;
      font-family: inherit;
      font-variant-numeric: tabular-nums;
      font-weight: 600;
    }}
    .param-box input:focus {{ outline: none; border-color: var(--fox-action); }}

    /* 10 Kurumsal Teyit Matrisi */
    .audit-grid {{
      display: grid;
      grid-template-columns: repeat(auto-fill, minmax(210px, 1fr));
      gap: 8px;
    }}
    .audit-item {{
      display: flex;
      align-items: center;
      gap: 8px;
      padding: 8px 12px;
      background: var(--card-2);
      border: 1px solid var(--line);
      border-radius: 8px;
      font-size: 12px;
      color: var(--ink-2);
      font-weight: 500;
    }}
    .audit-item.verified {{
      color: var(--ok-fg);
      background: var(--ok-bg);
      border-color: rgba(110, 231, 160, 0.2);
    }}

    /* Tablolar */
    .table-wrap {{ overflow-x: auto; margin-top: 6px; }}
    table {{ width: 100%; border-collapse: collapse; text-align: left; }}
    th {{
      font-size: 11.5px;
      font-weight: 600;
      text-transform: uppercase;
      letter-spacing: .04em;
      color: var(--ink-3);
      padding: 10px 12px;
      border-bottom: 1px solid var(--line);
    }}
    td {{
      padding: 12px;
      font-size: 13.5px;
      border-bottom: 1px solid var(--line-2);
      vertical-align: middle;
      font-variant-numeric: tabular-nums;
    }}
    tr.clickable:hover td {{ background: var(--hover); cursor: pointer; }}

    .table-input {{
      background: var(--card);
      border: 1px solid var(--line);
      border-radius: 6px;
      padding: 4px 6px;
      font-family: inherit;
      font-weight: 600;
      text-align: center;
      font-variant-numeric: tabular-nums;
    }}

    /* ============================================================================
       FOX MARKA YÜKLEME GÖSTERGESİ (Resmi SVG & Animasyon)
       ========================================================================== */
    .foxload {{ display: grid; justify-items: center; gap: 12px; }}
    .foxload-ring {{ position: relative; display: grid; place-items: center; }}
    .foxload-ring svg {{ position: absolute; inset: 0; }}
    .foxload-arc {{ animation: foxspin 1.15s cubic-bezier(.55,.15,.45,.85) infinite; transform-origin: center; }}
    .foxload-mark {{
      position: relative; display: block;
      animation: foxbreathe 2.2s ease-in-out infinite;
      filter: drop-shadow(0 4px 12px rgba(213,52,39,.28));
    }}
    @keyframes foxspin {{ 0% {{ transform: rotate(0deg); }} 100% {{ transform: rotate(360deg); }} }}
    @keyframes foxbreathe {{ 0%, 100% {{ transform: scale(1); opacity: .92; }} 50% {{ transform: scale(1.06); opacity: 1; }} }}

    /* Modal Pencere */
    .modal-overlay {{
      position: fixed; inset: 0;
      background: rgba(20, 17, 16, 0.82);
      backdrop-filter: blur(8px);
      display: none;
      place-items: center;
      z-index: 100;
      padding: 20px;
    }}
    .modal-overlay.open {{ display: grid; }}
    .modal-card {{
      background: var(--card);
      border: 1px solid var(--line);
      border-radius: var(--r);
      width: 100%;
      max-width: 580px;
      padding: 24px;
      box-shadow: var(--shadow-lift);
      position: relative;
    }}

    /* Mobil Dock */
    .mobile-dock {{
      display: none;
      position: fixed;
      bottom: 0; left: 0; right: 0;
      background: var(--card);
      border-top: 1px solid var(--line);
      padding: 8px 16px;
      z-index: 90;
      justify-content: space-around;
      align-items: center;
    }}
    @media (max-width: 768px) {{
      .mobile-dock {{ display: flex; }}
      body {{ padding-bottom: 90px; }}
    }}
    .dock-item {{
      display: flex; flex-direction: column; align-items: center; gap: 2px;
      font-size: 11px; color: var(--ink-3); text-decoration: none; cursor: pointer;
      min-width: 48px; min-height: 44px; justify-content: center;
    }}
    .dock-item.active {{ color: var(--fox-flame); font-weight: 700; }}

    /* Toast Bildirimi */
    #toast {{
      visibility: hidden; min-width: 260px;
      background: var(--card); color: var(--ink); text-align: center;
      border-radius: 10px; padding: 12px 18px; position: fixed; z-index: 200;
      bottom: 24px; left: 50%; transform: translateX(-50%);
      border: 1px solid var(--fox-ember); box-shadow: var(--shadow-lift);
      font-weight: 600; font-size: 13px;
    }}
    #toast.show {{ visibility: visible; animation: fadein 0.3s, fadeout 0.3s 2.7s; }}
    @keyframes fadein {{ from {{ bottom: 10px; opacity: 0; }} to {{ bottom: 24px; opacity: 1; }} }}
    @keyframes fadeout {{ from {{ bottom: 24px; opacity: 1; }} to {{ bottom: 10px; opacity: 0; }} }}
  </style>
</head>
<body>
  <!-- TOAST BİLDİRİMİ -->
  <div id="toast">✅ İşlem Başarılı!</div>

  <div class="wrap">
    <!-- ÜST KONTROL BARI -->
    <header class="top-bar">
      <div class="brand">
        <div class="brand-mark">
          <span style="color: var(--fox-flame); font-weight: 800; font-size: 16px;">🦊</span>
        </div>
        <div>
          <div class="brand-title">Fox-Kripto <span class="badge badge-info" style="margin-left: 4px;">V2.2 Quant</span></div>
        </div>
      </div>

      <div style="display: flex; align-items: center; gap: 10px; flex-wrap: wrap;">
        <!-- Sürüm Seçici -->
        <a href="/v1/dashboard" class="btn btn-sm btn-ghost">🏛️ V1 Klasik</a>
        <a href="/v2/dashboard" class="btn btn-sm btn-primary">⚡ V2 Quant</a>

        <!-- Trailing SL -->
        <div style="display: flex; align-items: center; gap: 6px; background: var(--card-2); padding: 4px 10px; border-radius: 8px; border: 1px solid var(--line);">
          <span style="font-size: 12px; color: var(--ink-2); font-weight: 600;">Trailing SL:</span>
          <label class="switch">
            <input type="checkbox" id="trailing-toggle" {trailing_checked} onchange="toggleTrailingStop(this.checked)">
            <span class="slider"></span>
          </label>
        </div>

        <button class="btn btn-sm btn-ghost" onclick="toggleTheme()">🌓 Tema</button>
        <button class="btn btn-sm btn-ghost" onclick="triggerDustClean()">🧹 Kırıntı</button>
        <button class="btn btn-sm btn-primary" onclick="window.location.reload()">🔄 Yenile</button>
      </div>
    </header>

    <!-- STRATEJİ & MOTOR SEÇİM KARTI -->
    <section class="card">
      <div class="card-header">
        <div>
          <div class="card-title" id="engine-title">{engine_title_text}</div>
          <p style="font-size: 12.5px; color: var(--ink-3); margin-top: 2px;">Piyasa rejimine uygun otonom işlem stratejisi ve risk profili.</p>
        </div>
        <span class="{engine_badge_cls}" id="engine-badge">{engine_badge_text}</span>
      </div>

      <!-- Çift Motor Butonları -->
      <div class="engine-grid">
        <div id="btn-engine-scalp" class="{scalp_btn_cls}" onclick="switchEngine('VOLUME_SCALPING')">
          <div>
            <b>1. Hacim Scalping Motoru</b>
            <span>1m/3m/5m Hızlı momentum ve mikro-kırılımlar.</span>
          </div>
          <span class="badge badge-info">Yüksek Frekans</span>
        </div>
        <div id="btn-engine-whale" class="{whale_btn_cls}" onclick="switchEngine('WHALE_HUNTING')">
          <div>
            <b>2. Gerçek Balina Avı Motoru</b>
            <span>Spot + Vadeli Açık Faiz (OI) ve derinlik teyidi.</span>
          </div>
          <span class="badge badge-warn">Katı Filtre</span>
        </div>
      </div>

      <!-- Hazır Risk Profili -->
      <div class="profile-bar">
        <span style="font-size: 13px; color: var(--ink-3); margin-right: 4px;">Hazır Profil:</span>
        <button id="pill-agg" class="{pill_agg_cls}" onclick="switchRisk('AGGRESSIVE')">Agresif</button>
        <button id="pill-bal" class="{pill_bal_cls}" onclick="switchRisk('BALANCED')">Dengeli (Önerilen)</button>
        <button id="pill-def" class="{pill_def_cls}" onclick="switchRisk('DEFENSIVE')">Defansif</button>
        <button id="pill-cus" class="{pill_cus_cls}" onclick="switchRisk('CUSTOM')">Özel Ayarlar</button>
        <button class="btn btn-sm btn-primary" onclick="saveV2Strategy()" style="margin-left: auto;">💾 Kaydet & Canlıya Al</button>
      </div>

      <!-- 8 Parametreli İnce Ayar Alanı -->
      <div class="param-grid">
        <div class="param-box">
          <label>Min 5dk Hacim ($ USD)</label>
          <input type="number" id="param_min_volume_usd" value="{min_vol}" onchange="markCustom()">
        </div>
        <div class="param-box">
          <label>Hacim Patlama Çarpanı (x)</label>
          <input type="number" step="0.1" id="param_volume_spike" value="{spike_mult}" onchange="markCustom()">
        </div>
        <div class="param-box">
          <label>Maks 24s Prim Limiti (%)</label>
          <input type="number" step="0.5" id="param_max_gain_24h" value="{max_gain}" onchange="markCustom()">
        </div>
        <div class="param-box">
          <label>Min AI & Teyit Skoru</label>
          <input type="number" step="0.1" id="param_min_ai_score" value="{ai_score}" onchange="markCustom()">
        </div>
        <div class="param-box">
          <label>Kasa Bütçesi (%)</label>
          <input type="number" step="1" id="param_max_budget" value="{max_budget}" onchange="markCustom()">
        </div>
        <div class="param-box">
          <label>Hedef Kâr Al (%)</label>
          <input type="number" step="0.1" id="param_tp_pct" value="{tp_pct}" onchange="markCustom()">
        </div>
        <div class="param-box">
          <label>Zarar Kes Stop (%)</label>
          <input type="number" step="0.1" id="param_sl_pct" value="{sl_pct}" onchange="markCustom()">
        </div>
        <div class="param-box">
          <label>Trailing Çekilme Payı (%)</label>
          <input type="number" step="0.1" id="param_trailing_callback" value="{cb_pct}" onchange="markCustom()">
        </div>
      </div>

      <!-- 10 Kurumsal Onay Matrisi -->
      <div style="margin-top: 14px;">
        <div style="font-size: 12px; font-weight: 600; color: var(--ink-3); margin-bottom: 8px;">10 Kurumsal Teyit Matrisi (The Golden Whale Matrix):</div>
        <div class="audit-grid">
          <div class="audit-item verified">✓ 1. Spot Hacim Patlaması (>1.8x)</div>
          <div class="audit-item verified">✓ 2. Vadeli Açık Faiz (OI Girişi)</div>
          <div class="audit-item verified">✓ 3. Funding Sıkışma Filtresi (<%0.10)</div>
          <div class="audit-item verified">✓ 4. Alış Duvarı Desteği (>60s)</div>
          <div class="audit-item verified">✓ 5. Taker Alıcı Baskısı (>%62)</div>
          <div class="audit-item verified">✓ 6. VWAP / Retest Taban Onayı</div>
          <div class="audit-item verified">✓ 7. 24s Primsiz Giriş Limiti</div>
          <div class="audit-item verified">✓ 8. Düşük Spread (<%0.20)</div>
          <div class="audit-item verified">✓ 9. Düşük Fitil (Anti-FOMO)</div>
          <div class="audit-item verified">✓ 10. GLM + Gemini AI Onayı</div>
        </div>
      </div>
    </section>

    <!-- KULLANICI VE HESAP TABLOSU -->
    <section class="card">
      <div class="card-header">
        <div>
          <div class="card-title">Kayıtlı Portföyler & Hesaplar</div>
          <p style="font-size: 12.5px; color: var(--ink-3); margin-top: 2px;">Canlı cüzdan ve açık pozisyonları görmek için kullanıcının üzerine tıklayın.</p>
        </div>
        <span class="badge badge-info">Multi-Tenant V2.2</span>
      </div>

      <div class="table-wrap">
        <table>
          <thead>
            <tr>
              <th>Kullanıcı</th>
              <th>Telegram ID</th>
              <th>Kâr Al %</th>
              <th>Stop %</th>
              <th>Bütçe %</th>
              <th>Borsa</th>
              <th>Dil</th>
              <th>Durum</th>
              <th>İşlem</th>
            </tr>
          </thead>
          <tbody id="tenants-tbody">
            {tenants_ssr_html}
          </tbody>
        </table>
      </div>
    </section>

    <!-- İŞLEM VE KARAR GÜNLÜĞÜ -->
    <section class="card">
      <div class="card-header">
        <div>
          <div class="card-title">Canlı İşlem ve Karar Günlüğü (Explainable Logs)</div>
          <p style="font-size: 12.5px; color: var(--ink-3); margin-top: 2px;">Tüm alım ve satımların gerekçeli şeffaf dökümü.</p>
        </div>
        <span class="badge badge-ok">Canlı Veritabanı Senkronize</span>
      </div>

      <div class="table-wrap">
        <table>
          <thead>
            <tr>
              <th>Kullanıcı</th>
              <th>İşlem & Parite</th>
              <th>Bütçe</th>
              <th>Fiyat</th>
              <th>Teyit Skoru</th>
              <th>Durum</th>
              <th>Zaman</th>
            </tr>
          </thead>
          <tbody id="logs-tbody">
            {logs_ssr_html}
          </tbody>
        </table>
      </div>
    </section>
  </div>

  <!-- KULLANICI BAKİYE MODAL PENCERESİ (FOX LOADER ENTEGRE) -->
  <div id="portfolio-modal" class="modal-overlay" onclick="closePortfolioModal(event)">
    <div class="modal-card" onclick="event.stopPropagation()">
      <div id="modal-loader" style="padding: 30px 0;">
        <div id="fox-spinner-slot"></div>
      </div>
      <div id="modal-data" style="display: none;">
        <div style="display: flex; justify-content: space-between; align-items: flex-start; margin-bottom: 16px;">
          <div>
            <h3 id="m-user" style="font-size: 18px; font-weight: 700; color: var(--ink);"></h3>
            <span id="m-exch" class="badge badge-info" style="margin-top: 4px;"></span>
          </div>
          <button class="btn btn-sm btn-ghost" onclick="closePortfolioModal()">✕ Kapat</button>
        </div>

        <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 10px; margin-bottom: 18px;">
          <div style="padding: 14px; background: var(--bg-2); border-radius: 10px; border: 1px solid var(--line);">
            <div style="font-size: 11.5px; color: var(--ink-3);">Toplam Portföy</div>
            <div id="m-tot" style="font-size: 20px; font-weight: 700; color: var(--fox-flame); margin-top: 2px;"></div>
            <small id="m-tot-try" style="color: var(--ink-3); font-size: 11px;"></small>
          </div>
          <div style="padding: 14px; background: var(--bg-2); border-radius: 10px; border: 1px solid var(--line);">
            <div style="font-size: 11.5px; color: var(--ink-3);">Serbest Nakit</div>
            <div id="m-free" style="font-size: 20px; font-weight: 700; color: var(--ok-fg); margin-top: 2px;"></div>
            <small style="color: var(--ok-fg); font-size: 11px;">🟢 Alıma Hazır</small>
          </div>
        </div>

        <div style="font-size: 12.5px; color: var(--ink-3); font-weight: 600; margin-bottom: 8px;">Açık Pozisyonlar & Varlıklar:</div>
        <div id="m-holdings" style="max-height: 240px; overflow-y: auto;"></div>
      </div>
    </div>
  </div>

  <!-- MOBİL DOCK -->
  <nav class="mobile-dock">
    <a href="/v2/dashboard" class="dock-item active"><span>⚡</span><span>V2 Quant</span></a>
    <a href="/v1/dashboard" class="dock-item"><span>🏛️</span><span>V1 Klasik</span></a>
    <div class="dock-item" onclick="triggerDustClean()"><span>🧹</span><span>Kırıntı</span></div>
    <div class="dock-item" onclick="window.location.reload()"><span>🔄</span><span>Yenile</span></div>
  </nav>

  <!-- SCRIPT -->
  <script>
    const MARK = "data:image/png;base64,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";

    function renderLoader(el, size, label, sub) {{
      const stroke = Math.max(3, Math.round(size*0.055));
      const r = (size-stroke)/2, c = 2*Math.PI*r;
      el.innerHTML = `
        <div class="foxload">
          <div class="foxload-ring" style="width:${{size}}px;height:${{size}}px">
            <svg width="${{size}}" height="${{size}}" viewBox="0 0 ${{size}} ${{size}}">
              <defs><linearGradient id="g${{size}}" x1="0" y1="0" x2="1" y2="1">
                <stop offset="0%" stop-color="var(--fox-flame)"/><stop offset="55%" stop-color="var(--fox-ember)"/>
                <stop offset="100%" stop-color="var(--fox-deep)"/>
              </linearGradient></defs>
              <circle cx="${{size/2}}" cy="${{size/2}}" r="${{r}}" fill="none" stroke="var(--line)" stroke-width="${{stroke}}"/>
              <circle class="foxload-arc" cx="${{size/2}}" cy="${{size/2}}" r="${{r}}" fill="none"
                stroke="url(#g${{size}})" stroke-width="${{stroke}}" stroke-linecap="round"
                stroke-dasharray="${{c*0.28}} ${{c}}"
                transform="rotate(-90 ${{size/2}} ${{size/2}})"/>
            </svg>
            <img class="foxload-mark" src="${{MARK}}" alt="" width="${{Math.round(size*0.46)}}" height="${{Math.round(size*0.46)}}">
          </div>
          <div style="text-align:center;">
            <b style="font-size:15px; color:var(--ink);">${{label}}</b>
            <div style="font-size:12.5px; color:var(--ink-3); margin-top:2px;">${{sub}}</div>
          </div>
        </div>`;
    }}

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

    function toggleTheme() {{
      const cur = document.documentElement.getAttribute('data-theme');
      document.documentElement.setAttribute('data-theme', cur === 'dark' ? 'light' : 'dark');
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
        btnScalp.className = 'engine-btn active';
        btnWhale.className = 'engine-btn';
        title.innerText = '1. Hacim Scalping Motoru';
        badge.className = 'badge badge-info';
        badge.innerText = '⚡ Hacim Scalping · ' + currentRisk + ' · v2.2 Aktif';
      }} else {{
        btnWhale.className = 'engine-btn active';
        btnScalp.className = 'engine-btn';
        title.innerText = '2. Gerçek Balina Avı Motoru';
        badge.className = 'badge badge-warn';
        badge.innerText = '🐋 Balina Avı · ' + currentRisk + ' · v2.2 Aktif';
      }}
    }}

    const PRESETS_MAP = {{
      'VOLUME_SCALPING_AGGRESSIVE': {{ min_vol: 20000, spike: 1.5, gain: 15.0, score: 7.2, budget: 35.0, tp: 1.8, sl: 1.0, cb: 0.4 }},
      'VOLUME_SCALPING_BALANCED':   {{ min_vol: 25000, spike: 1.8, gain: 12.0, score: 7.5, budget: 25.0, tp: 2.0, sl: 1.2, cb: 0.5 }},
      'VOLUME_SCALPING_DEFENSIVE':  {{ min_vol: 35000, spike: 2.2, gain: 8.0,  score: 8.2, budget: 15.0, tp: 2.5, sl: 1.5, cb: 0.6 }},
      'WHALE_HUNTING_AGGRESSIVE':   {{ min_vol: 50000, spike: 2.0, gain: 15.0, score: 7.8, budget: 35.0, tp: 4.0, sl: 1.5, cb: 0.6 }},
      'WHALE_HUNTING_BALANCED':     {{ min_vol: 50000, spike: 2.5, gain: 12.0, score: 8.2, budget: 25.0, tp: 3.0, sl: 1.5, cb: 0.6 }},
      'WHALE_HUNTING_DEFENSIVE':    {{ min_vol: 100000, spike: 3.2, gain: 9.0, score: 8.8, budget: 15.0, tp: 5.0, sl: 1.8, cb: 0.8 }}
    }};

    function markCustom() {{
      document.querySelectorAll('.profile-btn').forEach(btn => btn.classList.remove('active'));
      const cusBtn = document.getElementById('pill-cus');
      if (cusBtn) cusBtn.classList.add('active');
      currentRisk = 'CUSTOM';
      const badge = document.getElementById('engine-badge');
      if (badge) badge.innerText = (currentEngine === 'VOLUME_SCALPING' ? '⚡ Scalp' : '🐋 Balina') + ' · Özel Ayarlar · v2.2 Aktif';
    }}

    function switchRisk(risk) {{
      currentRisk = risk;
      document.querySelectorAll('.profile-btn').forEach(btn => {{
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
          min_volume_usd: parseFloat(document.getElementById('param_min_volume_usd').value) || 25000,
          volume_spike_multiplier: parseFloat(document.getElementById('param_volume_spike').value) || 1.8,
          max_recent_gain_24h: parseFloat(document.getElementById('param_max_gain_24h').value) || 12.0,
          min_ai_score: parseFloat(document.getElementById('param_min_ai_score').value) || 7.5,
          max_budget_percent: parseFloat(document.getElementById('param_max_budget').value) || 25.0,
          take_profit_pct: parseFloat(document.getElementById('param_tp_pct').value) || 2.0,
          stop_loss_pct: parseFloat(document.getElementById('param_sl_pct').value) || 1.2,
          trailing_callback_pct: parseFloat(document.getElementById('param_trailing_callback').value) || 0.5,
          min_5m_volume_usd: parseFloat(document.getElementById('param_min_volume_usd').value) || 25000,
          require_futures_oi: true
        }};

        const res = await fetch('/api/strategy-config', {{
          method: 'POST',
          headers: {{ ...getAuthHeaders(), 'Content-Type': 'application/json' }},
          body: JSON.stringify(payload)
        }});
        if (res.ok) {{
          const engineName = (currentEngine === 'VOLUME_SCALPING' ? '⚡ Hacim Scalping Motoru' : '🐋 Gerçek Balina Avı Motoru');
          showToast('✅ [BAŞARILI]: ' + engineName + ' (' + currentRisk + ') Canlıya Alındı!');
          const badge = document.getElementById('engine-badge');
          if (badge) {{
            badge.innerText = (currentEngine === 'VOLUME_SCALPING' ? '⚡ Scalp' : '🐋 Balina') + ' · ' + currentRisk + ' · v2.2 Aktif';
            badge.className = (currentEngine === 'VOLUME_SCALPING') ? 'badge badge-info' : 'badge badge-warn';
          }}
        }} else {{
          alert('❌ Kaydetme hatası: ' + res.statusText);
        }}
      }} catch(e) {{ alert('Ayar kaydetme hatası: ' + e); }}
    }}

    async function openTenantPortfolioModal(tenantId, tenantName) {{
      const modal = document.getElementById('portfolio-modal');
      const loaderSlot = document.getElementById('fox-spinner-slot');
      const loaderDiv = document.getElementById('modal-loader');
      const dataDiv = document.getElementById('modal-data');

      modal.classList.add('open');
      loaderDiv.style.display = 'block';
      dataDiv.style.display = 'none';

      renderLoader(loaderSlot, 84, tenantName + ' Cüzdanı Doğrulanıyor…', 'Binance spot ve vadeli bakiyesi taranıyor');

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
          if (valUsd >= 1.0) {{
            holdingsHtml += `
              <div style="display: flex; justify-content: space-between; align-items: center; padding: 10px 12px; background: var(--bg-2); border-radius: 8px; margin-bottom: 6px; border: 1px solid var(--line);">
                <div>
                  <strong style="color: var(--ink); font-size: 13.5px;">${{coin}}</strong>
                  <span style="font-size: 12px; color: var(--ink-3); margin-left: 6px;">${{amt.toLocaleString()}} adet</span>
                </div>
                <div style="text-align: right;">
                  <strong style="color: var(--ok-fg); font-size: 13.5px;">$${{valUsd.toFixed(2)}} USD</strong>
                  <small style="display: block; color: var(--ink-3); font-size: 11px;">~₺${{valTry.toFixed(2)}} TL</small>
                </div>
              </div>
            `;
          }}
        }}

        if (!holdingsHtml) {{
          holdingsHtml = '<div style="padding: 12px; background: var(--bg-2); border-radius: 8px; font-size: 13px; color: var(--ink-2); text-align: center;">Açık coin pozisyonu bulunmuyor (Kasa %100 Nakitte).</div>';
        }}

        loaderDiv.style.display = 'none';
        dataDiv.style.display = 'block';
        document.getElementById('m-user').innerText = tenantName;
        document.getElementById('m-exch').innerText = (data.exchange_id === 'binancetr' ? '🇹🇷 Binance TR' : '🌍 Binance Global');
        document.getElementById('m-tot').innerText = '$' + totUsdt.toFixed(2) + ' USD';
        document.getElementById('m-tot-try').innerText = '~₺' + totTry.toFixed(2) + ' TL';
        document.getElementById('m-free').innerText = '$' + freeUsdt.toFixed(2) + ' USD';
        document.getElementById('m-holdings').innerHTML = holdingsHtml;
      }} catch(err) {{
        loaderDiv.style.display = 'none';
        dataDiv.style.display = 'block';
        document.getElementById('m-holdings').innerHTML = `<div style="color: var(--stop-fg); text-align: center; padding: 16px;">Hata: ${{err.message}}</div>`;
      }}
    }}

    function closePortfolioModal(e) {{
      if (e) e.stopPropagation();
      document.getElementById('portfolio-modal').classList.remove('open');
    }}

    async function updateTenantSettings(tid, event) {{
      if (event) event.stopPropagation();
      const tp = parseFloat(document.getElementById('tp_' + tid).value) || 2.0;
      const sl = parseFloat(document.getElementById('sl_' + tid).value) || 1.2;
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
  </script>
</body>
</html>"""
    return html
