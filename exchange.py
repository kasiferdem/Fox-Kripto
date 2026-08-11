import os, sys
if hasattr(sys.stdout, 'reconfigure'): sys.stdout.reconfigure(encoding='utf-8')
import ccxt
from typing import Dict, Any, Optional
from dotenv import load_dotenv

load_dotenv()

EXCHANGE_ID = os.environ.get("EXCHANGE_ID", "binance").lower()
API_KEY = os.environ.get("EXCHANGE_API_KEY", "")
SECRET_KEY = os.environ.get("EXCHANGE_SECRET_KEY", "")
IS_TESTNET = os.environ.get("EXCHANGE_TESTNET", "true").lower() == "true"

def get_exchange_client():
    """CCXT borsa istemcisini ilklendirir (Binance, OKX, Bybit vb.)."""
    try:
        exchange_class = getattr(ccxt, EXCHANGE_ID)
        exchange = exchange_class({
            'apiKey': API_KEY if API_KEY != "your_exchange_api_key_here" else "",
            'secret': SECRET_KEY if SECRET_KEY != "your_exchange_secret_key_here" else "",
            'enableRateLimit': True,
            'options': {
                'defaultType': 'spot'  # Sınırlı yalnız Spot trade yetkisi
            }
        })
        if IS_TESTNET and hasattr(exchange, 'set_sandbox_mode'):
            exchange.set_sandbox_mode(True)
        return exchange
    except Exception as e:
        print(f"⚠️ CCXT Borsa Bağlantı Uyarısı ({EXCHANGE_ID}): {e}")
        return None

def fetch_portfolio_balance() -> Dict[str, Any]:
    """
    CCXT üzerinden güncel cüzdan bakiyesini (USDT ve Coin miktarlarını) çeker.
    API anahtarları yoksa veya test modundaysa emniyetli Paper Trading bakiyesi verir.
    """
    exchange = get_exchange_client()
    if exchange and exchange.apiKey:
        try:
            balance = exchange.fetch_balance()
            usdt_info = balance.get('USDT', {})
            free_usdt = float(usdt_info.get('free', 0.0))
            used_usdt = float(usdt_info.get('used', 0.0))
            total_usdt = float(usdt_info.get('total', 0.0))
            
            # 0'dan büyük varlıkları filtrele
            crypto_holdings = {}
            for asset, details in balance.get('total', {}).items():
                if float(details) > 0 and asset != 'USDT':
                    crypto_holdings[asset] = float(details)

            return {
                "exchange": EXCHANGE_ID,
                "is_paper_trading": False,
                "free_usdt": free_usdt,
                "used_usdt": used_usdt,
                "total_usdt": total_usdt,
                "crypto_holdings": crypto_holdings
            }
        except Exception as e:
            print(f"⚠️ CCXT Canlı Bakiye Alma Hatası: {e}. Paper Trading moduna geçiliyor.")

    # API Anahtarları girilene kadar Paper-Trading Güvenli Bakiye
    return {
        "exchange": EXCHANGE_ID,
        "is_paper_trading": True,
        "free_usdt": 1000.0,
        "used_usdt": 0.0,
        "total_usdt": 1000.0,
        "crypto_holdings": {"BTC": 0.0, "ETH": 0.0}
    }

def fetch_ticker_price(symbol: str = "BTC/USDT") -> Dict[str, Any]:
    """CCXT ile anlık canlı sembol fiyatı ve 24h değişimini okur."""
    exchange = get_exchange_client() or ccxt.binance()
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
        return {
            "symbol": symbol,
            "last_price": 64000.0,
            "high": 65000.0,
            "low": 63000.0,
            "percentage_change": 0.0,
            "volume": 0.0
        }

def execute_spot_trade(symbol: str, side: str, amount_usd: float, stop_loss_price: Optional[float] = None) -> Dict[str, Any]:
    """
    Kullanıcı ONAY verdiğinde CCXT ile Spot piyasada emri borsaya iletir.
    """
    exchange = get_exchange_client()
    ticker = fetch_ticker_price(symbol)
    price = ticker["last_price"]
    quantity = amount_usd / price if price > 0 else 0

    if exchange and exchange.apiKey and not IS_TESTNET:
        try:
            # Spot Market Buy/Sell Order
            order = exchange.create_order(
                symbol=symbol,
                type='market',
                side=side.lower(),
                amount=quantity
            )
            print(f"✅ [CCXT CANLI EMİR BAŞARILI]: Order ID #{order.get('id')}")
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
            print(f"❌ [CCXT Canlı Emir Hatası]: {e}")
            return {"status": "FAILED", "error": str(e)}
    
    # Paper-Trading İnfaz Simülasyonu
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
    print("🚀 CCXT exchange.py Modülü Test Ediliyor...")
    portfolio = fetch_portfolio_balance()
    print("Portföy Durumu:", portfolio)
    ticker = fetch_ticker_price("BTC/USDT")
    print("BTC/USDT Canlı Fiyat:", ticker)
