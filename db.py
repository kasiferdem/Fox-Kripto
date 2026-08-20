import os, sys, time
if hasattr(sys.stdout, 'reconfigure'): sys.stdout.reconfigure(encoding='utf-8')
from typing import Dict, Any, Optional, List
from dotenv import load_dotenv
from supabase import create_client, Client

load_dotenv()

SUPABASE_URL = os.environ.get("SUPABASE_URL", "https://guxltqbzlquozniriznm.supabase.co")
SUPABASE_KEY = os.environ.get("SUPABASE_SERVICE_ROLE_KEY", "")

_supabase_client: Optional[Client] = None

def get_supabase() -> Optional[Client]:
    """Supabase istemcisini güvenli bir şekilde ilklendirir."""
    global _supabase_client
    if _supabase_client is not None:
        return _supabase_client
    if SUPABASE_URL and SUPABASE_KEY:
        try:
            _supabase_client = create_client(SUPABASE_URL, SUPABASE_KEY)
            return _supabase_client
        except Exception as e:
            print(f"⚠️ Supabase Bağlantı Uyarısı: {e}")
            return None
    return None

# -----------------------------------------
# MULTI-TENANT KULLANICI / KİRACI YÖNETİMİ
# -----------------------------------------

def register_user_tenant(
    tenant_name: str,
    telegram_chat_id: int,
    exchange_api_key: str,
    exchange_secret_key: str,
    exchange_id: str = "binance",
    max_budget_percent: float = 10.0
) -> Optional[Dict[str, Any]]:
    """Sisteme yeni bir kullanıcı (Tenant) ve borsa API anahtarları ekler."""
    client = get_supabase()
    if not client: return None
    try:
        payload = {
            "tenant_name": tenant_name,
            "telegram_chat_id": telegram_chat_id,
            "exchange_id": exchange_id,
            "exchange_api_key": exchange_api_key,
            "exchange_secret_key": exchange_secret_key,
            "max_budget_percent": max_budget_percent,
            "is_active": True
        }
        res = client.table("user_tenants").upsert(payload, on_conflict="telegram_chat_id").execute()
        print(f"✅ [Multi-Tenant]: Kullanıcı '{tenant_name}' (Chat ID: {telegram_chat_id}) başarıyla kaydedildi.")
        return res.data[0] if res.data else None
    except Exception as e:
        print(f"❌ [Multi-Tenant Kayıt Hatası]: {e}")
        return None

def get_tenant_by_chat_id(telegram_chat_id: int) -> Optional[Dict[str, Any]]:
    """Telegram Chat ID'sine göre ilgili kullanıcının borsa ve bütçe ayarlarını getirir."""
    client = get_supabase()
    if not client: return None
    try:
        res = client.table("user_tenants").select("*").eq("telegram_chat_id", telegram_chat_id).eq("is_active", True).execute()
        if res.data and len(res.data) > 0:
            t = dict(res.data[0])
            api_k = str(t.get("exchange_api_key", ""))
            if api_k.startswith("{"):
                try:
                    import json
                    kd = json.loads(api_k)
                    t["take_profit_percent"] = float(kd.get("take_profit_percent") or 1.5)
                    t["preferred_language"] = str(kd.get("preferred_language") or "tr").lower()
                except Exception:
                    pass
            else:
                t["preferred_language"] = str(t.get("preferred_language") or "tr").lower()
            return t
        return None
    except Exception as e:
        print(f"❌ [Multi-Tenant Sorgu Hatası]: {e}")
        return None

