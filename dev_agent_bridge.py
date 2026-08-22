"""
FOX AI 3-TIER MULTI-AGENT DEVELOPER BRIDGE
==========================================
1. Moderatör:        google/gemini-3.7-flash (Konuşma analizi & Görev yönlendirme)
2. Kodlama & Mimari: openai/gpt-5.6-sol (Codex motoru, dosya düzenleme, testler)
3. Bağımsız Denetçi: z-ai/glm-5.3 (Diff, güvenlik ve test denetimi, deploy onayı)
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

# 3'lü Ajan Modelleri
MODEL_MODERATOR = "google/gemini-3.7-flash"
MODEL_CODER = "openai/gpt-5.6-sol"
MODEL_AUDITOR = "z-ai/glm-5.3"

BASE_TELEGRAM_URL = f"https://api.telegram.org/bot{DEV_BOT_TOKEN}"
BASE_PROJECT_DIR = os.path.dirname(os.path.abspath(__file__))

PROJECTS_MAP = {
    "Fox-Kripto": BASE_PROJECT_DIR,
    "Fox-Agents-Team": os.path.abspath(os.path.join(BASE_PROJECT_DIR, "..", "Fox-Agents-Team")),
}
CURRENT_PROJECT = "Fox-Kripto"

CONVERSATION_HISTORY: List[Dict[str, Any]] = []

def log_dev_chat_message(sender: str, message: str):
    """Telefondaki konuşmayı gerçek zamanlı olarak Supabase hafızasına kaydeder."""
    try:
        from db import get_supabase
        client = get_supabase()
        if client:
            state_key = f"dev_chat_history_{AUTHORIZED_CHAT_ID}"
            res = client.table("crypto_agent_states").select("state_data").eq("session_id", state_key).execute()
            history = []
            if res.data and len(res.data) > 0:
                history = res.data[0].get("state_data", {}).get("messages", [])
            
            history.append({
                "timestamp": time.strftime("%Y-%m-%d %H:%M:%S", time.localtime()),
                "sender": sender,
                "message": message
            })
            if len(history) > 50:
                history = history[-50:]
                
            client.table("crypto_agent_states").upsert({
                "session_id": state_key,
                "updated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                "state_data": {"messages": history}
            }).execute()
    except Exception as e:
        print(f"⚠️ Dev Chat Log Hatası: {e}")

def send_telegram_msg(chat_id: int, text: str, parse_mode: str = "Markdown") -> bool:
    """Telegram üzerinden formatlı mesaj gönderir ve hafızaya kaydeder."""
    log_dev_chat_message("BOT (@FoxSystemBot)", text)
    try:
        url = f"{BASE_TELEGRAM_URL}/sendMessage"
        if len(text) > 4000:
            chunks = [text[i:i+3900] for i in range(0, len(text), 3900)]
            for ch in chunks:
                requests.post(url, json={"chat_id": chat_id, "text": ch, "parse_mode": parse_mode}, timeout=10)
            return True
        else:
            res = requests.post(url, json={"chat_id": chat_id, "text": text, "parse_mode": parse_mode}, timeout=10)
            if res.status_code != 200:
                requests.post(url, json={"chat_id": chat_id, "text": text}, timeout=10)
            return True
    except Exception as e:
        print(f"⚠️ Telegram Mesaj Hatası: {e}")
        return False

# =====================================================================
# TOOLS (KOD İNFAZ & DÜZENLEME ARAÇLARI)
# =====================================================================

def tool_view_file(filepath: str) -> str:
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
    proj_dir = PROJECTS_MAP.get(CURRENT_PROJECT, BASE_PROJECT_DIR)
    target_path = filepath if os.path.isabs(filepath) else os.path.join(proj_dir, filepath)
    if not os.path.exists(target_path):
        return f"HATA: '{filepath}' dosyası bulunamadı."
    try:
        with open(target_path, "r", encoding="utf-8", errors="ignore") as f:
            content = f.read()
        if target_text not in content:
            return f"HATA: Hedef kod bloğu dosyada bulunamadı."
        new_content = content.replace(target_text, replacement_text, 1)
        with open(target_path, "w", encoding="utf-8") as f:
            f.write(new_content)
        return f"✅ '{filepath}' başarıyla güncellendi."
    except Exception as e:
        return f"Dosya Düzenleme Hatası: {e}"

def tool_write_file(filepath: str, content: str) -> str:
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
    proj_dir = PROJECTS_MAP.get(CURRENT_PROJECT, BASE_PROJECT_DIR)
    try:
        res = subprocess.run(command, shell=True, cwd=proj_dir, capture_output=True, text=True, timeout=30)
        return f"ÇIKTI:\n{res.stdout}\nHATA:\n{res.stderr}\n(Kod: {res.returncode})"
    except Exception as e:
        return f"Komut Hatası: {e}"

def tool_git_deploy(commit_message: str) -> str:
    proj_dir = PROJECTS_MAP.get(CURRENT_PROJECT, BASE_PROJECT_DIR)
    try:
        subprocess.run("git add .", shell=True, cwd=proj_dir, capture_output=True, text=True)
        c2 = subprocess.run(f'git commit -m "{commit_message}"', shell=True, cwd=proj_dir, capture_output=True, text=True)
        c3 = subprocess.run("git push origin main", shell=True, cwd=proj_dir, capture_output=True, text=True)
        return f"🚀 Canlıya Alındı: {c2.stdout.strip()} | {c3.stdout.strip()}"
    except Exception as e:
        return f"Deploy Hatası: {e}"

CODER_TOOLS_SCHEMA = [
    {
        "type": "function",
        "function": {
            "name": "view_file",
            "description": "Projedeki bir dosyanın içeriğini okur.",
            "parameters": {"type": "object", "properties": {"filepath": {"type": "string"}}, "required": ["filepath"]}
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
                    "filepath": {"type": "string"},
                    "target_text": {"type": "string"},
                    "replacement_text": {"type": "string"}
                },
                "required": ["filepath", "target_text", "replacement_text"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "write_file",
            "description": "Yeni dosya oluşturur veya üzerine yazar.",
            "parameters": {"type": "object", "properties": {"filepath": {"type": "string"}, "content": {"type": "string"}}, "required": ["filepath", "content"]}
        }
    },
    {
        "type": "function",
        "function": {
            "name": "run_command",
            "description": "Terminal komutu ve testleri çalıştırır.",
            "parameters": {"type": "object", "properties": {"command": {"type": "string"}}, "required": ["command"]}
        }
    }
]

# =====================================================================
# 3 KADEMELİ AJAN DÖNGÜSÜ
# =====================================================================

def call_openrouter(model: str, messages: List[Dict[str, Any]], tools: Optional[List[Dict[str, Any]]] = None) -> Dict[str, Any]:
    """OpenRouter API çağrısı yapar."""
    headers = {
        "Authorization": f"Bearer {OPENROUTER_API_KEY}",
        "HTTP-Referer": "https://fox-system.internal",
        "X-Title": "Fox 3-Tier Multi-Agent Bridge",
        "Content-Type": "application/json"
    }
    payload: Dict[str, Any] = {
        "model": model,
        "messages": messages,
        "temperature": 0.2
    }
    if tools:
        payload["tools"] = tools
    
    r = requests.post("https://openrouter.ai/api/v1/chat/completions", headers=headers, json=payload, timeout=60)
    return r.json()

def execute_3tier_council(user_prompt: str, image_b64: Optional[str] = None) -> str:
    """
    3 Ajanlı Karar Konseyi:
    1. Moderatör (Gemini 3.7 Flash) -> Analiz & Yönlendirme
    2. Kodlama & Mimari (GPT-5.6 Sol) -> Kod İnfaz & Testler
    3. Bağımsız Denetçi (GLM-5.3) -> Diff & Güvenlik Denetimi
    """
    global CONVERSATION_HISTORY
    
    # -------------------------------------------------------------
    # 1. KADEME: MODERATÖR (google/gemini-3.7-flash)
    # -------------------------------------------------------------
    mod_sys_prompt = """Sen Fox AI Şirketinin Baş Yapay Zeka Moderatörü ve Sistem Liderisin (google/gemini-3.7-flash).
