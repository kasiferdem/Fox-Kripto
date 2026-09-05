import os, sys, time, requests, hmac, hashlib, math
from decimal import Decimal, ROUND_DOWN
if hasattr(sys.stdout, 'reconfigure'): sys.stdout.reconfigure(encoding='utf-8')
import ccxt
from typing import Dict, Any, Optional
from dotenv import load_dotenv

load_dotenv()

def get_live_usd_try_rate() -> float:
    """Canlı USDT/TRY kurunu Binance API üzerinden okur."""
    endpoints = [
        "https://api.binance.com/api/v3/ticker/price?symbol=USDTTRY",
        "https://api.binance.tr/open/v1/market/ticker/price?symbol=USDT_TRY"
    ]
    for url in endpoints:
        try:
            r = requests.get(url, timeout=3)
            if r.status_code == 200:
                data = r.json()
                price_val = float(data.get("price") or data.get("data", {}).get("price") or 0.0)
                if price_val > 10.0:
                    return price_val
        except Exception:
            continue
    return 0.0

def quantize_amount(amount: float, step_size: float = 1.0) -> float:
    """Miktarı borsanın LOT_SIZE adımına göre Decimal ile tam ve güvenli aşağı yuvarlar."""
    if amount <= 0:
        return 0.0
    if step_size <= 0:
        step_size = 1.0
    try:
        dec_amt = Decimal(str(amount))
        dec_step = Decimal(str(step_size))
        quantized = (dec_amt // dec_step) * dec_step
        return float(quantized)
    except Exception:
        return float(math.floor(amount))

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
                if amount_usdt < 10.0:
                    raise Exception(f"USDT alım tutarı (${amount_usdt:.2f}) asgari $10 limitinin altında.")
                params["quoteOrderQty"] = f"{amount_usdt:.2f}"
            else:
                usdt_try_price = get_live_usd_try_rate()
                if usdt_try_price <= 0:
                    raise Exception("Canlı USD/TRY kuru alınamadı. Güvenlik amacıyla alım durduruldu (Fail-Closed).")
                
                # Kesin ve sıkı bütçe hesabı: Asla bakiye %95 gibi kontrolsüz büyümelere izin verilmez
                calc_try = round(amount_usd * usdt_try_price, 2)
                try:
                    bal = self.fetch_balance()
                    free_try = float(bal.get("free", {}).get("TRY", 0.0))
                    if calc_try > free_try:
                        calc_try = round(free_try * 0.99, 2)
                except Exception:
                    pass
                    
                if calc_try < 10.0:
                    raise Exception(f"Hesaplanan işlem tutarı (₺{calc_try:.2f}) asgari işlem sınırının (₺10) altında.")
                
                amount_try = calc_try
                
                # LOT_SIZE adım büyüklüğü ve tam adet alımı
                base_coin = clean_symbol.split("_")[0].upper()
                step_size = 1.0
                try:
                    r_tr_info = requests.get(f"https://api.binance.com/api/v3/exchangeInfo?symbol={base_coin}TRY", timeout=2)
                    if r_tr_info.status_code != 200:
                        r_tr_info = requests.get(f"https://api.binance.com/api/v3/exchangeInfo?symbol={base_coin}USDT", timeout=2)
                    if r_tr_info.status_code == 200:
                        for s_item in r_tr_info.json().get("symbols", []):
                            for f_item in s_item.get("filters", []):
                                if f_item.get("filterType") == "LOT_SIZE":
                                    step_size = float(f_item.get("stepSize", 1.0))
                except Exception:
                    pass

                try:
                    c_ticker = fetch_ticker_price(f"{base_coin}/TRY")
                    coin_price = float(c_ticker.get("last_price", 0.0))
                    if coin_price > 0:
                        raw_qty = amount_try / coin_price
                        safe_buy_qty = quantize_amount(raw_qty, step_size)
                        if safe_buy_qty > 0 and (safe_buy_qty * coin_price >= 10.0):
                            if step_size >= 1.0:
                                params["quantity"] = f"{int(safe_buy_qty)}"
                            else:
                                dec_places = len(str(step_size).split(".")[1].rstrip("0")) if "." in str(step_size) else 0
                                params["quantity"] = f"{safe_buy_qty:.{dec_places}f}"
                        else:
                            params["quoteOrderQty"] = f"{amount_try:.2f}"
                    else:
                        params["quoteOrderQty"] = f"{amount_try:.2f}"
                except Exception:
                    params["quoteOrderQty"] = f"{amount_try:.2f}"
        else: # SELL
            asset_coin = clean_symbol.split("_")[0].upper()
            qty_to_sell = 0.0
            # 🛡️ KİLİTLİ BAKİYE KORUMASI: Açık stop/limit emirleri iptal ederek bakiyeyi serbest bırak
            try:
                c_params = {"symbol": clean_symbol}
                c_query = self._sign(c_params)
                c_url = f"{self.base_url}/open/v1/orders?{c_query}"
                headers_c = {"X-MBX-APIKEY": self.apiKey}
                requests.delete(c_url, headers=headers_c, timeout=5)
            except Exception:
                pass

            try:
                bal = self.fetch_balance()
                free_coin_amount = float(bal.get("free", {}).get(asset_coin, 0.0))
                if free_coin_amount > 0.0:
                    if amount > 0 and amount < free_coin_amount:
                        qty_to_sell = amount
                    else:
                        qty_to_sell = free_coin_amount
            except Exception:
                pass
            if qty_to_sell <= 0.0:
                qty_to_sell = amount
            
            step_size = 1.0
            try:
                r_tr_info = requests.get(f"https://api.binance.com/api/v3/exchangeInfo?symbol={asset_coin}TRY", timeout=2)
                if r_tr_info.status_code != 200:
                    r_tr_info = requests.get(f"https://api.binance.com/api/v3/exchangeInfo?symbol={asset_coin}USDT", timeout=2)
                if r_tr_info.status_code == 200:
                    for s_item in r_tr_info.json().get("symbols", []):
                        for f_item in s_item.get("filters", []):
                            if f_item.get("filterType") == "LOT_SIZE":
                                step_size = float(f_item.get("stepSize", 1.0))
            except Exception:
                pass
            
            safe_qty = quantize_amount(qty_to_sell, step_size)
            if step_size >= 1.0:
                params["quantity"] = f"{int(safe_qty)}"
            else:
                dec_places = len(str(step_size).split(".")[1].rstrip("0")) if "." in str(step_size) else 0
                params["quantity"] = f"{safe_qty:.{dec_places}f}"

        if price and type_code == 1:
            params["price"] = f"{price:.2f}"

        query_str = self._sign(params)
        url = f"{self.base_url}/open/v1/orders?{query_str}"
        headers = {"X-MBX-APIKEY": self.apiKey}

        res = requests.post(url, headers=headers, timeout=10)
        data = res.json()
        
        # 🛡️ 2 KADEMELİ İNFAZ DENEMESİ: Eğer 3203 veya -1013 miktar hatası gelirse, otomatik tam sayı adet ile 2. kez dene!
        if data.get("code") in [3203, -1013]:
            try:
                if side_code == 0: # BUY 2. Kademe
                    base_c = clean_symbol.split("_")[0].upper()
                    c_ticker = fetch_ticker_price(f"{base_c}/TRY")
                    coin_p = float(c_ticker.get("last_price", 0.0))
                    if coin_p > 0 and amount_try > 0:
                        int_buy_q = int(amount_try / coin_p)
                        if int_buy_q > 0:
                            print(f"⚠️ [Binance TR 2. Kademe ALIM]: {data.get('msg')} -> Tam sayı ({int_buy_q} {base_c}) ile 2. deneme yapılıyor...")
                            params.pop("quoteOrderQty", None)
                            params["quantity"] = str(int_buy_q)
                            query_str = self._sign(params)
                            url = f"{self.base_url}/open/v1/orders?{query_str}"
                            res = requests.post(url, headers=headers, timeout=10)
                            data = res.json()
                elif side_code == 1: # SELL 2. Kademe
                    curr_q = float(params.get("quantity", 0))
                    int_q = int(curr_q)
                    if int_q > 0 and str(int_q) != str(params.get("quantity")):
                        print(f"⚠️ [Binance TR 2. Kademe SATIM]: {params.get('quantity')} reddedildi, tam sayı ({int_q}) ile 2. deneme yapılıyor...")
                        params["quantity"] = str(int_q)
                        query_str = self._sign(params)
                        url = f"{self.base_url}/open/v1/orders?{query_str}"
                        res = requests.post(url, headers=headers, timeout=10)
                        data = res.json()
            except Exception as e_retry:
                print(f"⚠️ [Binance TR Retry Hatası]: {e_retry}")

        if data.get("code") == 0:
            order_data = data.get("data", {})
            return {
                "id": str(order_data.get("orderId") or order_data.get("id") or int(time.time())),
                "symbol": symbol,
                "price": float(order_data.get("price") or (price if price else 0.0)),
                "amount": amount,
                "status": "closed",
                "info": order_data
            }
        else:
            raise Exception(f"Binance TR Error ({data.get('code')}): {data.get('msg')}")

    def create_stop_order(self, symbol: str, quantity: float, stop_price: float, limit_price: Optional[float] = None) -> dict:
        """Binance TR üzerinde fiziksel Stop-Loss emri kurar."""
        clean_symbol = symbol.replace("/", "_").upper()
        l_price = limit_price if limit_price else round(stop_price * 0.995, 6 if stop_price < 1 else 2)
        params = {
            "symbol": clean_symbol,
            "side": 1, # SELL
            "type": 2, # STOP LIMIT
            "quantity": f"{quantity:.4f}" if quantity < 1 else f"{int(quantity)}",
            "price": f"{l_price:.4f}" if l_price < 1 else f"{l_price:.2f}",
            "stopPrice": f"{stop_price:.4f}" if stop_price < 1 else f"{stop_price:.2f}"
        }
        query_str = self._sign(params)
        url = f"{self.base_url}/open/v1/orders?{query_str}"
        headers = {"X-MBX-APIKEY": self.apiKey}
        try:
            res = requests.post(url, headers=headers, timeout=10)
            data = res.json()
            if data.get("code") == 0:
                ord_id = data.get("data", {}).get("orderId")
                print(f"🛡️ [Binance TR Fiziksel Stop Kuruldu]: #{ord_id} - Stop: ₺{stop_price}")
                return {"status": "success", "order_id": str(ord_id), "stop_price": stop_price, "info": data}
            else:
                return {"status": "failed", "error": data.get("msg")}
        except Exception as e:
            return {"status": "failed", "error": str(e)}

_lot_size_cache = {}

def get_lot_size_step(symbol: str) -> float:
    """Binance REST API üzerinden paritenin anlık kesin LOT_SIZE (stepSize) değerini çeker ve önbelleğe alır."""
    clean = symbol.replace("/", "").replace("_", "").upper()
    if clean in _lot_size_cache:
        return _lot_size_cache[clean]
    try:
        r = requests.get(f"https://api.binance.com/api/v3/exchangeInfo?symbol={clean}", timeout=3)
        if r.status_code == 200:
            for s in r.json().get("symbols", []):
                for f in s.get("filters", []):
                    if f.get("filterType") == "LOT_SIZE":
                        step = float(f.get("stepSize", 1.0))
                        _lot_size_cache[clean] = step
                        return step
    except Exception:
        pass
    return 1.0

def format_quantity_by_step(amount: float, symbol: str) -> str:
    """Borsanın kabul ettiği kesin basamak hassasiyetine göre pozisyonun %100'ünü satacak güvenli miktar dizgisi üretir."""
    if amount <= 0:
        return "0"
    step = get_lot_size_step(symbol)
    if step <= 0:
        return f"{amount:.4f}"
    import math
    steps_count = math.floor(amount / step)
    safe_amount = steps_count * step
    if step >= 1.0:
        return str(int(safe_amount))
    else:
        dec = len(str(step).split(".")[1].rstrip("0"))
        return f"{safe_amount:.{dec}f}"

class BinanceGlobalRESTClient:
    """Binance Global (api.binance.com) Doğrudan REST API İstemcisi"""
    _time_offset = 0
    _last_time_sync = 0

    def __init__(self, api_key: str, secret_key: str):
        self.id = "binance"
        self.apiKey = str(api_key or "").strip()
        self.secret = str(secret_key or "").strip()
        self.base_url = "https://api.binance.com"
        self.endpoints = [
            "https://api.binance.com",
            "https://api1.binance.com",
            "https://api2.binance.com",
            "https://api3.binance.com",
            "https://api4.binance.com"
        ]
        self._ccxt = None

    def get_ccxt(self):
        if not self._ccxt and self.apiKey and self.secret:
            try:
                import ccxt
                self._ccxt = ccxt.binance({
                    'apiKey': self.apiKey,
                    'secret': self.secret,
                    'enableRateLimit': True,
                    'options': {'adjustForTimeDifference': True, 'recvWindow': 60000}
                })
            except Exception:
                pass
        return self._ccxt

    @classmethod
    def _sync_time(cls):
        """Binance sunucusu ile milisaniye bazında zaman farkını senkronize eder."""
        now = time.time()
        if now - cls._last_time_sync > 300 or cls._last_time_sync == 0:
            for endpoint in ["https://api.binance.com", "https://api1.binance.com", "https://api2.binance.com"]:
                try:
                    r = requests.get(f"{endpoint}/api/v3/time", timeout=2)
                    if r.status_code == 200:
                        server_time = int(r.json().get("serverTime", 0))
                        local_time = int(time.time() * 1000)
                        if server_time > 0:
                            cls._time_offset = server_time - local_time
                            cls._last_time_sync = now
                            break
                except Exception:
                    pass

    def _sign(self, params: dict) -> str:
        self._sync_time()
        params['recvWindow'] = 60000
        params['timestamp'] = int(time.time() * 1000) + BinanceGlobalRESTClient._time_offset
        query = '&'.join([f'{k}={v}' for k, v in sorted(params.items())])
        sig = hmac.new(self.secret.encode('utf-8'), query.encode('utf-8'), hashlib.sha256).hexdigest()
        return f"{query}&signature={sig}"

    def fetch_balance(self) -> dict:
        # Doğrudan Yüksek Hızlı REST Failover Havuzu (CCXT 10sn gecikmesi tamamen devreden çıkarıldı)
        params = {}
        query_str = self._sign(params)
        headers = {
            "X-MBX-APIKEY": self.apiKey,
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            "Accept": "application/json"
        }
        
        last_err = None
        for base in self.endpoints:
            try:
                url = f"{base}/api/v3/account?{query_str}"
                res = requests.get(url, headers=headers, timeout=3)
                if res.status_code == 200:
                    data = res.json()
                    if "balances" in data:
                        tot_dict, free_dict = {}, {}
                        for b in data["balances"]:
                            coin = b["asset"].upper()
                            free_v = float(b["free"])
                            locked_v = float(b["locked"])
                            tot = free_v + locked_v
                            if tot > 0:
                                tot_dict[coin] = tot
                                free_dict[coin] = free_v
                        return {"total": tot_dict, "free": free_dict, "info": data}
                    else:
                        last_err = f"API Error: {data}"
                else:
                    last_err = f"Status {res.status_code}: {res.text}"
            except Exception as ex:
                last_err = str(ex)
                
        raise Exception(f"Binance Global Balance Error across all endpoints: {last_err}")

    def create_order(self, symbol: str, type: str, side: str, amount: float, amount_usd: float = 10.0) -> dict:
        clean_symbol = symbol.replace("/", "").replace("-", "").replace("_", "").upper()
        base_c = symbol.split("/")[0].split("_")[0].upper()
        
        if side.upper() == "BUY":
            spend_usd = max(10.0, float(amount_usd or 10.0))
            
            # 🎯 KULLANICI ÖNERİSİ: NET SATILABİLİR ADET ALIMI (SIFIR KÜSURAT / ZERO DUST)
            step_map_buy = {
                "BTC": 5, "ETH": 4, "SOL": 2, "AVAX": 2, "BNB": 3, 
                "SHIB": 0, "PEPE": 0, "BONK": 0, "DOGE": 0, "FLOKI": 0, "PLUME": 0,
                "FLM": 1, "WAVES": 2, "CLV": 1, "UTK": 1, "GPS": 0, "ACE": 2, "PORTAL": 2,
                "OPN": 1, "LA": 1, "TUT": 0, "RED": 1, "MUBARAK": 0,
                "HEMI": 0, "GNO": 3, "PROM": 2, "ZRO": 2, "HEI": 0
            }
            dec_buy = step_map_buy.get(base_c)
            if dec_buy is None:
                try:
                    r_info = requests.get("https://api.binance.com/api/v3/exchangeInfo", params={"symbol": clean_symbol}, timeout=2)
                    if r_info.status_code == 200:
                        for s_item in r_info.json().get("symbols", []):
                            for f_item in s_item.get("filters", []):
                                if f_item.get("filterType") == "LOT_SIZE":
                                    step_v = float(f_item.get("stepSize", 1.0))
                                    dec_buy = 0 if step_v >= 1.0 else len(str(step_v).split(".")[1].rstrip("0"))
                except Exception:
                    pass
            if dec_buy is None:
                dec_buy = 0 if "MUBARAK" in base_c or "HEMI" in base_c or "HEI" in base_c or "TREE" in base_c else 2
                
            try:
                g_ticker = fetch_ticker_price(f"{base_c}/USDT")
                g_price = float(g_ticker.get("last_price", 0.0))
                if g_price > 0:
                    raw_qty = spend_usd / g_price
                    if dec_buy == 0:
                        safe_buy_qty = math.floor(raw_qty)
                        if safe_buy_qty > 0 and (safe_buy_qty * g_price >= 5.0):
                            params = {
                                "symbol": clean_symbol,
                                "side": "BUY",
                                "type": "MARKET",
                                "quantity": f"{int(safe_buy_qty)}"
                            }
                        else:
                            params = {"symbol": clean_symbol, "side": "BUY", "type": "MARKET", "quoteOrderQty": f"{spend_usd:.2f}"}
                    else:
                        mult = 10 ** dec_buy
                        safe_buy_qty = math.floor(raw_qty * mult) / float(mult)
                        if safe_buy_qty > 0 and (safe_buy_qty * g_price >= 5.0):
                            params = {
                                "symbol": clean_symbol,
                                "side": "BUY",
                                "type": "MARKET",
                                "quantity": f"{safe_buy_qty:.{dec_buy}f}"
                            }
                        else:
                            params = {"symbol": clean_symbol, "side": "BUY", "type": "MARKET", "quoteOrderQty": f"{spend_usd:.2f}"}
                else:
                    params = {"symbol": clean_symbol, "side": "BUY", "type": "MARKET", "quoteOrderQty": f"{spend_usd:.2f}"}
            except Exception:
                params = {"symbol": clean_symbol, "side": "BUY", "type": "MARKET", "quoteOrderQty": f"{spend_usd:.2f}"}
        else:
            # 🛡️ KİLİTLİ BAKİYE KORUMASI: Eğer açık fiziksel Stop-Loss veya Limit emir varsa önce onu iptal et (kilitli bakiyeyi serbest bırak)!
            try:
                c_params = {"symbol": clean_symbol}
                c_query = self._sign(c_params)
                c_url = f"{self.base_url}/api/v3/openOrders?{c_query}"
                headers_c = {"X-MBX-APIKEY": self.apiKey}
                r_c = requests.delete(c_url, headers=headers_c, timeout=5)
                if r_c.status_code == 200:
                    print(f"🔓 [Binance Global Kilit Çözüldü]: {clean_symbol} açık stop emirleri iptal edilerek bakiye serbest bırakıldı.")
            except Exception as e_c:
                print(f"⚠️ [Binance Global Açık Emir İptal Hatası]: {e_c}")

            try:
                bal = self.fetch_balance()
                free_c = float(bal.get("free", {}).get(base_c, 0.0))
                if free_c > 0:
                    if amount > 0 and amount < free_c:
                        amount = amount
                    else:
                        amount = free_c
            except Exception:
                pass
                
            qty_str = format_quantity_by_step(amount, clean_symbol)
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
        
        # 🛡️ 2 KADEMELİ İNFAZ DENEMESİ: Eğer -1013/-2010 miktar veya limit hatası gelirse
        if ("code" in data and data.get("code") in [-1013, -2010, 3203]) and side.upper() == "SELL":
            # 1. Aşama: Eğer MIN_NOTIONAL ($5 altı) veya precision geldiyse, cüzdandaki tüm serbest bakiyeyi (%100) satmayı dene!
            if "NOTIONAL" in str(data.get("msg", "")).upper():
                try:
                    bal = self.fetch_balance()
                    full_free = float(bal.get("free", {}).get(base_c, 0.0))
                    if full_free > 0:
                        params["quantity"] = format_quantity_by_step(full_free, clean_symbol)
                        query_str = self._sign(params)
                        url = f"{self.base_url}/api/v3/order?{query_str}"
                        res = requests.post(url, headers=headers, timeout=10)
                        data = res.json()
                except Exception:
                    pass

            # 2. Aşama: Tam sayı düzeltmesi (LOT_SIZE)
            if "orderId" not in data:
                try:
                    curr_q = float(params.get("quantity", 0))
                    int_q = int(curr_q)
                    if int_q > 0 and str(int_q) != str(params.get("quantity")):
                        print(f"⚠️ [Binance Global 2. Kademe]: {params.get('quantity')} reddedildi, tam sayı ({int_q}) ile 2. deneme yapılıyor...")
                        params["quantity"] = str(int_q)
                        query_str = self._sign(params)
                        url = f"{self.base_url}/api/v3/order?{query_str}"
                        res = requests.post(url, headers=headers, timeout=10)
                        data = res.json()
                except Exception as e_retry:
                    print(f"⚠️ [Binance Global Retry Hatası]: {e_retry}")

        if "orderId" in data:
            exec_p = 0.0
            fills = data.get("fills", [])
            if fills:
                total_fill_qty = sum(float(f.get("qty", 0.0)) for f in fills)
                if total_fill_qty > 0:
                    exec_p = sum(float(f.get("price", 0.0)) * float(f.get("qty", 0.0)) for f in fills) / total_fill_qty
                else:
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

    def execute_marketable_limit_ioc(
        self,
        symbol: str,
        side: str,
        amount_coin: float,
        reference_price: float,
        max_fill_deviation_pct: float = 0.15,
        timeout_seconds: int = 3
    ) -> dict:
        """
        Bölüm 10 — Fiyat Korumalı Marketable Limit IOC Emri:
        Maksimum %0.15 sapma tavanlı limit emir gönderir, dolmayan kısmı anında iptal eder.
        """
        clean_symbol = symbol.replace("/", "").replace("_", "").upper()
        qty_str = format_quantity_by_step(amount_coin, clean_symbol)
        
        # Fiyat sapma tavanı hesabı
        if side.upper() == "BUY":
            capped_price = reference_price * (1.0 + (max_fill_deviation_pct / 100.0))
        else:
            capped_price = reference_price * (1.0 - (max_fill_deviation_pct / 100.0))
            
        p_dec = 2 if capped_price >= 1.0 else (4 if capped_price >= 0.01 else 6)
        price_str = f"{capped_price:.{p_dec}f}"
        
        params = {
            "symbol": clean_symbol,
            "side": side.upper(),
            "type": "LIMIT",
            "timeInForce": "IOC",
            "quantity": qty_str,
            "price": price_str
        }
        
        query_str = self._sign(params)
        url = f"{self.base_url}/api/v3/order?{query_str}"
        headers = {"X-MBX-APIKEY": self.apiKey}
        
        res = requests.post(url, headers=headers, timeout=timeout_seconds + 2)
        data = res.json()
        
        if "orderId" in data:
            exec_qty = float(data.get("executedQty", 0.0))
            cum_quote = float(data.get("cummulativeQuoteQty", 0.0))
            exec_price = (cum_quote / exec_qty) if exec_qty > 0 else reference_price
            
            return {
                "id": str(data["orderId"]),
                "symbol": symbol,
                "price": exec_price,
                "executed_qty": exec_qty,
                "status": data.get("status", "FILLED"),
                "partial_fill_accepted": (exec_qty > 0),
                "info": data
            }
        else:
            raise Exception(f"Marketable Limit IOC Error ({data.get('code')}): {data.get('msg')}")

    def create_stop_order(self, symbol: str, quantity: float, stop_price: float, limit_price: Optional[float] = None) -> dict:
        """Binance Global üzerinde fiziksel STOP_LOSS_LIMIT emri kurar."""
        clean_symbol = symbol.replace("/", "").replace("_", "").upper()
        l_price = limit_price if limit_price else round(stop_price * 0.995, 6 if stop_price < 1 else 2)
        params = {
            "symbol": clean_symbol,
            "side": "SELL",
            "type": "STOP_LOSS_LIMIT",
            "timeInForce": "GTC",
            "quantity": f"{quantity:.4f}" if quantity < 1 else f"{int(quantity)}",
            "price": f"{l_price:.4f}" if l_price < 1 else f"{l_price:.2f}",
            "stopPrice": f"{stop_price:.4f}" if stop_price < 1 else f"{stop_price:.2f}"
        }
        query_str = self._sign(params)
        url = f"{self.base_url}/api/v3/order?{query_str}"
        headers = {"X-MBX-APIKEY": self.apiKey}
        try:
            res = requests.post(url, headers=headers, timeout=10)
            data = res.json()
            if "orderId" in data:
                print(f"🛡️ [Binance Global Fiziksel Stop Kuruldu]: #{data['orderId']} - Stop: ${stop_price}")
                return {"status": "success", "order_id": str(data["orderId"]), "stop_price": stop_price, "info": data}
            else:
                return {"status": "failed", "error": data.get("msg")}
        except Exception as e:
            return {"status": "failed", "error": str(e)}

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

class VirtualPaperExchangeClient:
    """Sanal Test (Paper Trading) Borsa İstemcisi: 0 Borsa Riski, Gerçek Canlı Veri."""
    def __init__(self, tenant_id: str, initial_balance: float = 100.0):
        self.tenant_id = str(tenant_id)
        self.id = "paper"
        self.apiKey = "VIRTUAL_PAPER_API_KEY"
        self.initial_balance = initial_balance

    def fetch_balance(self) -> dict:
        from db import get_virtual_balance, get_active_positions_from_db
        free_usdt = get_virtual_balance(self.tenant_id, self.initial_balance)
        positions = get_active_positions_from_db(self.tenant_id, "paper", is_simulated=True)
        free_dict = {"USDT": free_usdt}
        total_dict = {"USDT": free_usdt}
        for base, pos in positions.items():
            amt = float(pos.get("amount", 0.0))
            free_dict[base] = amt
            total_dict[base] = amt
        return {
            "free": free_dict,
            "total": total_dict,
            "used": {"USDT": 0.0},
            "info": {"is_paper": True, "virtual_balance": free_usdt}
        }

    def create_order(self, symbol: str, type: str, side: str, amount: float, price: Optional[float] = None, amount_usd: Optional[float] = None) -> dict:
        from db import get_virtual_balance, update_virtual_balance, save_position_to_db, remove_position_from_db
        ticker = fetch_ticker_price(symbol if "/" in symbol else f"{symbol}/USDT")
        exec_price = float(ticker.get("last_price") or price or 1.0)
        curr_balance = get_virtual_balance(self.tenant_id, self.initial_balance)
        base_c = symbol.split("/")[0].split("_")[0].upper()
        quote_c = symbol.split("/")[1].split("_")[0].upper() if "/" in symbol or "_" in symbol else "USDT"

        if side.lower() == "buy":
            spend = float(amount_usd or (amount * exec_price))
            if spend > curr_balance:
                raise Exception(f"Sanal serbest bakiye yetersiz (${curr_balance:.2f} < ${spend:.2f})")
            net_spend = spend * 1.001 # %0.10 sanal komisyon
            new_bal = max(0.0, curr_balance - net_spend)
            update_virtual_balance(self.tenant_id, new_bal)
            actual_amount = spend / exec_price if exec_price > 0 else amount
            save_position_to_db(self.tenant_id, "paper", symbol, base_c, quote_c, actual_amount, exec_price, is_simulated=True)
            print(f"🧪 [SANAL ALIŞ İNFAZI]: {actual_amount:.4f} {base_c} @ ${exec_price:,.4f} | Kalan Sanal Kasa: ${new_bal:.2f}")
            return {
                "id": f"PAPER_BUY_{int(time.time()*1000)}",
                "symbol": symbol,
                "price": exec_price,
                "amount": actual_amount,
                "status": "closed",
                "info": {"is_paper": True, "free_usdt": new_bal}
            }
        else:
            proceeds = float(amount * exec_price * 0.999) # %0.10 sanal komisyon
            new_bal = curr_balance + proceeds
            update_virtual_balance(self.tenant_id, new_bal)
            remove_position_from_db(self.tenant_id, "paper", symbol)
            print(f"🧪 [SANAL SATIŞ İNFAZI]: {amount:.4f} {base_c} @ ${exec_price:,.4f} -> +${proceeds:.2f} | Yeni Sanal Kasa: ${new_bal:.2f}")
            return {
                "id": f"PAPER_SELL_{int(time.time()*1000)}",
                "symbol": symbol,
                "price": exec_price,
                "amount": amount,
                "status": "closed",
                "info": {"is_paper": True, "free_usdt": new_bal}
            }

    def create_stop_order(self, symbol: str, quantity: float, stop_price: float, limit_price: Optional[float] = None) -> dict:
        print(f"🧪 [SANAL FİZİKSEL STOP KAYDI]: {symbol} için ${stop_price} sanal stop-loss kaydedildi.")
        return {"status": "success", "order_id": f"PAPER_STOP_{int(time.time())}", "stop_price": stop_price}

def get_exchange_for_tenant(tenant_config: Optional[Dict[str, Any]] = None):
    """
    Multi-Tenant Borsa İstemcisi (Binance Global REST, Binance TR REST, Çift Borsa ve Sanal Paper Destekli):
    """
    if tenant_config:
        if tenant_config.get("is_paper_trading") or tenant_config.get("exchange_id") == "paper":
            return VirtualPaperExchangeClient(tenant_config.get("id") or tenant_config.get("telegram_chat_id", "paper_tenant"))
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
    """Tüm Binance coin fiyatlarını tek bir süper hızlı bulk istekte çeker ve 30 saniye cache'ler."""
    global _cached_price_map, _cached_price_map_ts
    now = time.time()
    if _cached_price_map and (now - _cached_price_map_ts < 30):
        return _cached_price_map
    endpoints = ["https://api1.binance.com", "https://api2.binance.com", "https://api3.binance.com", "https://api.binance.com"]
    for ep in endpoints:
        try:
            r = requests.get(f"{ep}/api/v3/ticker/price", timeout=2)
            if r.status_code == 200:
                _cached_price_map = {item["symbol"]: float(item["price"]) for item in r.json()}
                _cached_price_map_ts = now
                return _cached_price_map
        except Exception:
            continue
    return _cached_price_map or {}

def fetch_portfolio_balance(tenant_config: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """İlgili kullanıcının (Tenant) güncel bakiye ve varlıklarını okur (Çift Borsa ve Sanal Destekli)."""
    # 0. SANAL TEST (PAPER TRADING) KONTROLÜ
    if tenant_config and (tenant_config.get("is_paper_trading") or tenant_config.get("exchange_id") == "paper"):
        from db import get_virtual_balance, get_active_positions_from_db
        t_id = str(tenant_config.get("id") or tenant_config.get("telegram_chat_id", "paper_tenant"))
        free_usdt = get_virtual_balance(t_id, 100.0)
        positions = get_active_positions_from_db(t_id, "paper", is_simulated=True)
        price_map = get_all_prices_map()
        usdt_try_price = get_live_usd_try_rate()
        
        holdings_details = {}
        total_holdings_val = 0.0
        for base, p in positions.items():
            amt = float(p.get("amount", 0.0))
            p_usd = price_map.get(f"{base}USDT", float(p.get("buy_price", 1.0)))
            val_u = amt * p_usd
            val_t = val_u * usdt_try_price
            total_holdings_val += val_u
            holdings_details[base] = {
                "amount": amt,
                "price": p_usd,
                "price_try": val_t,
                "val_usd": val_u,
                "val_try": val_t
            }
        tot_usd = free_usdt + total_holdings_val
        return {
            "exchange": "paper",
            "is_dual": False,
            "is_paper_trading": True,
            "free_usdt": free_usdt,
            "used_usdt": total_holdings_val,
            "total_usdt": tot_usd,
            "total_try": tot_usd * usdt_try_price,
            "crypto_holdings": {k: v["amount"] for k, v in holdings_details.items()},
            "holdings_details": holdings_details
        }

    # 1. ÇİFT BORSA KONTROLÜ (Yalnızca exchange_id 'dual' veya 'both' ise)
    api_k = str((tenant_config or {}).get("exchange_api_key", ""))
    exch_id = str((tenant_config or {}).get("exchange_id", "")).lower()
    if exch_id in ["dual", "both"]:
        try:
            import json
            keys_dict = json.loads(api_k) if api_k.startswith("{") else {}
            
            tenant_tr = dict(tenant_config or {})
            tenant_tr["exchange_id"] = "binancetr"
            tenant_tr["exchange_api_key"] = keys_dict.get("binancetr", {}).get("api_key") or os.environ.get("BINANCE_TR_API_KEY") or os.environ.get("EXCHANGE_API_KEY")
            tenant_tr["exchange_secret_key"] = keys_dict.get("binancetr", {}).get("secret_key") or os.environ.get("BINANCE_TR_SECRET_KEY") or os.environ.get("EXCHANGE_SECRET_KEY")
            
            tenant_gl = dict(tenant_config or {})
            tenant_gl["exchange_id"] = "binance"
            tenant_gl["exchange_api_key"] = keys_dict.get("binance", {}).get("api_key") or os.environ.get("EXCHANGE_API_KEY")
            tenant_gl["exchange_secret_key"] = keys_dict.get("binance", {}).get("secret_key") or os.environ.get("EXCHANGE_SECRET_KEY")
            
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
            
            usdt_try_price = get_live_usd_try_rate()
            free_try_val = float(bal_tr.get("free_try") or (bal_tr.get("holdings_details", {}).get("TRY", {}).get("amount", 0.0) if isinstance(bal_tr.get("holdings_details"), dict) else 0.0))
            tot_usd = float(bal_tr.get("total_usdt", 0.0)) + gl_actual_usd
            free_usd = float(bal_tr.get("free_usdt", 0.0)) + gl_free_usd
            
            return {
                "exchange": "dual",
                "is_dual": True,
                "is_paper_trading": False,
                "free_try": free_try_val,
                "free_usdt": gl_free_usd,
                "total_usdt": tot_usd,
                "total_try": tot_usd * usdt_try_price,
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

            usdt_try_price = get_live_usd_try_rate()
            estimated_total_usd = free_usdt
            estimated_total_try = free_usdt * usdt_try_price
            holdings_details = {}
            price_map = get_all_prices_map()
            
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
                            price_usd = price_map.get(f"{clean_lookup_coin}USDT", 0.0)
                            price_try = price_map.get(f"{clean_lookup_coin}TRY", 0.0)
                            
                            if price_usd > 0:
                                val_usd = amount * price_usd
                                val_try = val_usd * usdt_try_price
                            elif price_try > 0:
                                val_try = amount * price_try
                                val_usd = val_try / usdt_try_price if usdt_try_price > 0 else 0.0
                            else:
                                val_usd = 0.0
                                val_try = 0.0
                                
                            estimated_total_usd += val_usd
                            estimated_total_try += val_try
                            holdings_details[asset] = {
                                "amount": amount, 
                                "price": price_usd if price_usd > 0 else (price_try / usdt_try_price if usdt_try_price > 0 else 0.0), 
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
            print(f"⚠️ CCXT Multi-Tenant Bakiye Hatası: {e}")
            return {
                "exchange": "binance",
                "is_paper_trading": False,
                "free_usdt": 0.0,
                "used_usdt": 0.0,
                "total_usdt": 0.0,
                "total_try": 0.0,
                "crypto_holdings": {},
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
        
    live_fx = get_live_usd_try_rate()
    if live_fx <= 0:
        return {"status": "FAILED", "error": "Canlı USD/TRY kuru alınamadı (Fail-Closed)."}

    from db import get_system_setting
    exec_mode = str(get_system_setting("execution_mode", "PAPER_TRADING")).upper()
    new_buys_enabled = bool(get_system_setting("new_buy_orders_enabled", False))
    tenant_mode = str((tenant_config or {}).get("trading_mode", "")).lower()

    # 🛑 1. GÜVENLİ MOD ALIM KİLİDİ: Eğer yeni alımlar kapalıysa kesinlikle alım gönderme
    if side.lower() in ["buy", "alim"] and not new_buys_enabled:
        print(f"🛑 [Güvenli Mod Kalkanı]: Yeni alımlar kapalı (new_buy_orders_enabled=False). {symbol} alımı engellendi.")
        return {"status": "BLOCKED_BY_SAFE_MODE", "error": "🛑 Yeni alımlar sistem güvenlik kilidiyle kapatılmıştır (new_buy_orders_enabled=False)."}

    # 🛡️ 2. PAPER / SIGNAL TRADING KONTROLÜ
    is_paper = bool((tenant_config or {}).get("is_paper_trading")) or (tenant_mode == "paper") or (exec_mode in ["SIGNAL_ONLY", "PAPER_TRADING"])
    is_testnet = os.environ.get("EXCHANGE_TESTNET", "false").lower() == "true"

    # TRY Çiftlerini Doğrudan Binance TR İstemcisine Yönlendir (Eğer canlı modda ise)
    is_try_pair = symbol.endswith("/TRY") or symbol.endswith("_TRY")
    api_k = str((tenant_config or {}).get("exchange_api_key", ""))
    
    if is_try_pair and api_k.startswith("{") and not is_paper and not is_testnet:
        import json
        try:
            kd = json.loads(api_k)
            if "binancetr" in kd:
                client_tr = BinanceTRClient(kd["binancetr"].get("api_key"), kd["binancetr"].get("secret_key"))
                clean_sym = symbol.replace("/", "_").upper()
                ticker = fetch_ticker_price(symbol)
                price_try = float(ticker.get("last_price") or 0.0)
                if price_try <= 0:
                    return {"status": "FAILED", "error": f"{symbol} anlık borsa fiyatı okunamadı (Fail-Closed)."}
                    
                amount_coin = (amount_usd * live_fx) / price_try
                res = client_tr.create_order(symbol=clean_sym, type="market", side=side.lower(), amount=amount_coin, amount_usd=amount_usd)
                print(f"✅ [CANLI BINANCE TR OTOMATİK EMİR İNFAZ EDİLDİ]: Order ID #{res.get('id')}")
                
                # 🛡️ FİZİKSEL STOP-LOSS: Alım başarılı olduysa borsaya canlı Stop-Loss emri ilet
                physical_stop = None
                trade_status = "success"
                if side.lower() == "buy" and stop_loss_price and stop_loss_price > 0:
                    try:
                        physical_stop = client_tr.create_stop_order(symbol=clean_sym, quantity=amount_coin, stop_price=stop_loss_price)
                    except Exception as e_st:
                        print(f"⚠️ [Binance TR Fiziksel Stop Hatası]: {e_st}")
                        trade_status = "UNPROTECTED_POSITION"
                        
                return {
                    "status": trade_status,
                    "order_id": str(res.get("id")),
                    "symbol": symbol,
                    "side": side,
                    "amount_usd": amount_usd,
                    "amount_coin": amount_coin,
                    "executed_price": res.get("price") or price_try,
                    "stop_loss_price": stop_loss_price,
                    "physical_stop": physical_stop,
                    "raw_order": res
                }
        except Exception as e:
            print(f"❌ [Canlı Binance TR Otomatik Emir Hatası]: {e}")
            return {"status": "FAILED", "error": str(e)}

    exchange = get_exchange_for_tenant(tenant_config)
    ticker = fetch_ticker_price(symbol if "/" in symbol else f"{symbol}/USDT")
    price = float(ticker.get("last_price") or 0.0)
    if price <= 0:
        return {"status": "FAILED", "error": f"{symbol} anlık fiyatı okunamadı (Fail-Closed)."}
        
    quantity = amount_usd / price if price > 0 else 0
    
    if side.lower() == "sell" and exchange and hasattr(exchange, "fetch_balance"):
        base_asset = symbol.split("/")[0].split("_")[0].upper()
        try:
            bal_check = exchange.fetch_balance()
            free_c = float(bal_check.get("free", {}).get(base_asset, 0.0))
            if free_c > 0:
                quantity = free_c
        except Exception:
            pass

    if exchange and getattr(exchange, "apiKey", None) and not is_testnet:
        try:
            # CCXT create_order çağrısı
            order = exchange.create_order(
                symbol=symbol,
                type='market',
                side=side.lower(),
                amount=quantity
            )
            print(f"✅ [CANLI MULTI-TENANT EMİR İNFAZ EDİLDİ]: Order ID #{order.get('id')}")
            
            # 🛡️ FİZİKSEL STOP-LOSS: Alım başarılı olduysa borsaya canlı Stop-Loss emri ilet
            physical_stop = None
            trade_status = "success"
            if side.lower() == "buy" and stop_loss_price and stop_loss_price > 0 and hasattr(exchange, "create_stop_order"):
                try:
                    physical_stop = exchange.create_stop_order(symbol=symbol, quantity=quantity, stop_price=stop_loss_price)
                except Exception as e_st:
                    print(f"⚠️ [Binance Global Fiziksel Stop Hatası]: {e_st}")
                    trade_status = "UNPROTECTED_POSITION"
                    
            return {
                "status": trade_status,
                "order_id": str(order.get('id')),
                "symbol": symbol,
                "side": side,
                "amount_usd": amount_usd,
                "amount_coin": quantity,
                "executed_price": order.get('price') or price,
                "stop_loss_price": stop_loss_price,
                "physical_stop": physical_stop,
                "raw_order": order
            }
        except Exception as e:
            print(f"❌ [Canlı Multi-Tenant Emir Hatası]: {e}")
            return {"status": "FAILED", "error": str(e)}
    
    # Canlı modda kimlik doğrulanamazsa Fail-Closed kuralı gereği işlem iptal edilir
    if tenant_config and (tenant_config.get("exchange_api_key") or tenant_config.get("telegram_chat_id")):
        return {"status": "FAILED", "error": "Borsa API anahtarı doğrulanamadı veya yetkisiz. Fail-Closed devreye girdi."}
        
    # Sadece tenant yapılandırması olmayan yerel geliştirme testlerinde simülasyon
    return {
        "status": "EXECUTED_SIMULATED",
        "order_id": f"SIM_{int(price * 100)}",
        "symbol": symbol,
        "side": side,
        "amount_usd": amount_usd,
        "amount_coin": quantity,
        "executed_price": price,
        "stop_loss_price": stop_loss_price
    }

def convert_dust_to_bnb(tenant_config: Optional[Dict[str, Any]] = None, max_usd_threshold: float = 0.50) -> Dict[str, Any]:
    """
    Kullanıcının Binance Global hesabındaki $0.50 altı mikro kırıntıları tespit edip
    otomatik olarak BNB'ye (Komisyon Yakıtı) dönüştürür.
    Açık pozisyonları veya $0.50 üzerindeki değerli coinleri (PROM, ONG vb.) asla dönüştürmez.
    """
    client = get_exchange_for_tenant(tenant_config)
    if not client or not getattr(client, "apiKey", None) or not getattr(client, "secret", None):
        return {"status": "FAILED", "error": "Borsa API istemcisi bulunamadı."}

    if not isinstance(client, BinanceGlobalRESTClient):
        return {"status": "SKIPPED", "message": "Yalnızca Binance Global hesapları için desteklenir."}

    try:
        # 1. Mevcut portföy varlıklarını ve değerlerini çek
        bal = fetch_portfolio_balance(tenant_config)
        if bal.get("api_error"):
            return {"status": "FAILED", "error": f"Binance API Bağlantı Hatası: {bal.get('api_error')}"}
        holdings = bal.get("holdings_details", {})
        
        # 2. Açık pozisyonları çek (ASLA DÖNÜŞTÜRÜLMEYECEK COINLER)
        from db import get_active_positions_from_db
        t_id = str((tenant_config or {}).get("id") or (tenant_config or {}).get("telegram_chat_id", "default"))
        open_positions = get_active_positions_from_db(t_id, "binance", is_simulated=False)
        protected_symbols = set(open_positions.keys())
        
        # 3. Korumalı temel varlıklar
        protected_assets = {"USDT", "TRY", "FDUSD", "BNB", "USDC", "BTC", "ETH"}.union(protected_symbols)
        
        # 4. Kırıntı (Dust) Adaylarını Belirle
        dust_candidates = []
        for asset, details in holdings.items():
            clean_asset = asset.replace(" (Earn)", "").replace(" (Global)", "").strip()
            if clean_asset in protected_assets:
                continue
            val_usd = float(details.get("val_usd", 0.0))
            amt = float(details.get("amount", 0.0))
            if 0 < val_usd <= max_usd_threshold and amt > 0:
                dust_candidates.append(clean_asset)
                
        if not dust_candidates:
            return {"status": "SUCCESS", "converted_count": 0, "message": "Dönüştürülecek kırıntı bulunamadı. Kasa temiz."}

        # 5. Binance SAPI POST /sapi/v1/asset/dust çağrısı yap
        ts = int(time.time() * 1000)
        query_params = []
        for a in dust_candidates[:10]: # Binance tek seferde maksimum 10-20 varlık kabul eder
            query_params.append(f"asset={a}")
        query_params.append(f"timestamp={ts}")
        
        query_str = "&".join(query_params)
        sig = hmac.new(client.secret.encode("utf-8"), query_str.encode("utf-8"), hashlib.sha256).hexdigest()
        url = f"https://api.binance.com/sapi/v1/asset/dust?{query_str}&signature={sig}"
        
        headers = {
            "X-MBX-APIKEY": client.apiKey,
            "User-Agent": "Mozilla/5.0 (Fox-Kripto Autonomous)"
        }
        resp = requests.post(url, headers=headers, timeout=10)
        data = resp.json()
        
        if resp.status_code == 200:
            return {
                "status": "SUCCESS",
                "converted_assets": dust_candidates[:10],
                "converted_count": len(dust_candidates[:10]),
                "raw_response": data,
                "message": f"{len(dust_candidates[:10])} adet kırıntı ({', '.join(dust_candidates[:10])}) başarıyla BNB'ye dönüştürüldü."
            }
        else:
            return {
                "status": "FAILED",
                "error": data.get("msg") or str(data),
                "candidates": dust_candidates
            }
    except Exception as e:
        return {"status": "ERROR", "error": str(e)}

if __name__ == "__main__":
    print("🚀 Multi-Tenant exchange.py Modülü Test Ediliyor...")
    portfolio = fetch_portfolio_balance()
    print("Multi-Tenant Canlı Portföy Durumu:", portfolio)
