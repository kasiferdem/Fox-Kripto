import os, sys
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
        print(f"⚠️ [DB Loglama Uyarısı]: {e}")
        return None

def save_graph_state(session_id: str, state_data: Dict[str, Any], tenant_id: Optional[str] = None) -> bool:
    """LangGraph State kalıcılığını (Persistence) tenant_id ile Supabase'e saklar."""
    client = get_supabase()
    if not client: return False
    payload = {
        "session_id": session_id,
        "tenant_id": tenant_id or state_data.get("tenant_id"),
        "state_data": state_data
    }
    try:
        client.table("crypto_agent_states").upsert(payload).execute()
        return True
    except Exception as e:
        if "tenant_id" in payload:
            payload.pop("tenant_id", None)
            try:
                client.table("crypto_agent_states").upsert(payload).execute()
                return True
            except Exception:
                pass
        print(f"⚠️ [DB State Kayıt Uyarısı]: {e}")
        return False

def load_graph_state(session_id: str) -> Optional[Dict[str, Any]]:
    """LangGraph State verisini Supabase'den geri yükler."""
    client = get_supabase()
    if not client: return None
    try:
        res = client.table("crypto_agent_states").select("state_data").eq("session_id", session_id).execute()
        if res.data and len(res.data) > 0:
            return res.data[0]["state_data"]
        return None
    except Exception as e:
        print(f"❌ [DB State Yükleme Hatası]: {e}")
        return None

if __name__ == "__main__":
    print("🚀 Multi-Tenant db.py Modülü Test Ediliyor...")
    client = get_supabase()
    if client:
        print("✅ Supabase istemcisi başarıyla bağlandı!")
        # Mevcut kullanıcıyı otomatik tenant olarak kaydet
        register_user_tenant(
            tenant_name="Ana Kullanıcı (S)",
            telegram_chat_id=8739367825,
            exchange_api_key=os.environ.get("EXCHANGE_API_KEY", ""),
            exchange_secret_key=os.environ.get("EXCHANGE_SECRET_KEY", "")
        )
