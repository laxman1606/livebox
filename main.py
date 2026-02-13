import os
import logging
import asyncio
from aiohttp import web
from pyrogram import Client, filters
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton
import urllib.parse

# --- LOGGING ---
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# --- CONFIGURATION (Error Handling ke saath) ---
try:
    API_ID = int(os.environ.get("API_ID"))
    API_HASH = os.environ.get("API_HASH")
    BOT_TOKEN = os.environ.get("BOT_TOKEN")
    # Render PORT environment variable automatically deta hai
    PORT = int(os.environ.get("PORT", 8080)) 
    PUBLIC_URL = os.environ.get("PUBLIC_URL", "http://localhost").rstrip("/")
    WEB_APP_URL = os.environ.get("WEB_APP_URL", "http://localhost").rstrip("/")
except Exception as e:
    logger.error(f"Environment Vars Missing! Check Render Settings: {e}")
    # Default values taaki code crash na ho turant
    API_ID = 0
    API_HASH = ""
    BOT_TOKEN = ""

# --- BOT SETUP ---
bot = Client(
    "DiskWala_Render",
    api_id=API_ID,
    api_hash=API_HASH,
    bot_token=BOT_TOKEN,
    in_memory=True
)

routes = web.RouteTableDef()

@routes.get("/")
async def health_check(request):
    return web.Response(text="✅ Server is Online & Running!")

@routes.get("/stream/{chat_id}/{message_id}")
async def stream_handler(request):
    try:
        chat_id = int(request.match_info['chat_id'])
        message_id = int(request.match_info['message_id'])

        # File get karna
        message = await bot.get_messages(chat_id, message_id)
        if not message: return web.Response(status=404, text="Message Not Found")
        
        media = message.video or message.document or message.audio
        if not media: return web.Response(status=404, text="No Media")

        file_size = getattr(media, "file_size", 0)
        file_name = getattr(media, "file_name", "video.mp4")
        mime_type = getattr(media, "mime_type", "video/mp4")

        # Range Request (Seeking) Logic
        range_header = request.headers.get('Range')
        start = 0
        end = file_size - 1
        
        if range_header:
            bytes_range = range_header.replace('bytes=', '').split('-')
            start = int(bytes_range[0])
            if len(bytes_range) > 1 and bytes_range[1]:
                end = int(bytes_range[1])
        
        headers = {
            'Content-Type': mime_type,
            'Accept-Ranges': 'bytes',
            'Content-Range': f'bytes {start}-{end}/{file_size}',
            'Content-Length': str(end - start + 1),
            'Content-Disposition': f'inline; filename="{file_name}"',
            'Access-Control-Allow-Origin': '*'
        }

        async def chunk_generator():
            try:
                # Telegram se stream karke browser ko bhejna
                async for chunk in bot.stream_media(message, offset=start):
                    yield chunk
            except Exception:
                pass

        return web.Response(body=chunk_generator(), headers=headers, status=206 if range_header else 200)

    except Exception as e:
        logger.error(f"Stream Error: {e}")
        return web.Response(status=500, text="Internal Server Error")

# --- BOT COMMANDS ---
@bot.on_message(filters.command("start"))
async def start_handler(client, message):
    await message.reply_text("👋 **Bot is Live!**\nSend me a file.")

@bot.on_message(filters.private & (filters.video | filters.document | filters.audio))
async def file_handler(client, message):
    try:
        media = message.video or message.document or message.audio
        fname = getattr(media, "file_name", "file")
        
        stream_link = f"{PUBLIC_URL}/stream/{message.chat.id}/{message.id}"
        web_link = f"{WEB_APP_URL}/?src={stream_link}&name={urllib.parse.quote(fname)}"
        
        await message.reply_text(
            f"✅ **Link Generated:**\n`{stream_link}`",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("▶️ Watch Online", url=web_link)]
            ])
        )
    except Exception as e:
        logger.error(e)

# --- BACKGROUND TASKS ---
async def start_bot_background(app):
    # Ye Bot ko background mein start karega taaki PORT block na ho
    logger.info("Server started! Now connecting Bot...")
    asyncio.create_task(bot.start())

async def stop_bot_background(app):
    await bot.stop()

# --- MAIN RUNNER ---
if __name__ == "__main__":
    app = web.Application()
    app.add_routes(routes)
    
    # Bot ko startup process mein daal diya
    app.on_startup.append(start_bot_background)
    app.on_cleanup.append(stop_bot_background)
    
    # Ye Render ke liye sabse important line hai
    logger.info(f"Binding to Port {PORT}")
    web.run_app(app, host="0.0.0.0", port=PORT)
