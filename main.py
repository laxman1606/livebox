import os
import asyncio
import logging
import urllib.parse
from pyrogram import Client, filters
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from aiohttp import web

# --- ⚙️ CONFIGURATION ---
API_ID = int(os.environ.get("API_ID", "0")) 
API_HASH = os.environ.get("API_HASH", "")
BOT_TOKEN = os.environ.get("BOT_TOKEN", "")
PUBLIC_URL = os.environ.get("PUBLIC_URL", "https://your-app.onrender.com")
WEB_APP_URL = os.environ.get("WEB_APP_URL", "https://apki-website.netlify.app")
PORT = int(os.environ.get("PORT", 8080))
HOST = "0.0.0.0"

# --- LOGGING ---
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# --- BOT SETUP ---
if not os.path.exists("sessions"):
    os.makedirs("sessions")

# Plugins=None aur No_Updates=False default hain, explicitly set karne ki zaroorat nahi
app = Client(
    "sessions/DiskWala_Render",
    api_id=API_ID,
    api_hash=API_HASH,
    bot_token=BOT_TOKEN
)

# --- WEB SERVER ---
routes = web.RouteTableDef()

@routes.get("/")
async def status_check(request):
    return web.Response(text="✅ DiskWala Bot is Online!")

@routes.get("/stream/{chat_id}/{message_id}")
async def stream_handler(request):
    try:
        chat_id = int(request.match_info['chat_id'])
        message_id = int(request.match_info['message_id'])
        
        try:
            message = await app.get_messages(chat_id, message_id)
        except Exception:
            return web.Response(status=404, text="Message Not Found")

        media = message.video or message.document or message.audio
        if not media:
            return web.Response(status=400, text="No Media Found")

        file_name = getattr(media, "file_name", "video.mp4") or "video.mp4"
        mime_type = getattr(media, "mime_type", "video/mp4") or "video/mp4"
        file_size = getattr(media, "file_size", 0)

        headers = {
            'Content-Type': mime_type,
            'Content-Disposition': f'inline; filename="{file_name}"',
            'Access-Control-Allow-Origin': '*',
            'Content-Length': str(file_size)
        }

        async def file_generator():
            async for chunk in app.stream_media(message):
                yield chunk

        return web.Response(body=file_generator(), headers=headers)

    except Exception as e:
        logger.error(f"Stream Error: {e}")
        return web.Response(status=500, text=str(e))

# --- BOT COMMANDS ---
@app.on_message(filters.command("start"))
async def start(client, message):
    await message.reply_text(
        f"👋 **Bot Online!**\nServer: {PUBLIC_URL}\nVideo bhejo, link milega."
    )

@app.on_message(filters.private & (filters.video | filters.document | filters.audio))
async def media_handler(client, message):
    try:
        chat_id = message.chat.id
        msg_id = message.id
        media = message.video or message.document or message.audio
        
        if not media: return

        fname = getattr(media, "file_name", "file") or "file"
        stream_link = f"{PUBLIC_URL}/stream/{chat_id}/{msg_id}"
        safe_filename = urllib.parse.quote(fname)
        web_app_link = f"{WEB_APP_URL}/?src={stream_link}&name={safe_filename}"

        await message.reply_text(
            f"✅ **Link Generated:**\n`{stream_link}`",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("▶️ Play Online", url=web_app_link)]
            ])
        )
    except Exception as e:
        logger.error(e)

# --- RUNNER (FIXED FOR RENDER) ---
async def start_services():
    # Web Server
    app_runner = web.AppRunner(web.Application(client_max_size=1024**3))
    app_runner.app.add_routes(routes)
    await app_runner.setup()
    site = web.TCPSite(app_runner, HOST, PORT)
    await site.start()
    logger.info(f"✅ Web Server on Port {PORT}")
    
    # Telegram Bot
    await app.start()
    logger.info("✅ Telegram Bot Started")
    
    # Keep Process Alive
    await asyncio.Event().wait()

if __name__ == "__main__":
    # YAHAN FIX KIYA HAI: Loop manually create kar rahe hain
    try:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        loop.run_until_complete(start_services())
    except KeyboardInterrupt:
        pass
    except Exception as e:
        logger.error(f"Fatal Error: {e}")
