import logging
from pathlib import Path

from pyrogram import Client, filters
from pyrogram.types import Message

import config
from handlers.queue_manager import queue_manager
from utils.progress_bar import format_size

logger = logging.getLogger(__name__)


async def is_owner(_, __, message: Message) -> bool:
    """Strict owner check. Drops messages from all non-owners."""
    return bool(message.from_user and message.from_user.id == config.OWNER_ID)


owner_filter = filters.create(is_owner)


def register_video_handlers(app: Client) -> None:
    """Register message handlers for owner."""

    @app.on_message(owner_filter & filters.command(["start", "help"]))
    async def start_handler(client: Client, message: Message):
        text = (
            "👋 **Hello Owner!**\n\n"
            "I am your exclusive **Video Compressor Bot** powered by FFmpeg.\n\n"
            "**How to use:**\n"
            "1. Send me any video (native Telegram video or file up to 2 GB).\n"
            "2. I will inspect its resolution and present interactive compression options.\n"
            "3. Choose your desired quality, and I will compress it with live progress updates every 10 seconds.\n"
            "4. Your compressed video will be returned directly as a playable video streaming reply!"
        )
        await message.reply_text(text, quote=True)

    @app.on_message(owner_filter & (filters.video | filters.document))
    async def media_handler(client: Client, message: Message):
        file_id = None
        file_name = "video.mp4"
        file_size = 0

        if message.video:
            file_id = message.video.file_id
            file_name = message.video.file_name or f"video_{message.video.file_unique_id}.mp4"
            file_size = message.video.file_size
        elif message.document:
            doc = message.document
            mime = (doc.mime_type or "").lower()
            ext = Path(doc.file_name or "").suffix.lower()

            is_video = (
                mime.startswith("video/")
                or ext in config.SUPPORTED_VIDEO_EXTENSIONS
            )

            if not is_video:
                await message.reply_text(
                    "⚠️ The document you sent does not appear to be a supported video file.",
                    quote=True,
                )
                return

            file_id = doc.file_id
            file_name = doc.file_name or f"doc_video_{doc.file_unique_id}.mp4"
            file_size = doc.file_size

        if not file_id:
            return

        # Check 2 GB limit
        if file_size > config.MAX_FILE_SIZE:
            await message.reply_text(
                f"❌ **File too large!**\n\n"
                f"• Video Size: `{format_size(file_size)}`\n"
                f"• Maximum Allowed: `{format_size(config.MAX_FILE_SIZE)}` (2 GB)\n\n"
                f"Please send a video smaller than 2 GB.",
                quote=True,
            )
            return

        # Enqueue the task
        await queue_manager.add_task(
            message=message,
            file_id=file_id,
            file_name=file_name,
            file_size=file_size,
        )

    @app.on_message(owner_filter & filters.text)
    async def text_handler(client: Client, message: Message):
        await message.reply_text(
            "📹 Please send a video or video file (up to 2 GB) that you want to compress.",
            quote=True,
        )
