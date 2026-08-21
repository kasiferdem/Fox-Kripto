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

def translate_to_turkish(text: str) -> str:
    """İngilizce metni anında profesyonel Türkçeye çevirir."""
    try:
        import urllib.parse
        clean_text = text.strip()
        url = "https://translate.googleapis.com/translate_a/single?client=gtx&sl=en&tl=tr&dt=t&q=" + urllib.parse.quote(clean_text)
        r = requests.get(url, timeout=3, headers={"User-Agent": "Mozilla/5.0"})
        if r.status_code == 200:
            res_json = r.json()
            translated = "".join([part[0] for part in res_json[0] if part and part[0]])
            if translated and len(translated.strip()) > 3:
                return translated.strip()
    except Exception:
        pass
    return text

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
        formatted_items = []
        for item in selected:
            # "📰 [Kaynak]: Başlık" formatını ayrıştır
            source_tag = "📰 Haber:"
            content_part = item
            if ": " in item:
                parts = item.split(": ", 1)
                source_tag = parts[0]
                content_part = parts[1]
            
            tr_title = translate_to_turkish(content_part)
            formatted_items.append(f"• {source_tag}: {tr_title}")
            
        return "\n\n".join(formatted_items)
    else:
        # İngilizce formatlama
        return "\n\n".join([f"• {h}" for h in selected])

if __name__ == "__main__":
    news = fetch_live_global_crypto_news()
    print(f"✅ Toplam {len(news)} küresel canlı haber başlığı çekildi:")
    for n in news:
        print(n)
