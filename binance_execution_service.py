"""
Fox-Kripto V2.4 — Merkezi Binance İnfaz Servisi (Binance Execution Service)
Telif Hakkı (c) 2026 Fox-Kripto Quant Ekibi.

Bütün projede Binance Spot API'sine (Binance Global & Binance TR) emir iletebilen
YEGANE VE TEK YETKİLİ İNFAZ SERVİSİDİR (Section 5).

Hiçbir AI servisi, Telegram servisi, Scalping/Balina motoru veya Web paneli
bu servis ve ExecutionGate olmadan borsaya emir gönderemez.
"""

import os
import sys
import time
from typing import Dict, Any, Optional
from exchange import (
    BinanceGlobalRESTClient, BinanceTRClient, get_exchange_for_tenant,
    get_live_usd_try_rate, fetch_ticker_price
)

class BinanceExecutionService:
    """
    Binance ve Binance TR Spot Emirlerini İnfaz Eden Tek Yetkili Servis.
    """
    @classmethod
    def execute_market_order(
        cls,
        symbol: str,
        side: str,
        amount_usd: float,
        entry_price: Optional[float] = None,
        stop_loss_price: Optional[float] = None,
        take_profit_price: Optional[float] = None,
        tenant_config: Optional[Dict[str, Any]] = None,
        is_simulated: bool = False
    ) -> Dict[str, Any]:
        """
        Spot Market Emrini Borsaya İletir.
        """
        clean_sym = symbol.replace("-", "/").upper()
        if "/" not in clean_sym and not clean_sym.endswith("TRY") and not clean_sym.endswith("USDT"):
            clean_sym = f"{clean_sym}/USDT"

        side_clean = side.upper()
        if side_clean not in ["BUY", "SELL"]:
            return {"status": "REJECTED", "error": f"Geçersiz emir yönü: {side}"}

        # 1. Simülasyon / Paper Trading Modu
        if is_simulated:
            sim_price = float(entry_price or 0.0)
            if sim_price <= 0:
                try:
                    ticker = fetch_ticker_price(clean_sym)
                    sim_price = float(ticker.get("last_price") or 0.0)
                except Exception:
                    sim_price = 0.0
            if sim_price <= 0:
                sim_price = 95.50
                
            sim_order_id = f"SIM_{int(time.time() * 1000)}"
            print(f"🧪 [BinanceExecutionService SIMÜLASYON]: {side_clean} {clean_sym} - ${amount_usd:.2f} @ ${sim_price:,.4f}")
            return {
                "status": "EXECUTED_SIMULATED",
                "order_id": sim_order_id,
                "symbol": clean_sym,
                "side": side_clean,
                "amount_usd": amount_usd,
                "executed_price": sim_price,
                "stop_loss_price": stop_loss_price,
                "take_profit_price": take_profit_price,
                "timestamp": time.time()
            }

        # 2. Canlı Borsa İnfazı
        try:
            from exchange import execute_spot_trade
            res = execute_spot_trade(
                symbol=clean_sym,
                side=side_clean,
                amount_usd=amount_usd,
                stop_loss_price=stop_loss_price,
                tenant_config=tenant_config
            )
            return res
        except Exception as e:
            print(f"❌ [BinanceExecutionService Hata]: {e}")
            return {"status": "FAILED", "error": str(e)}

    @classmethod
    def cancel_all_open_orders(cls, symbol: str, tenant_config: Optional[Dict[str, Any]] = None) -> bool:
        """Açık stop veya limit emirlerini iptal eder."""
        try:
            exchange = get_exchange_for_tenant(tenant_config)
            clean_sym = symbol.replace("/", "").replace("_", "").upper()
            if hasattr(exchange, "base_url") and hasattr(exchange, "_sign"):
                c_params = {"symbol": clean_sym}
                c_query = exchange._sign(c_params)
                c_url = f"{exchange.base_url}/api/v3/openOrders?{c_query}"
                import requests
                headers_c = {"X-MBX-APIKEY": exchange.apiKey}
                r_c = requests.delete(c_url, headers=headers_c, timeout=5)
                return (r_c.status_code == 200)
            return False
        except Exception as e:
            print(f"⚠️ [BinanceExecutionService İptal Hatası]: {e}")
            return False
