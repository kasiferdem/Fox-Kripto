# 🦊 Fox-Kripto: Otonom Kripto Analiz, Takip ve İnsan-Onaylı Alım-Satım Sistemi

Fox-Kripto, 7/24 canlı piyasa verilerini (Binance REST & WebSocket API) takip eden, teknik indikatörler ve yapay zeka analiz ajanları (Claude Sonnet 4.5 & GPT-4o) ile alım-satım fırsatları üreten, bütçe/risk kurallarını denetleyen ve **sizin onayınız olmadan asla işlem yapmayan** yeni nesil kripto ticaret sistemidir.

## 🏛️ Mimari Mimarisi
1. **Piyasa Tarayıcısı (Market Scanner):** Binance canlı fiyat, hacim ve teknik indikatör (RSI, MACD, Bollinger) takibi.
2. **AI Strateji Ajanı (Claude 4.5 / GPT-4o):** Alım-Satım sinyalleri, Giriş Fiyatı, Kar Al (TP) ve Zarar Durdur (SL) seviyelerini üretir.
3. **Risk & Bütçe Denetmeni (Risk Auditor):** Kullanıcının belirlediği işlem başı maks bütçe ve günlük limitleri denetler.
4. **İnsan-Onay Mekanizması (HITL):** Sinyali görsel İşlem Kartı ile onayınıza sunar. Siz ONAYLA demeden borsaya emir gitmez.
5. **Otomatik İnfaz Motoru (Exchange API):** Onaylanan işlemleri borsa API'si üzerinden saniyeler içinde iletir ve OCO emirlerini kurar.

## 🚀 Başlangıç
```bash
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
python bot.py
```
