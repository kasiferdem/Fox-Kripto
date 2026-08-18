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

        side_code = 0 if side.lower() == "buy" else 1
        type_code = 2 if type.lower() == "market" else 1

        params = {
            "symbol": clean_symbol,
            "side": side_code,
            "type": type_code,
        }

        # Market Buy emrinde Binance TR quoteOrderQty bekler
        if side_code == 0 and type_code == 2:
            if clean_symbol.endswith("_USDT"):
                try:
                    bal = self.fetch_balance()
                    free_usdt = float(bal.get("free", {}).get("USDT", 0.0))
                    amount_usdt = min(amount_usd, free_usdt * 0.99) if free_usdt > 1.0 else amount_usd
                except Exception:
                    amount_usdt = amount_usd
                params["quoteOrderQty"] = f"{max(amount_usdt, 10.0):.2f}"
            else:
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
            asset_coin = clean_symbol.split("_")[0].upper()
            qty_to_sell = amount
            try:
                bal = self.fetch_balance()
                free_coin_amount = float(bal.get("free", {}).get(asset_coin, 0.0))
                if free_coin_amount > 0.0:
                    qty_to_sell = free_coin_amount
            except Exception:
                pass
            
            # Sembole Özel Katı Adım Hassasiyeti (Exact Step Size Mapping for Binance TR)
            import math
            decimals_map = {
                "BTC": 6,
                "ETH": 4,
                "SOL": 3,
                "BNB": 3,
                "AVAX": 2,
                "USDT": 0,
                "EDEN": 1,
                "SUI": 1,
                "RENDER": 1,
                "NEAR": 1,
                "XRP": 1,
                "DOGE": 1,
                "ADA": 1,
                "PEPE": 0,
                "SHIB": 0,
                "BONK": 0,
                "FLOKI": 0,
                "GPS": 0,
                "ACE": 1
            }
            
            base_coin = clean_symbol.split("_")[0].upper()
            num_decimals = decimals_map.get(base_coin, 2 if qty_to_sell >= 1.0 else 3)
            
            if num_decimals == 0:
                params["quantity"] = f"{int(qty_to_sell)}"
            else:
                multiplier = 10 ** num_decimals
                safe_qty = math.floor(qty_to_sell * multiplier) / float(multiplier)
                params["quantity"] = f"{safe_qty:.{num_decimals}f}"

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

