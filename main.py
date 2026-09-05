import os
import re
import time
import requests
import threading
from http.server import HTTPServer, BaseHTTPRequestHandler
import telebot
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton
import yt_dlp

# ==========================================
# 1. DUMMY HTTP SERVER FOR RENDER PORT BINDING
# ==========================================
class HealthCheckHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"All-in-One Downloader Bot is Running Perfectly!")

def run_health_check_server():
    port = int(os.environ.get("PORT", 8080))
    server = HTTPServer(("0.0.0.0", port), HealthCheckHandler)
    server.serve_forever()

threading.Thread(target=run_health_check_server, daemon=True).start()

# ==========================================
# 2. BOT INITIALIZATION
# ==========================================
BOT_TOKEN = os.getenv("BOT_TOKEN", "YOUR_BOT_TOKEN_HERE")
bot = telebot.TeleBot(BOT_TOKEN)

user_links = {}

TERABOX_DOMAINS = [
    "terabox", "1024tera", "teraboxapp", "freeterabox", 
    "mirrobox", "nebulabox", "4funbox", "momerybox"
]

def is_terabox(url):
    return any(domain in url.lower() for domain in TERABOX_DOMAINS)

def extract_terabox_id(url):
    match = re.search(r'(?:/s/|surl=)([a-zA-Z0-9_-]+)', url)
    if match:
        return match.group(1)
    clean_url = url.split('?')[0].rstrip('/')
    return clean_url.split('/')[-1]

# ==========================================
# 3. TELEGRAM BOT HANDLERS (ENGLISH ONLY)
# ==========================================
@bot.message_handler(commands=['start', 'help'])
def send_welcome(message):
    welcome_text = (
        "👋 *Welcome to All-in-One Media Downloader Bot*\n\n"
        "Send me any valid link from:\n"
        "🔸 *YouTube* (Videos & Shorts)\n"
        "🔸 *TeraBox* (All short links & domains)\n"
        "🔸 *Instagram* (Reels & Posts)\n"
        "🔸 *Pinterest* (Videos & Pins)\n"
        "🔸 *TikTok / Twitter / Facebook*\n\n"
        "👇 *Send your link below to get started!*"
    )
    bot.reply_to(message, welcome_text, parse_mode="Markdown")

@bot.message_handler(func=lambda message: True)
def handle_message(message):
    url = message.text.strip()
    
    if not (url.startswith("http://") or url.startswith("https://")):
        bot.reply_to(message, "❌ *Invalid Link!* Please send a valid media URL starting with http:// or https://", parse_mode="Markdown")
        return

    msg_id = message.message_id
    user_links[msg_id] = url

    markup = InlineKeyboardMarkup()
    btn_video = InlineKeyboardButton("🎥 Video (MP4)", callback_data=f"vid_{msg_id}")
    btn_audio = InlineKeyboardButton("🎵 Audio (MP3)", callback_data=f"aud_{msg_id}")
    markup.add(btn_video, btn_audio)

    bot.reply_to(
        message, 
        "⚙️ *Select Download Format:*\nPlease choose your preferred media format below:", 
        reply_markup=markup, 
        parse_mode="Markdown"
    )

@bot.callback_query_handler(func=lambda call: True)
def callback_listener(call):
    try:
        action, msg_id = call.data.split("_")
        msg_id = int(msg_id)
        url = user_links.get(msg_id)

        if not url:
            bot.answer_callback_query(call.id, "❌ Session expired! Please re-send your link.", show_alert=True)
            return

        bot.answer_callback_query(call.id, "⏳ Download request received!")
        status_msg = bot.send_message(
            call.message.chat.id, 
            "⏳ *Processing your request... Please wait.*", 
            parse_mode="Markdown"
        )

        if is_terabox(url):
            process_terabox(call.message.chat.id, url, action, status_msg)
        else:
            process_general_media(call.message.chat.id, url, action, status_msg)

    except Exception as e:
        bot.send_message(call.message.chat.id, f"❌ *An unexpected error occurred:* `{str(e)[:150]}`", parse_mode="Markdown")

