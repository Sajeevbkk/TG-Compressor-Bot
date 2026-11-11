import asyncio
import logging
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional

from pyrogram import Client
from pyrogram.errors import FloodWait, MessageIdInvalid, MessageNotModified
from pyrogram.types import (
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
)

import config
from utils.cleanup import cleanup_path
from utils.ffmpeg_utils import (
    compress_video,
    generate_thumbnail,
    get_available_resolutions,
    probe_video,
)
from utils.progress_bar import (
    ProgressTracker,
    format_size,
    format_time,
)

logger = logging.getLogger(__name__)


async def safe_edit_message(
    client: Client,
    chat_id: int,
    message_id: int,
    text: str,
    reply_markup: Optional[InlineKeyboardMarkup] = None,
) -> None:
    """Safely edit a message with Telegram error tolerance."""
    try:
        await client.edit_message_text(
            chat_id=chat_id,
            message_id=message_id,
            text=text,
            reply_markup=reply_markup,
        )
    except MessageNotModified:
        pass
    except FloodWait as e:
        logger.warning(f"FloodWait while editing message: sleeping {e.value}s")
        await asyncio.sleep(e.value)
    except MessageIdInvalid:
        logger.warning(f"Message {message_id} was deleted or invalid.")
    except Exception as e:
        logger.warning(f"Failed to edit message {message_id}: {e}")


@dataclass
class VideoTask:
    task_id: str
    message: Message
    status_msg: Message
    file_id: str
    file_name: str
    file_size: int
    created_at: float = field(default_factory=time.time)
    choice_future: asyncio.Future = field(default_factory=asyncio.Future)

    @property
    def work_dir(self) -> Path:
        return config.TEMP_DIR / self.task_id


