import os
from pathlib import Path
from dotenv import load_dotenv

# Base project directory
BASE_DIR = Path(__file__).resolve().parent

# Load environment variables from .env file
load_dotenv(dotenv_path=BASE_DIR / ".env")

def get_env_int(key: str, default: int | None = None) -> int:
    val = os.getenv(key)
    if val is None or val.strip() == "":
        if default is not None:
            return default
        raise ValueError(f"Missing required integer environment variable: {key}")
    try:
        return int(val.strip())
    except ValueError:
        raise ValueError(f"Environment variable '{key}' must be an integer, got: '{val}'")

def get_env_str(key: str, default: str | None = None) -> str:
    val = os.getenv(key)
    if val is None or val.strip() == "":
        if default is not None:
            return default
        raise ValueError(f"Missing required string environment variable: {key}")
    return val.strip()

# Required Telegram Credentials
API_ID = get_env_int("API_ID", default=0)
API_HASH = os.getenv("API_HASH", "").strip()
BOT_TOKEN = os.getenv("BOT_TOKEN", "").strip()
OWNER_ID = get_env_int("OWNER_ID", default=0)

# Paths
TEMP_DIR = BASE_DIR / "temp"
TEMP_DIR.mkdir(parents=True, exist_ok=True)

# 2 GB maximum file limit in bytes
MAX_FILE_SIZE = 2 * 1024 * 1024 * 1024  # 2,147,483,648 bytes

# Progress update interval in seconds
PROGRESS_UPDATE_INTERVAL = 10

# Standard height/dimension tiers for compression
STANDARD_RESOLUTIONS = [1080, 720, 480, 360, 240, 144]

# Supported video extensions when sent as documents
SUPPORTED_VIDEO_EXTENSIONS = (
    ".mp4", ".mkv", ".mov", ".avi", ".webm", ".flv", ".wmv", ".m4v", ".ts", ".3gp"
)

def validate_config() -> None:
    errors = []
    if not API_ID:
        errors.append("API_ID is missing or invalid.")
    if not API_HASH:
        errors.append("API_HASH is missing.")
    if not BOT_TOKEN:
        errors.append("BOT_TOKEN is missing.")
    if not OWNER_ID:
        errors.append("OWNER_ID is missing or invalid.")
    
    if errors:
        raise ValueError("Configuration Error:\n" + "\n".join(f"- {e}" for e in errors) + "\nPlease update your .env file.")