Kullanıcı (Sayın Yöneticimiz S), seni Telegram (@FoxSystemBot) üzerinden yönetmektedir.

PROJE VE SİSTEM BAĞLAMI:
• Aktif Proje: Fox-Kripto (Binance TR + Binance Global tam otonom çift borsa ticaret platformu).
• Canlı Kasa: $128.44 USD (~₺6.120 TL). Binance TR: ₺3.512,18 TL serbest nakit | Binance Global: $54.55 USDT serbest nakit.
• Aktif Ajanlar:
  1. 🎯 Moderatör (Gemini 3.7 Flash): Analiz, yönlendirme, stratejik sohbet ve durum takibi.
  2. 🛠️ Kodlama & Mimari (Codex CLI + openai/gpt-5.6-sol): Dosya düzenleme, test çalıştırma ve geliştirme.
  3. 🔍 Bağımsız Denetçi (z-ai/glm-5.3): Git diff kontrolü, güvenlik denetimi ve canlı deploy onayı.

GÖREVLERİN:
1. Kullanıcı soru sorduğunda, durum istediğinde veya sohbet ettiğinde ASLA ezber, kuru veya jenerik ("Selam nasılsınız" gibi robotik) konuşma!
2. Projenin durumunu, kasayı, mimariyi ve stratejiyi bilen usta bir Yapay Zeka Direktörü gibi akıllı, net, detaylı ve Türkçe yanıt ver.
3. Eğer kullanıcı bir KODLAMA, DOSYA DÜZENLEME, HATA DÜZELTME veya DEPLOY emri veriyorsa yanıtına tam olarak '[KOD_GOREVI]: <detayli_gorev_tanimi>' ile başla.
"""
    
    if image_b64:
        user_content = [
            {"type": "text", "text": user_prompt or "Ekran görüntüsünü incele ve analiz et."},
            {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{image_b64}"}}
        ]
    else:
        user_content = user_prompt

    mod_messages = [
        {"role": "system", "content": mod_sys_prompt},
        {"role": "user", "content": user_content}
    ]
    
    print(f"🎯 [1. Kademe Moderatör]: {MODEL_MODERATOR} analiz ediyor...")
    res_mod = call_openrouter(MODEL_MODERATOR, mod_messages)
    
    if "error" in res_mod:
        return f"⚠️ Moderatör Hatası: {res_mod['error'].get('message')}"
        
    mod_text = res_mod.get("choices", [{}])[0].get("message", {}).get("content", "")
    
    # Eğer doğrudan yanıt ise (kodlama görevi değilse) kullanıcıya ilet
    if not mod_text.startswith("[KOD_GOREVI]"):
        return f"🎯 *[Moderatör • Gemini 3.7 Flash]*\n\n{mod_text}"

    task_desc = mod_text.replace("[KOD_GOREVI]:", "").strip()
    
    # -------------------------------------------------------------
    # 2. KADEME: KODLAMA & MİMARİ (openai/gpt-5.6-sol + Codex)
    # -------------------------------------------------------------
    print(f"🛠️ [2. Kademe Kodlama]: {MODEL_CODER} görevi devraldı: {task_desc}")
    coder_sys_prompt = """Sen Fox AI Kodlama ve Mimari Ajanısın (Codex CLI + openai/gpt-5.6-sol).
