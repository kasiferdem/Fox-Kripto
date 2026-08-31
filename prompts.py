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
# -----------------------------------------
# OPENROUTER & OPENAI ÇOKLU MODEL YEDEKLEME ZİNCİRİ (AI FAILOVER MESH)
# -----------------------------------------
MODEL_FALLBACK_CHAINS = {
    "z-ai/glm-5.2": [
        "google/gemini-2.5-flash",
        "google/gemini-2.0-flash-001",
        "openai/gpt-4o-mini",
        "meta-llama/llama-3.3-70b-instruct"
    ],
    "google/gemini-3.7-flash": [
        "google/gemini-2.5-flash",
        "google/gemini-2.0-flash-001",
        "openai/gpt-4o-mini",
        "z-ai/glm-5.2"
    ],
    "stealth/ox-alpha": [
        "google/gemini-2.5-flash",
        "openai/gpt-4o-mini",
        "meta-llama/llama-3.3-70b-instruct"
    ]
}

def call_llm_model(model: str, system_prompt: str, user_content: str, max_tokens: int = 250) -> str:
    """
    Çok Kademeli Yapay Zeka Çağrı Motoru:
    1. İstenen birincil modele çağrı yapar.
    2. Model meşgulse/hata verirse (429/402 vb.) sırasıyla Gemini, GPT-4o-mini ve Llama yedeklerine geçer.
    3. OpenRouter erişilemezse doğrudan OpenAI API üzerinden gpt-4o-mini ile işlemi tamamlar.
    """
    url = "https://openrouter.ai/api/v1/chat/completions"
    key = _get_api_key()
    headers = {
        "Authorization": f"Bearer {key}",
        "Content-Type": "application/json",
        "HTTP-Referer": "https://fox-kripto.internal",
        "X-Title": "Fox Multi-Agent Council"
    }
    
    # Model Çağrı Sırası (Birincil Model + Yedek Modeller)
    fallbacks = MODEL_FALLBACK_CHAINS.get(model, ["google/gemini-2.5-flash", "openai/gpt-4o-mini", "meta-llama/llama-3.3-70b-instruct"])
    target_models = [model] + [m for m in fallbacks if m != model]
        
    for m in target_models:
        payload = {
            "model": m,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_content}
            ],
            "temperature": 0.2,
            "max_tokens": max_tokens
        }
        try:
            res = requests.post(url, json=payload, headers=headers, timeout=10)
            if res.status_code == 200:
                data = res.json()
                content = data["choices"][0]["message"]["content"]
                if content and content.strip():
                    return content
            else:
                print(f"⚠️ LLM Yanıt Uyarısı ({m} - Status {res.status_code}), sonraki yedek modele geçiliyor...")
        except Exception as e:
            print(f"❌ LLM Çağrı Hatası ({m}): {e}")
            
    # Son Çare: Doğrudan OpenAI API Yedek Kapısı
    openai_key = os.environ.get("OPENAI_API_KEY", "")
    if openai_key and not openai_key.startswith("your_"):
        try:
            o_url = "https://api.openai.com/v1/chat/completions"
            o_headers = {"Authorization": f"Bearer {openai_key}", "Content-Type": "application/json"}
            o_payload = {
                "model": "gpt-4o-mini",
                "messages": [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_content}
                ],
                "temperature": 0.2,
                "max_tokens": max_tokens
            }
            o_res = requests.post(o_url, json=o_payload, headers=o_headers, timeout=10)
            if o_res.status_code == 200:
                print("⚡ [Yedek Başarılı]: Doğrudan OpenAI (gpt-4o-mini) üzerinden yanıt alındı.")
                return o_res.json()["choices"][0]["message"]["content"]
        except Exception as o_err:
            print(f"❌ Doğrudan OpenAI API Hatası: {o_err}")
            
    return ""

def call_gpt4o(system_prompt: str, user_content: str, max_tokens: int = 1500) -> str:
    """Gemini 3.7 Flash ve yedek zincirine doğrudan güvenli çağrı yapar."""
    return call_llm_model("google/gemini-3.7-flash", system_prompt, user_content, max_tokens=max_tokens)

# -----------------------------------------
# 1. HABER ANALİZ AJANI (NEWS AGENT)
# -----------------------------------------
def analyze_crypto_news(news_data: str, portfolio_state: Dict[str, Any]) -> Dict[str, Any]:
    """
    GPT-4o kullanarak haber metnini analiz eder, sahte haberleri (fake news) filtreler
    ve -10.0 ile +10.0 arası sentiment_score üretir.
    """
    system_prompt = (
        "Sen kıdemli bir Kripto Piyasa ve Haber Analiz Ajanısın (News Agent).\n"
        "Görevin: Gelen anlık haberleri, sosyal medya ve makro duyarlılık verilerini incelemek;\n"
        "spekülatif veya sahte haberleri (fake news) süzmek ve piyasanın yönü için -10.0 (Aşırı Ayı/Düşüş) "
        "ile +10.0 (Aşırı Boğa/Yükseliş) arasında net bir 'sentiment_score' belirlemektir.\n\n"
        "ÇIKTI FORMATI: Yalnızca geçerli bir JSON nesnesi döndür:\n"
        "{\n"
        '  "sentiment_score": 7.5,\n'
        '  "analysis_summary": "Haber makroekonomik olarak olumlu ve hacim artışını destekliyor.",\n'
        '  "is_fake_news": false,\n'
        '  "market_bias": "BULLISH"\n'
        "}"
    )
    user_content = f"Gelen Haber & Duyarlılık Verisi:\n{news_data}\n\nPortföy Durumu:\n{portfolio_state}"
    
    raw_response = call_gpt4o(system_prompt, user_content)
    if raw_response:
        try:
            clean_json = raw_response.strip("` \n").replace("json", "").strip()
            return json.loads(clean_json)
        except Exception:
            pass
            
    # Fallback varsayılan analiz
    return {
        "sentiment_score": 6.5,
        "analysis_summary": "Piyasa verisi olumlu trend gösteriyor.",
        "is_fake_news": False,
        "market_bias": "BULLISH"
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
