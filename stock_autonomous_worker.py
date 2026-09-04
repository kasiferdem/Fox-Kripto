"""
Fox-Borsa: 7/24 Otonom ABD Hisse Senedi Alım-Satım ve Seans İşlem İşçisi (StockAutonomousWorker)
Telif Hakkı (c) 2026 Fox-Kripto / Fox-Borsa Quant Ekibi.

ABD Borsa Seansı Açıldığında (16:30 - 23:00 TSI):
1. Alpaca Market Clock ile seans durumunu teyit eder.
2. GlobalMarketRadar ile küresel rüzgarı (Tokyo, Londra, US Futures) kontrol eder.
3. StockMomentumEngine ile 2. Dalga Retest teyidi (STOCK_RETEST_CONFIRMED) arar.
4. Onaylanan hisseler için Alpaca Bracket Order (Alış + %3 TP + %1.5 SL) açar.
5. @FoxBorsaBot üzerinden anında bildirim gönderir.
"""

import time
import threading
from typing import Dict, Any, List
from alpaca_client import AlpacaClient
from stock_momentum_engine import StockMomentumEngine
from global_market_radar import GlobalMarketRadar
from stock_telegram_bot import notify_stock_trade, send_stock_telegram_message
from db import get_system_setting

_worker_thread = None
_worker_running = False
last_scanned_orders = {}  # Symbol -> timestamp (10 dk spam engeli)

def run_stock_autonomous_worker_loop():
    global _worker_running, last_scanned_orders
    print("🚀 [Fox-Borsa Otonom İşçi]: ABD Borsası 7/24 Otonom Seans Takibi Başlatıldı!")
    time.sleep(5)
    
    default_client = AlpacaClient()
    engine = StockMomentumEngine(default_client)
    radar = GlobalMarketRadar(default_client)

    while _worker_running:
        try:
            clock = default_client.get_market_clock()
            is_open = bool(clock.get("is_open", False))
            
            if not is_open:
                # Seans kapalıyken 60 saniyede bir kontrol et
                time.sleep(60)
                continue

            # Seans AÇIK! Piyasayı ve fırsatları tara
            global_sentiment = radar.evaluate_global_sentiment()
            allow_buys = global_sentiment.get("allow_aggressive_buys", True)
            
            if not allow_buys:
                print("⚠️ [Fox-Borsa]: Küresel piyasa skoru düşük (Risk-Off), alımlar geçici kilitlendi.")
                time.sleep(30)
                continue

            opportunities = engine.scan_opportunities()
            stock_tenants = get_system_setting("stock_tenants", default=[])
            active_tenants = [t for t in stock_tenants if t.get("is_active", True)]

            now_ts = time.time()
            for opp in opportunities:
                symbol = opp.get("symbol")
                is_ready = opp.get("is_ready", False)
                state = opp.get("state")
                price = opp.get("price", 0.0)

                # 🛡️ Yalnızca 2. Dalga Retest Teyidi Alan Hisseler (STOCK_RETEST_CONFIRMED)
                if is_ready and state == "STOCK_RETEST_CONFIRMED" and price > 0:
                    last_ord = last_scanned_orders.get(symbol, 0)
                    if now_ts - last_ord < 600:  # Aynı hisseye 10 dakika içinde tekrar girme
                        continue

                    # Aktif aboneler için Bracket Order aç
                    for tenant in active_tenants:
                        api_k = tenant.get("api_key")
                        sec_k = tenant.get("secret_key")
                        is_p = bool(tenant.get("is_paper", True))
                        chat_id = tenant.get("telegram_chat_id")
                        tp_pct = float(tenant.get("take_profit_percent") or 3.0)
                        sl_pct = float(tenant.get("stop_loss_percent") or 1.5)
                        
                        t_client = AlpacaClient(api_k, sec_k, is_paper=is_p)
                        
                        # Açık pozisyon sayısını kontrol et (Maksimum 3 hisse)
                        cur_positions = t_client.get_positions()
                        if len(cur_positions) >= 3:
                            continue
                        
                        # Hisse zaten açık mı?
                        if any(p.get("symbol") == symbol for p in cur_positions):
                            continue

                        # Bütçe hesapla (Örn: $1,000 USD)
                        order_amount_usd = 1000.0
                        tp_price = price * (1.0 + (tp_pct / 100.0))
                        sl_price = price * (1.0 - (sl_pct / 100.0))

                        res = t_client.create_bracket_order(
                            symbol=symbol,
                            amount_usd=order_amount_usd,
                            take_profit_price=tp_price,
                            stop_loss_price=sl_price,
                            side="buy"
                        )

                        if res.get("status") == "success":
                            last_scanned_orders[symbol] = now_ts
                            print(f"🎉 [Fox-Borsa Alım İnfaz Edildi]: {symbol} | Miktar: ${order_amount_usd} | Kullanıcı: {tenant.get('tenant_name')}")
                            if chat_id:
                                notify_stock_trade(
                                    chat_id=chat_id,
                                    action="BUY",
                                    symbol=symbol,
                                    qty=float(res.get("qty", 0.0)),
                                    price=price,
                                    amount_usd=order_amount_usd,
                                    order_id=str(res.get("order_id"))
                                )

            time.sleep(20)
        except Exception as e:
            print(f"⚠️ [Stock Worker Hata]: {e}")
            time.sleep(15)

def start_stock_autonomous_worker():
    """Otonom borsa işçisini arka planda başlatır."""
    global _worker_thread, _worker_running
    if _worker_thread and _worker_thread.is_alive():
        return
    _worker_running = True
    _worker_thread = threading.Thread(target=run_stock_autonomous_worker_loop, daemon=True)
    _worker_thread.start()
