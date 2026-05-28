import os
import re
import logging
from urllib.parse import quote
import requests
from bs4 import BeautifulSoup
from fastapi import FastAPI, Request, Response
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    filters,
    ContextTypes
)

# 配置
TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
RENDER_SERVICE_NAME = os.environ.get("RENDER_SERVICE_NAME")
WEBHOOK_URL = f"https://{RENDER_SERVICE_NAME}.onrender.com/webhook"
BASE_URL = "https://www.gequbao.net"
SEARCH_URL = f"{BASE_URL}/search/"

# 日志
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# 全局缓存
user_music_cache = {}

# FastAPI
app = FastAPI()
tg_app = Application.builder().token(TOKEN).build()

# ===================== 歌曲搜索爬虫 =====================
def search_music(keyword: str):
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    }
    try:
        url = f"{SEARCH_URL}{quote(keyword)}/"
        resp = requests.get(url, headers=headers, timeout=15)
        resp.encoding = "utf-8"
        soup = BeautifulSoup(resp.text, "html.parser")

        musics = []
        for item in soup.select(".list-song-item"):
            a = item.select_one("a")
            title = a.get_text(strip=True)
            link = BASE_URL + a["href"]
            artist = item.select_one(".song-artist").get_text(strip=True) if item.select_one(".song-artist") else "未知"
            musics.append({"title": title, "artist": artist, "link": link})
        return musics[:8]
    except Exception as e:
        logger.error(f"搜索失败: {e}")
        return []

def get_music_url(detail_url):
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    }
    try:
        resp = requests.get(detail_url, headers=headers, timeout=15)
        resp.encoding = "utf-8"
        match = re.search(r'url:\s*"([^"]+?\.mp3[^"]*)"', resp.text)
        return match.group(1) if match else None
    except:
        return None

# ===================== 机器人命令 =====================
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("🎵 发送歌曲名，我帮你搜索音乐！")

async def search_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyword = update.message.text.strip()
    user_id = update.effective_user.id
    await update.message.reply_text(f"🔍 正在搜索：{keyword}...")
    musics = search_music(keyword)
    if not musics:
        await update.message.reply_text("❌ 未找到相关歌曲")
        return
    user_music_cache[user_id] = musics
    keyboard = []
    for idx, m in enumerate(musics):
        btn_text = f"{idx+1}. {m['title']} - {m['artist']}"
        keyboard.append([InlineKeyboardButton(btn_text, callback_data=f"music_{idx}")])
    await update.message.reply_text("✅ 搜索结果（点击选择）：", reply_markup=InlineKeyboardMarkup(keyboard))

async def callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id
    data = query.data
    if not data.startswith("music_"):
        return
    idx = int(data.replace("music_", ""))
    musics = user_music_cache.get(user_id, [])
    if idx >= len(musics):
        await query.edit_message_text("❌ 选择无效")
        return
    music = musics[idx]
    await query.edit_message_text(f"⏳ 正在获取：{music['title']}...")
    mp3_url = get_music_url(music["link"])
    if not mp3_url:
        await query.edit_message_text("❌ 无法获取音乐链接")
        return
    try:
        await context.bot.send_audio(chat_id=query.message.chat_id, audio=mp3_url, title=music["title"], performer=music["artist"])
        await query.edit_message_text(f"✅ 已发送：{music['title']}")
    except:
        await query.edit_message_text(f"🎧 音乐链接：\n{mp3_url}")

# ===================== 注册 =====================
tg_app.add_handler(CommandHandler("start", start))
tg_app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, search_handler))
tg_app.add_handler(CallbackQueryHandler(callback_handler))

# ===================== Web Service =====================
@app.post("/webhook")
async def webhook(request: Request):
    data = await request.json()
    update = Update.de_json(data, tg_app.bot)
    await tg_app.process_update(update)
    return Response(status_code=200)

@app.get("/")
def index():
    return {"status": "running"}