def get_all_active_tenants() -> List[Dict[str, Any]]:
    """Sistemdeki tüm aktif kullanıcıları getirir (Çift Borsa / Dual-Exchange Destekli)."""
    client = get_supabase()
    if not client: return []
    try:
        res = client.table("user_tenants").select("*").eq("is_active", True).execute()
        raw_tenants = res.data or []
        unpacked = []
        import json
        for t in raw_tenants:
            exch_id = str(t.get("exchange_id", "")).lower()
            api_k = str(t.get("exchange_api_key", ""))
            
            # JSON formatında çift veya tekil borsa ve risk ayarları kontrolü
            if api_k.startswith("{"):
                try:
                    keys_dict = json.loads(api_k)
                    tp_val = float(keys_dict.get("take_profit_percent") or 1.5)
                    lang_val = str(keys_dict.get("preferred_language") or t.get("preferred_language") or "tr").lower()
                    
                    # Çift borsa durumu (hem binancetr hem binance varsa)
                    if "binancetr" in keys_dict or "binance" in keys_dict:
                        if "binancetr" in keys_dict:
                            t_tr = dict(t)
                            t_tr["exchange_id"] = "binancetr"
                            t_tr["take_profit_percent"] = tp_val
                            t_tr["preferred_language"] = lang_val
                            t_tr["tenant_name"] = f"{t.get('tenant_name', 'Kullanıcı').split('(')[0].strip()} (Binance TR)"
                            t_tr["exchange_api_key"] = keys_dict["binancetr"].get("api_key")
                            t_tr["exchange_secret_key"] = keys_dict["binancetr"].get("secret_key")
                            unpacked.append(t_tr)
                        if "binance" in keys_dict:
                            t_gl = dict(t)
                            t_gl["exchange_id"] = "binance"
                            t_gl["take_profit_percent"] = tp_val
                            t_gl["preferred_language"] = lang_val
                            t_gl["tenant_name"] = f"{t.get('tenant_name', 'Kullanıcı').split('(')[0].strip()} (Binance Global)"
                            t_gl["exchange_api_key"] = keys_dict["binance"].get("api_key")
                            t_gl["exchange_secret_key"] = keys_dict["binance"].get("secret_key")
                            unpacked.append(t_gl)
                        continue
                    else:
                        # Tekil borsa JSON kaydı (Örn: Moonwalker)
                        t_single = dict(t)
                        t_single["take_profit_percent"] = tp_val
                        t_single["preferred_language"] = lang_val
                        t_single["exchange_api_key"] = keys_dict.get("api_key") or api_k
                        t_single["exchange_secret_key"] = keys_dict.get("secret_key") or t.get("exchange_secret_key")
                        unpacked.append(t_single)
                        continue
                except Exception:
                    pass
            
            t_def = dict(t)
            t_def["take_profit_percent"] = float(t.get("take_profit_percent") or 1.5)
            t_def["preferred_language"] = str(t.get("preferred_language") or "tr").lower()
            unpacked.append(t_def)
        return unpacked
    except Exception as e:
        print(f"❌ [Multi-Tenant Liste Hatası]: {e}")
        return []

def log_trade_decision(trade_data: Dict[str, Any], tenant_id: Optional[str] = None) -> Optional[Dict[str, Any]]:
    """Ajan kararlarını ve infaz sonuçlarını ilgili tenant_id ile Supabase'e kaydeder."""
    client = get_supabase()
    if not client: return None
    payload = {
        "tenant_id": tenant_id or trade_data.get("tenant_id"),
        "symbol": trade_data.get("symbol", "BTC/USDT"),
        "direction": trade_data.get("direction", "BUY"),
        "amount_usd": trade_data.get("amount_usd", 0.0),
        "entry_price": trade_data.get("entry_price"),
        "stop_loss_price": trade_data.get("stop_loss_price"),
        "take_profit_price": trade_data.get("take_profit_price"),
        "sentiment_score": trade_data.get("sentiment_score", 0.0),
        "human_approval": trade_data.get("human_approval", "Pending"),
        "status": trade_data.get("status", "CREATED"),
        "order_id": trade_data.get("order_id"),
        "execution_details": trade_data.get("execution_details", {})
    }
    try:
        res = client.table("crypto_trade_logs").insert(payload).execute()
        print(f"✅ [DB Multi-Tenant Log]: İşlem kararı Supabase'e kaydedildi. ID: {res.data[0]['id'] if res.data else 'OK'}")
        return res.data[0] if res.data else None
    except Exception as e:
        # Şema uyumsuzluğunda tenant_id olmadan yedek deneme
        if "tenant_id" in payload:
            payload.pop("tenant_id", None)
            try:
                res = client.table("crypto_trade_logs").insert(payload).execute()
                return res.data[0] if res.data else None
            except Exception:
                pass
