import asyncio
import subprocess
import unittest
from pathlib import Path

from config import STANDARD_RESOLUTIONS, TEMP_DIR
from utils.cleanup import cleanup_path
from utils.ffmpeg_utils import (
    compress_video,
    generate_thumbnail,
    get_available_resolutions,
    probe_video,
)
from utils.progress_bar import (
    ProgressTracker,
    create_progress_bar,
    format_size,
    format_time,
)


class TestProgressUtils(unittest.TestCase):
    def test_format_size(self):
        self.assertEqual(format_size(0), "0 B")
        self.assertEqual(format_size(1024), "1.00 KB")
        self.assertEqual(format_size(1048576), "1.00 MB")
        self.assertEqual(format_size(1073741824), "1.00 GB")

    def test_format_time(self):
        self.assertEqual(format_time(0), "00:00")
        self.assertEqual(format_time(65), "01:05")
        self.assertEqual(format_time(3665), "01:01:05")

    def test_create_progress_bar(self):
        bar_0 = create_progress_bar(0)
        self.assertIn("0.0%", bar_0)
        bar_50 = create_progress_bar(50)
        self.assertIn("50.0%", bar_50)
        bar_100 = create_progress_bar(100)
        self.assertIn("100.0%", bar_100)

    def test_progress_tracker_throttling(self):
        tracker = ProgressTracker(update_interval=10.0)
        # First call with force=True should return True
        self.assertTrue(tracker.should_update(force=True))
        # Immediate next call without force should return False
        self.assertFalse(tracker.should_update(force=False))

    def test_get_available_resolutions(self):
        # 1080p video (1920x1080)
        tiers = get_available_resolutions(1920, 1080, STANDARD_RESOLUTIONS)
        self.assertEqual(tiers, [720, 480, 360, 240, 144])

        # 720p portrait video (720x1280)
        portrait_tiers = get_available_resolutions(720, 1280, STANDARD_RESOLUTIONS)
        self.assertEqual(portrait_tiers, [480, 360, 240, 144])

        # 144p video (256x144)
        low_tiers = get_available_resolutions(256, 144, STANDARD_RESOLUTIONS)
        self.assertEqual(low_tiers, [])


class TestFFmpegPipeline(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.test_dir = TEMP_DIR / "test_run"
        self.test_dir.mkdir(parents=True, exist_ok=True)
        self.input_file = self.test_dir / "test_input.mp4"
        self.output_file = self.test_dir / "test_output.mp4"
        self.thumb_file = self.test_dir / "test_thumb.jpg"

        # Create a synthetic 3-second 1280x720 video with test audio
        cmd = [
            "ffmpeg", "-y",
            "-f", "lavfi", "-i", "testsrc=duration=3:size=1280x720:rate=30",
            "-f", "lavfi", "-i", "sine=frequency=1000:duration=3",
            "-c:v", "libx264", "-pix_fmt", "yuv420p",
            "-c:a", "aac",
            str(self.input_file)
        ]
        res = subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        self.assertEqual(res.returncode, 0, "Failed to create synthetic test video")

    async def asyncTearDown(self):
        cleanup_path(self.test_dir)

    async def test_probe_video(self):
        meta = await probe_video(self.input_file)
        self.assertEqual(meta["width"], 1280)
        self.assertEqual(meta["height"], 720)
        self.assertAlmostEqual(meta["duration"], 3.0, places=1)
        self.assertGreater(meta["size"], 0)

    async def test_generate_thumbnail(self):
        ok = await generate_thumbnail(self.input_file, self.thumb_file, duration=3.0)
        self.assertTrue(ok)
        self.assertTrue(self.thumb_file.exists())
        self.assertGreater(self.thumb_file.stat().st_size, 0)

    async def test_compress_video(self):
        progress_calls = []

        async def on_progress(cur, tot, speed):
            progress_calls.append((cur, tot, speed))

        await compress_video(
            self.input_file,
            self.output_file,
            target_height=480,
            total_duration=3.0,
            progress_callback=on_progress
        )

        self.assertTrue(self.output_file.exists())
        out_meta = await probe_video(self.output_file)
        self.assertEqual(out_meta["height"], 480)
        self.assertGreater(len(progress_calls), 0)


if __name__ == "__main__":
    unittest.main()
