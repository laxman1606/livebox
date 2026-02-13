import os
import logging
from aiohttp import web
from pyrogram import Client, filters
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton
import urllib.parse

# --- ⚙️ CONFIGURATION ---
API_ID = int(os.environ.get("API_ID", "0"))
API_HASH = os.environ.get("API_HASH", "")
BOT_TOKEN = os.environ.get("BOT_TOKEN", "")
PUBLIC_URL = os.environ.get("PUBLIC_URL", "https://your-app.onrender.com").rstrip("/")
WEB_APP_URL = os.environ.get("WEB_APP_URL", "https://your-blog.blogspot.com").rstrip("/")
PORT = int(os.environ.get("PORT", 8080))

# --- LOGGING ---
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# --- BOT SETUP ---
# Bot ko yahan initialize karenge, start baad mein karenge
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
async def root_route(request):
    return web.Response(text="✅ Bot is Online and Running!")

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

        # Range Request Logic (Seek Support)
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

        # Streaming Generator
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

# --- BOT COMMANDS ---
@bot.on_message(filters.command("start"))
async def start_msg(client, message):
    await message.reply_text("👋 **Bot is Alive!**\nSend me a video.")

@bot.on_message(filters.private & (filters.video | filters.document | filters.audio))
async def media_process(client, message):
    try:
        media = message.video or message.document or message.audio
        fname = getattr(media, "file_name", "video.mp4")
        
        stream_link = f"{PUBLIC_URL}/stream/{message.chat.id}/{message.id}"
        online_link = f"{WEB_APP_URL}/?src={stream_link}&name={urllib.parse.quote(fname)}"
        
        await message.reply_text(
            f"✅ **Link Ready:**\n`{stream_link}`",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("▶️ Watch Online", url=online_link)]
            ])
        )
    except Exception as e:
        logger.error(e)

# --- SERVER STARTUP & SHUTDOWN HOOKS ---
async def on_startup(app):
    logger.info("Starting Bot...")
    await bot.start()
    logger.info("Bot Started!")

async def on_cleanup(app):
    logger.info("Stopping Bot...")
    await bot.stop()

# --- MAIN EXECUTION ---
if __name__ == "__main__":
    # Web App banayenge
    app = web.Application()
    app.add_routes(routes)
    
    # Bot ko Web App ke startup process ke saath jod denge
    app.on_startup.append(on_startup)
    app.on_cleanup.append(on_cleanup)
    
    # Server Run (Ye khud loop handle karega)
    web.run_app(app, host="0.0.0.0", port=PORT)
