import logging
import sys
from pathlib import Path

PRIMARY_LOG_FILE = Path("/var/log/remote-fuse.log")
FALLBACK_DIR = Path.home() / ".remote-fuse"
FALLBACK_LOG_FILE = FALLBACK_DIR / "remote-fuse.log"

def _setup_logger(log_level=logging.INFO):
    """
    Sets up logging, trying primary path first, then fallback.
    Returns the configured logger instance.
    """
    logger = logging.getLogger("remote-fuse")
    # Prevent adding handlers multiple times if this function is called again
    if logger.hasHandlers():
        logger.handlers.clear()
    logger.setLevel(log_level)

    log_formatter = logging.Formatter(
        "%(asctime)s [%(levelname)s] - %(message)s"
    )

    file_handler = None
    chosen_log_path = None
    try:
        # Attempt to create the handler directly. This checks permissions.
        file_handler = logging.FileHandler(PRIMARY_LOG_FILE, mode="a")
        chosen_log_path = PRIMARY_LOG_FILE
        print(f"Logging to primary location: {chosen_log_path}")
    except (PermissionError, OSError) as e:
        print(
            f"Warning: Cannot use primary log location {PRIMARY_LOG_FILE}: {e}. "
            f"Falling back to user directory."
        )
        try:
            FALLBACK_DIR.mkdir(parents=True, exist_ok=True) # Ensure dir exists
            file_handler = logging.FileHandler(FALLBACK_LOG_FILE, mode="a")
            chosen_log_path = FALLBACK_LOG_FILE
            print(f"Logging to fallback location: {chosen_log_path}")
        except Exception as fallback_e:
            print(
                f"Error: Could not configure fallback logging to "
                f"{FALLBACK_LOG_FILE}: {fallback_e}",
                file=sys.stderr,
            )
    except Exception as primary_e:
        print(
            f"Error: Unexpected issue configuring logging for "
            f"{PRIMARY_LOG_FILE}: {primary_e}",
            file=sys.stderr,
        )

    if file_handler:
        file_handler.setFormatter(log_formatter)
        logger.addHandler(file_handler)
    else:
        print(
            "Warning: File logging disabled due to setup errors.",
            file=sys.stderr,
        )

    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(log_formatter)
    logger.addHandler(console_handler)

    return logger

logger = _setup_logger()
