import os
import logging
import asyncio
import urllib.parse
from aiohttp import web

# --- 🛠️ LOOP FIX ---
try:
    loop = asyncio.get_running_loop()
except RuntimeError:
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)

from pyrogram import Client, filters
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton

# --- Imports for Seeking (Fixed) ---
from pyrogram.file_id import FileId, FileType
from pyrogram.raw.functions.upload import GetFile
from pyrogram.raw.types import InputDocumentFileLocation, InputFileLocation

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

app = Client(
    "sessions/DiskWala_Render",
    api_id=API_ID,
    api_hash=API_HASH,
    bot_token=BOT_TOKEN,
    workers=50,
    ipv6=False
)

# --- 🛠️ FIXED STREAMER CLASS (Better Logic) ---
class ByteStreamer:
    def __init__(self, client: Client, file_id: FileId):
        self.client = client
        self.file_id = file_id

        # Video/Document Detection Logic
        if file_id.file_type in (FileType.VIDEO, FileType.DOCUMENT, FileType.AUDIO):
            self.location = InputDocumentFileLocation(
                id=file_id.media_id,
                access_hash=file_id.access_hash,
                file_reference=file_id.file_reference,
                thumb_size=""
            )
        else:
            self.location = InputFileLocation(
                volume_id=file_id.volume_id,
                local_id=file_id.local_id,
                secret=file_id.secret,
                file_reference=file_id.file_reference
            )

    async def yield_chunk(self, offset, chunk_size, limit):
        # Ye loop chunk-by-chunk data bhejta hai
        while limit > 0:
            to_read = min(limit, chunk_size)
            try:
                result = await self.client.invoke(
                    GetFile(
                        location=self.location,
                        offset=offset,
                        limit=to_read
                    )
                )
                if not result.bytes: break # End of file
                
                yield result.bytes
                
                read_len = len(result.bytes)
                offset += read_len
                limit -= read_len
                
                if read_len < to_read: break 
            except Exception as e:
                logging.error(f"Stream Error: {e}")
                break

# --- WEB SERVER ---
routes = web.RouteTableDef()

@routes.get("/")
async def status_check(request):
    return web.Response(text="✅ Bot Online with Fixed Streaming!")

@routes.get("/stream/{chat_id}/{message_id}")
async def stream_handler(request):
    try:
        chat_id = int(request.match_info['chat_id'])
        message_id = int(request.match_info['message_id'])
        
        try:
            message = await app.get_messages(chat_id, message_id)
        except:
            return web.Response(status=404, text="File Not Found")

        media = message.video or message.document or message.audio
        if not media:
            return web.Response(status=400, text="No Media")

        # Variables
        file_name = getattr(media, "file_name", "video.mp4") or "video.mp4"
        mime_type = getattr(media, "mime_type", "video/mp4") or "video/mp4"
        file_size = getattr(media, "file_size", 0)
        
        file_id_obj = FileId.decode(media.file_id)

        # --- CORRECT RANGE LOGIC ---
        range_header = request.headers.get("Range")
        from_bytes, until_bytes = 0, file_size - 1
        
        if range_header:
            try:
                parts = range_header.replace("bytes=", "").split("-")
                from_bytes = int(parts[0])
                if len(parts) > 1 and parts[1]:
                    until_bytes = int(parts[1])
            except: pass
        
        # Calculate content length based on range
        content_length = until_bytes - from_bytes + 1
        
        headers = {
            'Content-Type': mime_type,
            'Content-Range': f"bytes {from_bytes}-{until_bytes}/{file_size}",
            'Content-Length': str(content_length),
            'Content-Disposition': f'inline; filename="{file_name}"',
            'Accept-Ranges': 'bytes',
            'Access-Control-Allow-Origin': '*'
        }

        # Status 206 Partial Content (Ye loading fix karega)
        response = web.StreamResponse(status=206, headers=headers)
        await response.prepare(request)

        streamer = ByteStreamer(app, file_id_obj)
        
        # 1MB Chunks (Standard for smoothness)
        async for chunk in streamer.yield_chunk(from_bytes, 1024*1024, content_length):
            try: await response.write(chunk)
            except: break

        return response

    except Exception as e:
        logger.error(f"Handler Error: {e}")
        return web.Response(status=500)

# --- BOT COMMANDS (NO CHANGES) ---

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
    app_runner = web.AppRunner(web.Application(client_max_size=1024**3))
    app_runner.app.add_routes(routes)
    await app_runner.setup()
    site = web.TCPSite(app_runner, HOST, PORT)
    await site.start()
    logger.info(f"✅ Web Server running on Port {PORT}")

    await app.start()
    logger.info("✅ Telegram Bot Started")
    
    await asyncio.Event().wait()

if __name__ == "__main__":
    try:
        loop.run_until_complete(start_services())
    except KeyboardInterrupt:
        pass
    except Exception as e:
        logger.error(f"Crash: {e}")