GÖREVİN:
1. Sana verilen görev için ASLA sadece niyet bildiren ("yapıyorum, süreci başlattım" gibi) boş metin üretme!
2. MUTLAKA sana verilen araçları (run_command, view_file, edit_file, write_file) DOĞRUDAN ÇAĞIR.
3. Eğer log, durum veya skor kontrolü istenmişse run_command ile terminal/python komutunu fiilen çalıştır ve dönen gerçek terminal çıktısını rapora ekle.
4. Kod yazdıysan diff ve test sonucunu, analiz yaptıysan gerçek verileri eksiksiz sun.
"""
    coder_messages = [
        {"role": "system", "content": coder_sys_prompt},
        {"role": "user", "content": f"GÖREV: {task_desc}\n\nLütfen gerekli dosya araçlarını kullanarak kodu yaz, düzenle ve test et."}
    ]
    
    coder_summary = ""
    for step in range(4):
        res_coder = call_openrouter(MODEL_CODER, coder_messages, tools=CODER_TOOLS_SCHEMA)
        if "error" in res_coder:
            coder_summary = f"Kodlama Hatası: {res_coder['error'].get('message')}"
            break
        
        c_msg = res_coder.get("choices", [{}])[0].get("message", {})
        coder_messages.append(c_msg)
        
        if c_msg.get("tool_calls"):
            for tc in c_msg["tool_calls"]:
                fn_name = tc["function"]["name"]
                args = json.loads(tc["function"]["arguments"])
                print(f"🛠️ [Codex Tool]: {fn_name}({args})")
                
                t_out = ""
                if fn_name == "view_file": t_out = tool_view_file(args.get("filepath", ""))
                elif fn_name == "edit_file": t_out = tool_edit_file(args.get("filepath", ""), args.get("target_text", ""), args.get("replacement_text", ""))
                elif fn_name == "write_file": t_out = tool_write_file(args.get("filepath", ""), args.get("content", ""))
                elif fn_name == "run_command": t_out = tool_run_command(args.get("command", ""))
                
                coder_messages.append({"role": "tool", "tool_call_id": tc["id"], "content": str(t_out)})
        else:
            coder_summary = c_msg.get("content", "")
            break
            
    # -------------------------------------------------------------
    # 3. KADEME: BAĞIMSIZ DENETÇİ (z-ai/glm-5.3)
    # -------------------------------------------------------------
    print(f"🔍 [3. Kademe Denetçi]: {MODEL_AUDITOR} diff ve testleri denetliyor...")
    git_diff_out = subprocess.run("git diff", shell=True, cwd=PROJECTS_MAP.get(CURRENT_PROJECT, BASE_PROJECT_DIR), capture_output=True, text=True).stdout
    
    auditor_sys_prompt = """Sen Fox AI Bağımsız Güvenlik ve Kod Denetçisisin (z-ai/glm-5.3).
