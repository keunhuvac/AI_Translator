# /logger_setup.py
import logging
import sys
import os
import time # Import time here only for the initial log write

LOG_FILE = "translator_log.txt"

def setup_logging():
    """Configures logging for the application."""
    log_formatter = logging.Formatter('%(asctime)s - %(levelname)s - [%(module)s:%(lineno)d] - %(message)s')

    # File Handler - Set level to ERROR
    file_handler = None
    try:
        # Ensure log file can be written to early
        with open(LOG_FILE, 'a', encoding='utf-8') as f:
             f.write(f"\n--- Log Session Start: {time.strftime('%Y-%m-%d %H:%M:%S')} ---\n")
        file_handler = logging.FileHandler(LOG_FILE, encoding='utf-8', mode='a')
        file_handler.setFormatter(log_formatter)
        # *** SET FILE HANDLER LEVEL TO ERROR ***
        file_handler.setLevel(logging.ERROR)
        print(f"File logging configured at ERROR level to: {LOG_FILE}") # Console feedback
    except Exception as log_init_e:
        print(f"CRITICAL: Cannot write to log file '{LOG_FILE}'. Error: {log_init_e}", file=sys.stderr)
        file_handler = None # Indicate failure

    logger = logging.getLogger()
    # *** SET ROOT LOGGER LEVEL TO DEBUG ***
    # This allows DEBUG messages to be processed by the logger object,
    # even if handlers filter them later.
    logger.setLevel(logging.DEBUG)

    # Clear existing handlers to avoid duplicates
    for handler in logger.handlers[:]:
        logger.removeHandler(handler)

    # Add handlers
    if file_handler:
        logger.addHandler(file_handler)
    # Add console handler if you want to see DEBUG messages on console
    # console_handler = logging.StreamHandler(sys.stdout)
    # console_handler.setFormatter(log_formatter)
    # console_handler.setLevel(logging.DEBUG) # Set console level
    # logger.addHandler(console_handler)

    if not logger.hasHandlers():
         print("WARNING: No logging handlers configured.", file=sys.stderr)
         logging.basicConfig(level=logging.ERROR)
         logger = logging.getLogger()

    logger.info("Logging setup complete (Root level: %s, File level: %s).",
                logging.getLevelName(logger.level),
                logging.getLevelName(file_handler.level) if file_handler else "N/A")
    return logger

