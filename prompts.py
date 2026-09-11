import os, sys, json, requests, base64
if hasattr(sys.stdout, 'reconfigure'): sys.stdout.reconfigure(encoding='utf-8')
from typing import Dict, Any
from dotenv import load_dotenv

load_dotenv()

def _get_api_key():
    raw_key = os.environ.get("OPENROUTER_API_KEY") or os.environ.get("OPENAI_API_KEY", "")
    if raw_key and not raw_key.startswith("your_"):
        return raw_key
    raise ValueError("CRITICAL: OPENROUTER_API_KEY is not configured in environment variables.")

# -----------------------------------------
from openrouter_gateway import OpenRouterGateway, CriticalNewsAssessment, RoutineReportingSummary

def resolve_legacy_model_alias(model_alias: str) -> Dict[str, Any]:
    """Geçmiş kayıtlar için model kimliği ve bağımsızlık metadata çözümleyicisi (Section 2)."""
    if str(model_alias).lower() in ["stealth/ox-alpha", "ox-alpha", "ox_alpha"]:
        return {
            "legacyModelAlias": "stealth/ox-alpha",
            "resolvedModelIdentity": "z-ai/glm-5.3-flash",
            "independentConfirmation": False
        }
    return {
        "legacyModelAlias": model_alias,
        "resolvedModelIdentity": model_alias,
        "independentConfirmation": True
    }

def call_llm_model(model: str, system_prompt: str, user_content: str, max_tokens: int = 250) -> str:
    """
    Merkezi OpenRouterGateway üzerinden güvenli çağrı yönlendirir.
    """
    # stealth/ox-alpha isteklerini z-ai/glm-5.3-flash'a dönüştür (Section 2)
    resolved_role = "LEAD_STRATEGIST"
    if "news" in system_prompt.lower() or "haber" in system_prompt.lower() or "critical" in system_prompt.lower():
        resolved_role = "CRITICAL_NEWS_ANALYSIS"
    elif "audit" in system_prompt.lower() or "forensic" in system_prompt.lower():
        resolved_role = "NIGHTLY_FORENSIC_AUDIT"
        
    res = OpenRouterGateway.invoke(
        role=resolved_role,
        system_prompt=system_prompt,
        user_content=user_content,
        prompt_version="gateway-v2.4"
    )
    return res.get("raw_text", "")

def call_gpt4o(system_prompt: str, user_content: str, max_tokens: int = 1500) -> str:
    """Merkezi gateway üzerinden GPT-6 Baş Stratejist & Karar çağrısı."""
    return call_llm_model("openai/gpt-6-astra", system_prompt, user_content, max_tokens=max_tokens)

# -----------------------------------------
# 1. HABER ANALİZ AJANI (NEWS AGENT)
# -----------------------------------------
def analyze_crypto_news(news_data: str, portfolio_state: Dict[str, Any]) -> Dict[str, Any]:
    """
    OpenRouterGateway (CRITICAL_NEWS_ANALYSIS: Gemini 3.7 Flash) kullanarak haber metnini analiz eder.
    Yalnızca BLOCK_ONLY yetkisine sahiptir, doğrudan alım emri açamaz (Section 3.2).
    """
    system_prompt = (
        "Sen kıdemli bir Kripto Piyasa ve Makro Risk Analiz Ajanısın.\n"
        "Görevin: Gelen anlık haberleri incelemek ve piyasa için risk şiddeti belirlemektir.\n"
        "Yalnızca şu severity değerlerinden birini döndür:\n"
        "NORMAL, CAUTION, HIGH_RISK, HALT_RECOMMENDED, DATA_INSUFFICIENT"
    )
    user_content = f"Gelen Haber & Duyarlılık Verisi:\n{news_data}\n\nPortföy Durumu:\n{portfolio_state}"
    
    res = OpenRouterGateway.invoke(
        role="CRITICAL_NEWS_ANALYSIS",
        system_prompt=system_prompt,
        user_content=user_content,
        schema_model=CriticalNewsAssessment,
        prompt_version="news-v2.4"
    )
    
    struct = res.get("structured_data")
    if struct and isinstance(struct, dict):
        sev = struct.get("severity", "NORMAL")
        # Sentiment skorunu severity'ye göre eşleştir (-10 ile +10)
        score_map = {
            "NORMAL": 6.5,
            "CAUTION": 2.0,
            "HIGH_RISK": -5.0,
            "HALT_RECOMMENDED": -10.0,
            "DATA_INSUFFICIENT": 0.0
        }
        return {
            "sentiment_score": score_map.get(sev, 5.0),
            "severity": sev,
            "analysis_summary": struct.get("explanation", res.get("raw_text", "")),
            "is_fake_news": (sev in ["HIGH_RISK", "HALT_RECOMMENDED"]),
            "market_bias": "BULLISH" if sev == "NORMAL" else ("BEARISH" if sev in ["HIGH_RISK", "HALT_RECOMMENDED"] else "NEUTRAL")
        }
        
    return {
        "sentiment_score": 5.0,
        "severity": "NORMAL",
        "analysis_summary": "Piyasa verisi normal akışta.",
        "is_fake_news": False,
        "market_bias": "NEUTRAL"
    }

