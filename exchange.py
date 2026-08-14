import os, sys, time, requests, hmac, hashlib
if hasattr(sys.stdout, 'reconfigure'): sys.stdout.reconfigure(encoding='utf-8')
import ccxt
from typing import Dict, Any, Optional
from dotenv import load_dotenv

load_dotenv()

class BinanceTRClient:
    """Binance TR (www.binance.tr) Özel REST API İstemcisi"""
    def __init__(self, api_key: str, secret_key: str):
        self.id = "binance.tr"
        self.apiKey = api_key
        self.secret = secret_key
        self.base_url = "https://www.binance.tr"

    def _sign(self, params: dict) -> str:
        params['timestamp'] = int(time.time() * 1000)
        query = '&'.join([f'{k}={v}' for k, v in sorted(params.items())])
        sig = hmac.new(self.secret.encode('utf-8'), query.encode('utf-8'), hashlib.sha256).hexdigest()
        return f'{query}&signature={sig}'

    def fetch_balance(self) -> dict:
        query_str = self._sign({})
        url = f"{self.base_url}/open/v1/account/spot?{query_str}"
        headers = {"X-MBX-APIKEY": self.apiKey}
        res = requests.get(url, headers=headers, timeout=10)
        data = res.json()
        if data.get("code") == 0:
            data_obj = data.get("data") or {}
            assets = data_obj.get("accountAssets") or [] if isinstance(data_obj, dict) else []
            total_dict = {}
            free_dict = {}
            for a in assets:
                coin = a.get("asset")
                free_v = float(a.get("free", 0.0))
                locked_v = float(a.get("locked", 0.0))
                tot = free_v + locked_v
                if tot > 0:
                    total_dict[coin] = tot
                    free_dict[coin] = free_v
            return {"total": total_dict, "free": free_dict, "info": data}
        else:
            raise Exception(f"Binance TR Hata ({data.get('code')}): {data.get('msg')}")

    def create_order(self, symbol: str, type: str, side: str, amount: float, price: Optional[float] = None, amount_usd: float = 10.0) -> dict:
        """
        Binance TR Spot Market/Limit Order Execution API:
        POST /open/v1/orders
        """
        clean_symbol = symbol.replace("/", "_").replace("-", "_").upper()
        if not clean_symbol.endswith("_TRY") and not clean_symbol.endswith("_USDT"):
            clean_symbol = f"{clean_symbol}_TRY"
        elif clean_symbol.endswith("_USDT"):
            clean_symbol = clean_symbol.replace("_USDT", "_TRY")

        side_code = 0 if side.lower() == "buy" else 1
        type_code = 2 if type.lower() == "market" else 1

        params = {
            "symbol": clean_symbol,
            "side": side_code,
            "type": type_code,
        }

        # Market Buy emrinde Binance TR quoteOrderQty (TL tutarı) bekler
        if side_code == 0 and type_code == 2:
            ticker = fetch_ticker_price("USDT/TRY")
            usdt_try_price = float(ticker.get('last_price', 35.0))
            calc_try = round(amount_usd * usdt_try_price, 2)
            
            # Cüzdandaki serbest TL bakiyesini oku ve aşmayı engelle
            try:
                bal = self.fetch_balance()
                free_try = float(bal.get("free", {}).get("TRY", 0.0))
                if free_try >= 10.0 and (calc_try > free_try or calc_try < 10.0):
                    calc_try = round(free_try * 0.95, 2)
            except Exception:
                pass
                
            amount_try = max(calc_try, 10.0)
            params["quoteOrderQty"] = f"{amount_try:.2f}"
        else:
            params["quantity"] = f"{amount:.6f}"

        if price and type_code == 1:
            params["price"] = f"{price:.2f}"

        query_str = self._sign(params)
        url = f"{self.base_url}/open/v1/orders?{query_str}"
        headers = {"X-MBX-APIKEY": self.apiKey}

        res = requests.post(url, headers=headers, timeout=10)
        data = res.json()
        if data.get("code") == 0:
            order_data = data.get("data", {})
            return {
                "id": str(order_data.get("orderId") or order_data.get("id") or int(time.time())),
                "symbol": symbol,
                "price": float(order_data.get("executedPrice") or price or 0.0),
                "amount": amount,
                "status": "closed" if type_code == 2 else "open",
                "info": data
            }
        else:
            raise Exception(f"Binance TR Order Execution Error ({data.get('code')}): {data.get('msg')}")

