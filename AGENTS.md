# AGENTS.md - Fox-Kripto Yapay Zeka Ajan Kuralları ve Hafıza Sistemi

Bu dosya Antigravity ve diğer AI kodlama asistanları için workspace talimatlarını içerir.

## 🧠 Oturum Hafızası Talimatı
Her yeni sohbet oturumu başladığında:
1. `STATUS.md` dosyasını mutlaka oku.
2. Kullanıcı "nerede kaldık?", "durum nedir?", "devam edelim" dediğinde `STATUS.md` dosyasındaki son tamamlanan adımları ve yapılacaklar listesini kullanıcıya özetle.
3. Projede yapılan her yeni değişiklikten sonra `STATUS.md` dosyasındaki Yapılacaklar ve Tamamlananlar listesini güncelle.

## 📂 Proje Bileşenleri
- **`app.py`**: FastAPI Web Arayüzü & 7/24 Arka Plan Döngüsü
- **`graph.py`**: LangGraph Akışı & State Machine
- **`prompts.py`**: GPT-4o / Claude 4.5 Analiz Promptları
- **`telegram_poller.py`**: Telegram Bot Dinleyici & Onay Mekanizması
- **`exchange.py`**: CCXT Binance Borsa Modülü
- **`db.py`**: Supabase Veritabanı ve Loglama

## 🛑 KESİN ÇALIŞTIRMA VE DAĞITIM KURALI (P0 - ASLA İHLAL EDİLEMEZ)
- **ASLA YEREL BİLGİSAYARDA `python app.py` VEYA `telegram_poller.py` ÇALIŞTIRILMAYACAKTIR.**
- Kullanıcı açıkça talimat vermedikçe yerel terminalde hiçbir bot, daemon veya poller süreci başlatılamaz.
- Sistemin tamamı 7/24 kesintisiz olarak **DigitalOcean Bulut Sunucusunda** (`https://fox-kripto-m7n46.ondigitalocean.app`) çalışır.
- Yapılan tüm geliştirmeler, hata düzeltmeleri ve parametreler `git push origin main` ile doğrudan DigitalOcean'a sevk edilir.
