import asyncio
import logging
import sys

import pyrogram
from pyrogram import Client

import config
from handlers.callback_handler import register_callback_handlers
from handlers.queue_manager import queue_manager
from handlers.video_handler import register_video_handlers
from utils.cleanup import cleanup_temp_dir

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout),
    ],
)
logger = logging.getLogger("VideoCompressBot")


async def run_bot(app: Client) -> None:
    """Async main routine that starts the client, workers, and idles."""
    await app.start()
    bot_me = await app.get_me()
    logger.info(f"Bot started successfully as @{bot_me.username} (ID: {bot_me.id})")
    logger.info(f"Authorized Owner ID: {config.OWNER_ID}")
    
    # Start the background task queue worker
    queue_manager.start(app)
    logger.info("Bot is now ready and listening for owner videos!")

    # Idle until Ctrl+C / SIGINT
    await pyrogram.idle()

    logger.info("Stopping bot and cleaning temporary files...")
    await app.stop()
    cleanup_temp_dir(config.TEMP_DIR)
    logger.info("Bot terminated cleanly.")


def main() -> None:
    """Entry point for the video compressor bot."""
    print("=" * 60)
    print("     Telegram Video Compressor Bot (Pyrogram & FFmpeg)    ")
    print("=" * 60)

    # Validate environment configuration
    try:
        config.validate_config()
    except ValueError as e:
        logger.error(str(e))
        print("\n[!] Please configure your .env file with valid credentials before starting.")
        sys.exit(1)

    # Clean up any leftover temporary files from previous runs
    cleanup_temp_dir(config.TEMP_DIR)

    # Initialize Pyrogram Bot Client
    app = Client(
        name="video_compress_bot",
        api_id=config.API_ID,
        api_hash=config.API_HASH,
        bot_token=config.BOT_TOKEN,
        workdir=str(config.BASE_DIR),
    )

    # Register handlers
    register_video_handlers(app)
    register_callback_handlers(app)

    # Run client with async runner
    app.run(run_bot(app))


if __name__ == "__main__":
    main()