def save_graph_state(session_id: str, state_data: Dict[str, Any], tenant_id: Optional[str] = None) -> bool:
    """LangGraph State kalıcılığını Supabase crypto_agent_states tablosuna saklar."""
    client = get_supabase()
    if not client: return False
    payload = {
        "session_id": str(session_id),
        "state_data": state_data
    }
    try:
        client.table("crypto_agent_states").upsert(payload).execute()
        return True
    except Exception as e:
        print(f"⚠️ [DB State Kayıt Uyarısı]: {e}")
        return False

def load_graph_state(session_id: str) -> Optional[Dict[str, Any]]:
    """LangGraph State verisini Supabase'den geri yükler."""
    client = get_supabase()
    if not client: return None
    try:
        res = client.table("crypto_agent_states").select("state_data").eq("session_id", str(session_id)).execute()
        if res.data and len(res.data) > 0:
            return res.data[0]["state_data"]
        return None
    except Exception as e:
        print(f"❌ [DB State Yükleme Hatası]: {e}")
        return None

# -----------------------------------------
# ATOMİK POZİSYON LEDGER & COOLDOWN YÖNETİMİ (SUPABASE POSTGRESQL)
# -----------------------------------------

def save_position_to_db(
    tenant_id: str,
    exchange_id: str,
    symbol: str,
    base_asset: str,
    quote_asset: str,
    amount: float,
    buy_price: float,
    stop_loss_price: Optional[float] = None,
    take_profit_price: Optional[float] = None,
    is_simulated: bool = False
) -> bool:
    """Açılan pozisyonu Supabase crypto_agent_states üzerinde atomik ledger olarak günceller."""
    client = get_supabase()
    if not client: return False
    session_id = f"pos_{str(tenant_id)}_{str(exchange_id).lower()}"
    try:
        # Mevcut pozisyonları oku
        res = client.table("crypto_agent_states").select("state_data").eq("session_id", session_id).execute()
        current_data = (res.data[0]["state_data"] if res.data and len(res.data) > 0 else {}) or {}
        
        base_upper = str(base_asset).upper()
        current_data[base_upper] = {
            "symbol": str(symbol).upper(),
            "base_asset": base_upper,
            "quote_asset": str(quote_asset).upper(),
            "amount": float(amount),
            "buy_price": float(buy_price),
            "is_simulated": bool(is_simulated),
            "time": time.time()
        }
        client.table("crypto_agent_states").upsert({
            "session_id": session_id,
            "state_data": current_data
        }).execute()
        print(f"✅ [Supabase DB Ledger]: {symbol} pozisyonu veritabanına kaydedildi ({amount} adet @ {buy_price})")
        return True
    except Exception as e:
        print(f"⚠️ [Supabase DB Pozisyon Kayıt Uyarısı]: {e}")
        return False

