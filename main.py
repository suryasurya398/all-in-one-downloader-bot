import os
import re
import time
import requests
import threading
from http.server import HTTPServer, BaseHTTPRequestHandler
import telebot
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton
import yt_dlp

# Dummy Web Server to satisfy Render Port Binding
class HealthCheckHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"Bot is Live!")

def run_health_check_server():
    port = int(os.environ.get("PORT", 8080))
    server = HTTPServer(("0.0.0.0", port), HealthCheckHandler)
    server.serve_forever()

# Start Web Server in Background Thread
threading.Thread(target=run_health_check_server, daemon=True).start()

# Bot Token Setup
BOT_TOKEN = os.getenv("BOT_TOKEN", "8936396715:AAF1iw4oIeGn3DwoY9znSkovrOZkq-X5sQo")
bot = telebot.TeleBot(BOT_TOKEN)

user_links = {}
TERABOX_DOMAINS = ["terabox", "1024tera", "teraboxapp", "freeterabox", "mirrobox", "nebulabox", "4funbox"]

def is_terabox(url):
    return any(domain in url for domain in TERABOX_DOMAINS)

@bot.message_handler(commands=['start', 'help'])
def send_welcome(message):
    welcome_text = (
        "👋 *Welcome to All-in-One Downloader Bot*\n\n"
        "Send me any link from:\n"
        "🔹 TeraBox (All domains)\n"
        "🔹 YouTube Shorts / Videos\n"
        "🔹 Instagram Reels\n"
        "🔹 Pinterest Videos\n\n"
        "Choose between Video (MP4) and Audio (MP3) formats!"
    )
    bot.reply_to(message, welcome_text, parse_mode="Markdown")

@bot.message_handler(func=lambda message: True)
def handle_message(message):
    url = message.text.strip()
    
    if not (url.startswith("http://") or url.startswith("https://")):
        bot.reply_to(message, "❌ Please send a valid media link.")
        return

    msg_id = message.message_id
    user_links[msg_id] = url

    markup = InlineKeyboardMarkup()
    btn_video = InlineKeyboardButton("🎥 Video (MP4)", callback_data=f"vid_{msg_id}")
    btn_audio = InlineKeyboardButton("🎵 Audio (MP3)", callback_data=f"aud_{msg_id}")
    markup.add(btn_video, btn_audio)

    bot.reply_to(message, "⚙️ *Select Format:* Please choose your download option:", reply_markup=markup, parse_mode="Markdown")

@bot.callback_query_handler(func=lambda call: True)
def callback_listener(call):
    try:
        action, msg_id = call.data.split("_")
        msg_id = int(msg_id)
        url = user_links.get(msg_id)

        if not url:
            bot.answer_callback_query(call.id, "❌ Link expired. Please send the link again.")
            return

        bot.answer_callback_query(call.id, "⏳ Processing started...")
        status_msg = bot.send_message(call.message.chat.id, "⏳ *Processing your request, please wait...*", parse_mode="Markdown")

        if is_terabox(url):
            download_terabox(call.message.chat.id, url, action, status_msg)
        else:
            download_general_ytdlp(call.message.chat.id, url, action, status_msg)
    except Exception as e:
        bot.send_message(call.message.chat.id, f"❌ Error: {str(e)[:200]}")

def download_terabox(chat_id, url, action, status_msg):
    api_url = f"https://terabox-dl.qtcloud.workers.dev/api/get-info?shorturl={url.split('/')[-1]}"
    res = requests.get(api_url).json()

    if "downloadUrl" in res:
        direct_link = res["downloadUrl"]
        file_name = res.get("fileName", "video.mp4")
        
        file_data = requests.get(direct_link, stream=True)
        with open(file_name, "wb") as f:
            for chunk in file_data.iter_content(chunk_size=1024*1024):
                if chunk:
                    f.write(chunk)

        if action == "vid":
            with open(file_name, "rb") as video:
                bot.send_video(chat_id, video, caption="✅ *TeraBox Video Downloaded!*", parse_mode="Markdown")
        else:
            with open(file_name, "rb") as audio:
                bot.send_audio(chat_id, audio, caption="✅ *TeraBox Audio Extracted!*", parse_mode="Markdown")
        
        if os.path.exists(file_name):
            os.remove(file_name)
        bot.delete_message(chat_id, status_msg.message_id)
    else:
        bot.edit_message_text("❌ Unable to bypass TeraBox link. File may be private.", chat_id=chat_id, message_id=status_msg.message_id)

def download_general_ytdlp(chat_id, url, action, status_msg):
    out_file = f"download_{chat_id}_{int(time.time())}"
    
    # Bypass YouTube Cloud Server IP Blockers
    ydl_opts = {
        'quiet': True,
        'no_warnings': True,
        'max_filesize': 50 * 1024 * 1024,
        'extractor_args': {
            'youtube': {
                'player_client': ['ios', 'android', 'mweb']
            }
        },
        'http_headers': {
            'User-Agent': 'Mozilla/5.0 (iPhone; CPU iPhone OS 16_5 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/16.5 Mobile/15E148 Safari/604.1'
        }
    }

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
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=True)
            filename = ydl.prepare_filename(info)

        if action == "vid":
            with open(filename, "rb") as video:
                bot.send_video(chat_id, video, caption=f"🎥 *{info.get('title', 'Video')}*", parse_mode="Markdown")
        else:
            mp3_filename = f"{out_file}.mp3"
            if os.path.exists(mp3_filename):
                filename = mp3_filename
            with open(filename, "rb") as audio:
                bot.send_audio(chat_id, audio, caption=f"🎵 *{info.get('title', 'Audio')}*", parse_mode="Markdown")

        if os.path.exists(filename):
            os.remove(filename)
        bot.delete_message(chat_id, status_msg.message_id)

    except Exception as e:
        bot.edit_message_text(f"❌ Extraction failed: {str(e)[:150]}", chat_id=chat_id, message_id=status_msg.message_id)

# Clear conflicting webhooks and start polling cleanly
try:
    bot.remove_webhook(drop_pending_updates=True)
    time.sleep(1)
except Exception:
    pass

bot.infinity_polling(timeout=10, long_polling_timeout=5, skip_pending=True)
