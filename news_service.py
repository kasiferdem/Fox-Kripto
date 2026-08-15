import requests
import xml.etree.ElementTree as ET
from typing import List

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

if __name__ == "__main__":
    news = fetch_live_global_crypto_news()
    print(f"✅ Toplam {len(news)} küresel canlı haber başlığı çekildi:")
    for n in news:
        print(n)
