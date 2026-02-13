import os
import asyncio
import logging
import urllib.parse
import math
from pyrogram import Client, filters, errors
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from aiohttp import web

# --- ⚙️ CONFIGURATION (Render Environment Variables se lega) ---
# Ye sab aapko Render ke "Environment Variables" tab mein daalna hai
API_ID = int(os.environ.get("API_ID", "0")) 
API_HASH = os.environ.get("API_HASH", "")
BOT_TOKEN = os.environ.get("BOT_TOKEN", "")

# Render App URL (Example: https://my-bot.onrender.com)
# Last mein '/' mat lagana
PUBLIC_URL = os.environ.get("PUBLIC_URL", "https://your-app.onrender.com")

# Netlify Website Link
WEB_APP_URL = os.environ.get("WEB_APP_URL", "https://apki-website.netlify.app")

# Render automatically PORT assign karta hai
PORT = int(os.environ.get("PORT", 8080))
HOST = "0.0.0.0"

# --- LOGGING ---
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# --- BOT SETUP ---
# WorkDir zaruri hai taaki session file save ho sake
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

# Custom Stream Response for Render (Memory Efficient)
class TelegramByteStream:
    def __init__(self, client, message, file_id, total_size):
        self.client = client
        self.message = message
        self.file_id = file_id
        self.total_size = total_size
        self.current_offset = 0

    async def __aiter__(self):
        # 1MB Chunks mein stream karega taaki RAM full na ho
        chunk_size = 1024 * 1024 
        async for chunk in self.client.stream_media(self.message, limit=0, offset=0):
            yield chunk

@routes.get("/")
async def status_check(request):
    return web.Response(text="✅ DiskWala Bot is Running on Render!")

@routes.get("/stream/{chat_id}/{message_id}")
async def stream_handler(request):
    try:
        chat_id = int(request.match_info['chat_id'])
        message_id = int(request.match_info['message_id'])
        
        try:
            message = await app.get_messages(chat_id, message_id)
        except Exception as e:
            return web.Response(status=404, text="Message Not Found or Bot Removed from Channel")

        # Smart Media Detection
        media = message.video or message.document or message.audio
        if not media:
            return web.Response(status=400, text="No Media Found")

        file_name = getattr(media, "file_name", "video.mp4") or "video.mp4"
        mime_type = getattr(media, "mime_type", "video/mp4") or "video/mp4"
        file_size = getattr(media, "file_size", 0)

        # HEADERS setup
        headers = {
            'Content-Type': mime_type,
            'Content-Disposition': f'inline; filename="{file_name}"',
            'Access-Control-Allow-Origin': '*',
            'Accept-Ranges': 'bytes',
            'Content-Length': str(file_size)
        }

        # NOTE: Render Free tier par 'Range' requests (Seek forward/backward) 
        # perfect nahi chalti bina complex proxy ke. Ye code direct stream karega.
        
        # Generator function to stream data directly from Telegram to Browser
        async def file_generator():
            try:
                async for chunk in app.stream_media(message):
                    yield chunk
            except Exception as e:
                logger.error(f"Streaming Error: {e}")

        return web.Response(body=file_generator(), headers=headers)

    except Exception as e:
        logger.error(f"Stream Error: {e}")
        return web.Response(status=500, text=f"Error: {str(e)}")

# --- BOT COMMANDS ---

@app.on_message(filters.command("start"))
async def start(client, message):
    await message.reply_text(
        "👋 **Render Bot Active!**\n\n"
        "Video bhejo ya forward karo, main Player Link bana dunga.\n"
        f"Server: `{PUBLIC_URL}`"
    )

@app.on_message(filters.private & (filters.video | filters.document | filters.audio))
async def media_handler(client, message):
    try:
        chat_id = message.chat.id
        msg_id = message.id
        
        media = message.video or message.document or message.audio
        
        if not media:
            await message.reply_text("❌ Is file ko main process nahi kar sakta.")
            return

        fname = getattr(media, "file_name", "Unknown File") or "Unknown File"
        fsize = media.file_size if hasattr(media, "file_size") else 0
        size_mb = f"{fsize / 1024 / 1024:.2f} MB"

        # Generate Links
        stream_link = f"{PUBLIC_URL}/stream/{chat_id}/{msg_id}"
        safe_filename = urllib.parse.quote(fname)
        web_app_link = f"{WEB_APP_URL}/?src={stream_link}&name={safe_filename}"

        await message.reply_text(
            text=(
                f"✅ **File Ready!**\n\n"
                f"📂 **Name:** `{fname}`\n"
                f"💾 **Size:** `{size_mb}`\n\n"
                f"🔗 **Raw Link:**\n`{stream_link}`\n\n"
                f"👇 **Click to Watch:**"
            ),
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("▶️ Watch in Web App", url=web_app_link)]
            ])
        )

    except Exception as e:
        logger.error(f"Handler Error: {e}")
        await message.reply_text(f"❌ Error: {e}")

# --- RUNNER ---
async def start_services():
    # Web Server Setup
    app_runner = web.AppRunner(web.Application(client_max_size=1024**3))
    app_runner.app.add_routes(routes)
    await app_runner.setup()
    
    # Render Port Binding
    site = web.TCPSite(app_runner, HOST, PORT)
    await site.start()
    
    logger.info(f"✅ Server running on Port {PORT}")
    
    # Start Bot
    await app.start()
    
    # Keep running
    await asyncio.Event().wait()

if __name__ == "__main__":
    loop = asyncio.get_event_loop()
    try:
        loop.run_until_complete(start_services())
    except KeyboardInterrupt:
        pass
    except Exception as e:
        logger.error(e)