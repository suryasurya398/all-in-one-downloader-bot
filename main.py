import os
import re
import requests
import telebot
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton
import yt_dlp

# Telegram Bot Token
BOT_TOKEN = os.getenv("BOT_TOKEN", "8936396715:AAF1iw4oIeGn3DwoY9znSkovrOZkq-X5sQo")
bot = telebot.TeleBot(BOT_TOKEN)

# Temporary Link Store
user_links = {}

# TeraBox Supported Domains Check
TERABOX_DOMAINS = ["terabox", "1024tera", "teraboxapp", "freeterabox", "mirrobox", "nebulabox", "4funbox"]

def is_terabox(url):
    return any(domain in url for domain in TERABOX_DOMAINS)

@bot.message_handler(commands=['start', 'help'])
def send_welcome(message):
    welcome_text = (
        "👋 *All-in-One Downloader Bot*\n\n"
        "Mujhe koi bhi link bhejo:\n"
        "🔹 TeraBox (All links)\n"
        "🔹 YouTube Shorts/Videos\n"
        "🔹 Instagram Reels\n"
        "🔹 Pinterest Videos\n\n"
        "Link bhejte hi Video aur MP3 Audio dono ka option milega!"
    )
    bot.reply_to(message, welcome_text, parse_mode="Markdown")

@bot.message_handler(func=lambda message: True)
def handle_message(message):
    url = message.text.strip()
    
    # URL Validation
    if not (url.startswith("http://") or url.startswith("https://")):
        bot.reply_to(message, "❌ Kripya valid video ya TeraBox link bhejein.")
        return

    # Store link against message ID
    msg_id = message.message_id
    user_links[msg_id] = url

    # Inline Buttons Create Karein
    markup = InlineKeyboardMarkup()
    btn_video = InlineKeyboardButton("🎥 Video (MP4)", callback_data=f"vid_{msg_id}")
    btn_audio = InlineKeyboardButton("🎵 Audio (MP3)", callback_data=f"aud_{msg_id}")
    markup.add(btn_video, btn_audio)

    bot.reply_to(message, "⚙️ *Select Format:* Download kis format me karna chahte hain?", reply_markup=markup, parse_mode="Markdown")

@bot.callback_query_handler(func=lambda call: True)
def callback_listener(call):
    action, msg_id = call.data.split("_")
    msg_id = int(msg_id)
    url = user_links.get(msg_id)

    if not url:
        bot.answer_callback_query(call.id, "❌ Link expire ho chuka hai, dubara link bhejein.")
        return

    bot.answer_callback_query(call.id, "⏳ Processing processing start ho gayi hai...")
    status_msg = bot.send_message(call.message.chat.id, "⏳ *File process ho rahi hai, kripya wait karein...*", parse_mode="Markdown")

    try:
        if is_terabox(url):
            download_terabox(call.message.chat.id, url, action, status_msg)
        else:
            download_general_ytdlp(call.message.chat.id, url, action, status_msg)
    except Exception as e:
        bot.edit_message_text(f"❌ Error aayi: {str(e)[:200]}", chat_id=call.message.chat.id, message_id=status_msg.message_id)

def download_terabox(chat_id, url, action, status_msg):
    # Free TeraBox API Bypass Logic
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
                bot.send_video(chat_id, video, caption="✅ TeraBox Video Downloaded!")
        else:
            with open(file_name, "rb") as audio:
                bot.send_audio(chat_id, audio, caption="✅ TeraBox Audio Extracted!")
        
        os.remove(file_name)
        bot.delete_message(chat_id, status_msg.message_id)
    else:
        bot.edit_message_text("❌ TeraBox link bypass nahi ho paaya. File private ho sakti hai.", chat_id=chat_id, message_id=status_msg.message_id)

def download_general_ytdlp(chat_id, url, action, status_msg):
    out_file = f"download_{chat_id}"
    
    if action == "vid":
        ydl_opts = {
            'format': 'bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best',
            'outtmpl': f'{out_file}.%(ext)s',
            'max_filesize': 50 * 1024 * 1024 # 50MB Limit for Telegram free bots
        }
    else:
        ydl_opts = {
            'format': 'bestaudio/best',
            'postprocessors': [{
                'key': 'FFmpegExtractAudio',
                'preferredcodec': 'mp3',
                'preferredquality': '192',
            }],
            'outtmpl': f'{out_file}.%(ext)s',
            'max_filesize': 50 * 1024 * 1024
        }

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

# Bot Run
bot.polling(non_stop=True)
