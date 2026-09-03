"""
Fox-Borsa: Alpaca ABD Hisse Senetleri ve Kripto REST API İstemcisi
Telif Hakkı (c) 2026 Fox-Kripto / Fox-Borsa Quant Ekibi.

Alpaca Paper ve Live ortamlarıyla tam uyumludur.
Kesirli hisse (fractional shares), Bracket Order (Alış + Otomatik TP + SL)
ve gerçek zamanlı portföy/fiyat takibini yönetir.
"""

import time
import json
import requests
from typing import Dict, Any, Optional, List

class AlpacaClient:
    def __init__(
        self,
        api_key: str = "PKCPPKY4Y5OP4RFIAVS37PARAH",
        secret_key: str = "8K22wKpWNE77xJgRWRxwX5sJ2YHRaqF9RaeJwnahgF6M",
        is_paper: bool = True
    ):
        self.api_key = api_key
        self.secret_key = secret_key
        self.is_paper = is_paper
        self.base_url = "https://paper-api.alpaca.markets/v2" if is_paper else "https://api.alpaca.markets/v2"
        self.data_url = "https://data.alpaca.markets/v2"

    def _get_headers(self) -> Dict[str, str]:
        return {
            "APCA-API-KEY-ID": self.api_key,
            "APCA-API-SECRET-KEY": self.secret_key,
            "Content-Type": "application/json"
        }

    def get_account(self) -> Dict[str, Any]:
        """Alpaca hesap durumunu, nakit ve portföy değerini okur."""
        try:
            r = requests.get(f"{self.base_url}/account", headers=self._get_headers(), timeout=8)
            if r.status_code == 200:
                acc = r.json()
                return {
                    "status": "success",
                    "id": acc.get("id"),
                    "account_number": acc.get("account_number"),
                    "status_code": acc.get("status"),
                    "currency": acc.get("currency", "USD"),
                    "portfolio_value": float(acc.get("portfolio_value", 0.0)),
                    "cash": float(acc.get("cash", 0.0)),
                    "buying_power": float(acc.get("buying_power", 0.0)),
                    "equity": float(acc.get("equity", 0.0)),
                    "is_paper": self.is_paper,
                    "raw": acc
                }
            return {"status": "failed", "error": r.text}
        except Exception as e:
            return {"status": "failed", "error": str(e)}

    def get_market_clock(self) -> Dict[str, Any]:
        """ABD Borsa Seans Saatini ve Pazarın Açık/Kapalı Durumunu Okur."""
        try:
            r = requests.get(f"{self.base_url}/clock", headers=self._get_headers(), timeout=5)
            if r.status_code == 200:
                data = r.json()
                return {
                    "status": "success",
                    "is_open": bool(data.get("is_open", False)),
                    "timestamp": data.get("timestamp"),
                    "next_open": data.get("next_open"),
                    "next_close": data.get("next_close")
                }
            return {"status": "failed", "error": r.text}
        except Exception as e:
            return {"status": "failed", "error": str(e)}

    def get_positions(self) -> List[Dict[str, Any]]:
        """Mevcut açık hisse senedi ve kripto pozisyonlarını listeler."""
        try:
            r = requests.get(f"{self.base_url}/positions", headers=self._get_headers(), timeout=8)
            if r.status_code == 200:
                raw_positions = r.json()
                positions = []
                for p in raw_positions:
                    positions.append({
                        "symbol": p.get("symbol"),
                        "qty": float(p.get("qty", 0.0)),
                        "market_value": float(p.get("market_value", 0.0)),
                        "avg_entry_price": float(p.get("avg_entry_price", 0.0)),
                        "current_price": float(p.get("current_price", 0.0)),
                        "unrealized_pl": float(p.get("unrealized_pl", 0.0)),
                        "unrealized_plpc": float(p.get("unrealized_plpc", 0.0)) * 100.0,
                        "change_today": float(p.get("change_today", 0.0)) * 100.0,
                        "asset_class": p.get("asset_class")
                    })
                return positions
            return []
        except Exception:
            return []

    def get_latest_bars(self, symbols: List[str]) -> Dict[str, Dict[str, Any]]:
        """Verilen hisseler için anlık borsa fiyatlarını ve son bar verilerini çeker."""
        try:
            sym_str = ",".join(symbols)
            url = f"{self.data_url}/stocks/bars/latest?symbols={sym_str}"
            r = requests.get(url, headers=self._get_headers(), timeout=8)
            if r.status_code == 200:
                raw_bars = r.json().get("bars", {})
                result = {}
                for s, b in raw_bars.items():
                    result[s] = {
                        "symbol": s,
                        "price": float(b.get("c", 0.0)),
                        "open": float(b.get("o", 0.0)),
                        "high": float(b.get("h", 0.0)),
                        "low": float(b.get("l", 0.0)),
                        "volume": float(b.get("v", 0.0)),
                        "timestamp": b.get("t")
                    }
                return result
            return {}
        except Exception:
            return {}

    def create_bracket_order(
        self,
        symbol: str,
        amount_usd: float,
        take_profit_price: float,
        stop_loss_price: float,
        side: str = "buy"
    ) -> Dict[str, Any]:
        """
        Alpaca üzerinden tek seferde Alış + Take Profit + Stop Loss zincir emri (Bracket Order) açar.
        Kesirli hisse (notional USD) veya adet bazlı infaz destekler.
        """
        try:
            # 1. Anlık Fiyatı Öğren
            bars = self.get_latest_bars([symbol])
            cur_price = bars.get(symbol, {}).get("price", 0.0)
            if cur_price <= 0:
                return {"status": "failed", "error": f"{symbol} anlık fiyatı okunamadı."}

            qty = round(amount_usd / cur_price, 4)
            if qty <= 0:
                return {"status": "failed", "error": "Geçersiz hisse adedi (Qty <= 0)."}

            payload = {
                "symbol": symbol.upper(),
                "qty": str(qty),
                "side": side.lower(),
                "type": "market",
                "time_in_force": "day",
                "order_class": "bracket",
                "take_profit": {
                    "limit_price": str(round(take_profit_price, 2))
                },
                "stop_loss": {
                    "stop_price": str(round(stop_loss_price, 2))
                }
            }

            r = requests.post(f"{self.base_url}/orders", headers=self._get_headers(), json=payload, timeout=10)
            if r.status_code in [200, 201]:
                order_data = r.json()
                return {
                    "status": "success",
                    "order_id": order_data.get("id"),
                    "client_order_id": order_data.get("client_order_id"),
                    "symbol": symbol,
                    "qty": qty,
                    "amount_usd": amount_usd,
                    "side": side,
                    "filled_avg_price": cur_price,
                    "take_profit_price": take_profit_price,
                    "stop_loss_price": stop_loss_price,
                    "raw": order_data
                }
            else:
                return {"status": "failed", "error": f"Alpaca Order Error ({r.status_code}): {r.text}"}
        except Exception as e:
            return {"status": "failed", "error": str(e)}

    def close_position(self, symbol: str) -> Dict[str, Any]:
        """Açık hisse senedi pozisyonunu piyasa fiyatından kapatır."""
        try:
            r = requests.delete(f"{self.base_url}/positions/{symbol.upper()}", headers=self._get_headers(), timeout=8)
            if r.status_code in [200, 204]:
                return {"status": "success", "message": f"{symbol} pozisyonu kapatıldı."}
            return {"status": "failed", "error": r.text}
        except Exception as e:
            return {"status": "failed", "error": str(e)}