def get_coin_historical_performance(tenant_id: str, base_asset: str) -> Dict[str, Any]:
    """
    Belirli bir coin için kullanıcının geçmiş alım-satım istatistiklerini Supabase'den sorgular.
    Bu veri karar mekanizmasını doğrudan engellemez, yalnızca analiz heyetine içgörü (insight) sağlar.
    """
    client = get_supabase()
    base_upper = base_asset.upper()
    default_stats = {
        "symbol": base_upper,
        "total_trades": 0,
        "win_count": 0,
        "loss_count": 0,
        "win_rate": 0.0,
        "total_net_pnl_pct": 0.0,
        "insight_summary": f"Geçmiş işlem kaydı bulunmuyor (İlk kez taranıyor)."
    }
    if not client:
        return default_stats
        
    try:
        res = client.table("crypto_trade_logs")\
            .select("symbol,direction,execution_details,created_at")\
            .like("symbol", f"{base_upper}%")\
            .order("created_at", desc=True)\
            .limit(20)\
            .execute()
            
        logs = res.data or []
        if not logs:
            return default_stats
            
        total_trades = 0
        win_count = 0
        loss_count = 0
        total_pnl = 0.0
        
        for l in logs:
            det = l.get("execution_details") or {}
            reason = str(det.get("reason_type", "")).lower()
            if "kâr alma" in reason or "take-profit" in reason or "kâr" in reason:
                win_count += 1
                total_trades += 1
                total_pnl += 3.0 # Ortalama TP
            elif "stop-loss" in reason or "stop" in reason:
                loss_count += 1
                total_trades += 1
                total_pnl -= 1.5 # Ortalama SL
                
        if total_trades == 0:
            total_trades = len(logs)
            
        win_rate = (win_count / total_trades * 100.0) if total_trades > 0 else 0.0
        summary = f"Geçmişte {total_trades} işlem ({win_count} Kâr, {loss_count} Zarar | %{win_rate:.0f} Başarı | Net: %{total_pnl:+.1f})"
        
        return {
            "symbol": base_upper,
            "total_trades": total_trades,
            "win_count": win_count,
            "loss_count": loss_count,
            "win_rate": round(win_rate, 1),
            "total_net_pnl_pct": round(total_pnl, 2),
            "insight_summary": summary
        }
    except Exception as e:
        print(f"⚠️ [Coin Geçmişi Sorgu Uyarısı]: {e}")
        return default_stats

def get_virtual_balance(tenant_id: str, default_balance: float = 100.0) -> float:
    """Sanal test hesabı için Supabase'deki güncel serbest USDT bakiyesini döner."""
    client = get_supabase()
    if not client: return default_balance
    session_id = f"virtual_balance_{str(tenant_id)}"
    try:
        res = client.table("crypto_agent_states").select("state_data").eq("session_id", session_id).execute()
        if res.data and len(res.data) > 0:
            data = res.data[0].get("state_data") or {}
            return float(data.get("free_usdt", default_balance))
    except Exception:
        pass
    return default_balance

def update_virtual_balance(tenant_id: str, new_balance: float) -> bool:
    """Sanal test hesabı serbest bakiyesini Supabase'de günceller."""
    client = get_supabase()
    if not client: return False
    session_id = f"virtual_balance_{str(tenant_id)}"
    try:
        payload = {
            "session_id": session_id,
            "updated_at": time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime()),
            "state_data": {"free_usdt": round(new_balance, 2)}
        }
        client.table("crypto_agent_states").upsert(payload).execute()
        return True
    except Exception as e:
        print(f"⚠️ [Sanal Bakiye Güncelleme Hatası]: {e}")
        return False

def get_active_positions_from_db(
    tenant_id: Optional[str] = None,
    exchange_id: Optional[str] = None,
    is_simulated: bool = False
) -> Dict[str, Dict[str, Any]]:
    """Supabase'den tenant ve borsa bazlı açık pozisyonları çeker."""
    client = get_supabase()
    if not client: return {}
    session_id = f"pos_{str(tenant_id)}_{str(exchange_id or 'binancetr').lower()}"
    try:
        res = client.table("crypto_agent_states").select("state_data").eq("session_id", session_id).execute()
        if res.data and len(res.data) > 0:
            raw_pos = res.data[0].get("state_data") or {}
            # İstenen simülasyon filtresine göre filtrele
            filtered = {}
            for k, v in raw_pos.items():
                if isinstance(v, dict):
                    if v.get("is_simulated", False) == is_simulated:
                        filtered[k] = v
            return filtered
        return {}
    except Exception as e:
        print(f"⚠️ [Supabase DB Pozisyon Okuma Uyarısı]: {e}")
        return {}

