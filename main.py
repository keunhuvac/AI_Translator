# /main.py
import tkinter as tk
import logging
import sys
import os
import importlib
import shutil
import glob

# Clear cached bytecode to ensure latest modules are loaded
def clear_pycache():
    for pycache in glob.glob("**/__pycache__", recursive=True):
        try:
            shutil.rmtree(pycache)
            print(f"Cleared cache: {pycache}")
        except Exception as e:
            print(f"Warning: Could not clear cache {pycache}: {e}")

# Use absolute imports assuming running from project root
try:
    from gui.main_window import TranslatorApp
    from logger_setup import setup_logging, LOG_FILE
except ImportError as e:
    tk.messagebox.showerror("Lỗi Import", f"Không thể import các module cần thiết: {e}\nĐảm bảo bạn chạy main.py từ thư mục gốc của dự án.")
    sys.exit(1)

if __name__ == "__main__":
    # Clear cached bytecode
    clear_pycache()

    # Setup logging first
    try:
        logger = setup_logging()
        if logger is None:
            tk.messagebox.showerror("Lỗi Logging", f"Không thể cấu hình logging vào file '{LOG_FILE}'.\nỨng dụng không thể tiếp tục.")
            sys.exit(1)
    except Exception as e:
        print(f"FATAL: Failed to initialize logging. Error: {e}", file=sys.stderr)
        try:
            root = tk.Tk()
            root.withdraw()
            tk.messagebox.showerror("Lỗi Nghiêm Trọng", f"Không thể khởi tạo logging vào file '{LOG_FILE}'.\n{e}\nỨng dụng không thể tiếp tục.")
        except Exception as tk_e:
            print(f"FATAL: Could not even show Tkinter error message: {tk_e}", file=sys.stderr)
        sys.exit(1)

    # Set DPI awareness for Windows AFTER logging setup
    try:
        from ctypes import windll
        windll.shcore.SetProcessDpiAwareness(1)
        logger.info("DPI awareness set for Windows.")
    except ImportError:
        logger.info("Not setting DPI awareness (not Windows or ctypes unavailable).")
    except Exception as dpi_e:
        logger.warning(f"Failed to set DPI awareness: {dpi_e}")

    # Create and run the application
    try:
        app = TranslatorApp()
        # Verify critical method exists
        if not hasattr(app, 'clear_dir_list'):
            raise AttributeError("TranslatorApp is missing 'clear_dir_list' method. Ensure gui/main_window.py is up to date.")
        app.mainloop()
    except Exception as app_e:
        logger.critical(f"Unhandled exception in application main loop: {app_e}", exc_info=True)
        tk.messagebox.showerror("Lỗi Ứng Dụng", f"Đã xảy ra lỗi nghiêm trọng:\n{app_e}\nVui lòng kiểm tra file log: {LOG_FILE}")

    logger.info("--- Application Exited ---")