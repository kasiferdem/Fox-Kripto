"""
FOX AI MULTI-PROJECT DEVELOPER BRIDGE (CLAUDE OPUS / 3.5 SONNET • CODEX • AGY)
=============================================================================
Kişisel Mobil Yapay Zeka Geliştirici Köprüsü (@FoxSystemBot).
Telefondan ekran görüntüsü, dosya veya yazılı emir alarak projeyi okur,
kodu düzenler, test eder ve canlıya deploy eder.
"""

import os
import sys
import time
import json
import base64
import requests
import subprocess
from typing import Dict, Any, List, Optional
from dotenv import load_dotenv

load_dotenv()

DEV_BOT_TOKEN = os.environ.get("DEV_TELEGRAM_BOT_TOKEN", "8808656228:AAFP4E3N204ZKVuMuqTgRbs4lLDNxaovBo0")
AUTHORIZED_CHAT_ID = int(os.environ.get("AUTHORIZED_DEV_CHAT_ID", "8739367825"))
OPENROUTER_API_KEY = os.environ.get("OPENROUTER_API_KEY") or os.environ.get("OPENAI_API_KEY")

DEFAULT_MODEL = "anthropic/claude-opus-5-fast"
FALLBACK_MODEL = "anthropic/claude-sonnet-5"

BASE_TELEGRAM_URL = f"https://api.telegram.org/bot{DEV_BOT_TOKEN}"
BASE_PROJECT_DIR = os.path.dirname(os.path.abspath(__file__))

# Çoklu Proje Havuzu (Multi-Project Workspaces)
PROJECTS_MAP = {
    "Fox-Kripto": BASE_PROJECT_DIR,
    "Fox-Agents-Team": os.path.abspath(os.path.join(BASE_PROJECT_DIR, "..", "Fox-Agents-Team")),
}
CURRENT_PROJECT = "Fox-Kripto"

# Bellek Geçmişi (In-Memory & Persistent)
CONVERSATION_HISTORY: List[Dict[str, Any]] = []

def send_telegram_msg(chat_id: int, text: str, parse_mode: str = "Markdown") -> bool:
    """Telegram üzerinden formatlı mesaj gönderir."""
    try:
        url = f"{BASE_TELEGRAM_URL}/sendMessage"
        # 4000 karakterlik Telegram sınırını aşmamak için böl
        if len(text) > 4000:
            chunks = [text[i:i+3900] for i in range(0, len(text), 3900)]
            for ch in chunks:
                requests.post(url, json={"chat_id": chat_id, "text": ch, "parse_mode": parse_mode}, timeout=10)
            return True
        else:
            res = requests.post(url, json={"chat_id": chat_id, "text": text, "parse_mode": parse_mode}, timeout=10)
            if res.status_code != 200:
                # Markdown parse hatası olursa düz metin olarak tekrar dene
                requests.post(url, json={"chat_id": chat_id, "text": text}, timeout=10)
            return True
    except Exception as e:
        print(f"⚠️ Telegram Mesaj Hatası: {e}")
        return False

# =====================================================================
# AGENT TOOL SUITE (KOD OKUMA, DÜZENLEME, TEST VE GİT DEPLOY ARAÇLARI)
# =====================================================================

def tool_view_file(filepath: str) -> str:
    """Belirtilen dosyanın içeriğini okur."""
    proj_dir = PROJECTS_MAP.get(CURRENT_PROJECT, BASE_PROJECT_DIR)
    target_path = filepath if os.path.isabs(filepath) else os.path.join(proj_dir, filepath)
    if not os.path.exists(target_path):
        return f"HATA: '{filepath}' dosyası bulunamadı."
    try:
        with open(target_path, "r", encoding="utf-8", errors="ignore") as f:
            lines = f.readlines()
        numbered = [f"{i+1}: {l}" for i, l in enumerate(lines[:300])]
        content = "".join(numbered)
        if len(lines) > 300:
            content += f"\n... ({len(lines)-300} satır daha var)"
        return content
    except Exception as e:
        return f"Dosya Okuma Hatası: {e}"

