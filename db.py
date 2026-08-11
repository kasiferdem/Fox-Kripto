import os, sys
if hasattr(sys.stdout, 'reconfigure'): sys.stdout.reconfigure(encoding='utf-8')
from typing import Dict, Any, Optional
from dotenv import load_dotenv
from supabase import create_client, Client

load_dotenv()

SUPABASE_URL = os.environ.get("SUPABASE_URL", "https://eodhhrokdmlltslqzerh.supabase.co")
SUPABASE_KEY = os.environ.get("SUPABASE_SERVICE_ROLE_KEY", "")

_supabase_client: Optional[Client] = None

def get_supabase() -> Optional[Client]:
    """Supabase istemcisini güvenli bir şekilde ilklendirir ve döndürür."""
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

def log_trade_decision(trade_data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """
    Ajan kararlarını, bütçeyi, Stop-Loss seviyesini ve infaz sonuçlarını Supabase'e loglar.
    """
    client = get_supabase()
    if not client:
        print("   [DB]: Supabase istemcisi aktif değil, loglama atlandı.")
        return None
    try:
        payload = {
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
        res = client.table("crypto_trade_logs").insert(payload).execute()
        print(f"✅ [DB]: İşlem kararı Supabase'e başarıyla loglandı. ID: {res.data[0]['id'] if res.data else 'OK'}")
        return res.data[0] if res.data else None
    except Exception as e:
        print(f"❌ [DB Loglama Hatası]: {e}")
        return None

def save_graph_state(session_id: str, state_data: Dict[str, Any]) -> bool:
    """LangGraph State kalıcılığını (Persistence) Supabase'e kaydeder."""
    client = get_supabase()
    if not client: return False
    try:
        payload = {
            "session_id": session_id,
            "state_data": state_data
        }
        client.table("crypto_agent_states").upsert(payload).execute()
        print(f"✅ [DB State]: LangGraph State '{session_id}' başarıyla saklandı.")
        return True
    except Exception as e:
        print(f"❌ [DB State Kayıt Hatası]: {e}")
        return False

def load_graph_state(session_id: str) -> Optional[Dict[str, Any]]:
    """LangGraph State verisini Supabase'den geri yükler."""
    client = get_supabase()
    if not client: return None
    try:
        res = client.table("crypto_agent_states").select("state_data").eq("session_id", session_id).execute()
        if res.data and len(res.data) > 0:
            print(f"✅ [DB State]: LangGraph State '{session_id}' geri yüklendi.")
            return res.data[0]["state_data"]
        return None
    except Exception as e:
        print(f"❌ [DB State Yükleme Hatası]: {e}")
        return None

if __name__ == "__main__":
    print("🚀 Supabase db.py Modülü Test Ediliyor...")
    client = get_supabase()
    if client:
        print("✅ Supabase istemcisi başarıyla bağlandı!")
    else:
        print("⚠️ Supabase anahtarları bekleniyor...")