class BinanceGlobalRESTClient:
    """Binance Global (api.binance.com) Doğrudan REST API İstemcisi"""
    def __init__(self, api_key: str, secret_key: str):
        self.id = "binance"
        self.apiKey = api_key
        self.secret = secret_key
        self.base_url = "https://api.binance.com"

    def _sign(self, params: dict) -> str:
        params['timestamp'] = int(time.time() * 1000)
        query = '&'.join([f'{k}={v}' for k, v in sorted(params.items())])
        sig = hmac.new(self.secret.encode('utf-8'), query.encode('utf-8'), hashlib.sha256).hexdigest()
        return f'{query}&signature={sig}'

    def fetch_balance(self) -> dict:
        query_str = self._sign({})
        url = f"{self.base_url}/api/v3/account?{query_str}"
        headers = {"X-MBX-APIKEY": self.apiKey}
        res = requests.get(url, headers=headers, timeout=10)
        data = res.json()
        if "balances" in data:
            free_dict = {}
            tot_dict = {}
            for b in data["balances"]:
                coin = b.get("asset")
                free_v = float(b.get("free", 0.0))
                locked_v = float(b.get("locked", 0.0))
                tot = free_v + locked_v
                if tot > 0:
                    tot_dict[coin] = tot
                    free_dict[coin] = free_v
            return {"total": tot_dict, "free": free_dict, "info": data}
        raise Exception(f"Binance Global Balance Error: {data}")

    def create_order(self, symbol: str, type: str, side: str, amount: float, amount_usd: float = 10.0) -> dict:
        clean_symbol = symbol.replace("/", "").replace("-", "").replace("_", "").upper()
        base_c = symbol.split("/")[0].split("_")[0].upper()
        
        if side.upper() == "BUY":
            # Binance Global Market Alımında 'quoteOrderQty' kullanarak LOT_SIZE hassasiyet hatasını %100 sıfırla!
            spend_usd = max(10.0, float(amount_usd or 10.0))
            params = {
                "symbol": clean_symbol,
                "side": "BUY",
                "type": "MARKET",
                "quoteOrderQty": f"{spend_usd:.2f}"
            }
        else:
            # Satışta serbest miktarı gönder
            try:
                bal = self.fetch_balance()
                free_c = float(bal.get("free", {}).get(base_c, 0.0))
                if free_c > 0:
                    amount = free_c
            except Exception:
                pass
                
            # Adım hassasiyeti
            step_map = {
                "BTC": 5, "ETH": 4, "SOL": 2, "AVAX": 2, "BNB": 3, 
                "SHIB": 0, "PEPE": 0, "BONK": 0, "DOGE": 0, "FLOKI": 0,
                "FLM": 1, "WAVES": 2, "CLV": 1, "UTK": 1, "GPS": 0, "ACE": 2, "PORTAL": 2
            }
            dec = step_map.get(base_c, 2)
            import math
            mult = 10 ** dec
            safe_qty = math.floor(amount * mult) / float(mult) if mult > 1 else int(amount)
            qty_str = f"{safe_qty:.{dec}f}" if dec > 0 else str(int(safe_qty))
            
            params = {
                "symbol": clean_symbol,
                "side": "SELL",
                "type": "MARKET",
                "quantity": qty_str
            }
        
        query_str = self._sign(params)
        url = f"{self.base_url}/api/v3/order?{query_str}"
        headers = {"X-MBX-APIKEY": self.apiKey}
        res = requests.post(url, headers=headers, timeout=10)
        data = res.json()
        if "orderId" in data:
            exec_p = 0.0
            fills = data.get("fills", [])
            if fills:
                exec_p = float(fills[0].get("price", 0.0))
            return {
                "id": str(data["orderId"]),
                "symbol": symbol,
                "price": exec_p,
                "amount": amount,
                "status": "closed",
                "info": data
            }
        else:
            raise Exception(f"Binance Global Error ({data.get('code')}): {data.get('msg')}")

    def convert_dust_to_bnb(self, assets: Optional[list] = None) -> dict:
        """
        Binance Global'deki küçük küsuratları (Dust Balances) resmi SAPI ile BNB'ye dönüştürür.
        """
        if not assets:
            # 1. Dönüştürülebilir varlıkları sorgula
            query_str = self._sign({"recvWindow": 60000})
            url_list = f"{self.base_url}/sapi/v1/asset/dust-btc?{query_str}"
            headers = {"X-MBX-APIKEY": self.apiKey}
            try:
                res_list = requests.post(url_list, headers=headers, timeout=10)
                data_list = res_list.json()
                details = data_list.get("details", [])
                assets = [d["asset"] for d in details if d.get("asset") and d["asset"] not in ["BNB", "USDT", "LDUSDT"]]
            except Exception as e:
                return {"status": "failed", "error": f"Toz bakiyeler sorgulanamadı: {e}"}
            
        if not assets:
            return {"status": "success", "message": "Dönüştürülecek küçük bakiye (Dust) bulunamadı.", "converted_assets": [], "total_bnb_received": 0.0}
            
        # 2. Tozları BNB'ye dönüştür
        ts = int(time.time() * 1000)
        asset_queries = "&".join([f"asset={a}" for a in assets])
        query_base = f"{asset_queries}&recvWindow=60000&timestamp={ts}"
        sig = hmac.new(self.secret.encode('utf-8'), query_base.encode('utf-8'), hashlib.sha256).hexdigest()
        
        url_convert = f"{self.base_url}/sapi/v1/asset/dust?{query_base}&signature={sig}"
        headers = {"X-MBX-APIKEY": self.apiKey}
        try:
            res = requests.post(url_convert, headers=headers, timeout=10)
            data = res.json()
            if "totalTransfered" in data or "totalServiceCharge" in data:
                return {
                    "status": "success",
                    "total_bnb_received": float(data.get("totalTransfered", 0.0)),
                    "service_charge": float(data.get("totalServiceCharge", 0.0)),
                    "converted_assets": assets,
                    "info": data
                }
            else:
                return {
                    "status": "failed",
                    "error": f"Binance Dust Error ({data.get('code')}): {data.get('msg')}",
                    "info": data
                }
        except Exception as ce:
            return {"status": "failed", "error": f"Dust dönüştürme hatası: {ce}"}