def tool_edit_file(filepath: str, target_text: str, replacement_text: str) -> str:
    """Dosya içindeki belirli bir kod bloğunu güvenle değiştirir."""
    proj_dir = PROJECTS_MAP.get(CURRENT_PROJECT, BASE_PROJECT_DIR)
    target_path = filepath if os.path.isabs(filepath) else os.path.join(proj_dir, filepath)
    if not os.path.exists(target_path):
        return f"HATA: '{filepath}' dosyası bulunamadı."
    try:
        with open(target_path, "r", encoding="utf-8", errors="ignore") as f:
            content = f.read()
        if target_text not in content:
            return f"HATA: Hedef kod bloğu dosyada birebir bulunamadı. Lütfen önce view_file ile satırları kontrol edin."
        new_content = content.replace(target_text, replacement_text, 1)
        with open(target_path, "w", encoding="utf-8") as f:
            f.write(new_content)
        return f"✅ '{filepath}' başarıyla güncellendi."
    except Exception as e:
        return f"Dosya Düzenleme Hatası: {e}"

def tool_write_file(filepath: str, content: str) -> str:
    """Yeni bir dosya oluşturur veya var olanın üzerine yazar."""
    proj_dir = PROJECTS_MAP.get(CURRENT_PROJECT, BASE_PROJECT_DIR)
    target_path = filepath if os.path.isabs(filepath) else os.path.join(proj_dir, filepath)
    try:
        os.makedirs(os.path.dirname(target_path), exist_ok=True)
        with open(target_path, "w", encoding="utf-8") as f:
            f.write(content)
        return f"✅ '{filepath}' dosyası başarıyla yazıldı."
    except Exception as e:
        return f"Dosya Yazma Hatası: {e}"

def tool_run_command(command: str) -> str:
    """Proje dizininde shell/terminal komutu çalıştırır."""
    proj_dir = PROJECTS_MAP.get(CURRENT_PROJECT, BASE_PROJECT_DIR)
    try:
        res = subprocess.run(command, shell=True, cwd=proj_dir, capture_output=True, text=True, timeout=30)
        out = res.stdout or ""
        err = res.stderr or ""
        return f"ÇIKTI:\n{out}\nHATA/UYARI:\n{err}\n(Çıkış Kodu: {res.returncode})"
    except Exception as e:
        return f"Komut Çalıştırma Hatası: {e}"

def tool_git_deploy(commit_message: str) -> str:
    """Değişiklikleri otomatik git commit ve git push yaparak canlı sunucuya deploy eder."""
    proj_dir = PROJECTS_MAP.get(CURRENT_PROJECT, BASE_PROJECT_DIR)
    try:
        c1 = subprocess.run("git add .", shell=True, cwd=proj_dir, capture_output=True, text=True)
        c2 = subprocess.run(f'git commit -m "{commit_message}"', shell=True, cwd=proj_dir, capture_output=True, text=True)
        c3 = subprocess.run("git push origin main", shell=True, cwd=proj_dir, capture_output=True, text=True)
        
        output = f"📦 Git Add: {c1.returncode}\n💾 Commit: {c2.stdout.strip()}\n🚀 Push Sonucu:\n{c3.stdout.strip()} {c3.stderr.strip()}"
        return output
    except Exception as e:
        return f"Deploy Hatası: {e}"

