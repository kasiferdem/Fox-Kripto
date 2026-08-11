import os, sys
if hasattr(sys.stdout, 'reconfigure'): sys.stdout.reconfigure(encoding='utf-8')
from db import register_user_tenant

print("=========================================================")
print(" 🦊 FOX-KRİPTO MULTI-TENANT KULLANICI EKLEME ARACI")
print("=========================================================\n")

name = input("1. Kullanıcı Adı (Örn: Mehmet): ").strip()
chat_id = input("2. Telegram Chat ID (Örn: 987654321): ").strip()
api_key = input("3. Binance API Key: ").strip()
secret_key = input("4. Binance Secret Key: ").strip()
budget_pct = input("5. İşlem Başı Maks Bütçe % (Varsayılan 10): ").strip() or "10"

if not (name and chat_id and api_key and secret_key):
    print("❌ HATA: Tüm alanları doldurmanız gerekmektedir!")
    sys.exit(1)

res = register_user_tenant(
    tenant_name=name,
    telegram_chat_id=int(chat_id),
    exchange_api_key=api_key,
    exchange_secret_key=secret_key,
    max_budget_percent=float(budget_pct)
)

if res:
    print(f"\n🎉 BAŞARILI! Kullanıcı '{name}' sisteme eklendi.")
    print(f"   ID: {res.get('id')}")
    print(f"   Telegram Chat ID: {res.get('telegram_chat_id')}")
else:
    print("\n❌ Kayıt oluşturulamadı. Lütfen bilgileri kontrol edin.")