def convert_dust_to_bnb(tenant_config: Optional[Dict[str, Any]] = None, assets: Optional[list] = None) -> Dict[str, Any]:
    """İlgili kullanıcının Binance Global hesabındaki tüm küçük küsuratları (Dust) tek hamlede BNB'ye çevirir."""
    api_k = str((tenant_config or {}).get("exchange_api_key", ""))
    if api_k.startswith("{"):
        import json
        try:
            kd = json.loads(api_k)
            if "binance" in kd:
                client = BinanceGlobalRESTClient(kd["binance"].get("api_key"), kd["binance"].get("secret_key"))
                return client.convert_dust_to_bnb(assets)
        except Exception:
            pass
    client = get_exchange_for_tenant(tenant_config)
    if hasattr(client, "convert_dust_to_bnb"):
        return client.convert_dust_to_bnb(assets)
    return {"status": "failed", "error": "Borsa istemcisi Dust to BNB özelliğini desteklemiyor."}

def get_exchange_for_tenant(tenant_config: Optional[Dict[str, Any]] = None):
    """
    Multi-Tenant Borsa İstemcisi (Binance Global REST, Binance TR REST ve Çift Borsa Destekli):
    """
    if tenant_config:
        exchange_id = tenant_config.get("exchange_id", "binance").lower()
        api_key = tenant_config.get("exchange_api_key", "")
        secret_key = tenant_config.get("exchange_secret_key", "")
    else:
        exchange_id = os.environ.get("EXCHANGE_ID", "binance").lower()
        api_key = os.environ.get("EXCHANGE_API_KEY", "")
        secret_key = os.environ.get("EXCHANGE_SECRET_KEY", "")
        
    # JSON Formatındaki Borsa Anahtarlarını Güvenle Ayrıştır
    if isinstance(api_key, str) and api_key.startswith("{"):
        try:
            import json
            keys_dict = json.loads(api_key)
            if "binancetr" in keys_dict and exchange_id in ["binancetr", "binance.tr", "trbinance"]:
                tr_k = keys_dict.get("binancetr", {})
                return BinanceTRClient(tr_k.get("api_key"), tr_k.get("secret_key"))
            elif "binance" in keys_dict:
                gl_k = keys_dict.get("binance", {})
                return BinanceGlobalRESTClient(gl_k.get("api_key"), gl_k.get("secret_key"))
            elif "api_key" in keys_dict:
                api_key = keys_dict.get("api_key", "")
                secret_key = keys_dict.get("secret_key") or secret_key
        except Exception:
            pass

    if exchange_id in ["binancetr", "binance.tr", "trbinance"] or (isinstance(api_key, str) and api_key.startswith("BbD")):
        return BinanceTRClient(api_key, secret_key)

    return BinanceGlobalRESTClient(api_key, secret_key)

_cached_price_map = {}
_cached_price_map_ts = 0

def get_all_prices_map() -> Dict[str, float]:
    """Tüm Binance coin fiyatlarını tek bir süper hızlı bulk istekte (100ms) çeker ve 10 saniye cache'ler."""
    global _cached_price_map, _cached_price_map_ts
    now = time.time()
    if _cached_price_map and (now - _cached_price_map_ts < 10):
        return _cached_price_map
    try:
        r = requests.get("https://api.binance.com/api/v3/ticker/price", timeout=3)
        if r.status_code == 200:
            _cached_price_map = {item["symbol"]: float(item["price"]) for item in r.json()}
            _cached_price_map_ts = now
            return _cached_price_map
    except Exception:
        pass
    return _cached_price_map or {}