def remove_position_from_db(tenant_id: str, exchange_id: str, symbol: str) -> bool:
    """Kapanan pozisyonu Supabase ledger'ından siler."""
    client = get_supabase()
    if not client: return False
    session_id = f"pos_{str(tenant_id)}_{str(exchange_id).lower()}"
    base_upper = symbol.split("/")[0].split("_")[0].upper()
    try:
        res = client.table("crypto_agent_states").select("state_data").eq("session_id", session_id).execute()
        if res.data and len(res.data) > 0:
            current_data = res.data[0].get("state_data") or {}
            if base_upper in current_data:
                current_data.pop(base_upper, None)
                client.table("crypto_agent_states").upsert({
                    "session_id": session_id,
                    "state_data": current_data
                }).execute()
                print(f"🗑️ [Supabase DB Ledger]: {symbol} pozisyonu veritabanından başarıyla silindi.")
        return True
    except Exception as e:
        print(f"⚠️ [Supabase DB Pozisyon Silme Uyarısı]: {e}")
        return False

def set_cooldown_in_db(tenant_id: str, symbol: str, base_asset: str, duration_seconds: int = 3600, reason: str = "TRADE_EXIT") -> bool:
    """Satılan coin için Supabase üzerinde atomik soğuma süresi başlatır."""
    client = get_supabase()
    if not client: return False
    session_id = f"cooldowns_{str(tenant_id)}"
    base_upper = str(base_asset).upper()
    until_ts = time.time() + duration_seconds
    try:
        res = client.table("crypto_agent_states").select("state_data").eq("session_id", session_id).execute()
        current_data = (res.data[0]["state_data"] if res.data and len(res.data) > 0 else {}) or {}
        current_data[base_upper] = {
            "symbol": str(symbol).upper(),
            "until_ts": until_ts,
            "reason": str(reason)
        }
        client.table("crypto_agent_states").upsert({
            "session_id": session_id,
            "state_data": current_data
        }).execute()
        print(f"⏳ [Supabase DB Cooldown]: {base_upper} için {duration_seconds//60} dk soğuma süresi veritabanına işlendi.")
        return True
    except Exception as e:
        print(f"⚠️ [Supabase DB Cooldown Kayıt Uyarısı]: {e}")
        return False

def get_active_cooldowns_from_db(tenant_id: str) -> List[str]:
    """Supabase'den halen aktif olan soğuma altındaki coin listesini çeker."""
    client = get_supabase()
    if not client: return []
    session_id = f"cooldowns_{str(tenant_id)}"
    now_ts = time.time()
    try:
        res = client.table("crypto_agent_states").select("state_data").eq("session_id", session_id).execute()
        if res.data and len(res.data) > 0:
            cds = res.data[0].get("state_data") or {}
            active_list = []
            for coin, info in cds.items():
                if isinstance(info, dict) and float(info.get("until_ts", 0)) > now_ts:
                    active_list.append(coin.upper())
            return active_list
        return []
    except Exception as e:
        print(f"⚠️ [Supabase DB Cooldown Okuma Uyarısı]: {e}")
        return []

if __name__ == "__main__":
    print("🚀 Multi-Tenant db.py Modülü Test Ediliyor...")
    client = get_supabase()
    if client:
        print("✅ Supabase istemcisi başarıyla bağlandı!")
        register_user_tenant(
            tenant_name="Ana Kullanıcı (S)",
            telegram_chat_id=8739367825,
            exchange_api_key=os.environ.get("EXCHANGE_API_KEY", ""),
            exchange_secret_key=os.environ.get("EXCHANGE_SECRET_KEY", "")
        )

