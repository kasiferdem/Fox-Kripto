from typing import TypedDict, Optional, Dict, Any

class CryptoAgentState(TypedDict):
    """
    LangGraph Multi-Tenant İş Akışında (State Graph) Gezen Veri Yapısı.
    """
    tenant_id: Optional[str]                       # Kullanıcı / Kiracı UUID
    tenant_config: Optional[Dict[str, Any]]       # Kullanıcının Binance API ve Telegram ayarları
    news_data: str                                # Toplanan anlık haber metinleri ve makro veriler
    portfolio_state: Dict[str, Any]               # Tenant'a ait güncel cüzdan bakiyesi
    sentiment_score: float                        # Haber analiz ajanı duyarlılık skoru (-10 ile +10)
    trade_proposal: Optional[Dict[str, Any]]      # Tenant'a özel işlem teklifi
    human_approval: str                           # "Pending", "Approved", "Rejected"
    execution_result: Optional[Dict[str, Any]]   # İnfaz sonucu ve Supabase log özeti