def fetch_portfolio_balance(tenant_config: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """İlgili kullanıcının (Tenant) güncel bakiye ve varlıklarını okur (Çift Borsa Destekli)."""
    # 1. ÇİFT BORSA KONTROLÜ
    api_k = str((tenant_config or {}).get("exchange_api_key", ""))
    exch_id = str((tenant_config or {}).get("exchange_id", "")).lower()
    if (api_k.startswith("{") and "binancetr" in api_k) or exch_id in ["dual", "both"]:
        try:
            import json
            keys_dict = json.loads(api_k) if api_k.startswith("{") else {}
            
            tenant_tr = dict(tenant_config or {})
            tenant_tr["exchange_id"] = "binancetr"
            tenant_tr["exchange_api_key"] = keys_dict.get("binancetr", {}).get("api_key")
            tenant_tr["exchange_secret_key"] = keys_dict.get("binancetr", {}).get("secret_key")
            
            tenant_gl = dict(tenant_config or {})
            tenant_gl["exchange_id"] = "binance"
            tenant_gl["exchange_api_key"] = keys_dict.get("binance", {}).get("api_key")
            tenant_gl["exchange_secret_key"] = keys_dict.get("binance", {}).get("secret_key")
            
            import concurrent.futures
            with concurrent.futures.ThreadPoolExecutor(max_workers=2) as executor:
                f_tr = executor.submit(fetch_portfolio_balance, tenant_tr)
                f_gl = executor.submit(fetch_portfolio_balance, tenant_gl)
                bal_tr = f_tr.result()
                bal_gl = f_gl.result()
            
            combined_holdings = {}
            if bal_tr.get("holdings_details"):
                combined_holdings.update(bal_tr["holdings_details"])
            if bal_gl.get("holdings_details"):
                for k, v in bal_gl["holdings_details"].items():
                    if k in combined_holdings:
                        combined_holdings[f"{k} (Global)"] = v
                    else:
                        combined_holdings[k] = v
                        
            gl_actual_usd = 0.0 if bal_gl.get("api_error") else float(bal_gl.get("total_usdt", 0.0))
            gl_free_usd = 0.0 if bal_gl.get("api_error") else float(bal_gl.get("free_usdt", 0.0))
            
            tot_usd = float(bal_tr.get("total_usdt", 0.0)) + gl_actual_usd
            free_usd = float(bal_tr.get("free_usdt", 0.0)) + gl_free_usd
            
            return {
                "exchange": "dual",
                "is_dual": True,
                "is_paper_trading": False,
                "free_usdt": free_usd,
                "total_usdt": tot_usd,
                "holdings_details": combined_holdings,
                "binance_tr": bal_tr,
                "binance_global": bal_gl
            }
        except Exception as de:
            print(f"⚠️ Çift Borsa Bakiye Birleştirme Uyarısı: {de}")

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
            # 1. Öncelik: Binance Ham REST API 'info.balances' yanıtını doğrudan oku (Spot + Simple Earn LD)
            info_balances = balance.get('info', {}).get('balances', [])
            if isinstance(info_balances, list) and len(info_balances) > 0:
                for item in info_balances:
                    asset = item.get('asset', '')
                    try:
                        free_val = float(item.get('free', 0.0))
                        locked_val = float(item.get('locked', 0.0))
                        tot_val = free_val + locked_val
                        if tot_val > 0:
                            if asset in ['USDT', 'LDUSDT']:
                                if asset == 'USDT':
                                    free_usdt = free_val
                                    total_usdt = tot_val
                                elif asset == 'LDUSDT':
                                    free_usdt += tot_val
                                    total_usdt += tot_val
                            elif asset.startswith('LD') and len(asset) > 2:
                                clean_coin = asset[2:]
                                crypto_holdings[f"{clean_coin} (Earn)"] = tot_val
                            else:
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
                                if asset == 'LDUSDT':
                                    free_usdt += amt
                                    total_usdt += amt
                                elif asset.startswith('LD') and len(asset) > 2:
                                    clean_coin = asset[2:]
                                    crypto_holdings[f"{clean_coin} (Earn)"] = amt
                                else:
                                    crypto_holdings[asset] = amt
                        except Exception:
                            pass

            estimated_total_usd = free_usdt
            estimated_total_try = free_usdt * 47.80
            holdings_details = {}
            price_map = get_all_prices_map()
            usdt_try_price = price_map.get("USDTTRY", 47.80) or 47.80
            
            for asset, amount in crypto_holdings.items():
                if amount > 0:
                    try:
                        clean_lookup_coin = asset.replace(" (Earn)", "").strip()
                        if clean_lookup_coin == "TRY":
                            val_usd = amount / usdt_try_price if usdt_try_price > 0 else 0.0
                            val_try = amount
                            estimated_total_usd += val_usd
                            estimated_total_try += val_try
                            holdings_details[asset] = {"amount": amount, "price": 1.0, "val_usd": val_usd, "val_try": val_try}
                        else:
                            price_try = price_map.get(f"{clean_lookup_coin}TRY", 0.0)
                            price_usd = price_map.get(f"{clean_lookup_coin}USDT", 0.0)
                            
                            if price_try > 0:
                                val_try = amount * price_try
                                val_usd = val_try / usdt_try_price if usdt_try_price > 0 else (amount * price_usd)
                            else:
                                val_usd = amount * price_usd
                                val_try = val_usd * usdt_try_price
                                
                            estimated_total_usd += val_usd
                            estimated_total_try += val_try
                            holdings_details[asset] = {
                                "amount": amount, 
                                "price": price_usd if price_usd > 0 else (price_try / usdt_try_price), 
                                "price_try": price_try if price_try > 0 else (price_usd * usdt_try_price),
                                "val_usd": val_usd, 
                                "val_try": val_try
                            }
                    except Exception:
                        holdings_details[asset] = {"amount": amount, "price": 0.0, "val_usd": 0.0, "val_try": 0.0}

            return {
                "exchange": exchange.id,
                "is_paper_trading": False,
                "free_usdt": free_usdt,
                "used_usdt": used_usdt,
                "total_usdt": estimated_total_usd,
                "total_try": estimated_total_try,
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

_global_ccxt_binance = None
def get_global_binance_public():
    global _global_ccxt_binance
    if _global_ccxt_binance is None:
        _global_ccxt_binance = ccxt.binance({'enableRateLimit': True, 'timeout': 5000})
    return _global_ccxt_binance

def fetch_ticker_price(symbol: str = "BTC/USDT") -> Dict[str, Any]:
    """Borsadan anlık sembol fiyatı ve 24h değişimini hızlı ve hatasız okur (TRY ve USDT çiftleri destekli)."""
    clean_sym = symbol.replace("/", "").replace("_", "").replace("-", "").upper()
    # 1. Öncelik: Ultra Hızlı Binance Public 24hr Ticker API (TRY ve USDT destekli)
    try:
        r = requests.get(f"https://api.binance.com/api/v3/ticker/24hr?symbol={clean_sym}", timeout=3)
        if r.status_code == 200:
            data = r.json()
            return {
                "symbol": symbol,
                "last_price": float(data.get("lastPrice") or data.get("price") or 0.0),
                "high": float(data.get("highPrice") or 0.0),
                "low": float(data.get("lowPrice") or 0.0),
                "percentage_change": float(data.get("priceChangePercent") or 0.0),
                "volume": float(data.get("quoteVolume") or 0.0)
            }
    except Exception:
        pass

    # 2. Öncelik: CCXT Fallback
    exchange = get_global_binance_public()
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
    except Exception:
        return {"symbol": symbol, "last_price": 0.0, "percentage_change": 0.0, "volume": 0.0}

def fetch_top_volume_gainers(limit: int = 20) -> list:
    """
    Borsadaki tüm aktif işlem gören (TRADING) altcoinleri REST API ile tarar;
    24 saatlik işlem hacmi ve fiyat artışına göre en popüler aktif patlama liderlerini dinamik döndürür.
    """
    try:
        from surge_detector import get_active_trading_symbols
        active_syms = get_active_trading_symbols()
        r = requests.get("https://api.binance.com/api/v3/ticker/24hr", timeout=5)
        if r.status_code == 200:
            tickers = r.json()
            valid_list = []
            for t in tickers:
                raw_sym = t.get("symbol", "")
                if raw_sym.endswith("USDT") and (not active_syms or raw_sym in active_syms):
                    if any(st in raw_sym for st in ["UPUSDT", "DOWNUSDT", "FDUSDUSDT", "USDCUSDT", "EURUSDT", "TRYUSDT"]):
                        continue
                    vol = float(t.get("quoteVolume", 0.0) or 0.0)
                    change = float(t.get("priceChangePercent", 0.0) or 0.0)
                    price = float(t.get("lastPrice", 0.0) or 0.0)
                    if vol > 500000.0 and price > 0: # Min $500K hacim
                        clean_base = raw_sym.replace("USDT", "")
                        valid_list.append({
                            "symbol": f"{clean_base}/USDT",
                            "last_price": price,
                            "percentage_change": change,
                            "volume": vol
                        })
            valid_list.sort(key=lambda x: x["percentage_change"], reverse=True)
            return valid_list[:limit]
    except Exception as e:
        print(f"⚠️ Top Gainers Tarama Uyarısı: {e}")
    return []

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
