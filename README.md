# 🎬 Telegram Video Compressor Bot

A high-performance, owner-only Telegram bot written in Python using **Pyrogram** and **FFmpeg**. It downloads videos up to 2 GB, inspects the video properties, presents interactive buttons for all lower resolution compressions (plus same-resolution compression), and encodes the video with live 10-second progress updates before returning it as a playable streaming video reply.

---

## ✨ Features

- **Exclusive Owner Isolation**:
  - The bot exclusively serves the authorized owner (`OWNER_ID`).
  - Messages and callback queries from non-owners are silently ignored with zero response.
- **2 GB File Support**:
  - Accepts both native Telegram video messages and uncompressed document files (`.mp4`, `.mkv`, `.mov`, `.avi`, `.webm`, etc.) up to 2 GB.
- **FFmpeg Resolution Probing**:
  - Uses `ffprobe` to determine the video resolution, duration, bitrate, and codec.
- **Interactive Resolution Selection**:
  - Presents inline keyboard buttons dynamically for all available lower resolution tiers (`1080p`, `720p`, `480p`, `360p`, `240p`, `144p`).
  - Includes a **"Same Res (Compressed)"** button to compress high-bitrate videos without downscaling.
  - Includes a **"Cancel"** button to abort and clean up disk space.
- **Sequential Task Queue**:
  - Processes one compression task at a time via an asynchronous FIFO queue, preventing system CPU and memory exhaustion.
  - Automatically notifies the owner of their queue position if another video is already being processed.
- **Live Progress Updates (Every 10 Seconds)**:
  - FFmpeg compression progress is streamed and throttled to exactly 10-second intervals to satisfy requirements and prevent Telegram rate limits (`FloodWait`).
  - Visual progress bar `[██████░░░░] 60.0%`, current time, total duration, encoding speed, and estimated time remaining (ETA).
- **Native Video Streaming Output**:
  - Delivers the output via `send_video` with `-movflags +faststart`, extracted preview thumbnail, dimensions, and duration so it streams directly inside Telegram.
  - Sent as a direct reply to the original video message for easy tracking.
- **Automatic Cleanup**:
  - Safely deletes input files, output files, thumbnails, and temp directories upon completion or cancellation.

---

## 📋 Prerequisites

1. **Python 3.10+** (tested on Python 3.12).
2. **FFmpeg & FFprobe**:
   - Must be installed and accessible on your system PATH (`ffmpeg` and `ffprobe`).
   - Windows users can download from [gyan.dev](https://www.gyan.dev/ffmpeg/builds/) or install via `winget install Gyan.FFmpeg`.

---

## 🚀 Setup & Installation

### 1. Clone or Open the Repository
```bash
cd "Video Compress Bot"
```

### 2. Set Up Virtual Environment & Install Dependencies
```bash
# If using existing virtualenv:
.\.venv\Scripts\activate

# Or create a new one:
python -m venv .venv
.\.venv\Scripts\activate
pip install -r requirements.txt
```

### 3. Configure `.env`
Copy `.env.example` to `.env`:
```bash
cp .env.example .env
```
Open `.env` and fill in your credentials:
```env
# Telegram API Credentials (from https://my.telegram.org)
API_ID=12345678
API_HASH=abcdef1234567890abcdef1234567890

# Bot Token (from @BotFather)
BOT_TOKEN=123456789:ABCdefGhIJKlmNoPQRsTUVwxyZ

# Telegram User ID of the Bot Owner (numeric, e.g. from @userinfobot)
OWNER_ID=123456789
```

---

## 🏃 Running the Bot

Run the main bot script:
```bash
python bot.py
```

---

## 🧪 Running Automated Tests

Run the full test suite (FFmpeg execution, probe parsing, progress throttling, owner filters, task queueing):
```bash
python -m unittest discover tests
```

---

## 📁 Project Architecture

```
Video Compress Bot/
├── .env.example              # Sample environment configuration template
├── .gitignore                # Git ignore rules for venv, session files, temp data
├── requirements.txt          # Python dependencies (pyrogram, tgcrypto, python-dotenv)
├── config.py                 # Configuration loader and validator
├── bot.py                    # Main bot runner and entry point
├── utils/
│   ├── cleanup.py            # Temp directory and file deletion helpers
│   ├── ffmpeg_utils.py       # ffprobe metadata probe & async ffmpeg compression
│   └── progress_bar.py       # Visual progress bar & time formatters
├── handlers/
│   ├── queue_manager.py      # FIFO sequential task queue & pipeline coordinator
│   ├── video_handler.py      # Video and document message filters & handlers
│   └── callback_handler.py   # Interactive button callback router
└── tests/
    ├── test_ffmpeg.py        # FFmpeg & progress utilities unit tests
    └── test_bot_handlers.py  # Filter & queue integration tests
```
