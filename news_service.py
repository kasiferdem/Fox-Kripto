import os
import requests
import xml.etree.ElementTree as ET
from typing import List
from dotenv import load_dotenv

load_dotenv()

def fetch_live_global_crypto_news(limit_per_source: int = 4) -> List[str]:
    """
    Dünyanın en büyük küresel kripto otorite ve haber kaynaklarından (CoinDesk, CoinTelegraph, Decrypt)
    anlık sıcak son dakika haber başlıklarını çeker.
    """
    headlines = []
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}

    # 1. CoinTelegraph RSS Akışı
    try:
        r = requests.get("https://cointelegraph.com/rss", timeout=4, headers=headers)
        if r.status_code == 200:
            root = ET.fromstring(r.content)
            for item in root.findall(".//item")[:limit_per_source]:
                title = item.find("title")
                if title is not None and title.text:
                    headlines.append(f"📰 [CoinTelegraph]: {title.text.strip()}")
    except Exception as e:
        print(f"⚠️ CoinTelegraph RSS Uyarısı: {e}")

    # 2. CoinDesk RSS Akışı
    try:
        r = requests.get("https://www.coindesk.com/arc/outboundfeeds/rss/", timeout=4, headers=headers)
        if r.status_code == 200:
            root = ET.fromstring(r.content)
            for item in root.findall(".//item")[:limit_per_source]:
                title = item.find("title")
                if title is not None and title.text:
                    headlines.append(f"📰 [CoinDesk]: {title.text.strip()}")
    except Exception as e:
        print(f"⚠️ CoinDesk RSS Uyarısı: {e}")

    # 3. Decrypt RSS Akışı
    try:
        r = requests.get("https://decrypt.co/feed", timeout=4, headers=headers)
        if r.status_code == 200:
            root = ET.fromstring(r.content)
            for item in root.findall(".//item")[:limit_per_source]:
                title = item.find("title")
                if title is not None and title.text:
                    headlines.append(f"📰 [Decrypt]: {title.text.strip()}")
    except Exception as e:
        pass

    return headlines

def get_localized_crypto_news(lang: str = "tr", limit: int = 6) -> str:
    """
    Kullanıcının tercih ettiği dilde (TR / EN) güncel küresel haberleri çeker ve formatlar.
    """
    raw_news = fetch_live_global_crypto_news(limit_per_source=2)
    if not raw_news:
        if lang == "en":
            return "ℹ️ No breaking market movements at this moment, market is calm."
        return "ℹ️ Şu anda küresel haber akışında olağandışı bir son dakika gelişmesi bulunmuyor, piyasa sakin seyrediyor."

    selected = raw_news[:limit]
    
    if lang == "tr":
        try:
            from prompts import call_gpt4o
            system_prompt = (
                "Sen kıdemli bir finans ve kripto para tercümanısın. "
                "Sana verilen İngilizce kripto haber başlıklarını akıcı, anlaşılır ve profesyonel Türkçeye çevireceksin. "
                "Haber kaynağı etiketlerini (örneğin [CoinTelegraph], [CoinDesk], [Decrypt]) koru. "
                "Her bir haberi '• 📰 [Kaynak]: Türkçe Başlık' formatında alt alta yaz. Başka hiçbir açıklama ekleme."
            )
            user_content = "Aşağıdaki haber başlıklarını Türkçeye çevir:\n\n" + "\n".join(selected)
            translated_text = call_gpt4o(system_prompt, user_content)
            if translated_text and len(translated_text.strip()) > 10:
                return translated_text.strip()
        except Exception as te:
            pass
            
        # Fallback Türkçe formatlama
        return "\n\n".join([f"• {h}" for h in selected])
    else:
        # İngilizce formatlama
        return "\n\n".join([f"• {h}" for h in selected])

if __name__ == "__main__":
    news = fetch_live_global_crypto_news()
    print(f"✅ Toplam {len(news)} küresel canlı haber başlığı çekildi:")
    for n in news:
        print(n)
