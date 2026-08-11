from typing import TypedDict, Optional, Dict, Any

class CryptoAgentState(TypedDict):
    """
    LangGraph İş Akışında (State Graph) Gezen Ana Veri Yapısı.
    """
    news_data: str                                # Toplanan anlık haber metinleri ve makro veriler
    portfolio_state: Dict[str, Any]               # CCXT'den çekilen güncel cüzdan bakiyesi (USDT ve Coin miktarları)
    sentiment_score: float                        # Haber analiz ajanı tarafından belirlenen -10 ile +10 arası skor
    trade_proposal: Optional[Dict[str, Any]]      # Strateji ajanı tarafından oluşturulan işlem teklifi (Coin, Miktar, Fiyat, Stop-Loss %)
    human_approval: str                           # Kullanıcı onayı durumu ("Pending", "Approved", "Rejected")
    execution_result: Optional[Dict[str, Any]]   # İşlem infaz sonucu ve Supabase log özeti
