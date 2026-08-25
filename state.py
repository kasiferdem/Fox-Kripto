from typing import TypedDict, Optional, Dict, Any, List

class CryptoAgentState(TypedDict):
    """
    LangGraph Multi-Tenant İş Akışında (State Graph) Gezen Veri Yapısı (v2.1 Flowchart).
    """
    tenant_id: Optional[str]                       # Kullanıcı / Kiracı UUID
    tenant_config: Optional[Dict[str, Any]]       # Kullanıcının Binance API ve Telegram ayarları
    news_data: str                                # Toplanan anlık haber metinleri ve makro veriler
    portfolio_state: Dict[str, Any]               # Tenant'a ait güncel cüzdan bakiyesi
    sentiment_score: float                        # Gemini 3.7 Flash duyarlılık skoru (-10 ile +10)
    filtered_candidates: Optional[List[Dict[str, Any]]] # Deterministik ön filtreden geçen coinler
    glm_technical: Optional[Dict[str, Any]]       # GLM-5.2 Teknik analiz ve giriş seviyeleri
    ox_shadow: Optional[Dict[str, Any]]           # OX Alpha Gölge (Shadow) Piyasa Yapıcı analizi
    eval_record: Optional[Dict[str, Any]]         # GLM vs OX Alpha karşılaştırma ve benchmark kaydı
    trade_proposal: Optional[Dict[str, Any]]      # Tenant'a özel işlem teklifi
    policy_check_passed: bool                     # Deterministik RiskPolicyEngine kontrol sonucu
    human_approval: str                           # "Pending", "Approved", "Rejected"
    execution_result: Optional[Dict[str, Any]]   # İnfaz sonucu ve Supabase log özeti
