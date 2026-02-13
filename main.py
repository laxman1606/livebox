import os
import asyncio
import logging
import urllib.parse
from aiohttp import web
from pyrogram import Client, filters, idle
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton

# --- ⚙️ CONFIGURATION ---
API_ID = int(os.environ.get("API_ID", "0"))
API_HASH = os.environ.get("API_HASH", "")
BOT_TOKEN = os.environ.get("BOT_TOKEN", "")
PUBLIC_URL = os.environ.get("PUBLIC_URL", "").rstrip('/')
WEB_APP_URL = os.environ.get("WEB_APP_URL", "https://flyboxwala.blogspot.com").rstrip('/')
PORT = int(os.environ.get("PORT", 8080))

# --- LOGGING ---
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# --- BOT & SERVER SETUP ---
# Client ko globally define kiya hai par start async function ke andar karenge
bot = Client(
    "DiskWala_Render",
    api_id=API_ID,
    api_hash=API_HASH,
    bot_token=BOT_TOKEN,
    in_memory=True # Render par session files ka lafda khatam karne ke liye
)

routes = web.RouteTableDef()

@routes.get("/")
async def status_check(request):
    return web.Response(text="✅ Bot is Running Perfectly!")

@routes.get("/stream/{chat_id}/{message_id}")
async def stream_handler(request):
    try:
        chat_id = int(request.match_info['chat_id'])
        message_id = int(request.match_info['message_id'])
        
        message = await bot.get_messages(chat_id, message_id)
        if not message: return web.Response(status=404, text="File Not Found")

        media = message.video or message.document or message.audio
        if not media: return web.Response(status=400, text="No Media")

        file_size = media.file_size
        mime_type = getattr(media, "mime_type", "video/mp4")
        file_name = getattr(media, "file_name", "video.mp4")

        # Range Request Support (For Fast Loading)
        range_header = request.headers.get('Range')
        start = 0
        if range_header:
            bytes_range = range_header.replace('bytes=', '').split('-')
            start = int(bytes_range[0])
            
        headers = {
            'Content-Type': mime_type,
            'Content-Disposition': f'inline; filename="{file_name}"',
            'Accept-Ranges': 'bytes',
            'Access-Control-Allow-Origin': '*',
            'Access-Control-Allow-Methods': 'GET, OPTIONS',
            'Access-Control-Allow-Headers': '*',
        }

        if range_header:
            headers['Content-Range'] = f'bytes {start}-{file_size-1}/{file_size}'
            status = 206
        else:
            headers['Content-Length'] = str(file_size)
            status = 200

        async def file_generator():
            async for chunk in bot.stream_media(message, offset=start):
                yield chunk

        return web.Response(body=file_generator(), headers=headers, status=status)

    except Exception as e:
        logger.error(f"Stream Error: {e}")
        return web.Response(status=500, text="Stream Error")

# --- BOT HANDLERS ---
@bot.on_message(filters.command("start"))
async def start(client, message):
    await message.reply_text("👋 **DiskWala Bot is Ready!**\n\nVideo bhejo, link pao.")

@bot.on_message(filters.private & (filters.video | filters.document | filters.audio))
async def media_handler(client, message):
    try:
        media = message.video or message.document or message.audio
        fname = getattr(media, "file_name", "video.mp4")
        stream_link = f"{PUBLIC_URL}/stream/{message.chat.id}/{message.id}"
        web_link = f"{WEB_APP_URL}/?src={stream_link}&name={urllib.parse.quote(fname)}"

        await message.reply_text(
            f"✅ **Ready to Stream!**\n\n📂 `{fname}`",
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("▶️ Watch Online", url=web_link)
            ]])
        )
    except Exception as e:
        logger.error(f"Handler Error: {e}")

# --- THE MAIN RUNNER ---
async def main():
    # 1. Start Web Server
    server = web.Application()
    server.add_routes(routes)
    runner = web.AppRunner(server)
    await runner.setup()
    await web.TCPSite(runner, "0.0.0.0", PORT).start()
    logger.info(f"✅ Server started on port {PORT}")

    # 2. Start Bot
    await bot.start()
    logger.info("✅ Bot started")

    # 3. Keep Everything Running
    await idle()

    # 4. Cleanup on stop
    await runner.cleanup()

if __name__ == "__main__":
    # Naye Python ke liye ye sabse safe tarika hai
    asyncio.run(main())
