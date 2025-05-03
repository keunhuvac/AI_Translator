# /config_manager.py
import json
import os
import logging
from tkinter import messagebox  # Use standard messagebox for potential early errors
import tkinter as tk

logger = logging.getLogger(__name__)

CONFIG_FILE = "translator_config.json"

# --- DI CHUYỂN CÁC HẰNG SỐ LÊN ĐÂY ---
# Default values
DEFAULT_THEME = "cyborg"
DEFAULT_PRIMARY_MODEL = "gemini-2.0-flash"
DEFAULT_SECONDARY_MODEL = "gemini-2.0-flash"
DEFAULT_FINAL_RETRY_MODEL = "gemini-2.0-flash"
AVAILABLE_MODELS = [
    "gemini-1.5-flash-latest", 
    "gemini-2.0-flash",       
    "gemini-1.5-pro-latest",
    "gemini-2.0-flash-lite", 
    "gemini-2.5-pro-exp-03-25",
    "gemini-2.5-flash-preview-04-17",
]
DEFAULT_PROMPT = """
Dịch đoạn văn bản tiếng Trung sau sang tiếng Việt theo văn phong truyện Tiên hiệp/Huyền huyễn.
Ưu tiên dịch các thuật ngữ và tên riêng sang Hán Việt nếu có thể và hợp lý, giữ sự nhất quán.
Giữ văn phong tự nhiên, trôi chảy, phù hợp với ngữ cảnh truyện.
Đảm bảo bản dịch là tiếng Việt hoàn chỉnh, không còn sót bất kỳ ký tự tiếng Trung nào.
Không thêm bất kỳ lời giải thích hay ghi chú nào ngoài nội dung dịch.

Văn bản gốc:
{text_chunk}
"""
RETRY_PROMPT = """
Bản dịch trước đó vẫn còn chứa ký tự tiếng Trung. Hãy dịch lại đoạn văn bản tiếng Trung sau sang tiếng Việt theo văn phong truyện Tiên hiệp/Huyền huyễn.
Ưu tiên dịch các thuật ngữ và tên riêng sang Hán Việt nếu có thể và hợp lý, giữ sự nhất quán.
Giữ văn phong tự nhiên, trôi chảy, phù hợp với ngữ cảnh truyện.
TUYỆT ĐỐI ĐẢM BẢO bản dịch là tiếng Việt hoàn chỉnh, không còn sót bất kỳ ký tự tiếng Trung nào.
Không thêm bất kỳ lời giải thích hay ghi chú nào ngoài nội dung dịch.

Văn bản gốc:
{text_chunk}
"""
DEFAULT_ALLOWED_CHINESE_COUNT = 0
DEFAULT_TEMPERATURE = 0.7
DEFAULT_MAX_FOLDER_RETRIES = 2  # Thêm hằng số này
DEFAULT_REQUEST_TIMEOUT = 30  # Thêm hằng số này
# ---------------------------------------

# --- ĐỊNH NGHĨA DEFAULT_SETTINGS SAU KHI CÁC HẰNG SỐ ĐÃ CÓ ---
DEFAULT_SETTINGS = {
    "theme": DEFAULT_THEME,
    "api_key_file": None,
    "processing_dirs": [],  # Đã đổi tên từ source_directories
    "completed_dirs": [],
    "primary_model": DEFAULT_PRIMARY_MODEL,
    "secondary_model": DEFAULT_SECONDARY_MODEL,
    "final_retry_model": DEFAULT_FINAL_RETRY_MODEL,
    "translation_prompt": DEFAULT_PROMPT,
    "retry_prompt": RETRY_PROMPT,  # Thêm retry_prompt
    "max_workers": 3,
    "reader_font_family": "Segoe UI",
    "reader_font_size": 11,
    "allow_chinese_chars": DEFAULT_ALLOWED_CHINESE_COUNT,
    "temperature": DEFAULT_TEMPERATURE,
    "max_folder_retries": DEFAULT_MAX_FOLDER_RETRIES,  # Thêm vào settings
    "request_timeout": DEFAULT_REQUEST_TIMEOUT,  # Thêm vào settings
}
# -------------------------------------------------------------

def load_settings():
    """Loads settings from the JSON config file."""
    logger.info(f"Loading settings from {CONFIG_FILE}")
    try:
        if os.path.exists(CONFIG_FILE):
            with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
                try:
                    settings = json.load(f)
                except json.JSONDecodeError as json_e:
                    logger.error(f"Error decoding JSON from {CONFIG_FILE}: {json_e}")
                    # Use tk.Tk as parent might not exist yet if error is early
                    root = tk.Tk()
                    root.withdraw()
                    messagebox.showerror("Lỗi Config", f"Lỗi đọc file cấu hình {CONFIG_FILE}.\n{json_e}\nSử dụng cài đặt mặc định.", parent=root)
                    root.destroy()
                    return DEFAULT_SETTINGS.copy()

                logger.info("Settings file found. Validating...")
                updated = False
                # Validate against current defaults
                current_default_settings = DEFAULT_SETTINGS.copy()
                for key, value in current_default_settings.items():
                    if key not in settings:
                        logger.warning(f"Missing key '{key}' in config file. Adding default: {value}")
                        settings[key] = value
                        updated = True
                    # Rename old key if needed
                    elif key == "processing_dirs" and "source_directories" in settings:
                        logger.info("Found old 'source_directories' key, renaming to 'processing_dirs'.")
                        settings["processing_dirs"] = settings.pop("source_directories")
                        updated = True

                # Remove obsolete keys (optional, but keeps config clean)
                obsolete_keys = [k for k in settings if k not in current_default_settings]
                for k in obsolete_keys:
                    logger.warning(f"Removing obsolete key '{k}' from config file.")
                    del settings[k]
                    updated = True

                if updated:
                    logger.info("Config file updated with missing/renamed/obsolete keys.")
                    try:
                        save_settings(settings)  # Save updated config immediately
                    except Exception as save_e:
                        logger.error(f"Failed to automatically save updated config: {save_e}")
                logger.info("Settings loaded and validated successfully.")
                return settings
        else:
            logger.warning(f"Config file {CONFIG_FILE} not found. Returning default settings.")
            return DEFAULT_SETTINGS.copy()
    except Exception as e:
        logger.error(f"Failed to load settings from {CONFIG_FILE}: {e}", exc_info=True)
        root = tk.Tk()
        root.withdraw()
        messagebox.showerror("Lỗi Config", f"Không thể tải cài đặt từ {CONFIG_FILE}.\n{e}\nSử dụng cài đặt mặc định.", parent=root)
        root.destroy()
        return DEFAULT_SETTINGS.copy()

def save_settings(settings_data):
    """Saves the provided settings dictionary to the JSON config file."""
    logger.info(f"Saving settings to {CONFIG_FILE}")
    try:
        # Ensure only known keys are saved (based on current defaults)
        settings_to_save = {}
        for key in DEFAULT_SETTINGS:
            settings_to_save[key] = settings_data.get(key, DEFAULT_SETTINGS[key])  # Use provided or default

        with open(CONFIG_FILE, 'w', encoding='utf-8') as f:
            json.dump(settings_to_save, f, indent=4, ensure_ascii=False)
        logger.info("Settings saved successfully.")
    except TypeError as e:
        logger.error(f"Error saving settings: Data not JSON serializable. {e}", exc_info=True)
    except Exception as e:
        logger.error(f"Failed to save settings to {CONFIG_FILE}: {e}", exc_info=True)