Görevin: Kodlama ajanının yaptığı değişiklikleri (Git Diff) ve test sonuçlarını incelemek.
Eğer kod güvenli, doğru ve amaca uygunsa 'ONAYLANDI' de ve özetle.
Eğer hata veya güvenlik açığı varsa 'REDDEDİLDİ' de ve sebebini belirt.
"""
    auditor_messages = [
        {"role": "system", "content": auditor_sys_prompt},
        {"role": "user", "content": f"GÖREV: {task_desc}\n\nKODLAMA ÖZETİ:\n{coder_summary}\n\nGİT DIFF ÇIKTISI:\n{git_diff_out or '(Diff yok veya dosya yeni yazıldı)'}"}
    ]
    
    res_auditor = call_openrouter(MODEL_AUDITOR, auditor_messages)
    auditor_text = res_auditor.get("choices", [{}])[0].get("message", {}).get("content", "")
    
    # Eğer Denetçi Onay Verdiyse Git Deploy Yap
    deploy_status = ""
    if "ONAY" in auditor_text.upper():
        deploy_res = tool_git_deploy(f"feat: {task_desc[:60]} (Approved by GLM-5.3 & GPT-5.6 Sol)")
        deploy_status = f"\n\n🚀 *[Canlı Sunucu]:* {deploy_res}"
        
    final_report = (
        f"🎯 *[1. Moderatör • Gemini 3.7 Flash]*\n"
        f"Görev: `{task_desc}`\n\n"
        f"🛠️ *[2. Kodlama & Mimari • GPT-5.6 Sol]*\n"
        f"{coder_summary}\n\n"
        f"🔍 *[3. Bağımsız Denetçi • GLM-5.3]*\n"
        f"{auditor_text}"
        f"{deploy_status}"
    )
    return final_report

def start_dev_poller():
    """Mobil Geliştirici Köprüsünü başlatır."""
    global CURRENT_PROJECT
    print(f"🚀 [Fox 3-Tier Multi-Agent]: @FoxSystemBot dinlemede! (Gemini 3.7 Flash • GPT-5.6 Sol • GLM-5.3)")
    
    offset = 0
    while True:
        try:
            res = requests.get(f"{BASE_TELEGRAM_URL}/getUpdates", params={"offset": offset, "timeout": 20}, timeout=25).json()
            if res.get("ok"):
                for upd in res.get("result", []):
                    offset = upd["update_id"] + 1
                    msg = upd.get("message", {})
                    chat_id = msg.get("chat", {}).get("id")
                    
                    if not chat_id or chat_id != AUTHORIZED_CHAT_ID:
                        continue
                        
                    user_text = msg.get("text", "") or msg.get("caption", "")
                    photo_arr = msg.get("photo", [])
                    log_dev_chat_message("KULLANICI (S)", user_text or "[FOTOĞRAF / GÖRSEL]")
                    
                    # Fotoğraf İndirme
                    image_b64 = None
                    if photo_arr:
                        best_photo = photo_arr[-1]
                        img_bytes = download_telegram_file(best_photo["file_id"])
                        if img_bytes:
                            image_b64 = base64.b64encode(img_bytes).decode("utf-8")
                        
                    output = execute_3tier_council(user_text, image_b64)
                    send_telegram_msg(chat_id, output)
                    
        except Exception as e:
            print(f"⚠️ Poller Hatası: {e}")
            time.sleep(2)

def download_telegram_file(file_id: str) -> Optional[bytes]:
    try:
        r1 = requests.get(f"{BASE_TELEGRAM_URL}/getFile", params={"file_id": file_id}, timeout=10).json()
        if r1.get("ok"):
            f_path = r1["result"]["file_path"]
            r2 = requests.get(f"https://api.telegram.org/file/bot{DEV_BOT_TOKEN}/{f_path}", timeout=20)
            if r2.status_code == 200:
                return r2.content
    except Exception:
        pass
    return None

if __name__ == "__main__":
    start_dev_poller()