def get_exchange_for_tenant(tenant_config: Optional[Dict[str, Any]] = None):
    """
    Multi-Tenant Borsa İstemcisi (Binance Global & Binance TR Destekli):
    """
    if tenant_config:
        exchange_id = tenant_config.get("exchange_id", "binance").lower()
        api_key = tenant_config.get("exchange_api_key", "")
        secret_key = tenant_config.get("exchange_secret_key", "")
    else:
        exchange_id = os.environ.get("EXCHANGE_ID", "binance").lower()
        api_key = os.environ.get("EXCHANGE_API_KEY", "")
        secret_key = os.environ.get("EXCHANGE_SECRET_KEY", "")
        
    if exchange_id in ["binancetr", "binance.tr", "trbinance"] or api_key.startswith("BbD"):
        return BinanceTRClient(api_key, secret_key)

    try:
        exchange_class = getattr(ccxt, exchange_id)
        exchange = exchange_class({
            'apiKey': api_key,
            'secret': secret_key,
            'enableRateLimit': True,
            'options': {'defaultType': 'spot'}
        })
        is_testnet = os.environ.get("EXCHANGE_TESTNET", "false").lower() == "true"
        if is_testnet and hasattr(exchange, 'set_sandbox_mode'):
            exchange.set_sandbox_mode(True)
        return exchange
    except Exception as e:
        print(f"⚠️ Multi-Tenant Bağlantı Uyarısı ({exchange_id}): {e}")
        return None

