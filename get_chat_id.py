import os, sys, requests, time
if hasattr(sys.stdout, 'reconfigure'): sys.stdout.reconfigure(encoding='utf-8')

TOKEN = "8938326996:AAFLmy3S4uAb_GbF8TotsdL0CgWq4jGCFik"
url = f"https://api.telegram.org/bot{TOKEN}/getUpdates"

print("🔍 Telegram @FoxKriptoBot Dinleniyor...")
print("📱 Lütfen Telegram'da @FoxKriptoBot hesabına girip /start butonuna veya herhangi bir mesaja basın!\n")

offset = None
found = False

for i in range(15):
    try:
        params = {"timeout": 2, "offset": offset}
        res = requests.get(url, params=params, timeout=5)
        if res.status_code == 200:
            data = res.json()
            results = data.get("result", [])
            for update in results:
                offset = update["update_id"] + 1
                msg = update.get("message") or update.get("edited_message")
                if msg:
                    chat = msg.get("chat", {})
                    chat_id = chat.get("id")
                    first_name = chat.get("first_name", "Kullanıcı")
                    print(f"🎉 HARİKA! Chat ID Tespit Edildi:")
                    print(f"   👤 Kullanıcı: {first_name}")
                    print(f"   🆔 TELEGRAM_CHAT_ID = {chat_id}\n")
                    
                    # .env dosyasını otomatik güncelle
                    env_path = ".env"
                    if os.path.exists(env_path):
                        with open(env_path, "r", encoding="utf-8") as f:
                            content = f.read()
                        new_content = content.replace("TELEGRAM_CHAT_ID=", f"TELEGRAM_CHAT_ID={chat_id}")
                        with open(env_path, "w", encoding="utf-8") as f:
                            f.write(new_content)
                        print("✅ TELEGRAM_CHAT_ID otomatik olarak .env dosyanıza yazıldı!")
                    found = True
                    break
            if found:
                break
    except Exception as e:
        pass
    time.sleep(1)

if not found:
    print("⏳ Zaman aşımı. Lütfen Telegram'da @FoxKriptoBot botunuza /start mesajı atıp tekrar çalıştırın.")
