"""
Fox-Borsa: Sade, Anlaşılır ve Şık Wall Street Dashboard HTML Arayüzü (/borsa/dashboard)
Telif Hakkı (c) 2026 Fox-Kripto / Fox-Borsa Quant Ekibi.

ui-ux-designer prensiplerine uygun olarak tasarlanmıştır:
- F-Pattern hiyerarşisi
- Satoshi + JetBrains Mono font eşleşmesi
- Wall Street Koyu FinTech Teması (Koyu Arka Plan, Zümrüt Yeşili ve Altın Sarısı Aksanlar)
- 4 Temel Panel:
  1. Canlı Portföy Kartları ($100K Sanal Bakiye, Alım Gücü, Nakit)
  2. 👥 Alpaca Borsa Aboneleri & Kullanıcı Yönetimi (Multi-Tenant Panel)
  3. 💼 Açık Hisse Senedi Pozisyonları & Bracket Emir Koruması
  4. 🔍 ABD Hisse Senedi Tarayıcısı & 2. Dalga Retest Teyit Durumu
"""

import json
from typing import Dict, Any, List

def generate_stock_dashboard_html(
    account_info: Dict[str, Any],
    market_clock: Dict[str, Any],
    positions: List[Dict[str, Any]],
    opportunities: List[Dict[str, Any]],
    tenants: List[Dict[str, Any]],
    strategy_config: Dict[str, Any],
    global_sentiment: Optional[Dict[str, Any]] = None
) -> str:
    cash_val = float(account_info.get("cash", 100000.0))
    portfolio_val = float(account_info.get("portfolio_value", 100000.0))
    buying_power = float(account_info.get("buying_power", 400000.0))
    is_paper = bool(account_info.get("is_paper", True))
    is_market_open = bool(market_clock.get("is_open", False))

    market_badge = '<span class="badge badge-live">🟢 SEANS AÇIK (NYSE/NASDAQ)</span>' if is_market_open else '<span class="badge badge-closed">🔴 PİYASA KAPALI (16:30 TSI Bekleniyor)</span>'
    mode_badge = '<span class="badge badge-paper">🧪 ALPACA PAPER SANDBOX ($100K)</span>' if is_paper else '<span class="badge badge-live">🚀 LIVE TRADING</span>'

    # Küresel Makro Pusula Kartı
    g_sent = global_sentiment or {}
    g_score = g_sent.get("global_macro_score", 5.5)
    g_badge = g_sent.get("badge", "🟡 KÜRESEL NÖTR")
    g_advice = g_sent.get("advice", "Küresel piyasalar dengeli.")
    g_det = g_sent.get("details", {})
    asia_st = g_det.get("asia", {}).get("status", "NÖTR 🟡")
    eur_st = g_det.get("europe", {}).get("status", "NÖTR 🟡")
    us_st = g_det.get("us_futures", {}).get("status", "NÖTR 🟡")

    # 1. Borsa Aboneleri Tablosu (Multi-Tenant Panel)
    tenants_html = ""
    for idx, t in enumerate(tenants):
        tid = t.get("id", "")
        tname = t.get("tenant_name", "Kullanıcı")
        chat_id = t.get("telegram_chat_id", "-")
        tp = float(t.get("take_profit_percent") or 3.0)
        sl = float(t.get("stop_loss_percent") or 1.5)
        mb = float(t.get("max_budget_percent") or 25.0)
        is_active = bool(t.get("is_active", True))
        is_p = bool(t.get("is_paper", True))
        
        status_btn = f'<button class="btn btn-sm" style="padding: 3px 8px; font-size: 11px; font-weight: bold; cursor: pointer; background: {"rgba(16,185,129,0.2)" if is_active else "rgba(239,68,68,0.2)"}; color: {"#10b981" if is_active else "#ef4444"}; border: 1px solid {"#10b981" if is_active else "#ef4444"}; border-radius: 6px;" onclick="toggleStockTenantActive(\'{tid}\', {str(not is_active).lower()})">{"🟢 Aktif" if is_active else "🔴 Pasif"}</button>'
        acc_type_badge = '<span class="badge badge-paper">🧪 Paper ($100K)</span>' if is_p else '<span class="badge badge-live">🚀 Live Real</span>'

        tenants_html += f"""
        <tr>
            <td>
                <div style="display: flex; align-items: center; gap: 8px;">
                    <strong style="color: #38bdf8; font-size: 13.5px;">{tname}</strong>
                    <span class="badge badge-idle" style="font-size: 10px;">ID: {tid}</span>
                </div>
            </td>
            <td><code class="mono" style="color: #cbd5e1; font-weight: 600;">{chat_id}</code></td>
            <td><input type="number" step="0.1" class="table-input" id="tp_{tid}" value="{tp}" style="width: 65px; color: #10b981;"></td>
            <td><input type="number" step="0.1" class="table-input" id="sl_{tid}" value="{sl}" style="width: 65px; color: #ef4444;"></td>
            <td><input type="number" step="1.0" class="table-input" id="mb_{tid}" value="{mb}" style="width: 65px; color: #f59e0b;"></td>
            <td>{acc_type_badge}</td>
            <td>{status_btn}</td>
            <td>
                <button class="btn btn-sm btn-primary" onclick="updateStockTenantSettings('{tid}')">💾 Kaydet</button>
            </td>
        </tr>
        """
    if not tenants_html:
        tenants_html = '<tr><td colspan="8" style="text-align: center; color: #64748b; padding: 24px;">Kayıtlı borsa abonesi bulunamadı.</td></tr>'

    # 2. Açık Pozisyonlar Tablosu
    pos_html = ""
    for p in positions:
        pl = float(p.get("unrealized_pl", 0.0))
        plpc = float(p.get("unrealized_plpc", 0.0))
        pl_color = "#10b981" if pl >= 0 else "#ef4444"
        pos_html += f"""
        <tr>
            <td><strong style="color: #38bdf8; font-size: 14px;">{p.get('symbol')}</strong></td>
            <td><span class="mono">{p.get('qty')} adet</span></td>
            <td><span class="mono">${p.get('avg_entry_price', 0):.2f}</span></td>
            <td><span class="mono">${p.get('current_price', 0):.2f}</span></td>
            <td><span class="mono">${p.get('market_value', 0):,.2f}</span></td>
            <td><strong style="color: {pl_color};" class="mono">{'+' if pl>=0 else ''}${pl:.2f} ({'+' if plpc>=0 else ''}{plpc:.2f}%)</strong></td>
            <td>
                <button class="btn btn-sm btn-danger" onclick="closeStockPosition('{p.get('symbol')}')">🛑 Kapat</button>
            </td>
        </tr>
        """
    if not pos_html:
        pos_html = '<tr><td colspan="7" style="text-align: center; color: #64748b; padding: 24px;">Şu an açık hisse senedi pozisyonu bulunmuyor (Kasa %100 Nakitte).</td></tr>'

    # 3. Fırsat ve Retest Teyit Tablosu
    opp_html = ""
    for opp in opportunities:
        sym = opp.get("symbol")
        p_val = opp.get("price", 0.0)
        chg = opp.get("change_pct", 0.0)
        st = opp.get("state", "IDLE")
        chg_color = "#10b981" if chg >= 0 else "#ef4444"
        
        state_badge = '<span class="badge badge-retest">🛡️ 2. DALGA RETEST ONAYLI</span>' if st == "STOCK_RETEST_CONFIRMED" else (
            '<span class="badge badge-warn">⏳ GERİ ÇEKİLME BEKLENİYOR</span>' if st == "STOCK_WAITING_PULLBACK" else '<span class="badge badge-idle">👁️ İZLENİYOR</span>'
        )

        opp_html += f"""
        <tr>
            <td><strong style="color: #f59e0b; font-size: 14px;">{sym}</strong></td>
            <td><span class="mono" style="font-weight: 700;">${p_val:.2f}</span></td>
            <td><strong style="color: {chg_color};" class="mono">{'+' if chg>=0 else ''}{chg:.2f}%</strong></td>
            <td>{state_badge}</td>
            <td style="font-size: 12px; color: #94a3b8;">{opp.get('reason')}</td>
            <td><span class="mono" style="color: #10b981;">TP: ${opp.get('take_profit_target', 0):.2f}</span><br><span class="mono" style="color: #ef4444; font-size: 11px;">SL: ${opp.get('stop_loss_target', 0):.2f}</span></td>
            <td>
                <button class="btn btn-sm btn-primary" onclick="buyStockDirect('{sym}', 500)">🛒 $500 Al</button>
            </td>
        </tr>
        """

    return f"""<!DOCTYPE html>
<html lang="tr">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Fox-Borsa | ABD Hisse Senedi & Wall Street Quant Platformu</title>
  <link rel="preconnect" href="https://fonts.googleapis.com">
  <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
  <link href="https://fonts.googleapis.com/css2?family=JetBrains+Mono:wght@400;600;700;800&family=Plus+Jakarta+Sans:wght@400;500;600;700;800&display=swap" rel="stylesheet">
  <style>
    :root {{
      --bg: #0b0f17;
      --card: #111827;
      --card-2: #1e293b;
      --line: #334155;
      --ink: #f8fafc;
      --ink-2: #cbd5e1;
      --ink-3: #64748b;
      --emerald: #10b981;
      --amber: #f59e0b;
      --rose: #ef4444;
      --blue: #38bdf8;
      --radius: 12px;
    }}
    * {{ box-sizing: border-box; margin: 0; padding: 0; }}
    body {{
      background: var(--bg);
      color: var(--ink);
      font-family: 'Plus Jakarta Sans', -apple-system, BlinkMacSystemFont, sans-serif;
      font-size: 14px;
      line-height: 1.5;
      padding-bottom: 60px;
    }}
    .mono {{ font-family: 'JetBrains Mono', monospace; }}
    .wrap {{ max-width: 1280px; margin: 0 auto; padding: 24px; display: grid; gap: 24px; }}
    
    /* Üst Bar */
    .header {{
      display: flex; justify-content: space-between; align-items: center;
      background: var(--card); border: 1px solid var(--line); border-radius: var(--radius);
      padding: 18px 24px; flex-wrap: wrap; gap: 16px;
    }}
    .brand {{ display: flex; align-items: center; gap: 12px; }}
    .brand-logo {{ font-size: 28px; }}
    .brand-name {{ font-size: 18px; font-weight: 800; color: var(--ink); }}
    .brand-sub {{ font-size: 12px; color: var(--amber); font-weight: 600; }}
    
    /* Rozetler */
    .badge {{ display: inline-flex; align-items: center; padding: 4px 10px; border-radius: 6px; font-size: 11.5px; font-weight: 700; }}
    .badge-live {{ background: rgba(16, 185, 129, 0.15); color: var(--emerald); border: 1px solid var(--emerald); }}
    .badge-closed {{ background: rgba(239, 68, 68, 0.15); color: var(--rose); border: 1px solid var(--rose); }}
    .badge-paper {{ background: rgba(245, 158, 11, 0.15); color: var(--amber); border: 1px solid var(--amber); }}
    .badge-retest {{ background: rgba(16, 185, 129, 0.2); color: #34d399; font-weight: 800; }}
    .badge-warn {{ background: rgba(245, 158, 11, 0.2); color: #fbbf24; }}
    .badge-idle {{ background: rgba(100, 116, 139, 0.2); color: #94a3b8; }}

    /* Butonlar */
    .btn {{
      display: inline-flex; align-items: center; justify-content: center; gap: 6px;
      padding: 8px 16px; border-radius: 8px; font-size: 13px; font-weight: 700;
      cursor: pointer; border: none; transition: all 0.2s;
    }}
    .btn-primary {{ background: var(--amber); color: #000; }}
    .btn-primary:hover {{ background: #d97706; }}
    .btn-danger {{ background: rgba(239, 68, 68, 0.2); color: var(--rose); border: 1px solid var(--rose); }}
    .btn-danger:hover {{ background: var(--rose); color: #fff; }}
    .btn-ghost {{ background: var(--card-2); color: var(--ink); border: 1px solid var(--line); }}
    .btn-ghost:hover {{ background: #334155; }}
    .btn-sm {{ padding: 4px 10px; font-size: 11.5px; }}

    /* Portföy Kartları */
    .metrics-grid {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(240px, 1fr)); gap: 16px; }}
    .metric-card {{
      background: var(--card); border: 1px solid var(--line); border-radius: var(--radius);
      padding: 20px; position: relative; overflow: hidden;
    }}
    .metric-title {{ font-size: 12px; color: var(--ink-3); text-transform: uppercase; font-weight: 700; letter-spacing: 0.05em; }}
    .metric-val {{ font-size: 26px; font-weight: 800; color: var(--ink); margin-top: 6px; }}
    .metric-sub {{ font-size: 12px; color: var(--ink-2); margin-top: 4px; }}

    /* Tablo Kartı */
    .table-card {{ background: var(--card); border: 1px solid var(--line); border-radius: var(--radius); padding: 20px; }}
    .card-header {{ display: flex; justify-content: space-between; align-items: center; margin-bottom: 16px; flex-wrap: wrap; gap: 10px; }}
    .card-title {{ font-size: 16px; font-weight: 700; color: var(--ink); display: flex; align-items: center; gap: 8px; }}
    table {{ width: 100%; border-collapse: collapse; text-align: left; }}
    th {{ padding: 12px; font-size: 11px; text-transform: uppercase; color: var(--ink-3); border-bottom: 1px solid var(--line); font-weight: 700; }}
    td {{ padding: 14px 12px; border-bottom: 1px solid rgba(51, 65, 85, 0.5); font-size: 13.5px; vertical-align: middle; }}
    tr:hover td {{ background: rgba(30, 41, 59, 0.4); }}

    .table-input {{
      background: var(--card-2);
      border: 1px solid var(--line);
      border-radius: 6px;
      padding: 4px 8px;
      font-family: inherit;
      font-weight: 600;
      text-align: center;
      color: var(--ink);
    }}
    .table-input:focus {{ outline: none; border-color: var(--amber); }}

    /* Modal */
    .modal-overlay {{
      display: none; position: fixed; inset: 0; background: rgba(0,0,0,0.75);
      backdrop-filter: blur(6px); z-index: 999; place-items: center; padding: 20px;
    }}
    .modal-overlay.open {{ display: grid; }}
    .modal-card {{
      background: var(--card); border: 1px solid var(--line); border-radius: var(--radius);
      padding: 24px; width: 100%; max-width: 500px; display: grid; gap: 16px;
    }}
  </style>
</head>
<body>
  <div class="wrap">
    <!-- ÜST BİLGİ VE GEÇİŞ BARI -->
    <header class="header">
      <div class="brand">
        <div class="brand-logo">🏛️</div>
        <div>
          <div class="brand-name">Fox-Borsa <span class="brand-sub">Wall Street Quant</span></div>
          <div style="font-size: 11.5px; color: var(--ink-3);">Alpaca Securities LLC · NASDAQ & NYSE Algotrading</div>
        </div>
      </div>
      <div style="display: flex; align-items: center; gap: 10px; flex-wrap: wrap;">
        {mode_badge}
        {market_badge}
        <a href="/v2/dashboard" class="btn btn-ghost">🪙 Kripto Paneline Geç</a>
        <button class="btn btn-primary" onclick="window.location.reload()">🔄 Yenile</button>
      </div>
    </header>

    <!-- 🌍 KÜRESEL PİYASA PUSULASI & ÖNCÜ SEANS RADARI -->
    <section class="table-card" style="border-left: 4px solid var(--amber); background: linear-gradient(180deg, #111827 0%, #0f172a 100%);">
      <div class="card-header">
        <div>
          <div class="card-title">🌍 Küresel Piyasa Pusulası & Öncü Seans Radarı (Tokyo ➔ Londra ➔ Wall Street)</div>
          <span style="font-size: 12px; color: var(--ink-3);">{g_advice}</span>
        </div>
        <span class="badge badge-live" style="font-size: 12px; font-weight: 800;">{g_badge} · Makro Skor: {g_score}/10</span>
      </div>
      <div style="display: grid; grid-template-columns: repeat(auto-fit, minmax(280px, 1fr)); gap: 12px; margin-top: 6px;">
        <div style="padding: 12px 16px; background: var(--card-2); border-radius: 8px; border: 1px solid var(--line); display: flex; justify-content: space-between; align-items: center;">
          <div>
            <div style="font-size: 11px; color: var(--ink-3); font-weight: 700;">1. ASYA SEANSI (Tokyo & Çip)</div>
            <div style="font-size: 13.5px; font-weight: 800; color: #38bdf8; margin-top: 2px;">🇯🇵 Nikkei & TSMC</div>
          </div>
          <div style="text-align: right;">
            <div style="font-size: 12px; font-weight: 800; color: var(--ink);">{asia_st}</div>
            <div style="font-size: 11px; color: var(--ink-3);">03:00 - 09:00 TSI</div>
          </div>
        </div>
        <div style="padding: 12px 16px; background: var(--card-2); border-radius: 8px; border: 1px solid var(--line); display: flex; justify-content: space-between; align-items: center;">
          <div>
            <div style="font-size: 11px; color: var(--ink-3); font-weight: 700;">2. AVRUPA SEANSI (Londra & DAX)</div>
            <div style="font-size: 13.5px; font-weight: 800; color: #a78bfa; margin-top: 2px;">🇬🇧 DAX 40 & FTSE</div>
          </div>
          <div style="text-align: right;">
            <div style="font-size: 12px; font-weight: 800; color: var(--ink);">{eur_st}</div>
            <div style="font-size: 11px; color: var(--ink-3);">10:00 - 18:30 TSI</div>
          </div>
        </div>
        <div style="padding: 12px 16px; background: var(--card-2); border-radius: 8px; border: 1px solid var(--line); display: flex; justify-content: space-between; align-items: center;">
          <div>
            <div style="font-size: 11px; color: var(--ink-3); font-weight: 700;">3. ABD ÖN PİYASA (Futures)</div>
            <div style="font-size: 13.5px; font-weight: 800; color: var(--amber); margin-top: 2px;">🇺🇸 S&P & Nasdaq NQ</div>
          </div>
          <div style="text-align: right;">
            <div style="font-size: 12px; font-weight: 800; color: var(--ink);">{us_st}</div>
            <div style="font-size: 11px; color: var(--ink-3);">16:30 Açılış Öncesi</div>
          </div>
        </div>
      </div>
    </section>

    <!-- METRİK KARTLARI -->
    <section class="metrics-grid">
      <div class="metric-card">
        <div class="metric-title">Toplam Portföy Değeri</div>
        <div class="metric-val mono" style="color: var(--amber);">${portfolio_val:,.2f}</div>
        <div class="metric-sub">Alpaca Sanal / Canlı Bakiye</div>
      </div>
      <div class="metric-card">
        <div class="metric-title">Kullanılabilir Serbest Nakit</div>
        <div class="metric-val mono" style="color: var(--emerald);">${cash_val:,.2f}</div>
        <div class="metric-sub">Hazır Alım Sermayesi (USD)</div>
      </div>
      <div class="metric-card">
        <div class="metric-title">Gün İçi Alım Gücü (4x)</div>
        <div class="metric-val mono" style="color: var(--blue);">${buying_power:,.2f}</div>
        <div class="metric-sub">SEC Reg T Margin Gücü</div>
      </div>
      <div class="metric-card">
        <div class="metric-title">Strateji Modeli</div>
        <div class="metric-val" style="font-size: 18px; color: #a78bfa; margin-top: 10px;">⚡ ORB + 2. Dalga Retest</div>
        <div class="metric-sub">İlk Pump Engeli: <strong style="color: var(--emerald);">AÇIK</strong></div>
      </div>
    </section>

    <!-- 👥 KULLANICI & ABONE YÖNETİM PANELİ (MULTI-TENANT PANEL) -->
    <section class="table-card">
      <div class="card-header">
        <div>
          <div class="card-title">👥 Alpaca Borsa Aboneleri & Kullanıcı Yönetimi ({len(tenants)})</div>
          <span style="font-size: 12px; color: var(--ink-3);">Alpaca API bağlı kullanıcılar, risk parametreleri ve aktiflik durumları</span>
        </div>
        <button class="btn btn-primary btn-sm" onclick="openAddTenantModal()">➕ Yeni Abone Ekle</button>
      </div>
      <div style="overflow-x: auto;">
        <table>
          <thead>
            <tr>
              <th>Kullanıcı / Hesap</th>
              <th>Telegram Chat ID</th>
              <th>Kâr Al (TP %)</th>
              <th>Zarar Kes (SL %)</th>
              <th>Bütçe (%)</th>
              <th>Hesap Tipi</th>
              <th>Durum</th>
              <th>İşlem</th>
            </tr>
          </thead>
          <tbody>
            {tenants_html}
          </tbody>
        </table>
      </div>
    </section>

    <!-- AÇIK POZİSYONLAR BÖLÜMÜ -->
    <section class="table-card">
      <div class="card-header">
        <div class="card-title">💼 Açık Hisse Senedi Pozisyonları ({len(positions)})</div>
        <span style="font-size: 12px; color: var(--ink-3);">Anlık Kar/Zarar ve Bracket Emir Koruması</span>
      </div>
      <div style="overflow-x: auto;">
        <table>
          <thead>
            <tr>
              <th>Hisse</th>
              <th>Adet</th>
              <th>Alış Fiyatı</th>
              <th>Anlık Fiyat</th>
              <th>Piyasa Değeri</th>
              <th>Net Kâr/Zarar</th>
              <th>İşlem</th>
            </tr>
          </thead>
          <tbody>
            {pos_html}
          </tbody>
        </table>
      </div>
    </section>

    <!-- ABD HİSSE TARAYICISI VE RETEST FIRSATLARI -->
    <section class="table-card">
      <div class="card-header">
        <div class="card-title">🔍 ABD Hisse Senedi Tarayıcısı (NASDAQ / S&P 500)</div>
        <span style="font-size: 12px; color: var(--ink-3);">Seans Açılışı & 2. Dalga Retest Teyit Durumu</span>
      </div>
      <div style="overflow-x: auto;">
        <table>
          <thead>
            <tr>
              <th>Sembol</th>
              <th>Fiyat</th>
              <th>Değişim</th>
              <th>Retest Durumu</th>
              <th>Sinyal Notu</th>
              <th>Hedefler (TP/SL)</th>
              <th>Hızlı Alım</th>
            </tr>
          </thead>
          <tbody>
            {opp_html}
          </tbody>
        </table>
      </div>
    </section>
  </div>

  <!-- YENİ ABONE EKLEME MODALI -->
  <div id="add-tenant-modal" class="modal-overlay">
    <div class="modal-card">
      <h3 style="color: var(--amber);">➕ Yeni Alpaca Abonesi Ekle</h3>
      <div>
        <label style="font-size: 12px; color: var(--ink-3);">Kullanıcı / Hesap Adı:</label>
        <input type="text" id="m_tname" class="table-input" style="width: 100%; text-align: left; padding: 8px; margin-top: 4px;" placeholder="Örn: Mehmet (Alpaca)">
      </div>
      <div>
        <label style="font-size: 12px; color: var(--ink-3);">Telegram Chat ID:</label>
        <input type="number" id="m_chatid" class="table-input" style="width: 100%; text-align: left; padding: 8px; margin-top: 4px;" placeholder="Örn: 8739367825">
      </div>
      <div>
        <label style="font-size: 12px; color: var(--ink-3);">Alpaca API Key ID:</label>
        <input type="text" id="m_apikey" class="table-input" style="width: 100%; text-align: left; padding: 8px; margin-top: 4px;" placeholder="PK...">
      </div>
      <div>
        <label style="font-size: 12px; color: var(--ink-3);">Alpaca Secret Key:</label>
        <input type="password" id="m_secret" class="table-input" style="width: 100%; text-align: left; padding: 8px; margin-top: 4px;" placeholder="...">
      </div>
      <div style="display: flex; gap: 10px;">
        <div style="flex: 1;">
          <label style="font-size: 12px; color: var(--ink-3);">Kâr Al (TP %):</label>
          <input type="number" step="0.1" id="m_tp" class="table-input" style="width: 100%; padding: 8px; margin-top: 4px;" value="3.0">
        </div>
        <div style="flex: 1;">
          <label style="font-size: 12px; color: var(--ink-3);">Stop Loss (SL %):</label>
          <input type="number" step="0.1" id="m_sl" class="table-input" style="width: 100%; padding: 8px; margin-top: 4px;" value="1.5">
        </div>
      </div>
      <div style="display: flex; justify-content: flex-end; gap: 10px; margin-top: 10px;">
        <button class="btn btn-ghost" onclick="closeAddTenantModal()">İptal</button>
        <button class="btn btn-primary" onclick="submitAddStockTenant()">Kaydet</button>
      </div>
    </div>
  </div>

  <script>
    function openAddTenantModal() {{
      document.getElementById('add-tenant-modal').classList.add('open');
    }}
    function closeAddTenantModal() {{
      document.getElementById('add-tenant-modal').classList.remove('open');
    }}

    async function toggleStockTenantActive(tenantId, newActiveState) {{
      try {{
        const res = await fetch('/api/stock/tenants/' + tenantId + '/toggle-active', {{
          method: 'POST',
          headers: {{ 'Content-Type': 'application/json' }},
          body: JSON.stringify({{ is_active: newActiveState }})
        }});
        const data = await res.json();
        if (data.status === 'success') {{
          window.location.reload();
        }} else {{
          alert('Hata: ' + data.error);
        }}
      }} catch(e) {{
        alert('Bağlantı hatası: ' + e);
      }}
    }}

    async function updateStockTenantSettings(tenantId) {{
      const tp = parseFloat(document.getElementById('tp_' + tenantId)?.value || 3.0);
      const sl = parseFloat(document.getElementById('sl_' + tenantId)?.value || 1.5);
      const mb = parseFloat(document.getElementById('mb_' + tenantId)?.value || 25.0);

      try {{
        const res = await fetch('/api/stock/tenants/' + tenantId + '/update', {{
          method: 'POST',
          headers: {{ 'Content-Type': 'application/json' }},
          body: JSON.stringify({{ take_profit_percent: tp, stop_loss_percent: sl, max_budget_percent: mb }})
        }});
        const data = await res.json();
        if (data.status === 'success') {{
          alert('✅ Ayarlar başarıyla güncellendi!');
        }} else {{
          alert('Hata: ' + data.error);
        }}
      }} catch(e) {{
        alert('Bağlantı hatası: ' + e);
      }}
    }}

    async function submitAddStockTenant() {{
      const tname = document.getElementById('m_tname')?.value;
      const chatid = document.getElementById('m_chatid')?.value;
      const apikey = document.getElementById('m_apikey')?.value;
      const secret = document.getElementById('m_secret')?.value;
      const tp = parseFloat(document.getElementById('m_tp')?.value || 3.0);
      const sl = parseFloat(document.getElementById('m_sl')?.value || 1.5);

      if (!tname || !apikey || !secret) {{
        alert('Lütfen Kullanıcı Adı, API Key ve Secret alanlarını doldurunuz.');
        return;
      }}

      try {{
        const res = await fetch('/api/stock/tenants', {{
          method: 'POST',
          headers: {{ 'Content-Type': 'application/json' }},
          body: JSON.stringify({{
            tenant_name: tname,
            telegram_chat_id: parseInt(chatid) || 0,
            api_key: apikey,
            secret_key: secret,
            take_profit_percent: tp,
            stop_loss_percent: sl,
            max_budget_percent: 25.0
          }})
        }});
        const data = await res.json();
        if (data.status === 'success') {{
          alert('✅ Yeni Alpaca Abonesi Başarıyla Eklendi!');
          window.location.reload();
        }} else {{
          alert('Hata: ' + data.error);
        }}
      }} catch(e) {{
        alert('Bağlantı hatası: ' + e);
      }}
    }}

    async function buyStockDirect(symbol, amountUsd) {{
      if (!confirm(symbol + ' hissesinden $' + amountUsd + ' tutarında alım emri gönderilsin mi?')) return;
      try {{
        const res = await fetch('/api/stock/order', {{
          method: 'POST',
          headers: {{ 'Content-Type': 'application/json' }},
          body: JSON.stringify({{ symbol: symbol, amount_usd: amountUsd, side: 'buy' }})
        }});
        const data = await res.json();
        if (data.status === 'success') {{
          alert('✅ [EMİR BAŞARILI]: ' + symbol + ' hissesi için Bracket Order (Alış + TP + SL) oluşturuldu!\\nEmir No: #' + data.order_id);
          window.location.reload();
        }} else {{
          alert('❌ Hata: ' + (data.error || 'Bilinmeyen hata'));
        }}
      }} catch(e) {{
        alert('Bağlantı Hatası: ' + e);
      }}
    }}

    async function closeStockPosition(symbol) {{
      if (!confirm(symbol + ' pozisyonunu piyasa fiyatından kapatmak istediğinize emin misiniz?')) return;
      try {{
        const res = await fetch('/api/stock/positions/' + symbol + '/close', {{ method: 'POST' }});
        const data = await res.json();
        if (data.status === 'success') {{
          alert('✅ ' + symbol + ' pozisyonu kapatıldı.');
          window.location.reload();
        }} else {{
          alert('❌ Hata: ' + data.error);
        }}
      }} catch(e) {{
        alert('Bağlantı Hatası: ' + e);
      }}
    }}
  </script>
</body>
</html>
"""