class QueueManager:
    """Manages sequential execution of video compression tasks."""

    def __init__(self):
        self._queue: asyncio.Queue[VideoTask] = asyncio.Queue()
        self._active_tasks: Dict[str, VideoTask] = {}
        self._current_task: Optional[VideoTask] = None
        self._worker_task: Optional[asyncio.Task] = None
        self._client: Optional[Client] = None

    def start(self, client: Client) -> None:
        """Start the background queue worker."""
        self._client = client
        if self._worker_task is None or self._worker_task.done():
            self._worker_task = asyncio.create_task(self._worker_loop())
            logger.info("Video compression queue worker started.")

    async def add_task(
        self,
        message: Message,
        file_id: str,
        file_name: str,
        file_size: int,
    ) -> VideoTask:
        """Create and enqueue a new video compression task."""
        task_id = uuid.uuid4().hex[:8]

        queue_len = self._queue.qsize()
        is_busy = self._current_task is not None or queue_len > 0

        initial_text = (
            f"⏳ Added to queue (Position: #{queue_len + 1}). "
            f"Processing will begin shortly..."
            if is_busy
            else "📥 Initializing video processing..."
        )

        status_msg = await message.reply_text(
            initial_text,
            quote=True,
        )

        task = VideoTask(
            task_id=task_id,
            message=message,
            status_msg=status_msg,
            file_id=file_id,
            file_name=file_name,
            file_size=file_size,
        )

        self._active_tasks[task_id] = task
        await self._queue.put(task)
        logger.info(f"Task {task_id} added to queue. Queue size: {self._queue.qsize()}")
        return task

    def get_task(self, task_id: str) -> Optional[VideoTask]:
        return self._active_tasks.get(task_id)

    def handle_callback_choice(self, task_id: str, choice: Optional[int]) -> bool:
        """Set the resolution choice (or cancellation) for a waiting task."""
        task = self._active_tasks.get(task_id)
        if task and not task.choice_future.done():
            task.choice_future.set_result(choice)
            return True
        return False

    async def _worker_loop(self) -> None:
        """Main loop that executes tasks sequentially."""
        while True:
            task = await self._queue.get()
            self._current_task = task
            try:
                await self._process_task(task)
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.exception(f"Unhandled error processing task {task.task_id}: {e}")
                if self._client and task.status_msg:
                    await safe_edit_message(
                        self._client,
                        task.status_msg.chat.id,
                        task.status_msg.id,
                        f"❌ An error occurred while processing your video:\n`{e}`",
                    )
            finally:
                cleanup_path(task.work_dir)
                self._active_tasks.pop(task.task_id, None)
                self._current_task = None
                self._queue.task_done()

    async def _process_task(self, task: VideoTask) -> None:
        """Execute the end-to-end pipeline for a single video task."""
        client = self._client
        if client is None:
            logger.error("Pyrogram client is not attached to QueueManager.")
            return

        task.work_dir.mkdir(parents=True, exist_ok=True)
        # Determine extension
        ext = Path(task.file_name).suffix.lower()
        if not ext or ext not in config.SUPPORTED_VIDEO_EXTENSIONS:
            ext = ".mp4"
        input_path = task.work_dir / f"input{ext}"
        output_path = task.work_dir / "compressed.mp4"
        thumb_path = task.work_dir / "thumb.jpg"

        # Step 1: Download Video
        download_tracker = ProgressTracker(update_interval=config.PROGRESS_UPDATE_INTERVAL)
        await safe_edit_message(
            client,
            task.status_msg.chat.id,
            task.status_msg.id,
            "📥 Downloading video... Please wait.",
        )

        async def download_progress(current: int, total: int):
            if download_tracker.should_update():
                text = download_tracker.build_transfer_text(
                    current, total, action="Downloading"
                )
                await safe_edit_message(
                    client,
                    task.status_msg.chat.id,
                    task.status_msg.id,
                    text,
                )

        try:
            downloaded = await client.download_media(
                task.message,
                file_name=str(input_path),
                progress=download_progress,
            )
            if not downloaded or not Path(downloaded).exists():
                raise RuntimeError("Failed to download video from Telegram.")
            input_path = Path(downloaded)
        except Exception as e:
            await safe_edit_message(
                client,
                task.status_msg.chat.id,
                task.status_msg.id,
                f"❌ Failed to download video: `{e}`",
            )
            return

        # Step 2: Probe Video with ffprobe
        await safe_edit_message(
            client,
            task.status_msg.chat.id,
            task.status_msg.id,
            "🔍 Inspecting video details with FFmpeg...",
        )

        try:
            meta = await probe_video(input_path)
        except Exception as e:
            await safe_edit_message(
                client,
                task.status_msg.chat.id,
                task.status_msg.id,
                f"❌ Failed to analyze video with FFmpeg: `{e}`",
            )
            return

        width = meta["width"]
        height = meta["height"]
        duration = meta["duration"]
        size_bytes = meta["size"]
        min_dim = min(width, height)

        # Step 3: Generate Interactive Buttons
        lower_tiers = get_available_resolutions(width, height, config.STANDARD_RESOLUTIONS)

        keyboard: List[List[InlineKeyboardButton]] = []
        # Group lower resolution buttons in rows of 2
        row: List[InlineKeyboardButton] = []
        for tier in lower_tiers:
            btn = InlineKeyboardButton(
                f"📉 {tier}p",
                callback_data=f"cmp:{task.task_id}:{tier}",
            )
            row.append(btn)
            if len(row) == 2:
                keyboard.append(row)
                row = []
        if row:
            keyboard.append(row)

        # Add "Same Resolution (Compressed)" button
        keyboard.append([
            InlineKeyboardButton(
                f"🎞️ Same Res ({min_dim}p) [Compressed]",
                callback_data=f"cmp:{task.task_id}:same",
            )
        ])

        # Add Cancel button
        keyboard.append([
            InlineKeyboardButton(
                "❌ Cancel",
                callback_data=f"cmp:{task.task_id}:cancel",
            )
        ])

        info_text = (
            f"📹 **Video Analyzed Successfully!**\n\n"
            f"• **Resolution**: `{width}x{height}` ({min_dim}p)\n"
            f"• **Duration**: `{format_time(duration)}`\n"
            f"• **Original Size**: `{format_size(size_bytes)}`\n"
            f"• **Codec**: `{meta['codec']}`\n\n"
            f"👇 **Choose target compression option:**"
        )

        await safe_edit_message(
            client,
            task.status_msg.chat.id,
            task.status_msg.id,
            info_text,
            reply_markup=InlineKeyboardMarkup(keyboard),
        )

        # Step 4: Wait for user choice (up to 10 minutes)
        try:
            choice = await asyncio.wait_for(task.choice_future, timeout=600)
        except asyncio.TimeoutError:
            await safe_edit_message(
                client,
                task.status_msg.chat.id,
                task.status_msg.id,
                "⌛ Selection timed out (10 minutes). Task cancelled.",
            )
            return

        # -1 indicates cancellation
        if choice == -1:
            await safe_edit_message(
                client,
                task.status_msg.chat.id,
                task.status_msg.id,
                "❌ Compression cancelled by owner.",
            )
            return

        # Step 5: FFmpeg Compression
        target_height = choice  # None for same res, int for specific height
        target_label = f"{target_height}p" if target_height else f"Same Res ({min_dim}p)"

        compress_tracker = ProgressTracker(update_interval=config.PROGRESS_UPDATE_INTERVAL)
        await safe_edit_message(
            client,
            task.status_msg.chat.id,
            task.status_msg.id,
            f"⚙️ Compressing video to **{target_label}**... Starting FFmpeg...",
        )

        async def compress_progress(cur_sec: float, tot_sec: float, speed_str: Optional[str]):
            if compress_tracker.should_update():
                text = compress_tracker.build_compression_text(
                    cur_sec, tot_sec, speed_str=speed_str, target_label=target_label
                )
                await safe_edit_message(
                    client,
                    task.status_msg.chat.id,
                    task.status_msg.id,
                    text,
                )

        compress_start_time = time.time()
        try:
            await compress_video(
                input_path=input_path,
                output_path=output_path,
                target_height=target_height,
                total_duration=duration,
                progress_callback=compress_progress,
            )
        except Exception as e:
            await safe_edit_message(
                client,
                task.status_msg.chat.id,
                task.status_msg.id,
                f"❌ FFmpeg compression failed:\n`{e}`",
            )
            return

        compress_elapsed = time.time() - compress_start_time

        # Step 6: Probe compressed video & generate thumbnail
        await safe_edit_message(
            client,
            task.status_msg.chat.id,
            task.status_msg.id,
            "📤 Finalizing video and generating preview thumbnail...",
        )

        try:
            out_meta = await probe_video(output_path)
            out_width = out_meta["width"]
            out_height = out_meta["height"]
            out_duration = int(round(out_meta["duration"]))
            out_size = out_meta["size"]
        except Exception:
            out_width = width
            out_height = height
            out_duration = int(round(duration))
            out_size = output_path.stat().st_size if output_path.exists() else 0

        # Generate thumbnail
        has_thumb = await generate_thumbnail(
            output_path, thumb_path, duration=float(out_duration)
        )

        # Calculate compression stats
        saved_bytes = max(0, size_bytes - out_size)
        saved_pct = (saved_bytes / max(1, size_bytes)) * 100.0

        caption = (
            f"🎬 **Compression Completed!**\n\n"
            f"• **Resolution**: `{out_width}x{out_height}`\n"
            f"• **Original Size**: `{format_size(size_bytes)}`\n"
            f"• **Compressed Size**: `{format_size(out_size)}`\n"
            f"• **Space Saved**: `{saved_pct:.1f}%` ({format_size(saved_bytes)})\n"
            f"• **Encoding Time**: `{format_time(compress_elapsed)}`"
        )

        # Step 7: Upload Compressed Video
        upload_tracker = ProgressTracker(update_interval=config.PROGRESS_UPDATE_INTERVAL)
        await safe_edit_message(
            client,
            task.status_msg.chat.id,
            task.status_msg.id,
            "📤 Uploading compressed video to Telegram...",
        )

        async def upload_progress(current: int, total: int):
            if upload_tracker.should_update():
                text = upload_tracker.build_transfer_text(
                    current, total, action="Uploading"
                )
                await safe_edit_message(
                    client,
                    task.status_msg.chat.id,
                    task.status_msg.id,
                    text,
                )

        try:
            await client.send_video(
                chat_id=task.message.chat.id,
                video=str(output_path),
                caption=caption,
                duration=out_duration,
                width=out_width,
                height=out_height,
                thumb=str(thumb_path) if has_thumb else None,
                supports_streaming=True,
                reply_to_message_id=task.message.id,
                progress=upload_progress,
            )

            await safe_edit_message(
                client,
                task.status_msg.chat.id,
                task.status_msg.id,
                "✅ **Compression complete!** Compressed video has been sent as a reply above.",
            )
        except Exception as e:
            await safe_edit_message(
                client,
                task.status_msg.chat.id,
                task.status_msg.id,
                f"❌ Failed to upload compressed video: `{e}`",
            )


# Global queue manager instance
queue_manager = QueueManager()