# ==========================================
# 4. TERABOX DOWNLOADER ENGINE (MULTI-API FALLBACK)
# ==========================================
def process_terabox(chat_id, url, action, status_msg):
    surl = extract_terabox_id(url)
    
    # List of fallback APIs for TeraBox
    api_endpoints = [
        f"https://terabox-dl.qtcloud.workers.dev/api/get-info?shorturl={surl}",
        f"https://terabox.hnn.workers.dev/api/get-info?shorturl={surl}",
        f"https://terabox-app-api.vercel.app/api?url={url}"
    ]

    direct_link = None
    file_name = "terabox_file.mp4"

    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/115.0.0.0 Safari/537.36'
    }

    for endpoint in api_endpoints:
        try:
            res = requests.get(endpoint, headers=headers, timeout=12)
            if res.status_code == 200:
                data = res.json()
                if "downloadUrl" in data and data["downloadUrl"]:
                    direct_link = data["downloadUrl"]
                    file_name = data.get("fileName", "terabox_media.mp4")
                    break
                elif "url" in data and data["url"]:
                    direct_link = data["url"]
                    break
        except Exception:
            continue

    if not direct_link:
        bot.edit_message_text(
            "❌ *TeraBox Extraction Failed!*\n\nThe file might be private or TeraBox servers are currently blocking automated requests. Please try again later.",
            chat_id=chat_id,
            message_id=status_msg.message_id,
            parse_mode="Markdown"
        )
        return

    try:
        bot.edit_message_text("📥 *Downloading file from TeraBox cloud...*", chat_id=chat_id, message_id=status_msg.message_id, parse_mode="Markdown")
        
        local_filename = f"tb_{int(time.time())}.mp4"
        with requests.get(direct_link, stream=True, headers=headers, timeout=60) as r:
            r.raise_for_status()
            with open(local_filename, 'wb') as f:
                for chunk in r.iter_content(chunk_size=2*1024*1024):
                    if chunk:
                        f.write(chunk)

        bot.edit_message_text("📤 *Uploading media to Telegram...*", chat_id=chat_id, message_id=status_msg.message_id, parse_mode="Markdown")

        with open(local_filename, 'rb') as file_data:
            if action == "vid":
                bot.send_video(chat_id, file_data, caption="✅ *Downloaded via TeraBox Engine*", parse_mode="Markdown")
            else:
                bot.send_audio(chat_id, file_data, caption="✅ *Extracted Audio via TeraBox Engine*", parse_mode="Markdown")

        if os.path.exists(local_filename):
            os.remove(local_filename)
            
        bot.delete_message(chat_id, status_msg.message_id)

    except Exception as e:
        bot.edit_message_text(f"❌ *Failed to download file:* `{str(e)[:150]}`", chat_id=chat_id, message_id=status_msg.message_id, parse_mode="Markdown")

# ==========================================
# 5. GENERAL MEDIA ENGINE (COBALT + YT-DLP FALLBACK)
# ==========================================
def process_general_media(chat_id, url, action, status_msg):
    # Try Method A: Cobalt API Engine
    success = download_via_cobalt(chat_id, url, action, status_msg)
    if success:
        return

    # Try Method B: YT-DLP Engine with Mobile Emulation
    download_via_ytdlp(chat_id, url, action, status_msg)

