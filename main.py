import os
import logging
import asyncio
import urllib.parse
from aiohttp import web

# --- 🛠️ LOOP FIX (ISKO SABSE UPAR RAKHNA ZARURI HAI) ---
# Ye Pyrogram ko crash hone se bachayega
try:
    loop = asyncio.get_running_loop()
except RuntimeError:
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)

from pyrogram import Client, filters
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton

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
# Session file memory mein rakhenge taaki disk permission error na aaye
if not os.path.exists("sessions"):
    os.makedirs("sessions")

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
    return web.Response(text="✅ Bot & Server Online!")

@routes.get("/stream/{chat_id}/{message_id}")
async def stream_handler(request):
    try:
        chat_id = int(request.match_info['chat_id'])
        message_id = int(request.match_info['message_id'])
        
        try:
            message = await app.get_messages(chat_id, message_id)
        except Exception:
            return web.Response(status=404, text="File Not Found (Check Channel)")

        media = message.video or message.document or message.audio
        if not media:
            return web.Response(status=400, text="No Media Found")

        file_name = getattr(media, "file_name", "video.mp4") or "video.mp4"
        mime_type = getattr(media, "mime_type", "video/mp4") or "video/mp4"
        file_size = getattr(media, "file_size", 0)

        # Streaming Logic
        async def file_generator():
            try:
                async for chunk in app.stream_media(message):
                    yield chunk
            except Exception as e:
                logger.error(f"Stream interrupted: {e}")

        return web.Response(
            body=file_generator(),
            headers={
                'Content-Type': mime_type,
                'Content-Disposition': f'inline; filename="{file_name}"',
                'Content-Length': str(file_size),
                'Access-Control-Allow-Origin': '*'
            }
        )
    except Exception as e:
        logger.error(f"Handler Error: {e}")
        return web.Response(status=500, text="Server Error")

# --- BOT COMMANDS ---

@app.on_message(filters.command("start"))
async def start(client, message):
    await message.reply_text(
        f"👋 **Bot Started!**\n\nServer Link: `{PUBLIC_URL}`\nWaiting for files..."
    )

@app.on_message(filters.private & (filters.video | filters.document | filters.audio))
async def media_handler(client, message):
    try:
        chat_id = message.chat.id
        msg_id = message.id
        media = message.video or message.document or message.audio
        
        if not media: return

        file_name = getattr(media, "file_name", "file") or "file"
        
        # Link Generation
        stream_link = f"{PUBLIC_URL}/stream/{chat_id}/{msg_id}"
        web_link = f"{WEB_APP_URL}/?src={stream_link}&name={urllib.parse.quote(file_name)}"

        await message.reply_text(
            f"✅ **Ready to Watch!**\n\n"
            f"📂 `{file_name}`\n\n"
            f"🔗 **Stream Link:**\n`{stream_link}`",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("▶️ Watch Online", url=web_link)]
            ])
        )
    except Exception as e:
        logger.error(e)

# --- RUNNER ---
async def start_services():
    # Web Server Start
    app_runner = web.AppRunner(web.Application(client_max_size=1024**3))
    app_runner.app.add_routes(routes)
    await app_runner.setup()
    site = web.TCPSite(app_runner, HOST, PORT)
    await site.start()
    logger.info(f"✅ Web Server running on Port {PORT}")

    # Bot Start
    await app.start()
    logger.info("✅ Telegram Bot Started")
    
    # Keep alive
    await asyncio.Event().wait()

if __name__ == "__main__":
    # Jo loop humne upar banaya tha, usi ko use karenge
    try:
        loop.run_until_complete(start_services())
    except KeyboardInterrupt:
        pass
    except Exception as e:
        logger.error(f"Crash: {e}")