def fetch_portfolio_balance(tenant_config: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """İlgili kullanıcının (Tenant) güncel bakiye ve varlıklarını okur."""
    exchange = get_exchange_for_tenant(tenant_config)
    if exchange and exchange.apiKey:
        try:
            balance = exchange.fetch_balance()
            usdt_info = balance.get('USDT', {})
            if isinstance(usdt_info, dict):
                free_usdt = float(usdt_info.get('free', 0.0))
                used_usdt = float(usdt_info.get('used', 0.0))
                total_usdt = float(usdt_info.get('total', 0.0))
            else:
                free_usdt = float(balance.get('free', {}).get('USDT', 0.0))
                used_usdt = 0.0
                total_usdt = free_usdt
            
            crypto_holdings = {}
            # 1. Öncelik: Binance Ham REST API 'info.balances' yanıtını doğrudan oku
            info_balances = balance.get('info', {}).get('balances', [])
            if isinstance(info_balances, list) and len(info_balances) > 0:
                for item in info_balances:
                    asset = item.get('asset')
                    if asset and asset != 'USDT':
                        try:
                            free_val = float(item.get('free', 0.0))
                            locked_val = float(item.get('locked', 0.0))
                            tot_val = free_val + locked_val
                            if tot_val > 0:
                                crypto_holdings[asset] = tot_val
                        except Exception:
                            pass
            else:
                # 2. Öncelik: CCXT 'total' sözlük fallback'i
                metadata_keys = {'info', 'free', 'used', 'total', 'timestamp', 'datetime', 'USDT', 'code', 'msg'}
                total_dict = balance.get('total', {})
                if isinstance(total_dict, dict):
                    for asset, details in total_dict.items():
                        if asset in metadata_keys or not isinstance(asset, str) or len(asset) > 10 or not asset.isupper():
                            continue
                        try:
                            amt = float(details) if not isinstance(details, dict) else float(details.get('total') or details.get('free') or 0.0)
                            if amt > 0:
                                crypto_holdings[asset] = amt
                        except Exception:
                            pass

            estimated_total_usd = free_usdt
            holdings_details = {}
            for asset, amount in crypto_holdings.items():
                if amount > 0:
                    try:
                        if asset == "TRY":
                            ticker = fetch_ticker_price("USDT/TRY")
                            usdt_try_price = float(ticker.get('last_price', 40.50))
                            val_usd = amount / usdt_try_price if usdt_try_price > 0 else 0.0
                            estimated_total_usd += val_usd
                            holdings_details[asset] = {"amount": amount, "price": 1.0 / usdt_try_price if usdt_try_price > 0 else 0.0, "val_usd": val_usd}
                        else:
                            ticker = fetch_ticker_price(f"{asset}/USDT")
                            price = float(ticker.get('last_price', 0.0))
                            val_usd = amount * price
                            estimated_total_usd += val_usd
                            holdings_details[asset] = {"amount": amount, "price": price, "val_usd": val_usd}
                    except Exception:
                        holdings_details[asset] = {"amount": amount, "price": 0.0, "val_usd": 0.0}

            return {
                "exchange": exchange.id,
                "is_paper_trading": False,
                "free_usdt": free_usdt,
                "used_usdt": used_usdt,
                "total_usdt": estimated_total_usd,
                "crypto_holdings": crypto_holdings,
                "holdings_details": holdings_details
            }
        except Exception as e:
            print(f"⚠️ CCXT Multi-Tenant Bakiye Uyarısı: {e}")
            return {
                "exchange": "binance",
                "is_paper_trading": True,
                "free_usdt": 1000.0,
                "used_usdt": 0.0,
                "total_usdt": 1000.0,
                "crypto_holdings": {"BTC": 0.0},
                "api_error": str(e)
            }

def fetch_ticker_price(symbol: str = "BTC/USDT") -> Dict[str, Any]:
    """Borsadan anlık sembol fiyatı ve 24h değişimini okur."""
    exchange = ccxt.binance({'enableRateLimit': True})
    try:
        ticker = exchange.fetch_ticker(symbol)
        return {
            "symbol": symbol,
            "last_price": float(ticker.get('last', 0.0)),
            "high": float(ticker.get('high', 0.0)),
            "low": float(ticker.get('low', 0.0)),
            "percentage_change": float(ticker.get('percentage', 0.0)),
            "volume": float(ticker.get('quoteVolume', 0.0))
        }
    except Exception as e:
        print(f"❌ CCXT Fiyat Çekme Hatası ({symbol}): {e}")
        return {"symbol": symbol, "last_price": 64280.0, "percentage_change": 0.0, "volume": 0.0}

def fetch_top_volume_gainers(limit: int = 20) -> list:
    """
    Borsadaki tüm aktif işlem gören popüler altcoinleri tarar;
    24 saatlik işlem hacmi ve fiyat artışına göre en popüler İlk 20 Altcoini dinamik döndürür.
    """
    exchange = ccxt.binance({'enableRateLimit': True})
    try:
        tickers = exchange.fetch_tickers()
        valid_list = []
        for symbol, t in tickers.items():
            if symbol.endswith("/USDT") and not any(stable in symbol for stable in ["USDC", "FDUSD", "BUSD", "TUSD", "EUR", "DAI"]):
                vol = float(t.get('quoteVolume', 0.0) or 0.0)
                change = float(t.get('percentage', 0.0) or 0.0)
                price = float(t.get('last', 0.0) or 0.0)
                if vol > 5000000 and price > 0: # Min $5M USD 24h hacim
                    valid_list.append({
                        "symbol": symbol,
                        "last_price": price,
                        "percentage_change": change,
                        "volume": vol
                    })
        # Hacim ve % değişime göre en sıcak popüler coinleri sırala
        valid_list.sort(key=lambda x: (x["percentage_change"], x["volume"]), reverse=True)
        return valid_list[:limit]
    except Exception as e:
        print(f"⚠️ Top Gainers Tarama Uyarısı: {e}")
        default_symbols = ["BTC/USDT", "ETH/USDT", "SOL/USDT", "AVAX/USDT", "SUI/USDT", "NEAR/USDT", "PEPE/USDT", "RENDER/USDT", "DOGE/USDT", "XRP/USDT", "FET/USDT", "TIA/USDT", "SHIB/USDT", "LINK/USDT", "ADA/USDT"]
        fallback = []
        for sym in default_symbols[:limit]:
            try:
                t = fetch_ticker_price(sym)
                fallback.append(t)
            except Exception:
                pass
        return fallback

def execute_spot_trade(
    symbol: str,
    side: str,
    amount_usd: float,
    stop_loss_price: Optional[float] = None,
    tenant_config: Optional[Dict[str, Any]] = None
) -> Dict[str, Any]:
    """İlgili kullanıcının (Tenant) kendi Binance hesabından Spot emri borsaya iletir."""
    if not symbol or "AUTO" in symbol.upper():
        symbol = "BTC/USDT"
        
    exchange = get_exchange_for_tenant(tenant_config)
    ticker = fetch_ticker_price(symbol if "/" in symbol else f"{symbol}/USDT")
    price = float(ticker.get("last_price") or 64000.0)
    quantity = amount_usd / price if price > 0 else 0

    if exchange and getattr(exchange, "apiKey", None) and not os.environ.get("EXCHANGE_TESTNET", "false").lower() == "true":
        try:
            order = exchange.create_order(
                symbol=symbol,
                type='market',
                side=side.lower(),
                amount=quantity,
                amount_usd=amount_usd
            )
            print(f"✅ [CANLI MULTI-TENANT EMİR İNFAZ EDİLDİ]: Order ID #{order.get('id')}")
            return {
                "status": "success",
                "order_id": str(order.get('id')),
                "symbol": symbol,
                "side": side,
                "amount_usd": amount_usd,
                "executed_price": order.get('price') or price,
                "stop_loss_price": stop_loss_price,
                "raw_order": order
            }
        except Exception as e:
            print(f"❌ [Canlı Multi-Tenant Emir Hatası]: {e}")
            return {"status": "FAILED", "error": str(e)}
    
    # Simülasyon
    print(f"🧪 [PAPER TRADING İNFAZ]: {side.upper()} {symbol} - Tutar: ${amount_usd} USD (Fiyat: ${price})")
    return {
        "status": "EXECUTED_SIMULATED",
        "order_id": f"SIM_{int(price * 100)}",
        "symbol": symbol,
        "side": side,
        "amount_usd": amount_usd,
        "executed_price": price,
        "stop_loss_price": stop_loss_price
    }

if __name__ == "__main__":
    print("🚀 Multi-Tenant exchange.py Modülü Test Ediliyor...")
    portfolio = fetch_portfolio_balance()
    print("Multi-Tenant Canlı Portföy Durumu:", portfolio)