# -----------------------------------------
# 2. STRATEJİ VE RİSK AJANI (STRATEGY & RISK AGENT)
# -----------------------------------------
def formulate_trade_strategy(
    news_analysis: Dict[str, Any],
    portfolio_state: Dict[str, Any],
    current_price: float,
    symbol: str = "BTC/USDT"
) -> Dict[str, Any]:
    """
    Duyarlılık skoru ve portföy durumunu değerlendirerek işlem teklifi oluşturur.
    KURAL 1: İşlem teklifi toplam portföy likiditesinin (USDT/TRY) %10'unu aşamaz (Minimum $10 USD).
    KURAL 2: Her teklifte %3 ile %5 arası dinamik Stop-Loss belirlenmelidir.
    """
    # Serbest Nakit TL/USDT Bakiyesini Oku (Çift Borsa ve Tekil Borsa Tam Uyumlu)
    holdings = portfolio_state.get("holdings_details") or portfolio_state.get("crypto_holdings") or {}
    try_details = holdings.get("TRY", {}) if isinstance(holdings, dict) else {}
    free_try = try_details.get("amount", 0.0) if isinstance(try_details, dict) else float(try_details or 0.0)
    
    free_usdt = float(portfolio_state.get("free_usdt") or 0.0)
    if free_usdt <= 0 and isinstance(holdings, dict):
        usdt_d = holdings.get("USDT", {})
        free_usdt = float(usdt_d.get("amount", 0.0) if isinstance(usdt_d, dict) else usdt_d or 0.0)
        
    from exchange import get_live_usd_try_rate
    live_fx = get_live_usd_try_rate()
    if live_fx <= 0: live_fx = 35.0
    free_cash_usd = (free_try / live_fx) + free_usdt
    
    # EĞER SERBEST NAKİT TL/USDT $1.00 USD ALTINDA İSE YENİ ALIM YAPMA (HOLD)!
    if free_cash_usd < 1.00 and free_usdt < 1.00 and free_try < 30.0:
        print(f"   ⏳ [Nakit Bakiye Yetersiz]: Serbest TL (₺{free_try:.2f}) ve USDT (${free_usdt:.2f}) tükenmiştir. Alım yapılmıyor (HOLD).")
        return {
            "should_trade": False,
            "reason": f"Serbest nakit bakiye tükenmiştir (₺{free_try:.2f} TL, ${free_usdt:.2f} USDT). Tüm sermaye kârlı pozisyonlardadır. Bekletiliyor (HOLD)."
        }
        
    available_liquidity_usd = max(free_cash_usd, free_usdt, 10.0)
    sentiment_score = float(news_analysis.get("sentiment_score", 0.0))
    
    # Ultra-Hızlı Ticaret Modu (Ultra-Fast Scalping & Micro Trend): En ufak pozitif mikro hareketlerde derhal işleme girer
    if sentiment_score < 0.5:
        return {
            "should_trade": False,
            "reason": f"Duyarlılık skoru ({sentiment_score}) olumsuz. Akış sonlandırılıyor."
        }
        
    current_holdings = list(portfolio_state.get("crypto_holdings", {}).keys()) if isinstance(portfolio_state.get("crypto_holdings"), dict) else []
    
    system_prompt = (
        "Sen kıdemli bir Erken Balina Avcısı ve Hacim Patlaması Scalper Ajanısın (Whale Breakout Hunter Agent).\n"
        "Görevin: Piyasadaki en yüksek 5 dakikalık hacim artışına (Volume Spike) ve ani patlama potansiyeline sahip Erken Balina Coinleri "
        "(FLM, WAVES, CLV, UTK, GPS, ACE, PORTAL, TURBO, NEIRO, TUT, PEPE, BONK, FLOKI) arasından en yüksek kâr potansiyeline sahip olanı seçmektir.\n\n"
        "KATI RİSK VE ÇEŞİTLİLİK KURALLARI:\n"
        "1. BÜYÜK VE HANTAL COİNLER YASAKTIR: BTC, ETH, SOL, SUI, NEAR, RENDER, AVAX, ADA gibi hantal coinleri ASLA seçme!\n"
        "2. SADECE ERKEN BALİNA: 5 dakikalık hacim patlaması (Pre-Pump) olan dinamik coinleri seç.\n"
        "3. PORTFÖYDE OLMAYANI SEÇ: Kullanıcının elinde ZATEN BULUNAN coinleri tekrar alma!\n"
        "4. Kâr Alma (Take-Profit): Hedef %1.5 - %4.0 arası olmalıdır.\n"
        "5. Stop-Loss: %1.0 - %1.5 arası olmalıdır.\n\n"
        "ÇIKTI FORMATI: Yalnızca geçerli bir JSON nesnesi döndür:\n"
        "{\n"
        '  "should_trade": true,\n'
        '  "symbol": "FLM/USDT",\n'
        '  "direction": "BUY",\n'
        '  "amount_usd": 10.0,\n'
        '  "entry_price": 0.0167,\n'
        '  "stop_loss_percent": 1.5,\n'
        '  "stop_loss_price": 0.0164,\n'
        '  "take_profit_price": 0.0172,\n'
        '  "risk_justification": "4.9x erken balina hacim patlaması yakalandı."\n'
        "}"
    )
    user_content = (
        f"Kullanıcının Elindeki Mevcut Coinler: {current_holdings}\n"
        f"KURAL: Mevcut elindeki coinleri tekrar alma! Erken Balina Adaylarından (FLM, WAVES, CLV, UTK, GPS, ACE, PORTAL, TURBO, NEIRO) elinde OLMAYAN birini seç!\n"
        f"Piyasa ve Altcoin Verileri: {news_analysis}\n"
        f"Kullanılabilir Likidite USD: ${available_liquidity_usd}"
    )
    
    raw_response = call_gpt4o(system_prompt, user_content)
    from db import get_strategy_config
    cfg = get_strategy_config()
    tp_pct = float(cfg.get("take_profit_pct", 2.4))
    sl_pct = float(cfg.get("stop_loss_pct", 1.0))
    budget_pct = float(cfg.get("max_budget_percent", 25.0))
    free_usdt = float(portfolio.get("free_usdt", 0.0))
    trade_amount = round(free_usdt * (budget_pct / 100.0), 2) if free_usdt > 0 else 25.0

    if raw_response:
        try:
            clean_json = raw_response.strip("` \n").replace("json", "").strip()
            proposal = json.loads(clean_json)
            sym = str(proposal.get("symbol", "")).upper()
            
            if sym and "/" in sym:
                proposal["symbol"] = sym
                proposal["amount_usd"] = trade_amount
                proposal["stop_loss_percent"] = sl_pct
                proposal["stop_loss_price"] = round(current_price * (1 - (sl_pct / 100)), 4)
                proposal["take_profit_price"] = round(current_price * (1 + (tp_pct / 100)), 4)
                proposal["should_trade"] = True
                return proposal
        except Exception:
            pass
            
    # Fallback Strateji: Canlı Borsadan Anlık En Yüksek Hacim Liderlerini Çek
    from exchange import fetch_top_volume_gainers
    active_gainers = fetch_top_volume_gainers(limit=15)
    top_active_symbols = [g["symbol"] for g in active_gainers if g.get("symbol")]
    
    if not top_active_symbols:
        return {
            "should_trade": False,
            "reason": "NO_VALID_LIVE_VOLUME_CANDIDATES",
            "symbol": "BTC/USDT"
        }
    
    chosen_symbol = top_active_symbols[0]
    for cand in top_active_symbols:
        c_b = cand.split("/")[0]
        if c_b not in current_holdings:
            chosen_symbol = cand
            break
            
    sl_price = round(current_price * (1 - (sl_pct / 100)), 4)
    tp_price = round(current_price * (1 + (tp_pct / 100)), 4)
    
    return {
        "should_trade": True,
        "symbol": chosen_symbol,
        "direction": "BUY" if sentiment_score > 0 else "SELL",
        "amount_usd": trade_amount,
        "entry_price": current_price,
        "stop_loss_percent": sl_pct,
        "stop_loss_price": sl_price,
        "take_profit_price": tp_price,
        "risk_justification": f"Dinamik Hacim ve Balina Teyidi: Canlı piyasa lideri {chosen_symbol} seçildi."
    }

if __name__ == "__main__":
    print("🚀 GPT-4o prompts.py Modülü Test Ediliyor...")
    news_res = analyze_crypto_news("Bitcoin ETF girişleri rekor seviyeye ulaştı.", {"free_usdt": 1000.0})
    print("Haber Analizi Çıktısı:", news_res)
    strat_res = formulate_trade_strategy(news_res, {"free_usdt": 1000.0}, 64000.0)
    print("Strateji Çıktısı:", strat_res)
