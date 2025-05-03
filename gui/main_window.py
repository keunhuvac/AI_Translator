# /gui/main_window.py
import tkinter as tk
from tkinter import ttk, filedialog, messagebox, scrolledtext, font, simpledialog
import ttkbootstrap as ttk
from ttkbootstrap.constants import *
import threading
import queue
import os
#import random
import itertools
import logging
from concurrent.futures import ThreadPoolExecutor, as_completed, CancelledError
import time
from pathlib import Path
from ttkbootstrap import Style
from tkinter import font
import subprocess

# Import Pillow for PNG support
try:
    from PIL import Image, ImageTk
except ImportError:
    logging.error("Pillow library not found. Please install it: pip install Pillow")
    PIL_AVAILABLE = False
else:
    PIL_AVAILABLE = True

# Use absolute imports
try:
    from config_manager import (
        load_settings, save_settings, CONFIG_FILE,
        DEFAULT_THEME, AVAILABLE_MODELS, DEFAULT_PROMPT,
        DEFAULT_PRIMARY_MODEL, DEFAULT_SECONDARY_MODEL, DEFAULT_SETTINGS,
        RETRY_PROMPT, DEFAULT_ALLOWED_CHINESE_COUNT, DEFAULT_TEMPERATURE,
        DEFAULT_FINAL_RETRY_MODEL, DEFAULT_MAX_FOLDER_RETRIES, DEFAULT_REQUEST_TIMEOUT
    )
    from utils.helpers import contains_chinese
    from gui.reader_window import ReadWindow
    from gui.settings_window import SettingsWindow
    from gui.help_window import HelpWindow
    from gui.widgets import Tooltip, ListboxTooltip, ConfirmationDialog
    from core.translation_handler import translate_file_task
    try:
        from core.ebook_creator import EbookCreatorApp
        EBOOK_CREATOR_AVAILABLE = True
    except ImportError:
        logging.error("ebook_creator.py not found in 'core' folder or missing dependencies.")
        EBOOK_CREATOR_AVAILABLE = False
    try:
        import google.generativeai as genai
        from google.api_core import exceptions as google_exceptions
    except ImportError:
        logging.critical("google-generativeai library not found in main_window.")
except ImportError as import_err:
    logging.critical(f"Failed to import necessary modules: {import_err}")
    print(f"CRITICAL IMPORT ERROR: {import_err}. Ensure all modules are available and run from project root.")
    raise

logger = logging.getLogger(__name__)
ERROR_LOG_FILENAME = "00_dich_loi.txt"

