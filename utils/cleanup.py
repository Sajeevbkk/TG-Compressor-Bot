import shutil
import logging
from pathlib import Path
from typing import Union

logger = logging.getLogger(__name__)


def cleanup_path(target: Union[str, Path]) -> None:
    """Safely remove a file or directory with error handling."""
    if not target:
        return
    path = Path(target)
    try:
        if path.is_file() or path.is_symlink():
            path.unlink(missing_ok=True)
            logger.debug(f"Deleted file: {path}")
        elif path.is_dir():
            shutil.rmtree(path, ignore_errors=True)
            logger.debug(f"Deleted directory: {path}")
    except Exception as e:
        logger.warning(f"Failed to delete {path}: {e}")


def cleanup_temp_dir(temp_dir: Path) -> None:
    """Clean all files and subdirectories inside the temp folder on startup."""
    if not temp_dir.exists():
        temp_dir.mkdir(parents=True, exist_ok=True)
        return
    for item in temp_dir.iterdir():
        cleanup_path(item)
    logger.info("Temporary directory cleaned up successfully.")
