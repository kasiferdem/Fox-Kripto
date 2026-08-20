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

## 🚀 Hızlı Başlatma
Proje başlatılırken `python app.py` komutu kullanılır.