def download_via_cobalt(chat_id, url, action, status_msg):
    try:
        bot.edit_message_text("⚡ *Processing link via High-Speed Engine...*", chat_id=chat_id, message_id=status_msg.message_id, parse_mode="Markdown")
        
        cobalt_headers = {
            "Accept": "application/json",
            "Content-Type": "application/json",
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"
        }
        
        payload = {
            "url": url,
            "videoQuality": "720",
            "downloadMode": "audio" if action == "aud" else "auto"
        }

        res = requests.post("https://api.cobalt.tools/", json=payload, headers=cobalt_headers, timeout=15)
        
        if res.status_code == 200:
            data = res.json()
            media_url = None
            
            status = data.get("status")
            if status in ["redirect", "tunnel", "stream"]:
                media_url = data.get("url")
            elif status == "picker" and data.get("picker"):
                media_url = data["picker"][0].get("url")

            if media_url:
                bot.edit_message_text("📤 *Uploading media to Telegram...*", chat_id=chat_id, message_id=status_msg.message_id, parse_mode="Markdown")
                
                if action == "vid":
                    bot.send_video(chat_id, media_url, caption="✅ *Downloaded successfully!*", parse_mode="Markdown")
                else:
                    bot.send_audio(chat_id, media_url, caption="✅ *Audio extracted successfully!*", parse_mode="Markdown")
                
                bot.delete_message(chat_id, status_msg.message_id)
                return True
    except Exception:
        pass
    
    return False

def download_via_ytdlp(chat_id, url, action, status_msg):
    out_file = f"media_{chat_id}_{int(time.time())}"
    
    ydl_opts = {
        'quiet': True,
        'no_warnings': True,
        'max_filesize': 50 * 1024 * 1024, # 50MB Limit
        'extractor_args': {
            'youtube': {
                'player_client': ['ios', 'android', 'mweb']
            }
        },
        'http_headers': {
            'User-Agent': 'Mozilla/5.0 (iPhone; CPU iPhone OS 16_5 like Mac OS X) AppleWebKit/605.1.15'
        }
    }

    # Write cookies if available in environment variables
    yt_cookies = os.getenv("YT_COOKIES")
    if yt_cookies:
        cookies_file = f"cookies_{chat_id}.txt"
        with open(cookies_file, "w") as f:
            f.write(yt_cookies)
        ydl_opts['cookiefile'] = cookies_file

    if action == "vid":
        ydl_opts.update({
            'format': 'bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best',
            'outtmpl': f'{out_file}.%(ext)s',
        })
    else:
        ydl_opts.update({
            'format': 'bestaudio/best',
            'postprocessors': [{
                'key': 'FFmpegExtractAudio',
                'preferredcodec': 'mp3',
                'preferredquality': '192',
            }],
            'outtmpl': f'{out_file}.%(ext)s',
        })

    try:
        bot.edit_message_text("📥 *Downloading media file...*", chat_id=chat_id, message_id=status_msg.message_id, parse_mode="Markdown")
        
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=True)
            filename = ydl.prepare_filename(info)

        if action == "aud":
            mp3_file = f"{out_file}.mp3"
            if os.path.exists(mp3_file):
                filename = mp3_file

        bot.edit_message_text("📤 *Uploading media to Telegram...*", chat_id=chat_id, message_id=status_msg.message_id, parse_mode="Markdown")

        with open(filename, "rb") as file_data:
            if action == "vid":
                bot.send_video(chat_id, file_data, caption=f"🎥 *{info.get('title', 'Media Video')}*", parse_mode="Markdown")
            else:
                bot.send_audio(chat_id, file_data, caption=f"🎵 *{info.get('title', 'Media Audio')}*", parse_mode="Markdown")

        # Cleanup files
        if os.path.exists(filename):
            os.remove(filename)
        if yt_cookies and os.path.exists(cookies_file):
            os.remove(cookies_file)

        bot.delete_message(chat_id, status_msg.message_id)

    except Exception as e:
        bot.edit_message_text(
            f"❌ *Extraction Failed!*\n\n`{str(e)[:180]}`\n\n*Note:* If this is a YouTube video, YouTube may have temporarily blocked cloud downloads for this link.", 
            chat_id=chat_id, 
            message_id=status_msg.message_id, 
            parse_mode="Markdown"
        )

# ==========================================
# 6. SAFE BOT POLLING STARTUP (PREVENTS ERROR 409)
# ==========================================
if __name__ == "__main__":
    try:
        bot.remove_webhook(drop_pending_updates=True)
        time.sleep(2)
    except Exception:
        pass

    print("Bot started successfully!")
    bot.infinity_polling(timeout=15, long_polling_timeout=5, skip_pending=True)
