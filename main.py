import os
import asyncio
import logging
import urllib.parse
from aiohttp import web
from pyrogram import Client, filters
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton

# --- 🛠️ ASYNC LOOP FIX ---
try:
    loop = asyncio.get_running_loop()
except RuntimeError:
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)

# --- ⚙️ CONFIGURATION ---
API_ID = int(os.environ.get("API_ID", "0")) 
API_HASH = os.environ.get("API_HASH", "")
BOT_TOKEN = os.environ.get("BOT_TOKEN", "")
PUBLIC_URL = os.environ.get("PUBLIC_URL", "").rstrip('/')
WEB_APP_URL = os.environ.get("WEB_APP_URL", "https://flyboxwala.blogspot.com").rstrip('/')
PORT = int(os.environ.get("PORT", 8080))

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = Client("sessions/DiskWala", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN)

# --- WEB SERVER ---
routes = web.RouteTableDef()

@routes.get("/")
async def status_check(request):
    return web.Response(text="✅ Bot is Alive and Running!")

@routes.get("/stream/{chat_id}/{message_id}")
async def stream_handler(request):
    try:
        chat_id = int(request.match_info['chat_id'])
        message_id = int(request.match_info['message_id'])
        
        message = await app.get_messages(chat_id, message_id)
        if not message: return web.Response(status=404, text="File Not Found")

        media = message.video or message.document or message.audio
        if not media: return web.Response(status=400, text="No Media")

        file_size = media.file_size
        mime_type = getattr(media, "mime_type", "video/mp4")
        file_name = getattr(media, "file_name", "video.mp4")

        # --- RANGE REQUEST HANDLING (For Fast Loading & Seeking) ---
        range_header = request.headers.get('Range')
        start = 0
        if range_header:
            # Example: bytes=0-1024
            bytes_range = range_header.replace('bytes=', '').split('-')
            start = int(bytes_range[0])
            
        # Headers for Video Player
        headers = {
            'Content-Type': mime_type,
            'Content-Disposition': f'inline; filename="{file_name}"',
            'Accept-Ranges': 'bytes',
            'Access-Control-Allow-Origin': '*',
            'Access-Control-Allow-Methods': 'GET, OPTIONS',
            'Access-Control-Allow-Headers': 'Range, Content-Type',
        }

        if range_header:
            headers['Content-Range'] = f'bytes {start}-{file_size-1}/{file_size}'
            status = 206 # Partial Content
        else:
            headers['Content-Length'] = str(file_size)
            status = 200

        # Generator with offset support
        async def file_generator():
            try:
                # Telegram se usi point se download shuru karega jahan player ko chahiye
                async for chunk in app.stream_media(message, offset=start):
                    yield chunk
            except Exception as e:
                logger.error(f"Stream Error: {e}")

        return web.Response(body=file_generator(), headers=headers, status=status)

    except Exception as e:
        logger.error(f"Main Error: {e}")
        return web.Response(status=500, text="Server Error")

# --- BOT HANDLERS ---
@app.on_message(filters.command("start"))
async def start(client, message):
    await message.reply_text("👋 **Bot is Ready!**\nVideo bhejo, player link pao.")

@app.on_message(filters.private & (filters.video | filters.document | filters.audio))
async def media_handler(client, message):
    try:
        chat_id = message.chat.id
        msg_id = message.id
        media = message.video or message.document or message.audio
        fname = getattr(media, "file_name", "video.mp4")

        stream_link = f"{PUBLIC_URL}/stream/{chat_id}/{msg_id}"
        web_link = f"{WEB_APP_URL}/?src={stream_link}&name={urllib.parse.quote(fname)}"

        await message.reply_text(
            f"✅ **Link Generated!**\n\n📂 `{fname}`\n\n"
            f"🔗 **Direct Link:**\n`{stream_link}`",
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("▶️ Play Online", url=web_link)
            ]])
        )
    except Exception as e:
        logger.error(e)

async def start_services():
    app_runner = web.AppRunner(web.Application())
    app_runner.app.add_routes(routes)
    await app_runner.setup()
    await web.TCPSite(app_runner, "0.0.0.0", PORT).start()
    await app.start()
    await asyncio.Event().wait()

if __name__ == "__main__":
    loop.run_until_complete(start_services())
