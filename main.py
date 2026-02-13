import os
import logging
import asyncio
import urllib.parse
from aiohttp import web
from pyrogram import Client, filters
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton

# --- ⚙️ CONFIGURATION ---
API_ID = int(os.environ.get("API_ID", "0"))
API_HASH = os.environ.get("API_HASH", "")
BOT_TOKEN = os.environ.get("BOT_TOKEN", "")
PUBLIC_URL = os.environ.get("PUBLIC_URL", "https://your-app.onrender.com").rstrip("/")
WEB_APP_URL = os.environ.get("WEB_APP_URL", "https://your-website.net").rstrip("/")
PORT = int(os.environ.get("PORT", 8080))

# --- LOGGING ---
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# --- BOT INIT ---
# in_memory=True rakhna zaruri hai Render ke liye
bot = Client(
    "DiskWala_Render",
    api_id=API_ID,
    api_hash=API_HASH,
    bot_token=BOT_TOKEN,
    in_memory=True
)

# --- WEB SERVER ROUTES ---
routes = web.RouteTableDef()

@routes.get("/")
async def root_handler(request):
    return web.Response(text="✅ Bot & Server are Online!")

@routes.get("/stream/{chat_id}/{message_id}")
async def stream_handler(request):
    try:
        chat_id = int(request.match_info['chat_id'])
        message_id = int(request.match_info['message_id'])

        try:
            message = await bot.get_messages(chat_id, message_id)
        except Exception:
            return web.Response(status=404, text="Message Not Found")

        media = message.video or message.document or message.audio
        if not media:
            return web.Response(status=400, text="No Media Found")

        file_name = getattr(media, "file_name", "video.mp4")
        mime_type = getattr(media, "mime_type", "video/mp4")
        file_size = getattr(media, "file_size", 0)

        # Range Request Logic (Seeking Support)
        range_header = request.headers.get('Range')
        start = 0
        
        headers = {
            'Content-Type': mime_type,
            'Content-Disposition': f'inline; filename="{file_name}"',
            'Accept-Ranges': 'bytes',
            'Access-Control-Allow-Origin': '*'
        }

        if range_header:
            bytes_range = range_header.replace('bytes=', '').split('-')
            start = int(bytes_range[0])
            headers['Content-Range'] = f'bytes {start}-{file_size-1}/{file_size}'
            status_code = 206
        else:
            headers['Content-Length'] = str(file_size)
            status_code = 200

        # Data Generator
        async def file_generator():
            try:
                async for chunk in bot.stream_media(message, offset=start):
                    yield chunk
            except Exception:
                pass

        return web.Response(body=file_generator(), headers=headers, status=status_code)
    
    except Exception as e:
        logger.error(f"Stream Error: {e}")
        return web.Response(status=500, text="Server Error")

# --- BOT HANDLERS ---
@bot.on_message(filters.command("start"))
async def start_msg(client, message):
    await message.reply_text("👋 **Bot is Active!**\nSend a video to get the stream link.")

@bot.on_message(filters.private & (filters.video | filters.document | filters.audio))
async def media_handler(client, message):
    try:
        media = message.video or message.document or message.audio
        fname = getattr(media, "file_name", "video.mp4")
        
        stream_link = f"{PUBLIC_URL}/stream/{message.chat.id}/{message.id}"
        web_link = f"{WEB_APP_URL}/?src={stream_link}&name={urllib.parse.quote(fname)}"
        
        await message.reply_text(
            f"✅ **Link Ready:**\n`{stream_link}`",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("▶️ Play Online", url=web_link)]
            ])
        )
    except Exception as e:
        logger.error(e)

# --- MAIN EXECUTION (FIXED LOOP) ---
async def main():
    # 1. Start Bot First
    logger.info("Starting Telegram Bot...")
    await bot.start()
    
    # 2. Start Web Server Manually (No create_app clash)
    logger.info("Starting Web Server...")
    app = web.Application()
    app.add_routes(routes)
    
    runner = web.AppRunner(app)
    await runner.setup()
    
    # Render binds to 0.0.0.0 automatically
    site = web.TCPSite(runner, "0.0.0.0", PORT)
    await site.start()
    
    logger.info(f"✅ Server Running on Port {PORT}")
    
    # 3. Keep Running Forever
    await asyncio.Event().wait()

if __name__ == "__main__":
    # Explicitly creating a loop to avoid RuntimeError
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        loop.run_until_complete(main())
    except KeyboardInterrupt:
        pass
    except Exception as e:
        logger.error(f"Fatal Error: {e}")
