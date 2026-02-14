import os
import asyncio
import logging
import urllib.parse
from pyrogram import Client, filters
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from aiohttp import web
from pyrogram.file_id import FileId, FileType
from pyrogram.raw.functions.upload import GetFile
from pyrogram.raw.types import InputDocumentFileLocation, InputFileLocation

# --- CONFIGURATION (Render Environment se lega) ---
API_ID = int(os.environ.get("API_ID", 12345))
API_HASH = os.environ.get("API_HASH", "")
BOT_TOKEN = os.environ.get("BOT_TOKEN", "")

# Render Public Link (Bina last slash ke)
# Example: https://myapp.onrender.com
BOT_URL = os.environ.get("BOT_URL", "") 

# Livebox WebApp Link
WEB_APP_URL = os.environ.get("WEB_APP_URL", "https://flyboxwala.blogspot.com")

PORT = int(os.environ.get("PORT", 8080))

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# --- BOT SETUP ---
app = Client("RenderSeekBot", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN, workers=50)

# --- 🛠️ STREAMER CLASS (Seeking Support) ---
class ByteStreamer:
    def __init__(self, client: Client, file_id: FileId):
        self.client = client
        self.file_id = file_id
        
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
                if not result.bytes: break
                yield result.bytes
                offset += len(result.bytes)
                limit -= len(result.bytes)
                if len(result.bytes) < to_read: break 
            except Exception as e:
                logger.error(f"Stream Error: {e}")
                break

# --- WEB SERVER ---
routes = web.RouteTableDef()

@routes.get("/")
async def home(request):
    return web.Response(text="✅ Render Streamer Running!")

@routes.get("/stream/{chat_id}/{message_id}")
async def stream_handler(request):
    try:
        chat_id = int(request.match_info['chat_id'])
        message_id = int(request.match_info['message_id'])
        
        message = await app.get_messages(chat_id, message_id)
        media = message.video or message.document or message.audio
        
        if not media: return web.Response(status=404)

        file_id_obj = FileId.decode(media.file_id)
        file_size = media.file_size
        file_name = getattr(media, "file_name", "video.mp4") or "video.mp4"
        mime_type = getattr(media, "mime_type", "video/mp4") or "video/mp4"

        # --- SEEKING FIX FOR RENDER ---
        range_header = request.headers.get("Range")
        from_bytes, until_bytes = 0, file_size - 1
        
        if range_header:
            try:
                parts = range_header.replace("bytes=", "").split("-")
                from_bytes = int(parts[0])
                if len(parts) > 1 and parts[1]:
                    until_bytes = int(parts[1])
            except: pass
        
        content_length = until_bytes - from_bytes + 1
        
        headers = {
            "Content-Type": mime_type,
            "Content-Range": f"bytes {from_bytes}-{until_bytes}/{file_size}",
            "Content-Length": str(content_length),
            "Content-Disposition": f'inline; filename="{file_name}"',
            "Accept-Ranges": "bytes",
            "Access-Control-Allow-Origin": "*",
        }

        # Status 206 is MUST for seeking
        response = web.StreamResponse(status=206, headers=headers)
        await response.prepare(request)

        # Streamer ko offset (jaha user ne skip kiya) se start karo
        streamer = ByteStreamer(app, file_id_obj)
        
        # 512KB Chunk size Render ke liye safe hai
        async for chunk in streamer.yield_chunk(from_bytes, 512*1024, content_length):
            try: await response.write(chunk)
            except: break

        return response

    except Exception as e:
        logger.error(e)
        return web.Response(status=500)

# --- BOT COMMANDS ---
@app.on_message(filters.command("start"))
async def start(client, message):
    await message.reply_text("👋 **Render Bot Active!** Send video.")

@app.on_message(filters.private & (filters.video | filters.document))
async def handle_video(client, message):
    try:
        if not BOT_URL:
            return await message.reply_text("❌ Error: `BOT_URL` Env Variable not set in Render!")

        media = message.video or message.document
        fname = getattr(media, "file_name", "Video.mp4") or "Video.mp4"
        
        # Stream Link
        stream_link = f"{BOT_URL}/stream/{message.chat.id}/{message.id}"
        
        # Web App Link
        web_link = f"{WEB_APP_URL}/?src={urllib.parse.quote(stream_link)}&name={urllib.parse.quote(fname)}"

        await message.reply_text(
            f"✅ **Link Ready!**\n📂 `{fname}`\n👇 **Click to Play:**",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("▶️ WATCH VIDEO", url=web_link)]])
        )
    except Exception as e:
        logger.error(e)

# --- RUNNER ---
async def main():
    server = web.Application()
    server.add_routes(routes)
    runner = web.AppRunner(server)
    await runner.setup()
    await web.TCPSite(runner, "0.0.0.0", PORT).start()
    await app.start()
    print("✅ Bot Started on Render!")
    await asyncio.Event().wait()

if __name__ == "__main__":
    loop = asyncio.get_event_loop()
    loop.run_until_complete(main())