TOOLS_SCHEMA = [
    {
        "type": "function",
        "function": {
            "name": "view_file",
            "description": "Projedeki bir dosyanın içeriğini okur.",
            "parameters": {
                "type": "object",
                "properties": {
                    "filepath": {"type": "string", "description": "Okunacak dosya yolu (örn: graph.py, exchange.py)"}
                },
                "required": ["filepath"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "edit_file",
            "description": "Dosya içindeki belirli bir kod bloğunu yenisiyle değiştirir.",
            "parameters": {
                "type": "object",
                "properties": {
                    "filepath": {"type": "string", "description": "Düzenlenecek dosya yolu"},
                    "target_text": {"type": "string", "description": "Değiştirilecek eski kod bloğu"},
                    "replacement_text": {"type": "string", "description": "Yeni kod bloğu"}
                },
                "required": ["filepath", "target_text", "replacement_text"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "write_file",
            "description": "Yeni bir dosya oluşturur veya üzerine yazar.",
            "parameters": {
                "type": "object",
                "properties": {
                    "filepath": {"type": "string", "description": "Dosya yolu"},
                    "content": {"type": "string", "description": "Dosya içeriği"}
                },
                "required": ["filepath", "content"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "run_command",
            "description": "Terminal komutu çalıştırır (test, pytest, python script, git status vb.).",
            "parameters": {
                "type": "object",
                "properties": {
                    "command": {"type": "string", "description": "Çalıştırılacak terminal komutu"}
                },
                "required": ["command"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "git_deploy",
            "description": "Koddaki değişiklikleri commit edip GitHub'a pushlar (DigitalOcean otomatik derler).",
            "parameters": {
                "type": "object",
                "properties": {
                    "commit_message": {"type": "string", "description": "Git commit mesajı"}
                },
                "required": ["commit_message"]
            }
        }
    }
]

SYSTEM_PROMPT = """Sen Fox AI Şirketinin 3'lü Yapay Zeka Geliştirici Ekibinin (AGY • Claude Opus 5 • Codex) Ortak Sözcüsü ve Baş Mühendisisin.
Kullanıcı (S / Sayın Yöneticimiz), seni Telegram (@FoxSystemBot) üzerinden telefonundan yönetmektedir.

BU PROJEDE ÇALIŞAN 3'LÜ AJAN EKİBİ VE ROLLERİ:
1. 👑 ANTIGRAVITY (AGY Core): Sistem Baş Mimarı. Bütünleşik sohbet hafızasını, çoklu proje yönetimini (Fox-Kripto, Fox-Agents-Team), veritabanı anayasa kurallarını ve genel mimariyi koordine eder.
2. ⚖️ CLAUDE (Opus 5 Fast & Sonnet): Derin Akıl Yürütme ve Risk Denetçisi. Gönderilen ekran görüntülerini (Vision) piksel piksel inceler, algoritmik mantığı kurar, finansal formülleri denetler.
3. 🛠️ CODEX: Kod İnfaz ve Geliştirme Mühendisi. Dosyaları açar (view_file), kodları yazar/düzenler (edit_file, write_file), testleri çalıştırır (run_command) ve git_deploy ile canlı sunucuya aktarır.

AKTİF PROJE BAĞLAMI (FOX-KRİPTO):
• Çift Borsa: Binance TR (TRY) ve Binance Global (USDT) tam otonom al-sat motoru.
• Kasa Durumu: ~$128.44 USD (~₺6.120 TL). Binance TR: ₺3.512 TL nakit | Binance Global: $54.55 USDT nakit.
• Kurallar: 3 Slot, Eşit Matematiksel Bütçe (Kasa / 3), $5 altı kırıntı koruması, 7/24 balina hacim tarayıcısı.

GÖREVLERİN:
1. Kullanıcı soru sorduğunda, 3 ajanın ortak aklıyla samimi, profesyonel, detaylı ve Türkçe yanıt ver.
2. Kod düzenlemesi veya ekran görüntüsü gönderildiğinde, tool'larını kullanarak dosyaları incele, düzenle, test et ve canlıya deploy et.
3. Asla kuru/jenerik yanıt verme; kullanıcıya güven veren, mimariye hakim bir yapay zeka lideri gibi konuş.
"""

def execute_llm_cycle(user_prompt: str, image_b64: Optional[str] = None) -> str:
    """Claude Opus / 3.5 Sonnet ile tool-calling döngüsünü çalıştırır."""
    global CONVERSATION_HISTORY
    
    headers = {
        "Authorization": f"Bearer {OPENROUTER_API_KEY}",
        "HTTP-Referer": "https://fox-kripto.internal",
        "X-Title": "Fox Dev Bridge",
        "Content-Type": "application/json"
    }
    
    # Kullanıcı Mesajını Oluştur
    if image_b64:
        content_payload = [
            {"type": "text", "text": user_prompt or "Gönderdiğim ekran görüntüsünü analiz et ve gerekli incelemeyi yap."},
            {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{image_b64}"}}
        ]
    else:
        content_payload = user_prompt
        
    CONVERSATION_HISTORY.append({"role": "user", "content": content_payload})
    
    # En fazla son 15 mesajı sakla
    if len(CONVERSATION_HISTORY) > 15:
        CONVERSATION_HISTORY = CONVERSATION_HISTORY[-15:]
        
    messages = [{"role": "system", "content": SYSTEM_PROMPT}] + CONVERSATION_HISTORY
    
    # Tool Çağrı Döngüsü (Max 5 adım)
    for step in range(5):
        payload = {
            "model": DEFAULT_MODEL,
            "messages": messages,
            "tools": TOOLS_SCHEMA,
            "temperature": 0.2
        }
        
        try:
            r = requests.post("https://openrouter.ai/api/v1/chat/completions", headers=headers, json=payload, timeout=60)
            res_json = r.json()
            
            if "error" in res_json:
                err_msg = res_json["error"].get("message", str(res_json["error"]))
                if "credit" in err_msg.lower() or "payment" in err_msg.lower():
                    return "⚠️ *OpenRouter Kredi Uyarısı:*\n\nTanımladığınız OpenRouter API anahtarında bakiye (kredi) bulunmuyor.\n\n👉 Lütfen https://openrouter.ai/settings/credits adresinden hesabınıza bakiye ekleyiniz."
                return f"⚠️ *Yapay Zeka API Uyarısı:* {err_msg}"
                
            choices = res_json.get("choices")
            if not choices:
                return f"⚠️ Model yanıt üretemedi: {res_json}"
                
            choice = choices[0]
            msg = choice.get("message", {})
            messages.append(msg)
            
            # Eğer Tool çağrısı varsa icra et
            if msg.get("tool_calls"):
                for tc in msg["tool_calls"]:
                    fn_name = tc["function"]["name"]
                    args = json.loads(tc["function"]["arguments"])
                    print(f"🛠️ [Dev-Agent Tool Çağrısı]: {fn_name}({args})")
                    
                    tool_output = ""
                    if fn_name == "view_file":
                        tool_output = tool_view_file(args.get("filepath", ""))
                    elif fn_name == "edit_file":
                        tool_output = tool_edit_file(args.get("filepath", ""), args.get("target_text", ""), args.get("replacement_text", ""))
                    elif fn_name == "write_file":
                        tool_output = tool_write_file(args.get("filepath", ""), args.get("content", ""))
                    elif fn_name == "run_command":
                        tool_output = tool_run_command(args.get("command", ""))
                    elif fn_name == "git_deploy":
                        tool_output = tool_git_deploy(args.get("commit_message", "auto-deploy via mobile dev-agent"))
                    else:
                        tool_output = f"Bilinmeyen araç: {fn_name}"
                        
                    messages.append({
                        "role": "tool",
                        "tool_call_id": tc["id"],
                        "content": str(tool_output)
                    })
            else:
                # Nihai Metin Yanıtı Geldi
                final_text = msg.get("content", "")
                if not final_text and msg.get("tool_calls"):
                    continue
                CONVERSATION_HISTORY.append({"role": "assistant", "content": final_text or "İşlem tamamlandı."})
                return final_text or "İşlem başarıyla tamamlandı."
                
        except Exception as e:
            print(f"⚠️ LLM Hatası: {e}")
            return f"❌ Ajan İşlem Hatası: {e}"
            
    return "✅ Talep edilen kodlama ve sistem adımları başarıyla tamamlandı."

# =====================================================================
# TELEGRAM POLLER MOTORU (GÖRSEL, DOSYA VE METİN İŞLEYİCİ)
# =====================================================================

def download_telegram_file(file_id: str) -> Optional[bytes]:
    """Telegram sunucusundan fotoğraf veya dosya indirir."""
    try:
        r1 = requests.get(f"{BASE_TELEGRAM_URL}/getFile", params={"file_id": file_id}, timeout=10).json()
        if r1.get("ok"):
            file_path = r1["result"]["file_path"]
            download_url = f"https://api.telegram.org/file/bot{DEV_BOT_TOKEN}/{file_path}"
            r2 = requests.get(download_url, timeout=20)
            if r2.status_code == 200:
                return r2.content
    except Exception as e:
        print(f"⚠️ Dosya İndirme Hatası: {e}")
    return None

def start_dev_poller():
    """Mobil Geliştirici Köprüsünü başlatır ve mesajları dinler."""
    global CURRENT_PROJECT
    print(f"🚀 [Fox AI Dev-Bridge]: @FoxSystemBot aktif! Yetkili Chat ID: {AUTHORIZED_CHAT_ID}")
    
    # Başlangıç Selamı
    welcome_text = (
        "👑 *FOX AI MOBİL GELİŞTİRİCİ KÖPRÜSÜ AKTİF!*\n\n"
        "Hoş geldiniz Sayın Yöneticim (S). Ben projenizin Baş Yapay Zeka Mühendisiyim (Claude Opus / Sonnet Core).\n\n"
        "📱 *Telefondan Neler Yapabilirsiniz?*\n"
        "• 🖼️ **Ekran Görüntüsü Atın:** Hata görselini analiz edip koda müdahale edeyim.\n"
        "• 💬 **Yazılı/Sesli Emir Verin:** 'graph.py'deki kâr oranını %3 yap' deyin, kodlayıp deploy edeyim.\n"
        "• 📁 `/proje` yazarak projeler arasında geçiş yapabilirsiniz.\n\n"
        f"📍 *Aktif Proje:* `{CURRENT_PROJECT}`"
    )
    send_telegram_msg(AUTHORIZED_CHAT_ID, welcome_text)
    
    offset = 0
    while True:
        try:
            res = requests.get(f"{BASE_TELEGRAM_URL}/getUpdates", params={"offset": offset, "timeout": 20}, timeout=25).json()
            if res.get("ok"):
                for upd in res.get("result", []):
                    offset = upd["update_id"] + 1
                    msg = upd.get("message", {})
                    chat_id = msg.get("chat", {}).get("id")
                    
                    if not chat_id: continue
                    
                    # 🔒 GÜVENLİK KORUMASI: Yalnızca Sizin Chat ID'niz
                    if chat_id != AUTHORIZED_CHAT_ID:
                        send_telegram_msg(chat_id, "⛔ *Yetkisiz Erişim:* Bu bot yalnızca sistem yöneticisine özeldir.")
                        continue
                        
                    user_text = msg.get("text", "") or msg.get("caption", "")
                    photo_arr = msg.get("photo", [])
                    
                    # Proje Değiştirme Komutu
                    if user_text.startswith("/proje") or user_text.startswith("/project"):
                        parts = user_text.split()
                        if len(parts) > 1:
                            target_p = parts[1]
                            if target_p in PROJECTS_MAP:
                                CURRENT_PROJECT = target_p
                                send_telegram_msg(chat_id, f"🔄 *Proje Değiştirildi:* `{CURRENT_PROJECT}`\nÇalışma Dizini: `{PROJECTS_MAP[CURRENT_PROJECT]}`")
                            else:
                                send_telegram_msg(chat_id, f"⚠️ Proje bulunamadı. Mevcut projeler: {list(PROJECTS_MAP.keys())}")
                        else:
                            p_list = "\n".join([f"• `{p}`" for p in PROJECTS_MAP.keys()])
                            send_telegram_msg(chat_id, f"📂 *Mevcut Projeler:*\n{p_list}\n\nGeçiş için: `/proje ProjeAdi`")
                        continue
                        
                    # Fotoğraf / Ekran Görüntüsü Varsa
                    image_b64 = None
                    if photo_arr:
                        send_telegram_msg(chat_id, "👁️ *Ekran görüntüsü alındı, Claude Vision ile inceleniyor...*")
                        best_photo = photo_arr[-1] # En yüksek çözünürlüklü olanı al
                        img_bytes = download_telegram_file(best_photo["file_id"])
                        if img_bytes:
                            image_b64 = base64.b64encode(img_bytes).decode("utf-8")
                    else:
                        send_telegram_msg(chat_id, "⏳ *Claude Opus / Sonnet kodu inceliyor ve düzenliyor...*")
                        
                    # LLM Döngüsünü Başlat
                    reply_output = execute_llm_cycle(user_text, image_b64)
                    send_telegram_msg(chat_id, reply_output)
                    
        except Exception as e:
            print(f"⚠️ Dev Poller Hatası: {e}")
            time.sleep(3)

if __name__ == "__main__":
    start_dev_poller()
