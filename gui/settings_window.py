# D:\Ebooks\Test_dich\gui\settings_window.py
import tkinter as tk
from tkinter import ttk, scrolledtext, messagebox
from ttkbootstrap.constants import *
from config_manager import AVAILABLE_MODELS, DEFAULT_SETTINGS

class SettingsWindow(tk.Toplevel):
    def __init__(self, parent, settings, callback):
        super().__init__(parent)
        self.title("Cài đặt")
        self.geometry("700x600")
        self.transient(parent)
        self.grab_set()
        self.callback = callback
        self.settings = settings.copy()

        # Main frame
        main_frame = ttk.Frame(self, padding=10)
        main_frame.pack(fill=BOTH, expand=True)

        # Notebook for tabs
        notebook = ttk.Notebook(main_frame)
        notebook.pack(fill=BOTH, expand=True, pady=5)

        # General Settings Tab
        general_frame = ttk.Frame(notebook, padding=10)
        notebook.add(general_frame, text="Chung")
        self.setup_general_settings(general_frame)

        # Translation Settings Tab
        translation_frame = ttk.Frame(notebook, padding=10)
        notebook.add(translation_frame, text="Dịch")
        self.setup_translation_settings(translation_frame)

        # Prompt Settings Tab
        prompt_frame = ttk.Frame(notebook, padding=10)
        notebook.add(prompt_frame, text="Prompt")
        self.setup_prompt_settings(prompt_frame)

        # Button Frame
        button_frame = ttk.Frame(main_frame)
        button_frame.pack(fill=X, pady=10)
        ttk.Button(button_frame, text="Lưu", command=self.save_settings, bootstyle=SUCCESS).pack(side=LEFT, padx=5)
        ttk.Button(button_frame, text="Hủy", command=self.destroy, bootstyle=SECONDARY).pack(side=LEFT, padx=5)
        ttk.Button(button_frame, text="Đặt lại mặc định", command=self.reset_to_defaults, bootstyle=WARNING).pack(side=RIGHT, padx=5)

    def setup_general_settings(self, parent):
        # Theme
        ttk.Label(parent, text="Theme giao diện:").grid(row=0, column=0, sticky=W, pady=5)
        self.theme_var = tk.StringVar(value=self.settings.get("theme", DEFAULT_SETTINGS["theme"]))
        theme_combo = ttk.Combobox(parent, textvariable=self.theme_var, values=["cyborg", "litera", "darkly", "flatly"], state="readonly")
        theme_combo.grid(row=0, column=1, sticky=EW, pady=5)

        # Max Workers
        ttk.Label(parent, text="Số luồng tối đa:").grid(row=1, column=0, sticky=W, pady=5)
        self.workers_var = tk.IntVar(value=self.settings.get("max_workers", DEFAULT_SETTINGS["max_workers"]))
        workers_spin = ttk.Spinbox(parent, from_=1, to=10, textvariable=self.workers_var, width=5)
        workers_spin.grid(row=1, column=1, sticky=W, pady=5)

        # Allow Chinese Characters
        ttk.Label(parent, text="Số ký tự tiếng Trung cho phép:").grid(row=2, column=0, sticky=W, pady=5)
        self.chinese_var = tk.IntVar(value=self.settings.get("allow_chinese_chars", DEFAULT_SETTINGS["allow_chinese_chars"]))
        chinese_spin = ttk.Spinbox(parent, from_=0, to=100, textvariable=self.chinese_var, width=5)
        chinese_spin.grid(row=2, column=1, sticky=W, pady=5)

        # Max Folder Retries
        ttk.Label(parent, text="Số lần thử lại thư mục:").grid(row=3, column=0, sticky=W, pady=5)
        self.retries_var = tk.IntVar(value=self.settings.get("max_folder_retries", DEFAULT_SETTINGS["max_folder_retries"]))
        retries_spin = ttk.Spinbox(parent, from_=0, to=5, textvariable=self.retries_var, width=5)
        retries_spin.grid(row=3, column=1, sticky=W, pady=5)

        # Request Timeout
        ttk.Label(parent, text="Thời gian chờ request (giây):").grid(row=4, column=0, sticky=W, pady=5)
        self.timeout_var = tk.IntVar(value=self.settings.get("request_timeout", DEFAULT_SETTINGS["request_timeout"]))
        timeout_spin = ttk.Spinbox(parent, from_=30, to=600, textvariable=self.timeout_var, width=5)
        timeout_spin.grid(row=4, column=1, sticky=W, pady=5)

    def setup_translation_settings(self, parent):
        # Primary Model
        ttk.Label(parent, text="Model chính:").grid(row=0, column=0, sticky=W, pady=5)
        self.primary_model_var = tk.StringVar(value=self.settings.get("primary_model", DEFAULT_SETTINGS["primary_model"]))
        primary_combo = ttk.Combobox(parent, textvariable=self.primary_model_var, values=AVAILABLE_MODELS, state="readonly")
        primary_combo.grid(row=0, column=1, sticky=EW, pady=5)

        # Secondary Model
        ttk.Label(parent, text="Model phụ:").grid(row=1, column=0, sticky=W, pady=5)
        self.secondary_model_var = tk.StringVar(value=self.settings.get("secondary_model", DEFAULT_SETTINGS["secondary_model"]))
        secondary_combo = ttk.Combobox(parent, textvariable=self.secondary_model_var, values=AVAILABLE_MODELS, state="readonly")
        secondary_combo.grid(row=1, column=1, sticky=EW, pady=5)

        # Final Retry Model
        ttk.Label(parent, text="Model thử lại cuối:").grid(row=2, column=0, sticky=W, pady=5)
        self.final_retry_model_var = tk.StringVar(value=self.settings.get("final_retry_model", DEFAULT_SETTINGS["final_retry_model"]))
        final_combo = ttk.Combobox(parent, textvariable=self.final_retry_model_var, values=AVAILABLE_MODELS, state="readonly")
        final_combo.grid(row=2, column=1, sticky=EW, pady=5)

        # Temperature
        ttk.Label(parent, text="Temperature:").grid(row=3, column=0, sticky=W, pady=5)
        self.temperature_var = tk.DoubleVar(value=self.settings.get("temperature", DEFAULT_SETTINGS["temperature"]))
        temp_scale = ttk.Scale(parent, from_=0.0, to=1.0, variable=self.temperature_var, orient=HORIZONTAL)
        temp_scale.grid(row=3, column=1, sticky=EW, pady=5)
        temp_entry = ttk.Entry(parent, textvariable=self.temperature_var, width=5)
        temp_entry.grid(row=3, column=2, padx=5)

    def setup_prompt_settings(self, parent):
        # Translation Prompt
        ttk.Label(parent, text="Prompt dịch:").grid(row=0, column=0, sticky=NW, pady=5)
        self.translation_prompt_text = scrolledtext.ScrolledText(parent, wrap=tk.WORD, height=6, font=("Consolas", 10))
        self.translation_prompt_text.grid(row=0, column=1, sticky=NSEW, pady=5, padx=5)
        self.translation_prompt_text.insert("1.0", self.settings.get("translation_prompt", DEFAULT_SETTINGS["translation_prompt"]))

        # Retry Prompt
        ttk.Label(parent, text="Prompt thử lại:").grid(row=1, column=0, sticky=NW, pady=5)
        self.retry_prompt_text = scrolledtext.ScrolledText(parent, wrap=tk.WORD, height=6, font=("Consolas", 10))
        self.retry_prompt_text.grid(row=1, column=1, sticky=NSEW, pady=5, padx=5)
        self.retry_prompt_text.insert("1.0", self.settings.get("retry_prompt", DEFAULT_SETTINGS["retry_prompt"]))

        parent.columnconfigure(1, weight=1)
        parent.rowconfigure(0, weight=1)
        parent.rowconfigure(1, weight=1)

    def save_settings(self):
        updated_settings = {
            "theme": self.theme_var.get(),
            "max_workers": self.workers_var.get(),
            "allow_chinese_chars": self.chinese_var.get(),
            "max_folder_retries": self.retries_var.get(),
            "request_timeout": self.timeout_var.get(),
            "primary_model": self.primary_model_var.get(),
            "secondary_model": self.secondary_model_var.get(),
            "final_retry_model": self.final_retry_model_var.get(),
            "temperature": self.temperature_var.get(),
            "translation_prompt": self.translation_prompt_text.get("1.0", tk.END).strip(),
            "retry_prompt": self.retry_prompt_text.get("1.0", tk.END).strip(),
        }
        # Validate prompts
        if "{text_chunk}" not in updated_settings["translation_prompt"]:
            if not messagebox.askyesno("Cảnh báo", "Prompt dịch không chứa '{text_chunk}'. Tiếp tục lưu?", parent=self):
                return
        if "{text_chunk}" not in updated_settings["retry_prompt"]:
            if not messagebox.askyesno("Cảnh báo", "Prompt thử lại không chứa '{text_chunk}'. Tiếp tục lưu?", parent=self):
                return
        self.callback(updated_settings)
        self.destroy()

    def reset_to_defaults(self):
        if messagebox.askyesno("Xác nhận", "Đặt lại tất cả cài đặt về mặc định?", parent=self):
            self.theme_var.set(DEFAULT_SETTINGS["theme"])
            self.workers_var.set(DEFAULT_SETTINGS["max_workers"])
            self.chinese_var.set(DEFAULT_SETTINGS["allow_chinese_chars"])
            self.retries_var.set(DEFAULT_SETTINGS["max_folder_retries"])
            self.timeout_var.set(DEFAULT_SETTINGS["request_timeout"])
            self.primary_model_var.set(DEFAULT_SETTINGS["primary_model"])
            self.secondary_model_var.set(DEFAULT_SETTINGS["secondary_model"])
            self.final_retry_model_var.set(DEFAULT_SETTINGS["final_retry_model"])
            self.temperature_var.set(DEFAULT_SETTINGS["temperature"])
            self.translation_prompt_text.delete("1.0", tk.END)
            self.translation_prompt_text.insert("1.0", DEFAULT_SETTINGS["translation_prompt"])
            self.retry_prompt_text.delete("1.0", tk.END)
            self.retry_prompt_text.insert("1.0", DEFAULT_SETTINGS["retry_prompt"])
            messagebox.showinfo("Thành công", "Đã đặt lại cài đặt mặc định.", parent=self)