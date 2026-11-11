import time
from typing import Optional


def format_size(num_bytes: int | float) -> str:
    """Format bytes into human-readable string (B, KB, MB, GB)."""
    if num_bytes <= 0:
        return "0 B"
    units = ["B", "KB", "MB", "GB", "TB"]
    unit_idx = 0
    val = float(num_bytes)
    while val >= 1024.0 and unit_idx < len(units) - 1:
        val /= 1024.0
        unit_idx += 1
    return f"{val:.2f} {units[unit_idx]}"


def format_time(seconds: float | int) -> str:
    """Format seconds into HH:MM:SS or MM:SS."""
    if seconds is None or seconds < 0:
        return "--:--"
    sec = int(round(seconds))
    hrs = sec // 3600
    mins = (sec % 3600) // 60
    rem_secs = sec % 60
    if hrs > 0:
        return f"{hrs:02d}:{mins:02d}:{rem_secs:02d}"
    return f"{mins:02d}:{rem_secs:02d}"


def create_progress_bar(percentage: float, length: int = 10) -> str:
    """Create a visual text progress bar, e.g. [██████░░░░] 60%."""
    pct = max(0.0, min(100.0, percentage))
    filled_len = int(round(length * pct / 100.0))
    bar = "█" * filled_len + "░" * (length - filled_len)
    return f"[{bar}] {pct:.1f}%"


class ProgressTracker:
    """
    Tracks and throttles progress updates to respect Telegram rate limits
    and the 10-second requirement.
    """

    def __init__(self, update_interval: float = 10.0):
        self.start_time = time.time()
        self.last_update_time = 0.0
        self.update_interval = update_interval

    def should_update(self, force: bool = False) -> bool:
        """Check if enough time has elapsed since the last update."""
        now = time.time()
        if force or (now - self.last_update_time >= self.update_interval):
            self.last_update_time = now
            return True
        return False

    def build_compression_text(
        self,
        current_sec: float,
        total_sec: float,
        speed_str: Optional[str] = None,
        target_label: str = "Compressed"
    ) -> str:
        """Construct the progress text message for video compression."""
        total_sec = max(0.1, total_sec)
        pct = min(100.0, (current_sec / total_sec) * 100.0)
        bar = create_progress_bar(pct)
        cur_fmt = format_time(current_sec)
        tot_fmt = format_time(total_sec)

        # Estimate remaining time
        elapsed = time.time() - self.start_time
        if current_sec > 0 and pct < 100:
            rate = current_sec / max(0.001, elapsed)
            rem_sec = (total_sec - current_sec) / max(0.001, rate)
            eta_fmt = format_time(rem_sec)
        else:
            eta_fmt = "--:--"

        speed_line = f"• **Speed**: `{speed_str}`\n" if speed_str else ""

        return (
            f"⚙️ **Compressing Video...**\n\n"
            f"• **Target**: `{target_label}`\n"
            f"• **Progress**: {bar}\n"
            f"• **Duration**: `{cur_fmt}` / `{tot_fmt}`\n"
            f"{speed_line}"
            f"• **ETA**: `{eta_fmt}`\n\n"
            f"_(Updates every 10s)_"
        )

    def build_transfer_text(
        self,
        current_bytes: int,
        total_bytes: int,
        action: str = "Downloading"
    ) -> str:
        """Construct progress text for download or upload."""
        total_bytes = max(1, total_bytes)
        pct = min(100.0, (current_bytes / total_bytes) * 100.0)
        bar = create_progress_bar(pct)
        cur_fmt = format_size(current_bytes)
        tot_fmt = format_size(total_bytes)

        elapsed = time.time() - self.start_time
        speed_bps = current_bytes / max(0.001, elapsed)
        speed_fmt = f"{format_size(speed_bps)}/s"

        if current_bytes > 0 and pct < 100:
            rem_sec = (total_bytes - current_bytes) / max(0.001, speed_bps)
            eta_fmt = format_time(rem_sec)
        else:
            eta_fmt = "--:--"

        emoji = "📥" if action == "Downloading" else "📤"

        return (
            f"{emoji} **{action} Video...**\n\n"
            f"• **Progress**: {bar}\n"
            f"• **Size**: `{cur_fmt}` / `{tot_fmt}`\n"
            f"• **Speed**: `{speed_fmt}`\n"
            f"• **ETA**: `{eta_fmt}`\n\n"
            f"_(Updates every 10s)_"
        )
