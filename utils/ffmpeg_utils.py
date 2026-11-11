import asyncio
import json
import logging
from pathlib import Path
from typing import Any, Callable, Coroutine, Dict, List, Optional

logger = logging.getLogger(__name__)


async def probe_video(file_path: Path) -> Dict[str, Any]:
    """
    Probe video metadata using ffprobe.
    Returns a dictionary containing width, height, duration, size, and bitrate.
    """
    cmd = [
        "ffprobe",
        "-v", "error",
        "-select_streams", "v:0",
        "-show_entries", "stream=width,height,duration,codec_name:format=duration,size,bit_rate",
        "-of", "json",
        str(file_path)
    ]

    process = await asyncio.create_subprocess_exec(
        *cmd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE
    )
    stdout, stderr = await process.communicate()

    if process.returncode != 0:
        err_msg = stderr.decode(errors="replace").strip()
        raise RuntimeError(f"ffprobe failed (code {process.returncode}): {err_msg}")

    data = json.loads(stdout.decode(errors="replace"))

    streams = data.get("streams", [])
    format_data = data.get("format", {})

    if not streams:
        raise ValueError("No video stream found in file.")

    video_stream = streams[0]

    width = int(video_stream.get("width") or 0)
    height = int(video_stream.get("height") or 0)

    # Duration might be in stream or format
    duration_str = video_stream.get("duration") or format_data.get("duration") or "0"
    try:
        duration = float(duration_str)
    except ValueError:
        duration = 0.0

    # Size in bytes
    size_str = format_data.get("size") or "0"
    try:
        size = int(size_str)
    except ValueError:
        size = file_path.stat().st_size if file_path.exists() else 0

    # Bitrate
    bitrate_str = format_data.get("bit_rate") or "0"
    try:
        bitrate = int(bitrate_str)
    except ValueError:
        bitrate = 0

    return {
        "width": width,
        "height": height,
        "duration": duration,
        "size": size,
        "bitrate": bitrate,
        "codec": video_stream.get("codec_name", "unknown")
    }


def get_available_resolutions(width: int, height: int, standard_tiers: List[int]) -> List[int]:
    """
    Find available lower resolution tiers based on the video's shorter dimension.
    """
    min_dim = min(width, height)
    return [tier for tier in standard_tiers if tier < min_dim]


async def generate_thumbnail(video_path: Path, thumb_path: Path, duration: float = 1.0) -> bool:
    """
    Extract a single frame from video to use as a preview thumbnail.
    """
    ss_time = min(1.0, max(0.0, duration / 2.0))
    cmd = [
        "ffmpeg",
        "-y",
        "-ss", f"{ss_time:.2f}",
        "-i", str(video_path),
        "-vframes", "1",
        "-vf", "scale='min(320,iw)':-1",
        str(thumb_path)
    ]

    try:
        process = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.DEVNULL,
            stderr=asyncio.subprocess.PIPE
        )
        _, stderr = await process.communicate()
        if process.returncode == 0 and thumb_path.exists():
            return True
        logger.warning(f"Thumbnail generation returned code {process.returncode}: {stderr.decode(errors='replace')}")
    except Exception as e:
        logger.error(f"Error generating thumbnail: {e}")
    return False


async def compress_video(
    input_path: Path,
    output_path: Path,
    target_height: Optional[int],
    total_duration: float,
    progress_callback: Optional[Callable[[float, float, Optional[str]], Coroutine[Any, Any, None]]] = None
) -> None:
    """
    Compress video using ffmpeg with live stdout progress reporting.
    """
    # Build video filter
    if target_height is not None:
        # Responsive scale: handles landscape (iw >= ih) and portrait (ih > iw)
        scale_filter = (
            f"scale='if(gt(iw,ih),-2,{target_height})':"
            f"'if(gt(iw,ih),{target_height},-2)'"
        )
    else:
        # Same resolution, guarantee even dimensions for libx264
        scale_filter = "scale=trunc(iw/2)*2:trunc(ih/2)*2"

    cmd = [
        "ffmpeg",
        "-y",
        "-i", str(input_path),
        "-vf", scale_filter,
        "-c:v", "libx264",
        "-preset", "fast",
        "-crf", "26",
        "-pix_fmt", "yuv420p",
        "-c:a", "aac",
        "-b:a", "128k",
        "-movflags", "+faststart",
        "-progress", "pipe:1",
        str(output_path)
    ]

    process = await asyncio.create_subprocess_exec(
        *cmd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE
    )

    current_speed: Optional[str] = None
    stderr_lines: List[str] = []

    # Read progress output from stdout line-by-line
    async def read_stdout():
        nonlocal current_speed
        if process.stdout is None:
            return
        while True:
            line_bytes = await process.stdout.readline()
            if not line_bytes:
                break
            line = line_bytes.decode(errors="replace").strip()
            if not line:
                continue

            if "=" in line:
                key, val = line.split("=", 1)
                key = key.strip()
                val = val.strip()

                if key == "speed":
                    current_speed = val
                elif key == "out_time_us":
                    try:
                        cur_us = int(val)
                        cur_sec = cur_us / 1_000_000.0
                        if progress_callback:
                            await progress_callback(cur_sec, total_duration, current_speed)
                    except ValueError:
                        pass
                elif key == "progress" and val == "end":
                    if progress_callback:
                        await progress_callback(total_duration, total_duration, current_speed)

    async def read_stderr():
        if process.stderr is None:
            return
        while True:
            line_bytes = await process.stderr.readline()
            if not line_bytes:
                break
            stderr_lines.append(line_bytes.decode(errors="replace"))

    # Run both readers concurrently with process execution
    await asyncio.gather(read_stdout(), read_stderr(), process.wait())

    if process.returncode != 0:
        err_msg = "".join(stderr_lines[-20:]).strip()
        raise RuntimeError(f"FFmpeg compression failed (code {process.returncode}):\n{err_msg}")
