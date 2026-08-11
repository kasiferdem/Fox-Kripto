import os, sys
if hasattr(sys.stdout, 'reconfigure'): sys.stdout.reconfigure(encoding='utf-8')
import ccxt
from typing import Dict, Any, Optional
from dotenv import load_dotenv

load_dotenv()

def get_exchange_for_tenant(tenant_config: Optional[Dict[str, Any]] = None):
    """
    Multi-Tenant CCXT Borsa İstemcisi:
    Eğer tenant_config verilmişse ilgili kullanıcının özel Binance API anahtarlarını,
    verilmemişse varsayılan .env anahtarlarını ilklendirir.
    """
    if tenant_config:
        exchange_id = tenant_config.get("exchange_id", "binance").lower()
        api_key = tenant_config.get("exchange_api_key", "")
        secret_key = tenant_config.get("exchange_secret_key", "")
    else:
        exchange_id = os.environ.get("EXCHANGE_ID", "binance").lower()
        api_key = os.environ.get("EXCHANGE_API_KEY", "")
        secret_key = os.environ.get("EXCHANGE_SECRET_KEY", "")
        
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
        print(f"⚠️ CCXT Multi-Tenant Bağlantı Uyarısı ({exchange_id}): {e}")
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

def execute_spot_trade(
    symbol: str,
    side: str,
    amount_usd: float,
    stop_loss_price: Optional[float] = None,
    tenant_config: Optional[Dict[str, Any]] = None
) -> Dict[str, Any]:
    """İlgili kullanıcının (Tenant) kendi Binance hesabından Spot emri borsaya iletir."""
    exchange = get_exchange_for_tenant(tenant_config)
    ticker = fetch_ticker_price(symbol)
    price = ticker["last_price"]
    quantity = amount_usd / price if price > 0 else 0

    if exchange and exchange.apiKey and not os.environ.get("EXCHANGE_TESTNET", "false").lower() == "true":
        try:
            order = exchange.create_order(
                symbol=symbol,
                type='market',
                side=side.lower(),
                amount=quantity
            )
            print(f"✅ [CCXT CANLI MULTI-TENANT EMİR]: Order ID #{order.get('id')}")
            return {
                "status": "EXECUTED",
                "order_id": str(order.get('id')),
                "symbol": symbol,
                "side": side,
                "amount_usd": amount_usd,
                "executed_price": order.get('price') or price,
                "stop_loss_price": stop_loss_price,
                "raw_order": order
            }
        except Exception as e:
            print(f"❌ [CCXT Canlı Multi-Tenant Emir Hatası]: {e}")
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
