"""
Fox-Borsa: Sade, Anlaşılır ve Şık Wall Street Dashboard HTML Arayüzü (/borsa/dashboard)
Telif Hakkı (c) 2026 Fox-Kripto / Fox-Borsa Quant Ekibi.

ui-ux-designer prensiplerine uygun olarak tasarlanmıştır:
- F-Pattern hiyerarşisi
- Satoshi + JetBrains Mono font eşleşmesi
- Wall Street Koyu FinTech Teması (Koyu Arka Plan, Zümrüt Yeşili ve Altın Sarısı Aksanlar)
- 3 Temel Panel: Canlı Portföy, Seans Sayacı, Hisse Tarayıcısı & 2. Dalga Retest Teyidi
"""

import json
from typing import Dict, Any, List

def generate_stock_dashboard_html(
    account_info: Dict[str, Any],
    market_clock: Dict[str, Any],
    positions: List[Dict[str, Any]],
    opportunities: List[Dict[str, Any]],
    tenants: List[Dict[str, Any]],
    strategy_config: Dict[str, Any]
) -> str:
    cash_val = float(account_info.get("cash", 100000.0))
    portfolio_val = float(account_info.get("portfolio_value", 100000.0))
    buying_power = float(account_info.get("buying_power", 400000.0))
    is_paper = bool(account_info.get("is_paper", True))
    is_market_open = bool(market_clock.get("is_open", False))

    market_badge = '<span class="badge badge-live">🟢 SEANS AÇIK (NYSE/NASDAQ)</span>' if is_market_open else '<span class="badge badge-closed">🔴 PİYASA KAPALI (16:30 TSI Bekleniyor)</span>'
    mode_badge = '<span class="badge badge-paper">🧪 ALPACA PAPER SANDBOX ($100K)</span>' if is_paper else '<span class="badge badge-live">🚀 LIVE TRADING</span>'

    # Açık Pozisyonlar Tablosu
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

    # Fırsat ve Retest Teyit Tablosu
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
    .card-header {{ display: flex; justify-content: space-between; align-items: center; margin-bottom: 16px; }}
    .card-title {{ font-size: 16px; font-weight: 700; color: var(--ink); display: flex; align-items: center; gap: 8px; }}
    table {{ width: 100%; border-collapse: collapse; text-align: left; }}
    th {{ padding: 12px; font-size: 11px; text-transform: uppercase; color: var(--ink-3); border-bottom: 1px solid var(--line); font-weight: 700; }}
    td {{ padding: 14px 12px; border-bottom: 1px solid rgba(51, 65, 85, 0.5); font-size: 13.5px; vertical-align: middle; }}
    tr:hover td {{ background: rgba(30, 41, 59, 0.4); }}
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

  <script>
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