class TranslatorApp(ttk.Window):
    def __init__(self):
        logger.info("--- Main Application Window Initializing ---")
        self.settings = load_settings()
        theme_to_use = self.settings.get("theme", DEFAULT_THEME)
        try:
            super().__init__(themename=theme_to_use)
        except tk.TclError as e:
            logger.error(f"TclError applying theme '{theme_to_use}' during init: {e}. Falling back.")
            temp_style = ttk.Style()
            available_themes = temp_style.theme_names()
            fallback_theme = 'litera' if 'litera' in available_themes else available_themes[0]
            theme_to_use = fallback_theme
            logger.warning(f"Falling back to theme: {fallback_theme}")
            self.settings["theme"] = theme_to_use
            del temp_style
            super().__init__(themename=theme_to_use)

        self.title("AI Novel Translator v3.26")
        self.geometry("1200x850")
        self.minsize(1000, 600)
        style = Style()
        default_font = font.nametofont("TkDefaultFont")
        default_font.configure(size=11)  # Tăng kích cỡ font lên 12
        style.configure('.', font=('TkDefaultFont', 11))  # Áp dụng cho tất cả widget
        style.configure('Treeview', font=('TkDefaultFont', 11))  # Font cho Treeview
        style.configure('Treeview.Heading', font=('TkDefaultFont', 11, 'bold'))  # Font cho tiêu đề Treeview
        # State variables
        self.api_keys = []
        self.api_key_iter = None
        self.current_api_key = None
        self.api_key_file = self.settings.get("api_key_file", None)
        self.processing_directories = self.settings.get("processing_dirs", [])
        self.completed_directories = self.settings.get("completed_dirs", [])
        self.translation_prompt = self.settings.get("translation_prompt", DEFAULT_PROMPT)
        self.retry_prompt = self.settings.get("retry_prompt", RETRY_PROMPT)
        self.primary_model_name = self.settings.get("primary_model", DEFAULT_PRIMARY_MODEL)
        self.secondary_model_name = self.settings.get("secondary_model", DEFAULT_SECONDARY_MODEL)
        self.max_workers = self.settings.get("max_workers", 3)
        self.allow_chinese_chars = tk.IntVar(value=self.settings.get("allow_chinese_chars", DEFAULT_ALLOWED_CHINESE_COUNT))
        self.temperature = tk.DoubleVar(value=self.settings.get("temperature", DEFAULT_TEMPERATURE))
        self.max_folder_retries = self.settings.get("max_folder_retries", DEFAULT_MAX_FOLDER_RETRIES)
        self.request_timeout = self.settings.get("request_timeout", DEFAULT_REQUEST_TIMEOUT)

        # Threading and Communication
        self.translation_active = threading.Event()
        self.stop_requested = threading.Event()
        self.log_queue = queue.Queue()
        self.progress_queue = queue.Queue()
        self.session_start_time = None

        # Highlight State
        self.highlighted_dir_index = None
        self.default_listbox_bg = None
        self.default_listbox_fg = None
        self.highlight_listbox_bg = '#FFF9C4'
        self.highlight_listbox_fg = 'black'

        # Load Icons
        self.icons = {}
        self.persistent_icons = []
        self._load_icons()

        # UI Setup
        self.setup_ui()

        # Configure Styles
        self._configure_styles()

        # Load API keys
        self._load_initial_api_keys()

        # Initialize Listbox Tooltips
        self.processing_tooltip_manager = ListboxTooltip(self.processing_listbox, self.processing_directories)
        self.completed_tooltip_manager = ListboxTooltip(self.completed_listbox, self.completed_directories)
        self._get_default_listbox_colors()

        # Start background queue listeners
        self.update_log_from_queue()
        self.update_progress_from_queue()

        self.protocol("WM_DELETE_WINDOW", self.on_closing)
        logger.info("Main Application Window initialized successfully.")

    def _load_icons(self):
        if not PIL_AVAILABLE:
            logger.warning("Pillow library not available for loading PNG icons.")
            return
        icon_dir = Path("icons")
        icon_sizes = {"large": (60, 60), "medium": (34, 34), "small": (24, 24)}
        icon_files = {
            "add": ("add.png", "medium"), "remove": ("remove.png", "medium"),
            "up": ("up.png", "medium"), "down": ("down.png", "medium"),
            "download": ("download.png", "medium"),
            "clear_all": ("clear_all.png", "medium"), "key": ("key.png", "small"),
            "start": ("start.png", "large"), "stop": ("stop.png", "large"),
            "read": ("read.png", "large"), "edit": ("edit.png", "large"),
            "ebook": ("ebook.png", "large"), "settings": ("settings.png", "medium"),
            "guide": ("guide.png", "medium"),
            "mark_done": ("mark_done.png", "medium"),
            "mark_undone": ("mark_undone.png", "medium")
        }
        if not icon_dir.is_dir():
            logger.warning(f"Icon directory '{icon_dir}' not found.")
            return

        self.persistent_icons.clear()
        for name, (filename, size_key) in icon_files.items():
            photo_image = None
            try:
                path = icon_dir / filename
                if path.exists():
                    size = icon_sizes.get(size_key, (16, 16))
                    img = Image.open(path).convert("RGBA").resize(size, Image.Resampling.LANCZOS)
                    photo_image = ImageTk.PhotoImage(img)
                    self.icons[name] = photo_image
                    self.persistent_icons.append(photo_image)
                    logger.debug(f"Loaded icon: {name} from {path} with size {size}")
                else:
                    logger.warning(f"Icon file not found: {path}. No icon for '{name}'.")
                    self.icons[name] = None
            except Exception as e:
                logger.error(f"Failed to load icon '{filename}': {e}", exc_info=True)
                self.icons[name] = None

    def _get_icon(self, name, fallback_text="?"):
        if PIL_AVAILABLE and name in self.icons and self.icons[name]:
            return {"image": self.icons[name], "compound": tk.LEFT}
        else:
            fallback_map = {
                "add": "+", "remove": "-", "up": "↑", "down": "↓",
                "download": "⬇️",
                "clear_all": "Clr", "key": "Key", "start": "▶", "stop": "⏹",
                "read": "📖", "edit": "✎", "ebook": "📦", "settings": "⚙", "guide": "❓",
                "mark_done": "✓", "mark_undone": "↩"
            }
            return {"text": fallback_map.get(name, fallback_text), "compound": tk.LEFT}

    def _get_default_listbox_colors(self):
        try:
            temp_item_needed = self.processing_listbox.size() == 0
            if temp_item_needed:
                self.processing_listbox.insert(tk.END, "temp")
            self.default_listbox_bg = self.processing_listbox.itemcget(0, 'background') or 'white'
            self.default_listbox_fg = self.processing_listbox.itemcget(0, 'foreground') or 'black'
            if temp_item_needed:
                self.processing_listbox.delete(0)
            logger.info(f"Default Listbox colors: BG='{self.default_listbox_bg}', FG='{self.default_listbox_fg}'")
        except tk.TclError:
            logger.warning("Could not get default listbox colors. Using hardcoded defaults.")
            self.default_listbox_bg = 'white'
            self.default_listbox_fg = 'black'

    def _configure_styles(self):
        logger.debug("Configuring custom ttk styles.")
        try:
            default_tab_font = font.nametofont("TkDefaultFont")
            bold_tab_font = default_tab_font.copy()
            bold_tab_font.config(weight='bold')
            selected_fg = self.style.colors.primary if hasattr(self.style, 'colors') else 'blue'
            self.style.map('TNotebook.Tab', foreground=[('selected', selected_fg)], font=[('selected', bold_tab_font)])
            logger.info(f"Configured style map for selected Notebook tab (FG: {selected_fg}).")
        except Exception as e:
            logger.warning(f"Error configuring styles: {e}")

    def _load_initial_api_keys(self):
        key_file_path = self.api_key_file
        if key_file_path and Path(key_file_path).is_file():
            logger.info(f"Found API key file in settings: {key_file_path}. Loading keys...")
            self.load_api_keys_from_file(key_file_path)
        else:
            logger.info("No API key file specified. Please select one.")
            self.log_message("INFO: Chưa chọn file API key. Vui lòng chọn file.", "info")
            self.key_file_label_var.set("File key: Chưa chọn")

    def setup_ui(self):
        logger.debug("Setting up UI elements.")
        self.columnconfigure(0, weight=1)
        self.rowconfigure(0, weight=1)

        # Main container
        main_frame = ttk.Frame(self, padding=10)
        main_frame.grid(row=0, column=0, sticky="nsew")
        main_frame.columnconfigure(1, weight=1)
        main_frame.rowconfigure(1, weight=1)

        # Toolbar
        toolbar_frame = ttk.Frame(main_frame)
        toolbar_frame.grid(row=0, column=0, columnspan=2, sticky="ew", pady=(0, 3))
        toolbar_buttons = [
            ("settings", self.open_settings, "Cài đặt", "primary"),
            ("download", self.open_download, "Tải truyện", "success"),
            ("guide", self.open_guide, "Hướng dẫn", "info"),
        ]
        for idx, (icon_name, command, tooltip, style) in enumerate(toolbar_buttons):
            icon_data = self._get_icon(icon_name)
            btn = ttk.Button(toolbar_frame, command=command, bootstyle=f"{style}-link", **icon_data)
            btn.grid(row=0, column=idx, padx=5, sticky="w")
            Tooltip(btn, tooltip)

        # Thêm tiêu đề ứng dụng
        title_label = ttk.Label(main_frame, text="Ứng dụng dịch thuật bằng AI", font=('TkDefaultFont', 16, 'bold'))
        title_label.grid(row=0, column=1, columnspan=2, sticky="ew", pady=(0, 5))

        # Left Frame
        self.left_frame = ttk.Frame(main_frame, padding=10, width=500)
        self.left_frame.grid(row=1, column=0, sticky="nsw")
        self.left_frame.grid_propagate(False)
        self.left_frame.columnconfigure(0, weight=1)

        # Right Frame (Log)
        right_frame = ttk.Frame(main_frame, padding=(0, 10, 10, 10))
        right_frame.grid(row=1, column=1, sticky="nsew")
        right_frame.rowconfigure(1, weight=1)
        right_frame.columnconfigure(0, weight=1)
        ttk.Label(right_frame, text="Log Theo Dõi", font=("Segoe UI", 11, "bold")).grid(row=0, column=0, sticky="nw", pady=(0, 5))
        log_font = ("Consolas", 11)
        self.log_text = scrolledtext.ScrolledText(right_frame, wrap=tk.WORD, height=15, state=DISABLED, font=log_font)
        self.log_text.grid(row=1, column=0, sticky="nsew")
        self._update_log_tag_colors()

        # Directory Controls Frame
        dir_controls_frame = ttk.Frame(self.left_frame)
        dir_controls_frame.grid(row=0, column=0, sticky="ew", pady=(0, 10))
        dir_buttons = [
            ("add", self.select_source_directory, "Thêm thư mục..."),
            ("remove", self.remove_selected_directory, "Xóa thư mục đã chọn"),
            ("up", self.move_dir_up, "Di chuyển lên"),
            ("down", self.move_dir_down, "Di chuyển xuống"),
            ("clear_all", self.clear_dir_list, "Xóa hết danh sách"),
            ("mark_done", self.mark_as_completed, "Đánh dấu hoàn thành"),
            ("mark_undone", self.mark_as_processing, "Đánh dấu chưa hoàn thành")
        ]
        for idx, (icon_name, command, tooltip) in enumerate(dir_buttons):
            icon_data = self._get_icon(icon_name)
            btn = ttk.Button(dir_controls_frame, command=command, bootstyle="link", **icon_data)
            btn.grid(row=0, column=idx, padx=2, sticky="w")
            Tooltip(btn, tooltip)
            setattr(self, f"btn_{icon_name}", btn)

        # Directory Management Frame with Tabs
        dir_frame = ttk.LabelFrame(self.left_frame, text="Danh sách Thư mục", padding=5)
        dir_frame.grid(row=1, column=0, sticky="nsew", pady=5)
        self.left_frame.rowconfigure(1, weight=0)
        dir_frame.columnconfigure(0, weight=1)
        dir_frame.rowconfigure(0, weight=1)
        self.notebook = ttk.Notebook(dir_frame, style='TNotebook')
        self.notebook.grid(row=0, column=0, sticky="nsew", pady=5, padx=5)
        self.notebook.bind("<<NotebookTabChanged>>", self._on_tab_changed)

        # Processing Tab
        processing_tab_frame = ttk.Frame(self.notebook)
        self.notebook.add(processing_tab_frame, text="Đang xử lý")
        processing_tab_frame.rowconfigure(0, weight=1)
        processing_tab_frame.columnconfigure(0, weight=1)
        proc_list_scrollbar = ttk.Scrollbar(processing_tab_frame, orient="vertical")
        proc_list_scrollbar.grid(row=0, column=1, sticky="ns")
        self.processing_listbox = tk.Listbox(processing_tab_frame, yscrollcommand=proc_list_scrollbar.set, selectmode=tk.EXTENDED, exportselection=False)
        self.processing_listbox.grid(row=0, column=0, sticky="nsew")
        proc_list_scrollbar.config(command=self.processing_listbox.yview)
        for dir_path in self.processing_directories:
            self.processing_listbox.insert(tk.END, os.path.basename(dir_path))

        # Completed Tab
        completed_tab_frame = ttk.Frame(self.notebook)
        self.notebook.add(completed_tab_frame, text="Hoàn thành")
        completed_tab_frame.rowconfigure(0, weight=1)
        completed_tab_frame.columnconfigure(0, weight=1)
        comp_list_scrollbar = ttk.Scrollbar(completed_tab_frame, orient="vertical")
        comp_list_scrollbar.grid(row=0, column=1, sticky="ns")
        self.completed_listbox = tk.Listbox(completed_tab_frame, yscrollcommand=comp_list_scrollbar.set, selectmode=tk.SINGLE, exportselection=False)
        self.completed_listbox.grid(row=0, column=0, sticky="nsew")
        comp_list_scrollbar.config(command=self.completed_listbox.yview)
        for dir_path in self.completed_directories:
            self.completed_listbox.insert(tk.END, os.path.basename(dir_path))

        # API Key file selection Frame
        key_file_frame = ttk.Frame(self.left_frame)
        key_file_frame.grid(row=2, column=0, sticky="ew", pady=10)
        icon_data_key = self._get_icon("key")
        btn_key_file = ttk.Button(key_file_frame, command=self.select_api_key_file, bootstyle="link", **icon_data_key)
        btn_key_file.pack(side=LEFT, padx=(0, 5))
        Tooltip(btn_key_file, "Chọn file chứa API Keys (.txt)")
        self.key_file_label_var = tk.StringVar(value="File key: Đang tải...")
        key_file_entry = ttk.Entry(key_file_frame, textvariable=self.key_file_label_var, state="readonly")
        key_file_entry.pack(side=LEFT, fill=X, expand=True)

        # Action Buttons Frame
        action_frame = ttk.Frame(self.left_frame)
        action_frame.grid(row=3, column=0, sticky="ew", pady=10)
        action_buttons = [
            ("start", self.start_translation_thread, "Bắt đầu dịch", "success"),
            ("stop", self.stop_translation, "Dừng dịch", "danger"),
            ("read", self.open_reader_contextual, "Mở cửa sổ đọc", "info"),
            ("ebook", self.open_ebook_creator_contextual, "Tạo Ebook", "primary"),
            ("edit", self.edit_prompt, "Chỉnh sửa prompt", "secondary")
        ]
        for idx, (icon_name, command, tooltip, style) in enumerate(action_buttons):
            icon_data = self._get_icon(icon_name)
            btn = ttk.Button(action_frame, command=command, bootstyle=f"{style}-link", **icon_data)
            btn.grid(row=0, column=idx, padx=5, sticky="ew")
            Tooltip(btn, tooltip)
            setattr(self, f"{icon_name}_button", btn)
        self.stop_button.config(state=DISABLED)
        self.ebook_button.config(state=tk.NORMAL if EBOOK_CREATOR_AVAILABLE else tk.DISABLED)

        # Progress Label Frame
        progress_frame = ttk.LabelFrame(self.left_frame, text="Tiến độ", padding=5)
        progress_frame.grid(row=4, column=0, sticky="ew", pady=5)
        self.folder_progress_label = ttk.Label(progress_frame, text="Thư mục: -/-", anchor=W)
        self.folder_progress_label.pack(fill=X)
        self.session_progress_label = ttk.Label(progress_frame, text="Session: 0/0/0 (0s)", anchor=W)
        self.session_progress_label.pack(fill=X)

        self._on_tab_changed()
        logger.debug("UI setup complete.")

    def _update_log_tag_colors(self):
        logger.debug("Updating log tag colors for current theme.")
        default_colors = {"info": "blue", "warning": "orange", "danger": "red", "success": "green", "skip": "gray", "debug": "purple", "default": "black"}
        try:
            colors = getattr(self.style, 'colors', None)
            self.log_text.tag_configure("info", foreground=colors.info if colors else default_colors['info'])
            self.log_text.tag_configure("warning", foreground=colors.warning if colors else default_colors['warning'])
            self.log_text.tag_configure("danger", foreground=colors.danger if colors else default_colors['danger'])
            self.log_text.tag_configure("success", foreground=colors.success if colors else default_colors['success'])
            self.log_text.tag_configure("skip", foreground=colors.secondary if colors else default_colors['skip'])
            self.log_text.tag_configure("debug", foreground=colors.primary if colors else default_colors['debug'])
            self.log_text.tag_configure("default", foreground=self.style.lookup('TLabel', 'foreground') or default_colors['default'])
        except Exception as e:
            logger.warning(f"Failed to update log tag colors: {e}. Using defaults.")
            for level, color in default_colors.items():
                self.log_text.tag_configure(level, foreground=color)

    def update_log_from_queue(self):
        try:
            while True:
                message, level = self.log_queue.get_nowait()
                self.log_text.config(state=tk.NORMAL)
                if self.log_text.index('end-1c') != "1.0":
                    self.log_text.insert(tk.END, "\n")
                timestamp = time.strftime("[%H:%M:%S]")
                tag = level if level in self.log_text.tag_names() else "default"
                self.log_text.insert(tk.END, f"{timestamp} {message}", tag)
                self.log_text.config(state=tk.DISABLED)
                self.log_text.yview(tk.END)
                log_level_enum = getattr(logging, level.upper(), logging.INFO)
                logger.log(log_level_enum, message)
                self.log_queue.task_done()
        except queue.Empty:
            pass
        except tk.TclError:
            logger.debug("TclError in update_log_from_queue (widget destroyed?).")
            return
        finally:
            if self.log_text.winfo_exists():
                self.after(150, self.update_log_from_queue)

    def update_progress_from_queue(self):
        try:
            while True:
                message_data = self.progress_queue.get_nowait()
                if isinstance(message_data, dict):
                    self.update_progress_labels(message_data)
                elif isinstance(message_data, tuple) and len(message_data) == 2:
                    msg_type, msg_payload = message_data
                    if msg_type == 'folder_start':
                        self._update_processing_highlight(msg_payload, highlight=True)
                    elif msg_type == 'folder_end':
                        self._update_processing_highlight(msg_payload, highlight=False)
                self.progress_queue.task_done()
        except queue.Empty:
            pass
        except tk.TclError:
            logger.debug("TclError in update_progress_from_queue (widget destroyed?).")
            return
        finally:
            if self.winfo_exists():
                self.after(100, self.update_progress_from_queue)

    def update_progress_labels(self, progress_data):
        if not self.folder_progress_label.winfo_exists():
            return
        folder_name = progress_data.get("folder_name", "-")
        folder_a = progress_data.get("folder_a", 0)
        folder_b = progress_data.get("folder_b", 0)
        self.folder_progress_label.config(text=f"Thư mục: {folder_name} [{folder_a}/{folder_b}]")
        session_c = progress_data.get("session_success", 0)
        session_d = progress_data.get("session_queued", 0)
        elapsed_time = progress_data.get("elapsed_time", 0)
        secs = int(elapsed_time % 60)
        mins = int((elapsed_time // 60) % 60)
        hrs = int(elapsed_time // 3600)
        time_str = f"{hrs:02d}:{mins:02d}:{secs:02d}" if hrs > 0 else f"{mins:02d}:{secs:02d}"
        session_completed = progress_data.get("completed_count", 0)
        self.session_progress_label.config(text=f"Session: {session_c}/{session_completed}/{session_d} ({time_str})")

    def log_message(self, message, level="info"):
        level = str(level).lower()
        valid_levels = ["info", "warning", "danger", "success", "skip", "debug", "default"]
        if level not in valid_levels:
            level = "info"
        self.log_queue.put((message, level))

    def update_progress(self, progress_dict):
        self.progress_queue.put(progress_dict)

    def save_app_settings(self):
        logger.debug("Gathering current settings to save.")
        current_settings = {
            "theme": self.settings.get("theme", DEFAULT_THEME),
            "api_key_file": self.api_key_file,
            "processing_dirs": self.processing_directories,
            "completed_dirs": self.completed_directories,
            "primary_model": self.primary_model_name,
            "secondary_model": self.secondary_model_name,
            "translation_prompt": self.translation_prompt,
            "retry_prompt": self.retry_prompt,
            "max_workers": self.max_workers,
            "reader_font_family": self.settings.get("reader_font_family", "Segoe UI"),
            "reader_font_size": self.settings.get("reader_font_size", 11),
            "allow_chinese_chars": self.allow_chinese_chars.get(),
            "temperature": self.temperature.get(),
            "max_folder_retries": self.max_folder_retries,
            "request_timeout": self.request_timeout,
        }
        save_settings(current_settings)
        self.settings = current_settings

    def open_settings(self):
        logger.debug("Opening settings window.")
        SettingsWindow(self, self.settings, self._update_settings)

    def open_download(self, event=None):
        subprocess.Popen(["python", "Piaotia_DL.py"])

    def open_guide(self):
        logger.debug("Opening guide window.")
        HelpWindow(self)

    def _update_settings(self, updated_settings):
        self.settings.update(updated_settings)
        self.primary_model_name = self.settings.get("primary_model", DEFAULT_PRIMARY_MODEL)
        self.secondary_model_name = self.settings.get("secondary_model", DEFAULT_SECONDARY_MODEL)
        self.translation_prompt = self.settings.get("translation_prompt", DEFAULT_PROMPT)
        self.retry_prompt = self.settings.get("retry_prompt", RETRY_PROMPT)
        self.max_workers = self.settings.get("max_workers", 3)
        self.allow_chinese_chars.set(self.settings.get("allow_chinese_chars", DEFAULT_ALLOWED_CHINESE_COUNT))
        self.temperature.set(self.settings.get("temperature", DEFAULT_TEMPERATURE))
        self.max_folder_retries = self.settings.get("max_folder_retries", DEFAULT_MAX_FOLDER_RETRIES)
        self.request_timeout = self.settings.get("request_timeout", DEFAULT_REQUEST_TIMEOUT)
        new_theme = self.settings.get("theme", DEFAULT_THEME)
        try:
            self.style.theme_use(new_theme)
            self._configure_styles()
            self._update_log_tag_colors()
            self._get_default_listbox_colors()
            self.log_message(f"INFO: Đã đổi theme thành {new_theme}", "info")
        except tk.TclError:
            logger.error(f"Failed to apply theme '{new_theme}'.")
            messagebox.showerror("Lỗi Theme", f"Không thể áp dụng theme '{new_theme}'.", parent=self)
        self.log_message("INFO: Cài đặt đã được cập nhật.", "info")
        logger.info("Settings updated from settings window.")

    def select_api_key_file(self):
        logger.debug("Opening API key file selection dialog.")
        initial_dir = os.path.dirname(self.api_key_file) if self.api_key_file else os.getcwd()
        filepath = filedialog.askopenfilename(title="Chọn file chứa API Keys (.txt)", filetypes=[("Text files", "*.txt"), ("All files", "*.*")], initialdir=initial_dir, parent=self)
        if filepath:
            logger.info(f"User selected API key file: {filepath}")
            if self.load_api_keys_from_file(filepath):
                self.api_key_file = filepath
                self.settings['api_key_file'] = self.api_key_file
        else:
            logger.debug("API key file selection cancelled.")
            self.log_message("INFO: Đã hủy chọn file API key.", "info")

    def load_api_keys_from_file(self, filepath):
        logger.info(f"Loading API keys from file: {filepath}")
        self.api_keys = []
        self.api_key_iter = None
        self.current_api_key = None
        file_basename = Path(filepath).name
        success = False
        self.key_file_label_var.set(f"File key: {file_basename} (Đang tải...)")
        self.update_idletasks()
        try:
            with Path(filepath).open('r', encoding='utf-8') as f:
                keys = [line.strip() for line in f if line.strip() and not line.strip().startswith('#')]
            if not keys:
                logger.warning(f"API key file '{filepath}' empty.")
                self.log_message(f"WARNING: File API key '{file_basename}' rỗng.", "warning")
                self.key_file_label_var.set(f"File key: {file_basename} (Rỗng)")
            else:
                #random.shuffle(keys)
                self.api_keys = keys
                self.api_key_iter = itertools.cycle(self.api_keys)
                logger.info(f"Loaded {len(keys)} keys.")
                self.log_message(f"INFO: Đã tải {len(keys)} API key.", "info")
                self.key_file_label_var.set(f"File key: {file_basename} ({len(keys)} keys)")
                if not self.configure_next_api_key():
                    self.log_message("WARNING: Lỗi cấu hình key đầu tiên.", "warning")
                    self.key_file_label_var.set(f"File key: {file_basename} ({len(keys)} keys), lỗi cấu hình")
                else:
                    success = True
        except FileNotFoundError:
            logger.error(f"File not found: {filepath}")
            self.log_message(f"ERROR: Không tìm thấy file key: {file_basename}", "danger")
            messagebox.showerror("Lỗi File Key", f"Không tìm thấy file:\n{filepath}", parent=self)
            self.key_file_label_var.set("File key: Lỗi - Không tìm thấy")
            self.api_key_file = None
            self.settings['api_key_file'] = None
        except Exception as e:
            logger.error(f"Failed read key file {filepath}: {e}", exc_info=True)
            self.log_message(f"ERROR: Lỗi đọc file key {file_basename}: {e}", "danger")
            messagebox.showerror("Lỗi File Key", f"Lỗi đọc file:\n{e}", parent=self)
            self.key_file_label_var.set("File key: Lỗi - Đọc file")
        return success

    def configure_next_api_key(self):
        if not self.api_keys or not self.api_key_iter:
            logger.warning("API Key Configure: No API keys loaded...")
            self.current_api_key = None
            if 'genai' in globals() and hasattr(genai, 'configure'):
                try:
                    genai.configure(api_key=None)
                except Exception as e:
                    logger.error(f"Error configuring genai with None key: {e}")
            return False

        start_key = self.current_api_key
        attempts = 0
        max_attempts = len(self.api_keys) + 1
        logger.debug(f"Configuring next API key. Start: ...{start_key[-4:] if start_key else 'None'}")

        while attempts < max_attempts:
            attempts += 1
            try:
                next_key = next(self.api_key_iter)
            except StopIteration:
                logger.error("Iterator stopped.")
                self.api_key_iter = itertools.cycle(self.api_keys)
                continue
            if not next_key:
                logger.warning("Skipping empty API key.")
                continue
            if next_key == start_key and attempts > 1:
                logger.warning(f"Single key ...{next_key[-4:]} failed.")
                break
            logger.info(f"Attempt {attempts}: Trying key ...{next_key[-4:]}")
            try:
                genai.configure(api_key=next_key)
                self.current_api_key = next_key
                self.log_message(f"INFO: Đã cấu hình API key: ...{next_key[-4:]}", "info")
                logger.info(f"Success key ...{next_key[-4:]}")
                return True
            except Exception as e:
                logger.error(f"Error config key ...{next_key[-4:]}: {e}", exc_info=True)
                self.log_message(f"ERROR: Lỗi config key ...{next_key[-4:]}: {e}", "danger")
        logger.error("API Key Configure Error: Exhausted attempts or no valid keys.")
        self.log_message("ERROR: Không thể cấu hình bất kỳ API key nào.", "danger")
        self.current_api_key = None
        return False

    def select_source_directory(self):
        logger.debug("Opening directory selection dialog.")
        dir_path = filedialog.askdirectory(title="Chọn thư mục chứa truyện gốc (.txt)", parent=self)
        if dir_path:
            full_path = os.path.abspath(dir_path)
            if full_path in self.processing_directories or full_path in self.completed_directories:
                logger.info(f"Directory already in list: {full_path}")
                self.log_message(f"INFO: Thư mục '{os.path.basename(full_path)}' đã có.", "info")
                messagebox.showinfo("Thông báo", f"Thư mục '{os.path.basename(full_path)}' đã có trong danh sách.", parent=self)
            else:
                logger.info(f"Adding source directory: {full_path}")
                self.processing_directories.append(full_path)
                self.processing_listbox.insert(tk.END, os.path.basename(full_path))
                self.log_message(f"INFO: Đã thêm thư mục: {os.path.basename(full_path)}", "info")
        else:
            logger.debug("Directory selection cancelled.")

    def remove_selected_directory(self):
        try:
            selected_tab_id = self.notebook.select()
            current_tab_index = self.notebook.index(selected_tab_id)
            target_listbox = self.processing_listbox if current_tab_index == 0 else self.completed_listbox
            target_data_list = self.processing_directories if current_tab_index == 0 else self.completed_directories
            tab_name = "Đang xử lý" if current_tab_index == 0 else "Hoàn thành"

            selected_indices = target_listbox.curselection()
            if not selected_indices:
                self.log_message(f"WARNING: Chọn thư mục trong tab '{tab_name}' để xóa.", "warning")
                return
            confirm_needed = (target_listbox.cget('selectmode') == tk.EXTENDED and len(selected_indices) > 1)
            if confirm_needed:
                confirm_dialog = ConfirmationDialog(self, "Xác nhận xóa", f"Xóa {len(selected_indices)} thư mục khỏi '{tab_name}'?")
                if not confirm_dialog.result:
                    logger.debug("Removal cancelled.")
                    return

            items_removed_count = 0
            indices_to_delete = sorted(list(selected_indices), reverse=True)
            for index in indices_to_delete:
                if 0 <= index < target_listbox.size() and index < len(target_data_list):
                    path = target_data_list[index]
                    target_data_list.remove(path)
                    target_listbox.delete(index)
                    items_removed_count += 1
                else:
                    logger.warning(f"Remove Error: Index {index} out of bounds on tab '{tab_name}'.")
            if items_removed_count > 0:
                self.log_message(f"INFO: Đã xóa {items_removed_count} thư mục khỏi '{tab_name}'.", "info")
        except Exception as e:
            logger.error(f"Error during remove: {e}", exc_info=True)
            self.log_message("ERROR: Lỗi xóa thư mục.", "danger")

    def move_dir_up(self):
        selected_indices = self.processing_listbox.curselection()
        if not selected_indices:
            self.log_message("WARNING: Chọn thư mục để di chuyển lên.", "warning")
            return
        if len(selected_indices) > 1:
            self.log_message("WARNING: Chỉ di chuyển một thư mục mỗi lần.", "warning")
            return
        index = selected_indices[0]
        if index > 0:
            item_path = self.processing_directories.pop(index)
            self.processing_directories.insert(index - 1, item_path)
            display_text = self.processing_listbox.get(index)
            self.processing_listbox.delete(index)
            self.processing_listbox.insert(index - 1, display_text)
            self.processing_listbox.selection_clear(0, tk.END)
            self.processing_listbox.selection_set(index - 1)
            self.processing_listbox.activate(index - 1)
            self.processing_listbox.see(index - 1)

    def move_dir_down(self):
        selected_indices = self.processing_listbox.curselection()
        if not selected_indices:
            self.log_message("WARNING: Chọn thư mục để di chuyển xuống.", "warning")
            return
        if len(selected_indices) > 1:
            self.log_message("WARNING: Chỉ di chuyển một thư mục mỗi lần.", "warning")
            return
        index = selected_indices[0]
        if index < self.processing_listbox.size() - 1:
            item_path = self.processing_directories.pop(index)
            self.processing_directories.insert(index + 1, item_path)
            display_text = self.processing_listbox.get(index)
            self.processing_listbox.delete(index)
            self.processing_listbox.insert(index + 1, display_text)
            self.processing_listbox.selection_clear(0, tk.END)
            self.processing_listbox.selection_set(index + 1)
            self.processing_listbox.activate(index + 1)
            self.processing_listbox.see(index + 1)

    def clear_dir_list(self):
        if not self.processing_directories:
            self.log_message("INFO: Danh sách 'Đang xử lý' đã trống.", "info")
            return
        confirm_dialog = ConfirmationDialog(self, "Xác nhận", "Xóa tất cả khỏi 'Đang xử lý'?")
        if confirm_dialog.result:
            self.processing_listbox.delete(0, tk.END)
            self.processing_directories.clear()
            self.log_message("INFO: Đã xóa hết danh sách 'Đang xử lý'.", "info")

    def mark_as_completed(self):
        selected_indices = self.processing_listbox.curselection()
        if not selected_indices:
            self.log_message("WARNING: Chọn thư mục để đánh dấu hoàn thành.", "warning")
            return
        moved_count = 0
        indices_to_delete = sorted(list(selected_indices), reverse=True)
        for index in indices_to_delete:
            if 0 <= index < len(self.processing_directories):
                full_path = self.processing_directories[index]
                if full_path not in self.completed_directories:
                    self.completed_directories.append(full_path)
                    self.completed_listbox.insert(tk.END, self.processing_listbox.get(index))
                    self.processing_directories.remove(full_path)
                    self.processing_listbox.delete(index)
                    moved_count += 1
        if moved_count > 0:
            self.log_message(f"INFO: Đã chuyển {moved_count} thư mục sang 'Hoàn thành'.", "info")

    def mark_as_processing(self):
        selected_indices = self.completed_listbox.curselection()
        if not selected_indices:
            self.log_message("WARNING: Chọn thư mục để chuyển lại.", "warning")
            return
        moved_count = 0
        indices_to_delete = sorted(list(selected_indices), reverse=True)
        for index in indices_to_delete:
            if 0 <= index < len(self.completed_directories):
                full_path = self.completed_directories[index]
                if full_path not in self.processing_directories:
                    self.processing_directories.append(full_path)
                    self.processing_listbox.insert(tk.END, self.completed_listbox.get(index))
                    self.completed_directories.remove(full_path)
                    self.completed_listbox.delete(index)
                    moved_count += 1
        if moved_count > 0:
            self.log_message(f"INFO: Đã chuyển {moved_count} thư mục về 'Đang xử lý'.", "info")

    def _get_selected_full_path(self, listbox, data_list):
        selected_indices = listbox.curselection()
        if not selected_indices:
            return None, None
        if len(selected_indices) > 1:
            return None, "multiple"
        index = selected_indices[0]
        if 0 <= index < listbox.size() and index < len(data_list):
            return data_list[index], None
        return None, "sync_error"

    def open_reader_contextual(self):
        selected_tab_id = self.notebook.select()
        current_tab_index = self.notebook.index(selected_tab_id)
        listbox = self.processing_listbox if current_tab_index == 0 else self.completed_listbox
        data_list = self.processing_directories if current_tab_index == 0 else self.completed_directories
        tab_name = "Đang xử lý" if current_tab_index == 0 else "Hoàn thành"
        full_path, error_type = self._get_selected_full_path(listbox, data_list)
        if error_type == "multiple":
            messagebox.showwarning("Chọn một", "Chọn một thư mục để đọc.", parent=self)
        elif error_type == "sync_error":
            messagebox.showerror("Lỗi Đồng Bộ", f"Lỗi lựa chọn '{tab_name}'.", parent=self)
        elif full_path is None:
            messagebox.showwarning("Chưa chọn", f"Chọn thư mục trong '{tab_name}'.", parent=self)
        else:
            self._open_reader_window(full_path)

    def open_ebook_creator_contextual(self):
        if not EBOOK_CREATOR_AVAILABLE:
            messagebox.showerror("Lỗi", "Không tìm thấy mô-đun tạo Ebook.", parent=self)
            return
        selected_tab_id = self.notebook.select()
        current_tab_index = self.notebook.index(selected_tab_id)
        if current_tab_index != 1:
            messagebox.showwarning("Chú ý", "Chỉ tạo Ebook từ tab 'Hoàn thành'.", parent=self)
            return
        full_path, error_type = self._get_selected_full_path(self.completed_listbox, self.completed_directories)
        if error_type == "multiple":
            messagebox.showwarning("Chọn một", "Chọn một thư mục để tạo Ebook.", parent=self)
        elif error_type == "sync_error":
            messagebox.showerror("Lỗi Đồng Bộ", "Lỗi lựa chọn 'Hoàn thành'.", parent=self)
        elif full_path is None:
            messagebox.showwarning("Chưa chọn", "Chọn thư mục trong 'Hoàn thành'.", parent=self)
        else:
            self._open_ebook_creator(full_path)

    def _open_reader_window(self, selected_dir_path):
        logger.info(f"Opening reader for: {selected_dir_path}")
        try:
            dir_to_check = Path(selected_dir_path)
            if not dir_to_check.is_dir():
                logger.error(f"Directory does not exist: {selected_dir_path}")
                messagebox.showerror("Lỗi", f"Thư mục không tồn tại:\n{selected_dir_path}", parent=self)
                return
            reader_font_family = self.settings.get("reader_font_family", "Segoe UI")
            reader_font_size = self.settings.get("reader_font_size", 11)
            if not hasattr(self, 'reader_window') or not self.reader_window or not self.reader_window.winfo_exists():
                self.reader_window = ReadWindow(self, selected_source_dir=selected_dir_path, initial_font_family=reader_font_family, initial_font_size=reader_font_size)
                self.reader_window.protocol("WM_DELETE_WINDOW", self.reader_window.on_reader_closing)
            else:
                self.reader_window.lift()
                self.reader_window.update_source_directory(selected_dir_path)
        except Exception as e:
            logger.error(f"Error opening reader window: {e}", exc_info=True)
            messagebox.showerror("Lỗi", f"Không thể mở cửa sổ đọc:\n{e}", parent=self)

    def _open_ebook_creator(self, selected_dir_path):
        logger.info(f"Opening Ebook Creator for: {selected_dir_path}")
        try:
            from pathlib import Path
            translated_dir_path = Path(selected_dir_path) / "translated"
            if not translated_dir_path.is_dir():
                messagebox.showerror("Lỗi", f"Không tìm thấy thư mục 'translated' trong:\n{selected_dir_path}", parent=self)
                return
            ebook_top_level = tk.Toplevel(self)
            ebook_top_level.title("Tạo Ebook EPUB")
            ebook_top_level.geometry("800x600")
            ebook_top_level.wm_attributes("-topmost", False)  # Đảm bảo không luôn ở trên
            # Bỏ transient để cửa sổ Ebook không luôn ở trên main GUI
            # ebook_top_level.transient(self)
            ebook_app = EbookCreatorApp(ebook_top_level, source_dir=str(translated_dir_path))
            # Không cần đặt directory_path và gọi start_scan_files_thread thủ công
            # vì EbookCreatorApp đã tự động quét source_dir trong __init__
        except Exception as e:
            logger.error(f"Error opening Ebook Creator: {e}", exc_info=True)
            messagebox.showerror("Lỗi", f"Không thể mở trình tạo Ebook:\n{e}", parent=self)

    def _on_tab_changed(self, event=None):
        selected_tab_id = self.notebook.select()
        current_tab_index = self.notebook.index(selected_tab_id)
        is_processing_tab = (current_tab_index == 0)
        remove_button_state = tk.NORMAL
        dir_modify_processing_state = tk.NORMAL if is_processing_tab else tk.DISABLED
        self.btn_remove.config(state=remove_button_state)
        self.btn_up.config(state=dir_modify_processing_state)
        self.btn_down.config(state=dir_modify_processing_state)
        self.btn_clear_all.config(state=dir_modify_processing_state)
        self.btn_mark_done.config(state=dir_modify_processing_state)
        self.btn_mark_undone.config(state=tk.DISABLED if is_processing_tab else tk.NORMAL)
        self.ebook_button.config(state=tk.NORMAL if not is_processing_tab and EBOOK_CREATOR_AVAILABLE else tk.DISABLED)
        self.read_button.config(state=tk.NORMAL)
        logger.debug(f"Tab changed to index {current_tab_index}. Button states updated.")

    def edit_prompt(self):
        logger.debug("Opening prompt edit dialog.")
        prompt_editor = tk.Toplevel(self)
        prompt_editor.title("Chỉnh sửa Prompt Dịch")
        prompt_editor.geometry("600x400")
        prompt_editor.transient(self)
        prompt_editor.grab_set()
        ttk.Label(prompt_editor, text="Nhập prompt mới ({text_chunk}):").pack(pady=(10, 5), padx=10, anchor=W)
        prompt_font = ("Consolas", 10)
        prompt_text = scrolledtext.ScrolledText(prompt_editor, wrap=tk.WORD, height=15, width=70, font=prompt_font, undo=True)
        prompt_text.pack(pady=5, padx=10, fill=BOTH, expand=True)
        prompt_text.insert('1.0', self.translation_prompt)
        button_frame = ttk.Frame(prompt_editor)
        button_frame.pack(pady=(5, 10), padx=10, fill=X)
        def save_prompt_and_close():
            new_prompt = prompt_text.get('1.0', tk.END + '-1c').strip()
            if new_prompt:
                if "{text_chunk}" not in new_prompt:
                    confirm = ConfirmationDialog(prompt_editor, "Cảnh báo Prompt", "Prompt không chứa '{text_chunk}'. Vẫn lưu?")
                    if not confirm.result:
                        return
                self.translation_prompt = new_prompt
                self.log_message("INFO: Prompt dịch đã cập nhật.", "info")
                logger.info("Translation prompt updated.")
                self.settings['translation_prompt'] = self.translation_prompt
                prompt_editor.destroy()
            else:
                messagebox.showerror("Lỗi Prompt", "Prompt không được trống.", parent=prompt_editor)
        ttk.Button(button_frame, text="Lưu", command=save_prompt_and_close, bootstyle=SUCCESS).pack(side=LEFT, padx=5)
        ttk.Button(button_frame, text="Hủy", command=prompt_editor.destroy, bootstyle=SECONDARY).pack(side=RIGHT, padx=5)
        prompt_editor.wait_window()

    def translation_worker(self):
        logger.info("Translation worker thread started.")
        self.session_start_time = time.time()
        session_total_queued = 0
        session_completed_count = 0
        session_success_count = 0
        current_processing_dir = None
        folder_started = False

        try:
            with open(ERROR_LOG_FILENAME, 'w', encoding='utf-8') as f_err:
                f_err.write(f"# Log lỗi dịch bắt đầu lúc: {time.strftime('%Y-%m-%d %H:%M:%S')}\n")
            logger.info(f"Cleared/created error log: {ERROR_LOG_FILENAME}")
        except Exception as e:
            logger.error(f"Cannot clear/create error log '{ERROR_LOG_FILENAME}': {e}")
            self.log_message(f"ERROR: Cannot create error log file", "danger")

        final_progress_details = {}
        try:
            if not self.current_api_key:
                logger.warning("Worker: No API key configured. Attempting configuration...")
                self.log_message("INFO: Đang kiểm tra và cấu hình API key...", "info")
                if not self.configure_next_api_key():
                    logger.error("Worker: Failed to configure any API key.")
                    self.log_message("ERROR: Không thể cấu hình API key.", "danger")
                    return

            dirs_to_scan = list(self.processing_directories)
            if not dirs_to_scan:
                logger.info("Worker: Processing list is empty.")
                self.log_message("INFO: Danh sách 'Đang xử lý' trống.", "info")
                return

            total_dirs_in_session = len(dirs_to_scan)
            final_retry_model_name = self.settings.get("final_retry_model", DEFAULT_FINAL_RETRY_MODEL)

            for dir_index, source_dir_str in enumerate(dirs_to_scan):
                if self.stop_requested.is_set():
                    break
                current_processing_dir = source_dir_str
                folder_fully_translated = False
                folder_attempt = 0

                while folder_attempt <= self.max_folder_retries and not folder_fully_translated:
                    folder_attempt += 1
                    folder_started = False
                    attempt_log_prefix = f"(Lần thử {folder_attempt}/{self.max_folder_retries+1})" if self.max_folder_retries > 0 else ""
                    try:
                        if self.stop_requested.is_set():
                            break
                        source_dir = Path(source_dir_str)
                        if not source_dir.is_dir():
                            logger.warning(f"Skipping dir {attempt_log_prefix}: {source_dir_str}")
                            self.log_message(f"SKIP {attempt_log_prefix}: Bỏ qua thư mục không tồn tại: {os.path.basename(source_dir_str)}", "skip")
                            folder_fully_translated = True
                            break

                        self.progress_queue.put(('folder_start', source_dir_str))
                        folder_started = True
                        folder_name = source_dir.name
                        logger.info(f"--- Processing folder {dir_index+1}/{total_dirs_in_session} {attempt_log_prefix}: {folder_name} ---")
                        self.log_message(f"INFO {attempt_log_prefix}: Bắt đầu xử lý: {folder_name}", "info")

                        folder_files_to_process_this_attempt = []
                        current_folder_total_files = 0
                        current_folder_already_translated = 0
                        folder_session_success_this_attempt = 0
                        folder_session_completed_this_attempt = 0
                        source_items = []

                        target_dir = source_dir / "translated"
                        os.makedirs(target_dir, exist_ok=True)

                        for item in source_dir.iterdir():
                            if item.is_file() and item.suffix.lower() == ".txt":
                                current_folder_total_files += 1
                                source_items.append(item)

                        if target_dir.is_dir():
                            current_folder_already_translated = len(list(target_dir.glob("*.txt")))

                        logger.info(f"'{folder_name}' {attempt_log_prefix} Counts: Src={current_folder_total_files}, Trg={current_folder_already_translated}")
                        progress_details = {
                            "folder_name": f"{folder_name} {attempt_log_prefix}",
                            "folder_a": current_folder_already_translated,
                            "folder_b": current_folder_total_files,
                            "session_success": session_success_count,
                            "session_queued": session_total_queued,
                            "elapsed_time": time.time() - self.session_start_time,
                            "completed_count": session_completed_count,
                        }
                        self.update_progress(progress_details)
                        final_progress_details = progress_details

                        if current_folder_total_files > 0 and current_folder_already_translated >= current_folder_total_files:
                            logger.info(f"Folder '{folder_name}' completed based on counts {attempt_log_prefix}.")
                            self.log_message(f"INFO {attempt_log_prefix}: Thư mục '{folder_name}' đã dịch đủ file.", "info")
                            folder_fully_translated = True
                            break

                        folder_queued_this_attempt = 0
                        for source_path in source_items:
                            if self.stop_requested.is_set():
                                break
                            filename = source_path.name
                            target_path = target_dir / filename
                            if not target_path.exists() and "download" not in filename.lower() and not filename.startswith('.'):
                                folder_files_to_process_this_attempt.append((str(source_path), str(target_path)))
                                folder_queued_this_attempt += 1

                        if folder_attempt == 1:
                            session_total_queued += folder_queued_this_attempt

                        progress_details = {
                            "folder_name": f"{folder_name} {attempt_log_prefix}",
                            "folder_a": current_folder_already_translated,
                            "folder_b": current_folder_total_files,
                            "session_success": session_success_count,
                            "session_queued": session_total_queued,
                            "elapsed_time": time.time() - self.session_start_time,
                            "completed_count": session_completed_count
                        }
                        self.update_progress(progress_details)
                        final_progress_details = progress_details

                        total_files_this_attempt = len(folder_files_to_process_this_attempt)
                        if total_files_this_attempt == 0:
                            logger.info(f"No new files to translate in {folder_name} {attempt_log_prefix}.")
                            self.log_message(f"INFO {attempt_log_prefix}: '{folder_name}' không có file mới cần dịch.", "info")
                            if current_folder_total_files > 0 and current_folder_already_translated >= current_folder_total_files:
                                folder_fully_translated = True
                            continue

                        logger.info(f"Starting translation pool {attempt_log_prefix}: {total_files_this_attempt} files in {folder_name}...")
                        app_state_for_task = {
                            "primary_model_name": self.primary_model_name,
                            "secondary_model_name": self.secondary_model_name,
                            "final_retry_model_name": final_retry_model_name,
                            "translation_prompt": self.translation_prompt,
                            "retry_prompt": self.retry_prompt,
                            "stop_event": self.stop_requested,
                            "log_message": self.log_message,
                            "configure_next_api_key": self.configure_next_api_key,
                            "available_models": AVAILABLE_MODELS,
                            "allowed_chinese_count": self.allow_chinese_chars.get(),
                            "temperature": self.temperature.get(),
                            "request_timeout": self.request_timeout
                        }

                        with ThreadPoolExecutor(max_workers=self.max_workers) as executor:
                            future_to_src = {executor.submit(translate_file_task, src, tgt, app_state_for_task): src for src, tgt in folder_files_to_process_this_attempt}
                            for future in as_completed(future_to_src):
                                if self.stop_requested.is_set():
                                    [f.cancel() for f in future_to_src if not f.done()]
                                    break
                                source_file_path = future_to_src[future]
                                source_filename = os.path.basename(source_file_path)
                                folder_a_this_loop = current_folder_already_translated + folder_session_success_this_attempt
                                folder_b_this_loop = current_folder_total_files
                                session_completed_count += 1
                                folder_session_completed_this_attempt += 1
                                try:
                                    _, success, status_msg = future.result()
                                    if success:
                                        session_success_count += 1
                                        folder_session_success_this_attempt += 1
                                        current_folder_already_translated += 1
                                        logger.info(f"Task '{source_filename}' {attempt_log_prefix} success: {status_msg}")
                                    else:
                                        logger.error(f"Task '{source_filename}' {attempt_log_prefix} failed: {status_msg}")
                                        with open(ERROR_LOG_FILENAME, 'a', encoding='utf-8') as f_err:
                                            f_err.write(f"{source_file_path} ({status_msg})\n")
                                except Exception as exc:
                                    logger.error(f'Task "{source_filename}" {attempt_log_prefix} exception: {exc}', exc_info=True)
                                    self.log_message(f'ERROR: File "{source_filename}" {attempt_log_prefix} lỗi: {exc}', "danger")
                                    with open(ERROR_LOG_FILENAME, 'a', encoding='utf-8') as f_err:
                                        f_err.write(f"{source_file_path} (Lỗi task: {exc})\n")

                                progress_details = {
                                    "folder_name": f"{folder_name} {attempt_log_prefix}",
                                    "folder_a": current_folder_already_translated,
                                    "folder_b": folder_b_this_loop,
                                    "session_success": session_success_count,
                                    "session_queued": session_total_queued,
                                    "elapsed_time": time.time() - self.session_start_time,
                                    "completed_count": session_completed_count
                                }
                                self.update_progress(progress_details)
                                final_progress_details = progress_details

                        folder_summary = f"Thư mục '{folder_name}' {attempt_log_prefix}: {folder_session_success_this_attempt}/{total_files_this_attempt} file mới."
                        logger.info(f"--- Finished attempt {folder_attempt} for folder: {folder_name}. Success: {folder_session_success_this_attempt}/{total_files_this_attempt} ---")
                        self.log_message(f"INFO: {folder_summary}", "info")

                    finally:
                        if folder_started:
                            self.progress_queue.put(('folder_end', source_dir_str))
                            logger.debug(f"Sent folder_end signal for attempt {folder_attempt} of: {source_dir_str}")

                    temp_translated_count = len(list(target_dir.glob("*.txt")))
                    if current_folder_total_files > 0 and temp_translated_count >= current_folder_total_files:
                        folder_fully_translated = True
                        logger.info(f"Folder '{folder_name}' confirmed complete after attempt {folder_attempt}.")

                    if self.stop_requested.is_set():
                        break

                current_processing_dir = None
                if self.stop_requested.is_set():
                    break

        except Exception as worker_exc:
            logger.critical(f"Critical error in translation worker: {worker_exc}", exc_info=True)
            self.log_message(f"CRITICAL: Lỗi nghiêm trọng trong luồng dịch: {worker_exc}", "danger")

        finally:
            if current_processing_dir and folder_started:
                self.progress_queue.put(('folder_end', current_processing_dir))
                logger.warning(f"Sent final folder_end for: {os.path.basename(current_processing_dir)}")

            logger.debug("Entering outer finally block in translation_worker.")
            end_time = time.time()
            total_duration = end_time - self.session_start_time if self.session_start_time else 0
            final_processed_info = f"{session_success_count}/{session_completed_count}/{session_total_queued}"

            if self.stop_requested.is_set():
                logger.info(f"Translation stopped by user after {total_duration:.2f}s.")
                self.log_message(f"INFO: Quá trình dịch đã bị dừng. ({final_processed_info})", "warning")
            else:
                logger.info(f"Translation finished in {total_duration:.2f}s. Processed: {final_processed_info}.")
                self.log_message(f"INFO: Hoàn thành session {final_processed_info} sau {total_duration:.1f}s.", "success")

            self.translation_active.clear()
            self.stop_requested.clear()
            self.after(0, self._update_button_states_after_stop)
            final_progress_details.update({
                "elapsed_time": total_duration,
                "session_success": session_success_count,
                "completed_count": session_completed_count,
                "session_queued": session_total_queued,
                "folder_name": "-",
                "folder_a": 0,
                "folder_b": 0
            })
            self.after(10, lambda: self.update_progress(final_progress_details))

    def _update_button_states_after_stop(self):
        logger.debug("Updating buttons and clearing highlight post-translation.")
        self._clear_listbox_highlight()
        self.start_button.config(state=tk.NORMAL)
        self.stop_button.config(state=tk.DISABLED)

    def start_translation_thread(self):
        logger.info("Attempting translation start...")
        if not self.processing_directories:
            messagebox.showwarning("Thiếu thông tin", "Thêm thư mục vào 'Đang xử lý'.", parent=self)
            return
        if not self.api_keys:
            messagebox.showwarning("Thiếu thông tin", "Chọn file API key.", parent=self)
            return
        if not self.current_api_key:
            logger.warning("No API key configured. Trying...")
            self.log_message("INFO: Đang cấu hình API key...", "info")
            if not self.configure_next_api_key():
                logger.error("Failed key config.")
                messagebox.showerror("Lỗi API Key", "Lỗi cấu hình API key.", parent=self)
                return
        if self.translation_active.is_set():
            logger.warning("Translation already active.")
            self.log_message("WARNING: Dịch đang chạy.", "warning")
            return
        logger.info("Starting translation thread...")
        self.translation_active.set()
        self.start_button.config(state=tk.DISABLED)
        self.stop_button.config(state=tk.NORMAL)
        self.update_progress({"folder_name":"-", "folder_a":0, "folder_b":0, "session_success":0, "session_queued":0, "elapsed_time":0, "completed_count":0})
        self.translation_thread = threading.Thread(target=self.translation_worker, daemon=True)
        self.translation_thread.start()
        self.log_message("INFO: Bắt đầu quá trình dịch...", "info")

    def stop_translation(self):
        if self.translation_active.is_set() and not self.stop_requested.is_set():
            logger.info("Requesting translation stop...")
            self.log_message("INFO: Đang yêu cầu dừng...", "info")
            self.stop_requested.set()
            self.stop_button.config(state=tk.DISABLED)
        else:
            logger.info("Stop ignored: No translation active.")
            self.log_message("INFO: Không có dịch nào đang chạy.", "info")

    def _update_processing_highlight(self, dir_path, highlight=True):
        target_index = self.processing_directories.index(str(dir_path)) if str(dir_path) in self.processing_directories else -1
        if target_index >= 0 and highlight:
            self.processing_listbox.itemconfigure(target_index, background=self.highlight_listbox_bg, foreground=self.highlight_listbox_fg)
            self.highlighted_dir_index = target_index
            self.processing_listbox.see(target_index)
        elif not highlight and self.highlighted_dir_index is not None:
            self._clear_listbox_highlight()

    def _clear_listbox_highlight(self):
        if self.highlighted_dir_index is not None:
            self.processing_listbox.itemconfigure(self.highlighted_dir_index, background=self.default_listbox_bg, foreground=self.default_listbox_fg)
            self.highlighted_dir_index = None

    def on_closing(self):
        logger.info("--- Application Closing Sequence ---")
        if self.translation_active.is_set():
            confirm = ConfirmationDialog(self, "Xác nhận thoát", "Dịch đang chạy.\nThoát sẽ dừng tiến trình.\nBạn chắc chắn muốn thoát?")
            if confirm.result:
                self.stop_translation()
                time.sleep(0.2)
                self.save_app_settings()
                self.destroy()
        else:
            self.save_app_settings()
            self.destroy()