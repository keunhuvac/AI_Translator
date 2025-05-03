# gui/reader_window.py
import tkinter as tk
from tkinter import ttk, messagebox, font, scrolledtext, filedialog # Added filedialog
from pathlib import Path
import os
import re
import copy
import threading
import queue
import logging
import time
import csv # Added csv
import subprocess # Added subprocess
import sys # Added sys for platform check

logger = logging.getLogger(__name__)
##
VIETNAMESE_NUMBER_WORDS = {
    "không", "linh", "một", "mốt", "hai", "nhị", "ba", "tam", "bốn", "tư", "tứ",
    "năm", "lăm", "ngũ", "sáu", "lục", "bảy", "thất", "tám", "bát", "chín", "cửu",
    "mười", "mươi", "thập", "trăm", "bách", "nghìn", "ngàn", "thiên", "vạn"
}
# Từ khóa bắt đầu chương
CHAPTER_KEYWORDS = {"chương", "quyển", "đệ", "c", "*", "#"}  #Bổ sung , "*", "#"
# Từ đệm có thể có
BUFFER_WORDS = {"thứ"}
##

# ==============================================================
# LỚP CỬA SỔ XÁC NHẬN ĐƠN GIẢN
# ==============================================================
class ConfirmationDialog(tk.Toplevel):
    def __init__(self, parent, title, message):
        super().__init__(parent)
        self.title(title)
        self.result = False
        self.resizable(False, False)
        #self.transient(parent) # Consider re-enabling if modality is desired
        #self.grab_set() # Consider re-enabling if modality is desired

        content_frame = ttk.Frame(self, padding="10 10 10 10")
        content_frame.pack(expand=True, fill="both")
        ttk.Label(content_frame, text=message, wraplength=350, justify="left").pack(padx=10, pady=(0, 15))
        button_frame = ttk.Frame(content_frame)
        button_frame.pack(pady=5)
        yes_button = ttk.Button(button_frame, text="Đồng ý (Yes)", command=self.on_yes, width=12, bootstyle="success")
        yes_button.pack(side="left", padx=10)
        no_button = ttk.Button(button_frame, text="Hủy bỏ (No)", command=self.on_no, width=12, bootstyle="secondary")
        no_button.pack(side="left", padx=10)

        self.update_idletasks()
        parent_x = parent.winfo_rootx(); parent_y = parent.winfo_rooty()
        parent_width = parent.winfo_width(); parent_height = parent.winfo_height()
        dialog_width = self.winfo_width(); dialog_height = self.winfo_height()
        x = parent_x + (parent_width // 2) - (dialog_width // 2)
        y = parent_y + (parent_height // 2) - (dialog_height // 2)
        self.geometry(f'+{x}+{y}')
        self.wait_window(self) # Make it modal

    def on_yes(self): self.result = True; self.destroy()
    def on_no(self): self.result = False; self.destroy()

# ==============================================================
# LỚP CỬA SỔ XEM TRƯỚC CHUNG (CHO FIX/INSERT)
# ==============================================================
class PreviewWindow(tk.Toplevel):
    MAX_PREVIEW_ITEMS = 1000
    def __init__(self, parent, window_title, preview_data, total_selected_count, apply_callback_func, apply_button_text="✅ Áp dụng"):
        super().__init__(parent)
        self.title(window_title)
        self.geometry("1200x750")
        #self.minsize(700, 450)
        #self.transient(parent)
        #self.grab_set()

        self.preview_data = preview_data
        self.total_selected_count = total_selected_count
        self.apply_callback = apply_callback_func
        self.apply_button_text = apply_button_text

        self.setup_ui()
        self.populate_treeview()

        self.update_idletasks()
        parent_x = parent.winfo_rootx(); parent_y = parent.winfo_rooty()
        parent_width = parent.winfo_width(); parent_height = parent.winfo_height()
        dialog_width = self.winfo_width(); dialog_height = self.winfo_height()
        x = parent_x + (parent_width // 2) - (dialog_width // 2)
        y = parent_y + (parent_height // 2) - (dialog_height // 2)
        self.geometry(f'+{x}+{y}')
        # self.wait_window(self) # Removed modal for preview

    def setup_ui(self):
        self.info_label = ttk.Label(self, text="", bootstyle="warning")
        self.info_label.pack(pady=(5, 0), padx=10, anchor="w")
        tree_frame = ttk.Frame(self)
        tree_frame.pack(fill="both", expand=True, padx=10, pady=5)
        tree_scroll = ttk.Scrollbar(tree_frame)
        tree_scroll.pack(side="right", fill="y")
        self.tree = ttk.Treeview(tree_frame, columns=("filename", "original", "proposed"), show="headings", yscrollcommand=tree_scroll.set, selectmode="none")
        tree_scroll.config(command=self.tree.yview)
        self.tree.heading("filename", text="Tên File")
        self.tree.heading("original", text="Dòng đầu gốc")
        self.tree.heading("proposed", text="Dòng đầu mới (Đề xuất)")
        self.tree.column("filename", anchor="w", width=200, stretch=tk.NO)
        self.tree.column("original", anchor="w", width=350)
        self.tree.column("proposed", anchor="w", width=350)
        self.tree.pack(fill="both", expand=True)
        button_frame = ttk.Frame(self)
        button_frame.pack(fill="x", padx=10, pady=(5, 10))
        ttk.Button(button_frame, text="Hủy bỏ", command=self.destroy, bootstyle="secondary").pack(side="right", padx=5)
        apply_count = len(self.preview_data)
        ttk.Button(button_frame, text=f"{self.apply_button_text} ({apply_count} file)", command=self.trigger_apply, bootstyle="success").pack(side="right", padx=5)

    def populate_treeview(self):
        for i in self.tree.get_children(): self.tree.delete(i)
        items_to_display = self.preview_data[:self.MAX_PREVIEW_ITEMS]
        for item in items_to_display:
            orig_display = item.get('original_line', '')[:100] + ('...' if len(item.get('original_line', '')) > 100 else '')
            new_display_key = 'new_line' if 'new_line' in item else 'inserted_line'
            new_display = item.get(new_display_key, '')[:100] + ('...' if len(item.get(new_display_key, '')) > 100 else '')
            self.tree.insert("", tk.END, values=(item.get('filename', ''), orig_display, new_display))
        if len(self.preview_data) > self.MAX_PREVIEW_ITEMS: self.info_label.config(text=f"Lưu ý: Chỉ hiển thị {self.MAX_PREVIEW_ITEMS} / {len(self.preview_data)} mục sẽ áp dụng...")
        elif not self.preview_data: self.info_label.config(text="Không có thay đổi xem trước.")
        else: self.info_label.config(text="")

    def trigger_apply(self):
        confirm = messagebox.askyesno("Xác nhận cuối cùng", f"Áp dụng thay đổi cho {len(self.preview_data)} file?", parent=self)
        if confirm: self.apply_callback(self.preview_data); self.destroy()


# --- LỚP PREVIEW MỚI CHO VIỆC XÓA LẶP ---
class DuplicatePreviewWindow(tk.Toplevel):
    """Cửa sổ xem trước các dòng lặp sẽ bị xóa."""
    MAX_PREVIEW_ITEMS = 200
    def __init__(self, parent, window_title, preview_data, apply_callback_func):
        super().__init__(parent)
        self.title(window_title)
        self.geometry("950x550")
        self.minsize(700, 450)
        #self.transient(parent) # Consider re-enabling
        #self.grab_set() # Consider re-enabling

        self.preview_data = preview_data # List of dicts from show_duplicate_line_preview
        self.apply_callback = apply_callback_func

        self.setup_ui()
        self.populate_treeview()

        self.update_idletasks()
        parent_x=parent.winfo_rootx(); parent_y=parent.winfo_rooty(); parent_width=parent.winfo_width(); parent_height=parent.winfo_height(); dialog_width=self.winfo_width(); dialog_height=self.winfo_height(); x=parent_x+(parent_width//2)-(dialog_width//2); y=parent_y+(parent_height//2)-(dialog_height//2); self.geometry(f'+{x}+{y}')
        # self.wait_window(self) # Removed modal

    def setup_ui(self):
        self.info_label = ttk.Label(self, text="", bootstyle="warning")
        self.info_label.pack(pady=(5, 0), padx=10, anchor="w")

        tree_frame = ttk.Frame(self)
        tree_frame.pack(fill="both", expand=True, padx=10, pady=5)
        tree_scroll = ttk.Scrollbar(tree_frame)
        tree_scroll.pack(side="right", fill="y")

        self.tree = ttk.Treeview(tree_frame, columns=("filename", "line_to_keep", "line_to_remove"), show="headings", yscrollcommand=tree_scroll.set, selectmode="none")
        tree_scroll.config(command=self.tree.yview)

        self.tree.heading("filename", text="Tên File")
        self.tree.heading("line_to_keep", text="Dòng đầu (Giữ lại)")
        self.tree.heading("line_to_remove", text="Dòng lặp (Sẽ xóa)")

        self.tree.column("filename", anchor="w", width=200, stretch=tk.NO)
        self.tree.column("line_to_keep", anchor="w", width=350)
        self.tree.column("line_to_remove", anchor="w", width=350)

        self.tree.pack(fill="both", expand=True)

        button_frame = ttk.Frame(self)
        button_frame.pack(fill="x", padx=10, pady=(5, 10))

        ttk.Button(button_frame, text="Hủy bỏ", command=self.destroy, bootstyle="secondary").pack(side="right", padx=5)
        apply_count = len(self.preview_data)
        ttk.Button(button_frame, text=f"✅ Áp dụng xóa ({apply_count} file)", command=self.trigger_apply, bootstyle="danger").pack(side="right", padx=5)

    def populate_treeview(self):
        for i in self.tree.get_children(): self.tree.delete(i)
        items_to_display = self.preview_data[:self.MAX_PREVIEW_ITEMS]
        for item in items_to_display:
            keep_display = item.get('original_line', '')[:100] + ('...' if len(item.get('original_line', '')) > 100 else '')
            remove_display = item.get('proposed', '')[:100] + ('...' if len(item.get('proposed', '')) > 100 else '') # 'proposed' holds the line to remove
            self.tree.insert("", tk.END, values=(item.get('filename', ''), keep_display, remove_display))

        if len(self.preview_data) > self.MAX_PREVIEW_ITEMS: self.info_label.config(text=f"Lưu ý: Chỉ hiển thị {self.MAX_PREVIEW_ITEMS} / {len(self.preview_data)} mục sẽ được xóa...")
        elif not self.preview_data: self.info_label.config(text="Không tìm thấy dòng lặp nào.")
        else: self.info_label.config(text="")

    def trigger_apply(self):
        confirm = messagebox.askyesno("Xác nhận cuối cùng", f"Áp dụng xóa các dòng lặp hiển thị cho {len(self.preview_data)} file?", parent=self)
        if confirm:
            self.apply_callback(self.preview_data)
            self.destroy()

# ==============================================================
# LỚP CỬA SỔ DANH SÁCH DÒNG ĐẦU
# ==============================================================
class FirstLinesWindow(tk.Toplevel):
    def __init__(self, parent, folder_path, reader_window_ref):
        super().__init__(parent)
        self.title("📋 Danh sách dòng đầu")
        self.geometry("950x650")
        self.minsize(750, 500)
        self.reader_window_ref = reader_window_ref # Reference to main reader
        self.base_folder_path = Path(folder_path)
        self.folder_path = self.base_folder_path / "translated" # Target the translated folder
        self.file_list = []
        self.all_items_data = [] # List of dictionaries: {'iid', 'filename', 'line', 'path', 'orig_filename', 'orig_line'}
        self.filter_after_id = None
        self.progress_queue = queue.Queue() # For thread communication

        logger.info(f"FirstLinesWindow: Initializing for folder {self.folder_path}")

        try:
            if not self.folder_path.is_dir(): raise FileNotFoundError(f"Thư mục không tồn tại: {self.folder_path}")
            self.file_list = sorted([f.name for f in self.folder_path.glob("*.txt") if f.is_file()])
            if not self.file_list: raise FileNotFoundError(f"Không tìm thấy file .txt trong: {self.folder_path}")
            logger.info(f"FirstLinesWindow: Found {len(self.file_list)} files.")
        except Exception as e:
            logger.error(f"FirstLinesWindow: Error reading directory: {e}", exc_info=True)
            messagebox.showerror("Lỗi đọc thư mục", f"{e}", parent=self)
            self.after(10, self.destroy); return # Use after for safe destroy

        self.setup_ui()
        self._preload_data() # Load all data initially
        self._populate_treeview() # Populate the treeview with all data
        self.search_entry.focus_set()

    def setup_ui(self):
        # --- Filter Frame ---
        top_filter = ttk.Frame(self); top_filter.pack(fill="x", padx=10, pady=5)
        self.filter_type_var = tk.StringVar(value="Chứa"); filter_options = ["Chứa", "Bắt đầu bằng", "Không chứa"]
        self.filter_combo = ttk.Combobox(top_filter, textvariable=self.filter_type_var, values=filter_options, state="readonly", width=12); self.filter_combo.pack(side="left", padx=(0, 5))
        self.search_var = tk.StringVar(); self.search_entry = ttk.Entry(top_filter, textvariable=self.search_var, width=40); self.search_entry.pack(side="left", padx=5, fill="x", expand=True)
        self.hide_correct_var = tk.BooleanVar(value=False); self.hide_correct_cb = ttk.Checkbutton(top_filter, text="Ẩn file đúng định dạng", variable=self.hide_correct_var); self.hide_correct_cb.pack(side="left", padx=10)

        # --- Treeview Frame ---
        tree_frame = ttk.Frame(self); tree_frame.pack(fill="both", expand=True, padx=10, pady=(0, 5))
        tree_scroll_y = ttk.Scrollbar(tree_frame, orient="vertical"); tree_scroll_y.pack(side="right", fill="y")
        tree_scroll_x = ttk.Scrollbar(tree_frame, orient="horizontal"); tree_scroll_x.pack(side="bottom", fill="x")
        self.tree = ttk.Treeview(tree_frame, columns=("filename", "first_line"), show="headings", selectmode="extended", yscrollcommand=tree_scroll_y.set, xscrollcommand=tree_scroll_x.set)
        tree_scroll_y.config(command=self.tree.yview); tree_scroll_x.config(command=self.tree.xview)
        self.tree.heading("filename", text="Tên File", anchor='w'); self.tree.heading("first_line", text="Dòng đầu", anchor='w')
        self.tree.column("filename", anchor="w", width=250, stretch=tk.NO); self.tree.column("first_line", anchor="w", width=600)
        self.tree.pack(fill="both", expand=True)

        # --- Bindings ---
        self.search_var.trace_add("write", self._on_filter_change);
        self.filter_combo.bind("<<ComboboxSelected>>", self._on_filter_change);
        self.hide_correct_cb.config(command=self._on_filter_change);
        self.tree.bind("<Double-Button-1>", self._on_double_click) # Bind double-click

        # --- Action Buttons ---
        self.bottom_frame = ttk.Frame(self); self.bottom_frame.pack(fill="x", padx=10, pady=(5, 10))
        ttk.Button(self.bottom_frame, text="🔧 Fix số Chương", command=self.show_fix_preview).pack(side="left", padx=5)
        ttk.Button(self.bottom_frame, text="➕ Chèn số Chương", command=self.show_insert_preview).pack(side="left", padx=5)
        ttk.Button(self.bottom_frame, text="🧹 Xóa dòng đầu", command=self.trigger_delete_first_lines, bootstyle="danger").pack(side="right", padx=5) # Danger style

    def _preload_data(self):
        self.all_items_data.clear(); logger.info("FirstLinesWindow: Preloading...")
        for i, filename in enumerate(self.file_list):
            path = self.folder_path / filename; line = ""
            try:
                encodings_to_try = ['utf-8', 'cp1252', 'latin-1']; read_ok = False
                for enc in encodings_to_try:
                    try:
                        # Read only the first line to speed up preloading
                        with path.open('r', encoding=enc) as f: line = f.readline().strip(); read_ok = True; break
                    except UnicodeDecodeError: continue # Try next encoding
                    except FileNotFoundError: line = "[Lỗi: Không tìm thấy]"; logger.warning(f"Not found preload (inner): {path}"); read_ok = True; break
                    except Exception as read_err: line = f"[Lỗi đọc: {type(read_err).__name__}]"; logger.error(f"Err read line {filename} {enc}: {read_err}"); read_ok = True; break
                if not read_ok: line = "[Lỗi đọc encoding]"; logger.warning(f"Failed read {filename} encodings.")
            except Exception as e: line = f"[Lỗi: {type(e).__name__}]"; logger.error(f"Unexpected preload error {filename}: {e}", exc_info=True)
            self.all_items_data.append({'iid': i, 'filename': filename.lower(), 'line': line.lower(), 'path': path, 'orig_filename': filename, 'orig_line': line})
        logger.info(f"FirstLinesWindow: Preloaded {len(self.all_items_data)} items.")

    def _populate_treeview(self, items_to_display=None):
        logger.debug("FirstLinesWindow: Populating treeview...")
        try:
            self.tree.delete(*self.tree.get_children()); data_source = items_to_display if items_to_display is not None else self.all_items_data
            for item_data in data_source:
                display_line = item_data['orig_line'][:150] + ('...' if len(item_data['orig_line']) > 150 else '')
                self.tree.insert('', tk.END, iid=item_data['iid'], values=(item_data['orig_filename'], display_line))
            logger.debug(f"Populated treeview with {len(data_source)} items.")
        except Exception as e: logger.error(f"Error populate treeview: {e}", exc_info=True)

    def _apply_filter(self):
        """Filters the preloaded data based on UI controls and updates Treeview."""
        filter_type = self.filter_type_var.get()
        keyword_raw = self.search_var.get().strip() # Keyword gốc người dùng nhập
        keyword_lower = keyword_raw.lower() # Keyword chữ thường cho so sánh case-insensitive
        hide_correct = self.hide_correct_var.get()
        logger.debug(f"Apply Filter: Type={filter_type}, Keyword='{keyword_raw}', Hide={hide_correct}")

        filtered_data = []
        for item_data in self.all_items_data:
            filename_lower = item_data['filename']
            orig_filename = item_data['orig_filename']
            line_lower = item_data['line']
            orig_line = item_data['orig_line']

            # Keyword Filtering
            matches_keyword = False
            if not keyword_raw: matches_keyword = True # Always match if no keyword
            else:
                if filter_type == "Chứa":
                    try:
                        # Use regex search for more flexible "contains" (case-insensitive)
                        pattern = re.escape(keyword_raw)
                        matches_keyword = bool(re.search(pattern, orig_line, flags=re.IGNORECASE)) or \
                                          bool(re.search(pattern, orig_filename, flags=re.IGNORECASE))
                    except re.error as re_err: # Handle invalid regex patterns entered by user
                        logger.warning(f"Invalid regex in filter '{keyword_raw}': {re_err}")
                        matches_keyword = False # Treat as no match if regex is bad
                elif filter_type == "Bắt đầu bằng":
                    matches_keyword = filename_lower.startswith(keyword_lower) or line_lower.startswith(keyword_lower)
                elif filter_type == "Không chứa":
                    try:
                        pattern = re.escape(keyword_raw)
                        matches_keyword = not (re.search(pattern, orig_line, flags=re.IGNORECASE) or
                                               re.search(pattern, orig_filename, flags=re.IGNORECASE))
                    except re.error as re_err:
                        logger.warning(f"Invalid regex in filter '{keyword_raw}': {re_err}")
                        matches_keyword = True # Treat as matching "not contains" if regex is bad

            if not matches_keyword: continue

            # Hide Correct Formatting Filter
            if hide_correct:
                try:
                    # Extract expected chapter number from filename more robustly
                    match_num_filename = re.search(r'[Cc](?:hương)?\s*(\d+)', orig_filename)
                    expected_num = int(match_num_filename.group(1)) if match_num_filename else None

                    if expected_num is not None:
                        # Check if the first line starts with "Chương {expected_num}" (case-insensitive)
                        correct_pattern = re.compile(rf'^\s*[Cc]hương\s+{expected_num}\s*[:].*', re.IGNORECASE) # Require colon now
                        if correct_pattern.match(orig_line):
                            continue # Skip this item as it's correctly formatted
                except ValueError: logger.warning(f"Could not parse chapter num from filename: {orig_filename}")
                except Exception as e: logger.error(f"Error checking 'hide_correct' for {orig_filename}: {e}")

            # If all filters passed, add to results
            filtered_data.append(item_data)

        self._populate_treeview(filtered_data)
        logger.debug(f"Filter done. Displaying {len(filtered_data)} items.")


    def _on_filter_change(self, *args):
        if self.filter_after_id: self.after_cancel(self.filter_after_id)
        # Determine if the change requires immediate update (combobox, checkbox) or delay (typing)
        is_immediate = False
        delay = 350 # Slightly longer delay for typing
        if args:
            # Check if the first argument is an event and which widget triggered it
            if isinstance(args[0], tk.Event) and args[0].widget in (self.filter_combo, self.hide_correct_cb):
                is_immediate = True
                delay = 0 # No delay for combo/check box change
            # Check if the change comes from the Checkbutton's variable trace
            elif len(args) >= 1 and isinstance(args[0], str) and args[0] == str(self.hide_correct_var._name):
                 is_immediate = True
                 delay = 0
        # If not immediate, use the standard delay for the Entry widget's typing
        self.filter_after_id = self.after(delay, self._apply_filter)

    def _run_file_operation_in_thread(self, items_to_process, operation_func, progress_title, completion_message_func):
        """Runs a file operation function on selected items in a separate thread."""
        if not items_to_process:
            messagebox.showwarning("Chưa chọn", "Không có mục hợp lệ để xử lý.", parent=self)
            return

        # Create Progress Window
        progress_win = tk.Toplevel(self)
        progress_win.title(progress_title)
        progress_win.geometry("400x130") # Slightly wider
        progress_win.transient(self)
        progress_win.grab_set()
        progress_win.resizable(False, False)

        status_label = ttk.Label(progress_win, text="Đang chuẩn bị...", wraplength=380) # Allow wrapping
        status_label.pack(pady=(10,5), padx=10, anchor='w', fill='x')
        progress_bar = ttk.Progressbar(progress_win, length=380, mode='determinate', maximum=len(items_to_process))
        progress_bar.pack(pady=(0,10), padx=10, fill='x')

        # Center the progress window relative to the parent (FirstLinesWindow)
        self.update_idletasks()
        parent_x=self.winfo_rootx(); parent_y=self.winfo_rooty(); parent_width=self.winfo_width(); parent_height=self.winfo_height()
        dialog_width=progress_win.winfo_width(); dialog_height=progress_win.winfo_height()
        x=parent_x+(parent_width//2)-(dialog_width//2); y=parent_y+(parent_height//2)-(dialog_height//2)
        progress_win.geometry(f'+{x}+{y}')
        progress_win.update() # Ensure it's drawn

        # --- Worker Thread ---
        def worker():
            processed_count=0; error_count=0; skipped_count=0; changed_paths = set()
            total_items = len(items_to_process)

            for i, item_data in enumerate(items_to_process):
                # Ensure progress window hasn't been closed prematurely
                if not progress_win.winfo_exists():
                    logger.warning("Progress window closed during operation.")
                    # Signal partial completion maybe? Or just break. Let's break.
                    break

                path = item_data.get('path')
                filename = item_data.get('orig_filename', path.name if path else 'N/A')

                # Check if path is valid before proceeding
                if not path or not isinstance(path, Path):
                    logger.error(f"Invalid path found in item data for worker: {item_data}")
                    error_count += 1
                    self.progress_queue.put({'type': 'progress', 'value': i + 1}) # Update progress even on error
                    continue # Skip this item

                # Update status label before processing the item
                status_text = f"Xử lý: {filename} ({i+1}/{total_items})"
                self.progress_queue.put({'type': 'status', 'text': status_text})

                try:
                    result = operation_func(item_data) # Call the specific operation

                    # Interpret the result string
                    if result == 'processed':
                        processed_count += 1
                        changed_paths.add(path)
                    elif result == 'skipped':
                        skipped_count += 1
                    elif result == 'error':
                         error_count += 1
                    else: # Unexpected result from operation_func
                        logger.warning(f"Unexpected result '{result}' from operation on {filename}")
                        # Decide how to count this - maybe error?
                        error_count += 1

                except Exception as e:
                    # Catch exceptions *within* the operation_func itself
                    logger.error(f"Worker thread exception processing {filename}: {e}", exc_info=True)
                    error_count += 1 # Count as error if the operation itself raises an exception

                # Update progress bar *after* processing the item
                self.progress_queue.put({'type': 'progress', 'value': i + 1})
                # time.sleep(0.01) # Optional small delay for visual feedback

            # Signal completion once the loop finishes or breaks
            self.progress_queue.put({
                'type': 'completion',
                'processed': processed_count,
                'errors': error_count,
                'skipped': skipped_count,
                'changed_paths': changed_paths
            })
            logger.info(f"Worker thread finished: Processed={processed_count}, Errors={error_count}, Skipped={skipped_count}")

        # --- Queue Checker ---
        def check_queue():
            try:
                while True: # Process all available messages
                    msg = self.progress_queue.get_nowait()

                    # Check window validity *before* updating widgets
                    if not progress_win.winfo_exists():
                        logger.info("Progress window closed, stopping queue check.")
                        return

                    if msg['type'] == 'status':
                        status_label.config(text=msg['text'])
                    elif msg['type'] == 'progress':
                        progress_bar['value'] = msg['value']
                    elif msg['type'] == 'completion':
                        progress_win.destroy() # Close progress window first
                        # Call the provided function to format the completion message
                        final_message = completion_message_func(msg['processed'], msg['errors'], msg['skipped'])
                        messagebox.showinfo("Hoàn tất", final_message, parent=self) # Show final message
                        # Trigger update in main reader if needed
                        self._trigger_main_reader_update(msg.get('changed_paths', set()))
                        return # Stop checking queue

                    # progress_win.update_idletasks() # Update UI - may cause slight lag but ensures responsiveness

            except queue.Empty:
                # Queue is empty, reschedule check if window still open
                if progress_win.winfo_exists():
                    self.after(100, check_queue)
            except tk.TclError as e:
                 # Catch potential errors if widgets are destroyed unexpectedly
                 logger.error(f"TclError during queue check (window likely closed): {e}")
                 if progress_win.winfo_exists(): progress_win.destroy() # Attempt cleanup
            except Exception as qe:
                logger.error(f"Unexpected error processing progress queue: {qe}", exc_info=True)
                if progress_win.winfo_exists(): progress_win.destroy() # Attempt cleanup

        # Start the worker thread and the queue checker
        threading.Thread(target=worker, daemon=True).start()
        self.after(50, check_queue) # Start checking the queue shortly after

    def _update_treeview_item(self, iid, new_first_line):
        try:
            if self.tree.exists(iid): # Check if item still exists
                item_values = list(self.tree.item(iid, 'values'))
                if item_values: # Ensure values were retrieved
                    display_line = new_first_line[:150] + ('...' if len(new_first_line) > 150 else '')
                    item_values[1] = display_line # Update the second column (first_line)
                    self.tree.item(iid, values=tuple(item_values))
            # else: logger.debug(f"Item iid={iid} no longer exists in treeview, skipping update.")
        except tk.TclError: logger.warning(f"Item iid={iid} not found during treeview update (TclError).")
        except Exception as e: logger.error(f"Error updating treeview item iid={iid}: {e}", exc_info=True)

    def _get_selected_data(self):
        selected_iids_str = self.tree.selection()
        if not selected_iids_str:
            logger.debug("No items selected in the treeview.")
            return []

        selected_data = []
        # Efficiently find selected items using a dictionary lookup (if needed for very large lists)
        # For moderate lists, iterating is fine.
        iid_map = {item['iid']: item for item in self.all_items_data}

        for iid_str in selected_iids_str:
            try:
                iid_int = int(iid_str)
                found_item = iid_map.get(iid_int) # Use dict.get for fast lookup
                if found_item:
                    selected_data.append(found_item)
                else:
                     logger.warning(f"Selected iid {iid_int} not found in all_items_data mapping.")
            except ValueError: logger.warning(f"Invalid iid format in selection: '{iid_str}'.")

        logger.debug(f"Retrieved {len(selected_data)} selected items data.")
        return selected_data

    def _process_delete_first_line(self, item_data):
        """Removes the first line of the file. Returns 'processed', 'skipped', or 'error'."""
        path = item_data.get('path')
        iid = item_data.get('iid')
        if not path or iid is None: return 'error' # Basic validation

        try:
            current_content = None; encodings = ['utf-8', 'cp1252', 'latin-1']; read_ok = False
            for enc in encodings:
                try:
                    current_content = path.read_text(encoding=enc); read_ok = True; break
                except UnicodeDecodeError: pass
                except FileNotFoundError: logger.error(f"File not found during delete: {path.name}"); return 'error'
            if not read_ok or current_content is None:
                logger.error(f"Could not read file {path.name} with any encoding for deletion."); return 'error'

            lines = current_content.splitlines()
            if not lines or len(lines) == 1: # Skip if empty or only one line
                return 'skipped'

            # Find the first non-blank line *after* the first line
            first_valid_content_index = -1
            for idx in range(1, len(lines)):
                 if lines[idx].strip():
                     first_valid_content_index = idx
                     break

            if first_valid_content_index != -1:
                 # Join lines starting from the first valid content line
                 new_content = "\n".join(lines[first_valid_content_index:])
                 new_first_line_display = lines[first_valid_content_index] # The new first line to display
            else:
                 # All subsequent lines were blank, result is empty file
                 new_content = ""
                 new_first_line_display = ""

            # Only write if content actually changed
            if new_content != current_content:
                path.write_text(new_content, encoding="utf-8")
                # Update internal data store immediately
                original_item = next((item for item in self.all_items_data if item['iid'] == iid), None)
                if original_item:
                    original_item['orig_line'] = new_first_line_display
                    original_item['line'] = new_first_line_display.lower()
                # Schedule Treeview update on the main thread
                self.after(0, lambda i=iid, n=new_first_line_display: self._update_treeview_item(i, n))
                return 'processed'
            else:
                return 'skipped' # No change needed

        except Exception as e:
            logger.error(f"Error deleting first line for {path.name}: {e}", exc_info=True)
            return 'error'

    def _process_apply_fix(self, item_data):
        """Applies the proposed 'new_line' fix to the file. Returns 'processed', 'skipped', or 'error'."""
        path = item_data.get('path')
        new_first_line = item_data.get('new_line')
        iid = item_data.get('iid')
        if not path or new_first_line is None or iid is None: return 'error'

        try:
            current_content = None; encodings = ['utf-8', 'cp1252', 'latin-1']; read_ok = False
            for enc in encodings:
                try:
                    current_content = path.read_text(encoding=enc); read_ok = True; break
                except UnicodeDecodeError: pass
                except FileNotFoundError: logger.error(f"File not found during fix: {path.name}"); return 'error'
            if not read_ok or current_content is None:
                 logger.error(f"Could not read file {path.name} with any encoding for fixing."); return 'error'

            lines = current_content.splitlines()
            if not lines: # If the file was empty, treat it as an error or skip? Let's skip.
                logger.warning(f"Skipping fix for empty file: {path.name}")
                return 'skipped'

            # Only modify if the first line is actually different
            if lines[0] == new_first_line:
                 logger.debug(f"Skipping fix for {path.name}: first line already matches.")
                 return 'skipped'

            lines[0] = new_first_line # Replace the first line
            new_content = "\n".join(lines)

            # Write the modified content
            path.write_text(new_content, encoding="utf-8")

            # Update internal data store
            original_item = next((item for item in self.all_items_data if item['iid'] == iid), None)
            if original_item:
                original_item['orig_line'] = new_first_line
                original_item['line'] = new_first_line.lower()
            # Schedule Treeview update
            self.after(0, lambda i=iid, n=new_first_line: self._update_treeview_item(i, n))
            return 'processed'

        except Exception as e:
            logger.error(f"Error applying fix to {path.name}: {e}", exc_info=True)
            return 'error'

    def _process_insert_number(self, item_data):
        """Inserts 'Chương X: ' at the beginning. Returns 'processed', 'skipped', or 'error'."""
        path = item_data.get('path')
        filename = item_data.get('orig_filename')
        iid = item_data.get('iid')
        if not path or not filename or iid is None: return 'error'

        try:
            # Extract chapter number from filename
            match_num_filename = re.search(r'[Cc](?:hương)?\s*(\d+)', filename)
            if not match_num_filename:
                 logger.warning(f"Could not extract chapter number from filename to insert: {filename}")
                 return 'error' # Treat as error if number extraction fails
            extracted_number = int(match_num_filename.group(1))

            # Read current content
            current_content = None; encodings = ['utf-8', 'cp1252', 'latin-1']; read_ok = False
            for enc in encodings:
                try:
                    current_content = path.read_text(encoding=enc); read_ok = True; break
                except UnicodeDecodeError: pass
                except FileNotFoundError: logger.error(f"File not found during insert: {filename}"); return 'error'
            if not read_ok:
                logger.error(f"Could not read file {filename} with any encoding for insert."); return 'error'
                
            # Handle potentially empty file read
            current_content = current_content or ""

            # Check if already formatted (optional, preview should handle this, but good safety check)
            first_line = current_content.splitlines()[0].strip() if current_content.splitlines() else ""
            chapter_pattern = re.compile(r'^\s*[Cc]hương\s+\d+\s*[:].*', re.IGNORECASE)
            if chapter_pattern.match(first_line):
                logger.debug(f"Skipping insert for {filename}: Already formatted.")
                return 'skipped'

            # Construct the new prefix and content
            prefix = f"Chương {extracted_number}: "
            # Insert prefix, add two newlines, then original content
            new_content = prefix + "\n\n" + current_content

            # Write the new content
            path.write_text(new_content, encoding="utf-8")
            new_display_first_line = prefix.strip() # Update display line

            # Update internal data store
            original_item = next((item for item in self.all_items_data if item['iid'] == iid), None)
            if original_item:
                original_item['orig_line'] = new_display_first_line
                original_item['line'] = new_display_first_line.lower()
            # Schedule Treeview update
            self.after(0, lambda i=iid, n=new_display_first_line: self._update_treeview_item(i, n))
            return 'processed'

        except ValueError: logger.error(f"Invalid chapter number format in filename: {filename}"); return 'error'
        except Exception as e: logger.error(f"Error inserting chapter number for {filename}: {e}", exc_info=True); return 'error'

    def trigger_delete_first_lines(self):
        logger.debug("Trigger delete first lines activated...")
        selected_data = self._get_selected_data()
        if not selected_data:
            messagebox.showwarning("Chưa chọn", "Vui lòng chọn ít nhất một file để xóa dòng đầu.", parent=self)
            return

        dialog = ConfirmationDialog(self, "Xác nhận xóa", f"Bạn có chắc chắn muốn xóa dòng đầu tiên của {len(selected_data)} file đã chọn không?\nHành động này không thể hoàn tác.")
        if dialog.result:
            logger.info(f"Starting deletion of first line for {len(selected_data)} files.")
            # Define the completion message function (lambda)
            msg_func = lambda p, e, s: f"Đã xóa dòng đầu của {p} file.\nBỏ qua (không đổi): {s} file.\nLỗi: {e} file."
            # Run the operation in a thread
            self._run_file_operation_in_thread(
                selected_data,
                self._process_delete_first_line,
                "Đang xóa dòng đầu...",
                msg_func
            )
        else:
            logger.info("User cancelled deletion of first lines.")

    def show_fix_preview(self):
        """Calculates and shows the preview for fixing chapter numbers."""
        logger.debug("Showing fix chapter number preview...")
        selected_data = self._get_selected_data()
        total_selected = len(selected_data)
        if not selected_data:
            messagebox.showwarning("Chưa chọn", "Vui lòng chọn ít nhất một file trong danh sách để xem trước sửa lỗi.", parent=self)
            return

        preview_items = []
        errors_calculating = 0
        skipped_count = 0
        filename_num_pattern = re.compile(r'[Cc](?:hương|ương)?\s*(\d+)')
        contains_chapter_keyword_pattern = re.compile(r'[Qq]uyển|[Cc]hương|[Đđ]ệ|[Cc]|Hồi', re.IGNORECASE)
        type1_pattern = re.compile(r'^\s*[Đđ]ệ\s+.*?\s+[Cc]hương\s*[:.,-]?\s*(.*)', re.IGNORECASE)
        type2a_pattern = re.compile(r'^\s*(?:[Qq]uyển|[Cc]hương|[Cc]|Hồi)\s*(?:thứ)?\s*(\d+)\s*[:.,\s-]\s*(.*)', re.IGNORECASE)
        type2b_pattern_start = re.compile(r'^\s*(?:[Qq]uyển|[Cc]hương)\s+(?:thứ)?\s*', re.IGNORECASE)
        # Regex to check if a line consists only of chapter keywords, numbers, words, and basic separators
        chapter_info_only_pattern = re.compile(
            r'^\s*' +                                      # Optional leading space
            r'(?:[Qq]uyển|[Cc]hương|[Đđ]ệ|[Cc]|Hồi)' +     # Chapter keyword
            r'\s*(?:thứ)?\s*' +                           # Optional 'thứ'
            r'[\d\w\s:.,-]*' +                             # The number/word part (allow digits, words, space, :, ., ,, -)
            r'\s*$',                                       # Optional trailing space and end of line
            re.IGNORECASE
        )
        separators_to_try = [':', '.', ',', '-']

        for item_data in selected_data:
            path = item_data.get('path')
            filename = item_data.get('orig_filename')
            original_first_line = item_data.get('orig_line', '')
            iid = item_data.get('iid')
            if not path or not filename or iid is None:
                 errors_calculating += 1; continue

            new_first_line = None; extracted_number_file = None; existing_title = ""
            processed = False # Flag to track if title was extracted

            try:
                # 1. Extract number reliably from filename
                match_filename = filename_num_pattern.search(filename)
                if match_filename:
                    try: extracted_number_file = int(match_filename.group(1))
                    except (ValueError, IndexError): pass
                if extracted_number_file is None:
                    logger.debug(f"Skip fix preview for {filename}: Cannot extract chapter number from filename.")
                    skipped_count += 1
                    continue

                # 2. Parse the original first line for the title
                line_to_parse = original_first_line.strip()

                if not line_to_parse or line_to_parse.startswith("[Lỗi đọc"):
                    existing_title = "[Không thể đọc tiêu đề gốc]" if not line_to_parse else line_to_parse
                    processed = True
                else:
                    # --- Priority 1: Specific Patterns ---
                    match_type1 = type1_pattern.match(line_to_parse)
                    if match_type1:
                        existing_title = match_type1.group(1).strip()
                        processed = True
                        logger.debug(f"Fix Preview ({filename}): Type 1 match. Title: '{existing_title}'")

                    if not processed:
                        match_type2a = type2a_pattern.match(line_to_parse)
                        if match_type2a:
                            existing_title = match_type2a.group(2).strip()
                            processed = True
                            logger.debug(f"Fix Preview ({filename}): Type 2a match. Title: '{existing_title}'")

                    # --- Priority 2: Explicit Separator Check ---
                    if not processed:
                        first_sep_index = float('inf')
                        best_title_candidate = None
                        found_sep_char = None
                        for sep in separators_to_try:
                            try: index = line_to_parse.index(sep)
                            except ValueError: continue
                            if index < first_sep_index:
                                prefix_part = line_to_parse[:index].strip()
                                potential_title = line_to_parse[index + 1:].strip()
                                if len(prefix_part) < 50 and potential_title and \
                                   (contains_chapter_keyword_pattern.search(prefix_part) or re.search(r'\d', prefix_part)):
                                    first_sep_index = index
                                    best_title_candidate = potential_title
                                    found_sep_char = sep
                        if best_title_candidate is not None:
                            existing_title = best_title_candidate
                            processed = True
                            logger.debug(f"Fix Preview ({filename}): Separator '{found_sep_char}' match. Title: '{existing_title}'")

                    # --- Priority 3: Type 2b Match (Word Parsing) ---
                    if not processed and type2b_pattern_start.match(line_to_parse):
                        words = line_to_parse.split()
                        last_num_word_index = -1
                        start_check_index = 1
                        if len(words) > 1 and words[1].lower() in BUFFER_WORDS: start_check_index = 2
                        elif len(words) == 1: start_check_index = -1
                        if start_check_index != -1:
                            for k in range(start_check_index, len(words)):
                                word_clean = words[k].lower().rstrip(':.,-')
                                is_potential_num_word = word_clean in VIETNAMESE_NUMBER_WORDS or word_clean.isdigit()
                                if is_potential_num_word: last_num_word_index = k
                                else: logger.debug(f"Fix Preview ({filename}) Type 2b: Stopping word check at '{words[k]}'"); break
                            if last_num_word_index != -1 and last_num_word_index + 1 < len(words):
                                title_part = " ".join(words[last_num_word_index + 1:]).strip()
                                existing_title = title_part
                                processed = True
                                logger.debug(f"Fix Preview ({filename}): Type 2b match. Title: '{existing_title}'")

                    # --- Fallback with Check for Chapter Info Only ---
                    if not processed:
                        cleaned_line_for_fallback = re.sub(r'^[\s*#:;_-]+', '', line_to_parse) # Basic clean

                        # Check if the cleaned line looks like ONLY chapter info
                        if chapter_info_only_pattern.match(cleaned_line_for_fallback):
                            existing_title = "[Không có tiêu đề]" # Use placeholder for clarity
                            logger.debug(f"Fix Preview ({filename}): Fallback detected chapter-info-only line ('{cleaned_line_for_fallback}'). Setting empty title.")
                        else:
                            # Otherwise, assume the cleaned line is the title
                            existing_title = cleaned_line_for_fallback
                            logger.debug(f"Fix Preview ({filename}): Fallback. Using cleaned line as title: '{existing_title}'")
                        # Fallback always marks as processed one way or another
                        # processed = True # No need to set processed=True here, it's handled by the block

                    # Final check: If somehow title ended up empty (and wasn't placeholder), use placeholder
                    if not existing_title:
                        existing_title = "[Không có tiêu đề]"

                # 3. Construct the new first line
                new_first_line = f"Chương {extracted_number_file}: {existing_title.strip()}"

                # 4. Add to preview ONLY if changed
                norm_orig = ' '.join(original_first_line.split())
                norm_new = ' '.join(new_first_line.split())

                if norm_new != norm_orig:
                    preview_items.append({
                        'path': path, 'filename': filename,
                        'original_line': original_first_line,
                        'new_line': new_first_line,
                        'iid': iid
                    })
                else:
                    skipped_count += 1

            except Exception as e:
                logger.error(f"Error calculating fix preview for {filename}: {e}", exc_info=True)
                errors_calculating += 1

        # --- Show Preview Window or appropriate message ---
        # (Rest of the message displaying logic remains the same)
        if errors_calculating > 0:
            messagebox.showwarning("Lỗi Tính Toán", f"Đã xảy ra lỗi khi tính toán xem trước cho {errors_calculating} file.\nMột số file có thể đã bị bỏ qua. Kiểm tra log để biết chi tiết.", parent=self)

        if not preview_items:
            # ... (message logic unchanged) ...
            msg = "Không tìm thấy file nào cần sửa lỗi định dạng chương."
            details = []
            if skipped_count > 0: details.append(f"Đã bỏ qua {skipped_count} file (đúng định dạng hoặc không đổi)")
            if errors_calculating > 0: details.append(f"Gặp lỗi khi xử lý {errors_calculating} file")
            if total_selected == 0: details.append("Không có file nào được chọn")

            if details: msg += "\n\n" + "\n".join(details)

            if errors_calculating == total_selected and total_selected > 0:
                 messagebox.showerror("Lỗi", "Tất cả các file được chọn đều gặp lỗi khi tính toán xem trước.\nKiểm tra log.", parent=self)
            else:
                 messagebox.showinfo("Hoàn tất quét", msg, parent=self)
            return

        logger.info(f"Showing fix preview for {len(preview_items)} items.")
        final_preview_data = copy.deepcopy(preview_items)
        PreviewWindow(self, "Xem trước sửa lỗi số chương", final_preview_data, len(preview_items), self.trigger_apply_fixes)

    def trigger_apply_fixes(self, data_to_apply):
        if not data_to_apply:
            logger.info("No fix data to apply.")
            return
        logger.info(f"Triggering application of fixes for {len(data_to_apply)} files.")
        msg_func = lambda p, e, s: f"Đã sửa định dạng chương cho {p} file.\nBỏ qua (không đổi): {s} file.\nLỗi: {e} file."
        # The data_to_apply already has the correct structure needed by _process_apply_fix
        self._run_file_operation_in_thread(data_to_apply, self._process_apply_fix, "Đang áp dụng sửa lỗi...", msg_func)

    def show_insert_preview(self):
        """Calculates and shows the preview for inserting chapter numbers."""
        logger.debug("Showing insert chapter number preview...")
        selected_data = self._get_selected_data()
        total_selected = len(selected_data)
        if not selected_data:
            messagebox.showwarning("Chưa chọn", "Vui lòng chọn ít nhất một file để xem trước chèn số chương.", parent=self)
            return

        preview_items = []
        errors_calculating = 0
        skipped_already_formatted = 0
        # Pattern to check if the line *already* looks like a correct chapter line
        chapter_pattern = re.compile(r'^\s*[Cc]hương\s+\d+\s*[:].*', re.IGNORECASE) # Require colon

        for item_data in selected_data:
            path = item_data.get('path')
            filename = item_data.get('orig_filename')
            original_first_line = item_data.get('orig_line', '')
            iid = item_data.get('iid')
            if not path or not filename or iid is None:
                 errors_calculating += 1; continue

            inserted_line = None
            try:
                # 1. Check if already formatted
                if chapter_pattern.match(original_first_line):
                    skipped_already_formatted += 1
                    logger.debug(f"Skip insert preview for {filename}: Already formatted.")
                    continue

                # 2. Extract number from filename
                match_num_filename = re.search(r'[Cc](?:hương)?\s*(\d+)', filename)
                if not match_num_filename:
                    logger.warning(f"Skip insert preview for {filename}: Cannot extract chapter number from filename.")
                    errors_calculating += 1 # Count as error if number extraction fails
                    continue
                extracted_number = int(match_num_filename.group(1))

                # 3. Prepare the line to be inserted
                inserted_line = f"Chương {extracted_number}: " # Line to be PREPENDED

                # 4. Add to preview list
                preview_items.append({
                    'path': path,
                    'filename': filename,
                    'original_line': original_first_line, # Show original for context
                    'inserted_line': inserted_line,      # Show the line that will be added
                    'iid': iid
                })

            except ValueError: logger.warning(f"Error calculating insert preview for {filename}: Invalid number format in filename."); errors_calculating += 1
            except Exception as e: logger.error(f"Error calculating insert preview for {filename}: {e}", exc_info=True); errors_calculating += 1

        # --- Show messages and Preview Window ---
        info_msgs = []
        if skipped_already_formatted > 0: info_msgs.append(f"Đã bỏ qua {skipped_already_formatted} file đã có định dạng chương.")
        if errors_calculating > 0: info_msgs.append(f"Gặp lỗi khi xử lý {errors_calculating} file (không tìm thấy số chương?).")

        if info_msgs:
            messagebox.showinfo("Thông tin quét", "\n".join(info_msgs), parent=self)

        if not preview_items:
            messagebox.showinfo("Không cần chèn", "Không tìm thấy file nào cần chèn số chương trong các file đã chọn (hoặc tất cả đã có định dạng/gặp lỗi).", parent=self)
            return

        logger.info(f"Showing insert preview for {len(preview_items)} items.")
        final_preview_data = copy.deepcopy(preview_items)
        PreviewWindow(self, "Xem trước chèn số chương", final_preview_data, len(preview_items), self.trigger_apply_inserts, apply_button_text="✅ Chèn số chương")

    def trigger_apply_inserts(self, data_to_apply):
        if not data_to_apply:
            logger.info("No insert data to apply.")
            return
        logger.info(f"Triggering application of inserts for {len(data_to_apply)} files.")
        msg_func = lambda p, e, s: f"Đã chèn số chương vào {p} file.\nBỏ qua (đã có): {s} file.\nLỗi: {e} file."
        # Prepare items for the processing function, ensuring correct keys
        items_to_process = [{'path': item['path'], 'orig_filename': item['filename'], 'iid': item['iid']} for item in data_to_apply]
        self._run_file_operation_in_thread(items_to_process, self._process_insert_number, "Đang chèn số chương...", msg_func)

    def _trigger_main_reader_update(self, changed_paths_set):
        if not changed_paths_set: return # No need to update if nothing changed
        # Check if the reader window exists and is accessible
        if self.reader_window_ref and hasattr(self.reader_window_ref, 'winfo_exists') and self.reader_window_ref.winfo_exists():
            # Call the reader's update method
            self.reader_window_ref.check_and_update_main_reader(changed_paths_set)
            logger.debug(f"Triggered main reader update for {len(changed_paths_set)} paths.")
        else:
            logger.debug("Main reader window reference is not valid or window closed. Cannot trigger update.")

    def _on_double_click(self, event):
        try:
            selected_item_id_str = self.tree.focus() # Get the ID of the focused item
            if not selected_item_id_str:
                logger.debug("Double click detected, but no item focused.")
                return # No item selected/focused

            iid_int = int(selected_item_id_str) # Treeview IID is usually a string representation of an integer
            selected_item_data = next((item for item in self.all_items_data if item.get('iid') == iid_int), None)

            if selected_item_data and 'path' in selected_item_data:
                file_path_to_load = selected_item_data['path']
                logger.info(f"Double-click on item iid={iid_int}, path={file_path_to_load}")

                # Check reader reference validity again before calling
                if self.reader_window_ref and hasattr(self.reader_window_ref, 'winfo_exists') and self.reader_window_ref.winfo_exists():
                    self.reader_window_ref.load_specific_file(file_path_to_load)
                else:
                    logger.warning("Main reader window reference is invalid or closed. Cannot load file.")
                    messagebox.showwarning("Lỗi", "Không thể mở file, cửa sổ đọc chính không tồn tại.", parent=self)
            else:
                logger.warning(f"No valid data or path found for double-clicked item iid={iid_int}.")

        except ValueError: logger.error(f"Invalid iid format '{selected_item_id_str}' during double-click.")
        except Exception as e: logger.error(f"Error processing double-click event: {e}", exc_info=True); messagebox.showerror("Lỗi", f"Đã xảy ra lỗi khi xử lý double-click:\n{e}", parent=self)


# ==============================================================
# LỚP CỬA SỔ ĐỌC CHÍNH (ReadWindow)
# ==============================================================
class ReadWindow(tk.Toplevel):
    DEFAULT_DICT_FILENAME = "dict.csv" # Default dictionary filename

    def __init__(self, parent, selected_source_dir, initial_font_family, initial_font_size):
        super().__init__(master=parent); self.master = parent; self.selected_source_dir = Path(selected_source_dir); self.folder_path = self.selected_source_dir / "translated"
        self.title("📖 Đọc chương đã dịch"); self.geometry("1600x800"); self.minsize(1000, 600)
        self.file_list = []; self.current_index = -1
        self.font_family = tk.StringVar(value=initial_font_family); self.font_size = tk.IntVar(value=initial_font_size); self.only_first_line = tk.BooleanVar(value=False)
        self.duplicate_removal_queue = queue.Queue()
        self.dictionary_replace_queue = queue.Queue() # Queue for dictionary replace

        # --- Dictionary Path Initialization ---
        self.dictionary_path = self._get_default_dictionary_path()
        logger.info(f"Initial dictionary path set to: {self.dictionary_path}")
        # --- End Dictionary Path ---

        try:
            if not self.folder_path.is_dir(): raise FileNotFoundError(f"Thư mục dịch không tồn tại: {self.folder_path}")
            self._reload_file_list()
            if not self.file_list: logger.warning(f"Không file .txt trong: {self.folder_path}")
        except Exception as e: logger.error(f"ReadWindow init error: {e}", exc_info=True); messagebox.showerror("Lỗi", f"Lỗi mở thư mục đọc:\n{e}", parent=self); self.after(10, self.destroy); return

        self.setup_ui() # Setup UI *after* initializing variables like dictionary_path

        if self.file_list:
             self.current_index = 0
             if hasattr(self, 'chapter_dropdown'): self.chapter_dropdown["values"] = self.file_list; self.chapter_dropdown.current(self.current_index)
             else: logger.error("chapter_dropdown missing after setup_ui")
             self.update_texts()
        else:
             if hasattr(self, 'chapter_dropdown'): self.chapter_dropdown["values"] = []; self.chapter_dropdown.set("(Không có file)")
             self.clear_text_areas(); self.title("📖 Đọc chương đã dịch (Thư mục rỗng)")

        self.bind("<Control-s>", lambda e: self.save_changes()); self.font_family.trace_add("write", lambda *a: self.update_font()); self.font_size.trace_add("write", lambda *a: self.update_font())
        self.protocol("WM_DELETE_WINDOW", self.on_reader_closing)

    def _get_default_dictionary_path(self) -> Path:
        """Determines the default path for the dictionary file."""
        # Try placing it next to the script first
        try:
            script_dir = Path(__file__).parent
            default_path = script_dir / self.DEFAULT_DICT_FILENAME
            if default_path.exists():
                return default_path.resolve() # Use absolute path
        except NameError: # __file__ might not be defined (e.g., in interactive session)
            pass
        # Fallback to current working directory
        default_path = Path.cwd() / self.DEFAULT_DICT_FILENAME
        return default_path.resolve()

    def _update_dictionary_label(self):
        """Updates the label showing the dictionary path."""
        if hasattr(self, 'dictionary_label') and self.dictionary_label:
             if self.dictionary_path and self.dictionary_path.exists():
                  # Show only the filename for brevity
                  display_text = f"Từ điển: {self.dictionary_path.name}"
                  self.dictionary_label.config(text=display_text, bootstyle="info") # Use info style
             elif self.dictionary_path:
                 display_text = f"Từ điển: {self.dictionary_path.name} (Không tìm thấy)"
                 self.dictionary_label.config(text=display_text, bootstyle="danger") # Use danger style
             else:
                  self.dictionary_label.config(text="Từ điển: Chưa chọn", bootstyle="warning") # Use warning style
        else:
            logger.warning("Dictionary label widget not available for update.")

    def _cleanup_blank_lines_after_header(self, content: str) -> str:
        """
        Ensures only one blank line exists between the first line (header)
        and the subsequent content, checking within the first few lines.

        Args:
            content: The string content of the file.

        Returns:
            The content string with cleaned blank lines near the header.
        """
        try:
            # Use split('\n') to preserve trailing blank lines if they exist beyond the header area
            all_lines = content.split('\n')

            # Need at least a header and one more line (even if blank) to potentially clean
            if len(all_lines) < 2:
                return content # No cleanup possible/needed

            header = all_lines[0]
            new_lines = [header] # Start constructing the result

            # Find the index of the first line with actual content after the header
            first_content_line_index = -1
            for i in range(1, len(all_lines)):
                if all_lines[i].strip():
                    first_content_line_index = i
                    break

            # Add the single blank line separator
            new_lines.append("")

            # If content was found, add it and the rest of the lines
            if first_content_line_index != -1:
                new_lines.extend(all_lines[first_content_line_index:])
            # If no content was found after the header (all remaining lines were blank),
            # the new_lines list currently just has [header, ""], which is correct.

            # Join back with newline characters
            cleaned_content = "\n".join(new_lines)

            # Check if cleaning actually changed anything compared to the input content
            # (This check is mostly for debugging/logging, the main worker compares to original)
            # if cleaned_content != content:
            #    logger.debug("Cleanup modified blank lines after header.")

            return cleaned_content

        except Exception as e:
            logger.error(f"Error during blank line cleanup: {e}", exc_info=True)
            # Return original content if cleanup fails
            return content

    def setup_ui(self):
        # --- Top Frame (Chapters, Navigation, Font) ---
        top_frame = ttk.Frame(self); top_frame.pack(fill="x", pady=5, padx=5)
        ttk.Label(top_frame, text="Chọn chương:").pack(side="left")
        try:
            self.chapter_dropdown = ttk.Combobox(top_frame, state="readonly", width=40)
            self.chapter_dropdown.pack(side="left", padx=5)
            self.chapter_dropdown.bind("<<ComboboxSelected>>", self.select_chapter)
        except Exception as e:
             logger.critical(f"Failed create chapter_dropdown: {e}", exc_info=True); messagebox.showerror("Lỗi Giao Diện", f"Lỗi tạo combobox chương:\n{e}", parent=self)
        ttk.Button(top_frame, text="⏪ Trước", command=self.prev_chapter).pack(side="left", padx=5)
        ttk.Button(top_frame, text="⏩ Sau", command=self.next_chapter).pack(side="left", padx=5)
        # Font controls
        ttk.Label(top_frame, text="Font:").pack(side="left", padx=(20, 5));
        try: font_families = sorted([f for f in font.families(self) if not f.startswith('@')])
        except: font_families = ["Consolas", "Arial", "Times New Roman", "Courier New", "Segoe UI", "Tahoma"]
        ttk.Combobox(top_frame, textvariable=self.font_family, values=font_families, state="readonly", width=15).pack(side="left")
        ttk.Label(top_frame, text="Cỡ:").pack(side="left", padx=5)
        ttk.Spinbox(top_frame, from_=8, to=32, textvariable=self.font_size, width=5, command=self.update_font).pack(side="left")
        # Right-aligned buttons in top frame
        button_frame_top_right = ttk.Frame(top_frame); button_frame_top_right.pack(side="right")
        ttk.Button(button_frame_top_right, text="🚫 Rà soát dòng lặp", command=self.show_duplicate_line_preview, bootstyle="warning").pack(side="right", padx=5) # Warning style
        ttk.Button(button_frame_top_right, text="📄 List dòng đầu", command=self.open_first_lines_window).pack(side="right", padx=5)
        ttk.Button(button_frame_top_right, text="💾 Lưu (Ctrl+S)", command=self.save_changes, bootstyle="success").pack(side="right", padx=5) # Success style

        # --- Find/Replace Frame ---
        find_replace_frame = ttk.Frame(self); find_replace_frame.pack(fill="x", padx=10, pady=(0,5)) # Combined frame
        # Find/Replace controls (left side)
        find_group = ttk.Frame(find_replace_frame); find_group.pack(side="left", fill="x", expand=True)
        ttk.Label(find_group, text="Tìm:").pack(side="left");
        self.entry_find = ttk.Entry(find_group, width=25); self.entry_find.pack(side="left", padx=5);
        ttk.Label(find_group, text="Thay bằng:").pack(side="left");
        self.entry_replace = ttk.Entry(find_group, width=25); self.entry_replace.pack(side="left", padx=5);
        self.only_first_line_cb = ttk.Checkbutton(find_group, text="Chỉ thay dòng đầu", variable=self.only_first_line);
        self.only_first_line_cb.pack(side="left", padx=5);
        ttk.Button(find_group, text="🔁 Thay thế toàn bộ", command=self.replace_all, bootstyle="info").pack(side="left", padx=(5,0)) # Info style

        # Dictionary controls (right side)
        dict_group = ttk.Frame(find_replace_frame); dict_group.pack(side="right", padx=(10,0))
        # Dictionary Buttons
        dict_button_frame = ttk.Frame(dict_group)
        dict_button_frame.pack(side=tk.TOP, anchor='e') # Pack buttons at the top right of their group
        self.dict_replace_button = ttk.Button(dict_button_frame, text="↔️ T&T theo Từ điển", command=self.find_replace_from_dictionary, bootstyle="primary") # Primary style
        self.dict_replace_button.pack(side="right", padx=(5,0))
        self.edit_dict_button = ttk.Button(dict_button_frame, text="Sửa TĐ", command=self._edit_dictionary, width=7)
        self.edit_dict_button.pack(side="right", padx=(5,0))
        self.select_dict_button = ttk.Button(dict_button_frame, text="Chọn TĐ", command=self._select_dictionary, width=8)
        self.select_dict_button.pack(side="right", padx=(0,0))
        # Dictionary Label (below buttons)
        self.dictionary_label = ttk.Label(dict_group, text="Từ điển: ...", anchor='e', width=35) # Anchor east, give width
        self.dictionary_label.pack(side=tk.TOP, anchor='e', pady=(2,0), fill='x') # Pack below buttons, fill space horizontally

        self._update_dictionary_label() # Update label text after creating it


        # --- Content Panes ---
        content_frame = ttk.PanedWindow(self, orient=tk.HORIZONTAL); content_frame.pack(fill="both", expand=True, padx=5, pady=(0, 5))
        # Left Pane (Text1)
        frame1 = ttk.Frame(content_frame, relief="sunken", borderwidth=1); content_frame.add(frame1, weight=1);
        scroll1 = ttk.Scrollbar(frame1, orient="vertical");
        self.text1 = tk.Text(frame1, wrap="word", undo=True, yscrollcommand=scroll1.set, font=(self.font_family.get(), self.font_size.get()));
        scroll1.config(command=self.text1.yview); scroll1.pack(side="right", fill="y"); self.text1.pack(side="left", fill="both", expand=True);
        self._apply_text_theme(self.text1)
        # Right Pane (Text2)
        frame2 = ttk.Frame(content_frame, relief="sunken", borderwidth=1); content_frame.add(frame2, weight=1);
        scroll2 = ttk.Scrollbar(frame2, orient="vertical");
        self.text2 = tk.Text(frame2, wrap="word", undo=True, yscrollcommand=scroll2.set, font=(self.font_family.get(), self.font_size.get()));
        scroll2.config(command=self.text2.yview); scroll2.pack(side="right", fill="y"); self.text2.pack(side="left", fill="both", expand=True);
        self._apply_text_theme(self.text2)

    def _apply_text_theme(self, text_widget):
         try:
             style = self.master.style # Use master's style (assuming ttkbootstrap)
             fg = style.colors.get("fg", "black")
             bg = style.colors.get("inputbg", "white") # Use input background for text area
             select_bg = style.colors.get("selectbg", "#0078D7")
             select_fg = style.colors.get("selectfg", "white")
             # Use foreground color for the insert cursor for visibility
             insert_bg = fg
             text_widget.config(
                 fg=fg, bg=bg,
                 selectbackground=select_bg, selectforeground=select_fg,
                 insertbackground=insert_bg,
                 borderwidth=0, # Remove tk Text border if using Frame border
                 highlightthickness=0 # Remove highlight border
            )
         except AttributeError:
             logger.warning("Could not access ttkbootstrap style object. Using default text colors.")
             # Fallback if style object is not available
             text_widget.config(borderwidth=0, highlightthickness=0)
         except Exception as e:
             logger.warning(f"Could not apply theme colors to text widget: {e}")
             text_widget.config(borderwidth=0, highlightthickness=0) # Ensure borders are off even on error


    def open_first_lines_window(self):
        # Check if already open? (Optional, prevents multiple instances)
        # for win in self.master.winfo_children():
        #     if isinstance(win, FirstLinesWindow):
        #         win.lift()
        #         return
        FirstLinesWindow(self, self.selected_source_dir, self) # Pass self (ReadWindow) as parent

    def update_font(self, *args):
        try:
            new_font_tuple = (self.font_family.get(), self.font_size.get())
            # Check if widgets exist before configuring
            if hasattr(self, 'text1') and self.text1:
                 self.text1.config(font=new_font_tuple)
            if hasattr(self, 'text2') and self.text2:
                 self.text2.config(font=new_font_tuple)
            logger.debug(f"Reader font updated to: {new_font_tuple}")
        except tk.TclError as e:
            # This can happen if the font name is invalid temporarily during selection
            logger.error(f"Error setting reader font (TclError): {e}. Font family: '{self.font_family.get()}', Size: {self.font_size.get()}")
            # Optionally show a non-blocking warning or just log it
            # messagebox.showwarning("Lỗi Font", f"Không thể đặt font '{self.font_family.get()}'.\n{e}", parent=self)
        except Exception as e:
            logger.error(f"Unexpected error updating font: {e}", exc_info=True)

    def _reload_file_list(self):
        """Reloads the list of .txt files from the current folder_path."""
        try:
            if not self.folder_path.is_dir():
                 logger.warning(f"Directory not found during reload: {self.folder_path}")
                 self.file_list = []
            else:
                 self.file_list = sorted([f.name for f in self.folder_path.glob("*.txt") if f.is_file()])
            logger.info(f"Reloaded file list: {len(self.file_list)} files found in {self.folder_path}")

            # Update dropdown only if it exists
            if hasattr(self, 'chapter_dropdown') and self.chapter_dropdown:
                self.chapter_dropdown["values"] = self.file_list
                if self.file_list:
                    # Try to maintain current selection if possible, otherwise reset
                    if self.current_index >= len(self.file_list) or self.current_index < 0:
                        self.current_index = 0
                    self.chapter_dropdown.current(self.current_index) # Update selection
                else:
                    self.current_index = -1
                    self.chapter_dropdown.set("(Không có file)") # Display placeholder
            else:
                 logger.warning("Cannot update chapter_dropdown during reload (widget may not exist yet).")
                 # Ensure current_index is reset if list becomes empty
                 if not self.file_list:
                     self.current_index = -1

            # Handle empty file list case for UI state
            if not self.file_list:
                self.clear_text_areas()
                self.title("📖 Đọc chương (Thư mục rỗng hoặc không có file .txt)")

        except Exception as e:
            logger.error(f"Error reloading file list for {self.folder_path}: {e}", exc_info=True)
            messagebox.showerror("Lỗi", f"Không thể tải lại danh sách file:\n{e}", parent=self)
            self.file_list = []
            self.current_index = -1
            # Safely update UI elements if they exist
            if hasattr(self, 'chapter_dropdown') and self.chapter_dropdown:
                self.chapter_dropdown["values"] = []
                self.chapter_dropdown.set("")
            self.clear_text_areas()
            self.title("📖 Đọc chương (Lỗi tải danh sách)")


    def update_texts(self):
        # Ensure text widgets are available
        if not all(hasattr(self, w) and getattr(self, w) for w in ['text1', 'text2']):
            logger.error("Cannot update texts: one or both text widgets are missing.")
            return

        logger.debug(f"Updating texts for index {self.current_index}")
        self.update_font() # Ensure font is current

        # Enable, clear, and load content
        self.text1.config(state=tk.NORMAL); self.text1.delete("1.0", tk.END)
        self.text2.config(state=tk.NORMAL); self.text2.delete("1.0", tk.END)

        content1 = self.read_file(self.current_index)
        content2 = self.read_file(self.current_index + 1)

        # Load content into text1
        if content1 is not None:
            self.text1.insert("1.0", content1)
            self.text1.edit_reset() # Clear undo stack
            self.text1.edit_modified(False) # Mark as not modified
        else:
            fname1 = self.file_list[self.current_index] if 0 <= self.current_index < len(self.file_list) else 'N/A'
            err_msg1 = f"[Lỗi đọc file: {fname1}]"
            self.text1.insert("1.0", err_msg1)
            self.text1.config(state=tk.DISABLED) # Disable if error
            logger.warning(f"Failed to read file for text1 at index {self.current_index} ({fname1})")

        # Load content into text2
        if content2 is not None:
            self.text2.insert("1.0", content2)
            self.text2.edit_reset()
            self.text2.edit_modified(False)
        else:
            # Check if the index+1 is valid but failed to read, or if it's beyond the list
            if 0 <= self.current_index + 1 < len(self.file_list):
                fname2 = self.file_list[self.current_index + 1]
                err_msg2 = f"[Lỗi đọc file: {fname2}]"
                self.text2.insert("1.0", err_msg2)
                self.text2.config(state=tk.DISABLED) # Disable if error
                logger.warning(f"Failed to read file for text2 at index {self.current_index + 1} ({fname2})")
            else:
                # Index + 1 is out of bounds, meaning it's the last chapter
                self.text2.insert("1.0", "[Hết chương]")
                self.text2.config(state=tk.DISABLED) # Disable the "end" message pane

        # Reset view and update title
        self.text1.mark_set(tk.INSERT, "1.0"); self.text1.see("1.0")
        self.text2.mark_set(tk.INSERT, "1.0"); self.text2.see("1.0")

        if 0 <= self.current_index < len(self.file_list):
            self.title(f"📖 Đọc: {self.file_list[self.current_index]}")
        elif not self.file_list:
             self.title("📖 Đọc chương (Thư mục rỗng)")
        else:
             self.title("📖 Đọc chương (Chỉ mục không hợp lệ)") # Should ideally not happen

        self.update_idletasks() # Ensure UI updates are processed


    def read_file(self, index):
        """Reads the content of the file at the given index. Handles encodings."""
        if not (0 <= index < len(self.file_list)):
            # logger.debug(f"Read attempt for invalid index: {index}")
            return None # Index out of bounds

        file_path = self.folder_path / self.file_list[index]
        if not file_path.is_file():
            logger.warning(f"File not found at expected path: {file_path}")
            return None

        encodings_to_try = ['utf-8', 'cp1252', 'latin-1']
        for enc in encodings_to_try:
            try:
                return file_path.read_text(encoding=enc)
            except UnicodeDecodeError:
                # logger.debug(f"Encoding {enc} failed for {file_path.name}, trying next.")
                continue # Try the next encoding
            except Exception as e:
                # Catch other potential errors like permission issues
                logger.error(f"Failed to read {file_path.name} with encoding {enc}: {e}", exc_info=True)
                return None # Return None on error

        # If all encodings failed
        logger.error(f"Could not read {file_path.name} with any tried encodings: {encodings_to_try}")
        return None


    def select_chapter(self, event=None):
        if not hasattr(self, 'chapter_dropdown') or not self.chapter_dropdown:
             logger.error("Cannot select chapter: dropdown widget missing.")
             return
        try:
            new_index = self.chapter_dropdown.current() # Get selected index
            # Check if selection is valid and different from current
            if new_index >= 0 and new_index < len(self.file_list) and new_index != self.current_index:
                 # TODO: Add check for unsaved changes before switching?
                 # if self.text1.edit_modified() or self.text2.edit_modified():
                 #     if not messagebox.askyesno("Unsaved Changes", "You have unsaved changes. Discard and switch chapter?", parent=self):
                 #         self.chapter_dropdown.current(self.current_index) # Revert dropdown
                 #         return
                 logger.debug(f"Chapter selected via dropdown: index {new_index} ('{self.file_list[new_index]}')")
                 self.current_index = new_index
                 self.update_texts()
            elif new_index == self.current_index:
                 logger.debug("Dropdown selection is the same as current index, no change.")
            # Handle invalid index from dropdown (shouldn't happen with readonly Combobox)
            elif new_index < 0:
                 logger.warning(f"Invalid index {new_index} obtained from chapter dropdown.")

        except Exception as e:
             logger.error(f"Error handling chapter selection: {e}", exc_info=True)


    def prev_chapter(self):
        if self.current_index > 0:
            # TODO: Add check for unsaved changes?
            self.current_index -= 1
            if hasattr(self, 'chapter_dropdown') and self.chapter_dropdown:
                self.chapter_dropdown.current(self.current_index) # Update dropdown visual
            self.update_texts()
            logger.debug(f"Navigated to previous chapter: index {self.current_index}")
        else:
            logger.debug("Already at the first chapter.")
            # Optionally provide visual feedback (e.g., flash window)
            # self.bell()


    def next_chapter(self):
        if self.current_index < len(self.file_list) - 1:
            # TODO: Add check for unsaved changes?
            self.current_index += 1
            if hasattr(self, 'chapter_dropdown') and self.chapter_dropdown:
                self.chapter_dropdown.current(self.current_index) # Update dropdown visual
            self.update_texts()
            logger.debug(f"Navigated to next chapter: index {self.current_index}")
        else:
            logger.debug("Already at the last chapter.")
            # self.bell()


    def save_changes(self):
        logger.info("Attempting to save changes for currently displayed chapters...")
        saved_files = []
        error_files = []

        # --- Helper function to save a single text widget's content ---
        def _save_widget_content(widget, file_index):
            if not (0 <= file_index < len(self.file_list)):
                # This case should ideally not happen if UI is consistent, but good to check
                logger.warning(f"Attempted to save invalid index {file_index}")
                return True, None # Return success=True, filename=None if index invalid

            # Check if the text widget actually exists and has been modified
            if not widget or not widget.edit_modified():
                 # logger.debug(f"Skipping save for index {file_index}: Widget invalid or not modified.")
                 return True, None # Not an error, just nothing to save

            filename = self.file_list[file_index]
            file_path = self.folder_path / filename
            try:
                content_to_save = widget.get("1.0", "end-1c") # Get content excluding final newline
                file_path.write_text(content_to_save, encoding="utf-8")
                widget.edit_modified(False) # Mark as saved
                logger.info(f"Successfully saved changes to: {filename}")
                return True, filename # Success
            except Exception as e:
                logger.error(f"Failed to save file {filename}: {e}", exc_info=True)
                messagebox.showerror("Lỗi Lưu File", f"Không thể lưu thay đổi cho file:\n{filename}\n\nLỗi: {e}", parent=self)
                return False, filename # Failure

        # --- Save content from text1 (current_index) ---
        if hasattr(self, 'text1'):
            success1, fname1 = _save_widget_content(self.text1, self.current_index)
            if fname1:
                (saved_files if success1 else error_files).append(fname1)

        # --- Save content from text2 (current_index + 1) ---
        if hasattr(self, 'text2'):
            # Only save text2 if it represents a valid file (not "[Hết chương]" or error message)
            if 0 <= self.current_index + 1 < len(self.file_list):
                 # Also check if text2 wasn't disabled due to a read error
                 if self.text2.cget('state') == tk.NORMAL:
                      success2, fname2 = _save_widget_content(self.text2, self.current_index + 1)
                      if fname2:
                           (saved_files if success2 else error_files).append(fname2)
                 # else: logger.debug(f"Skipping save for index {self.current_index + 1}: text2 widget is disabled.")
            # else: logger.debug(f"Skipping save for index {self.current_index + 1}: index out of bounds.")


        # --- Final feedback ---
        if not error_files and saved_files:
            messagebox.showinfo("Đã lưu", f"Đã lưu thành công thay đổi cho:\n- {', '.join(saved_files)}", parent=self)
        elif error_files:
             # Message already shown by _save_widget_content for each error
             logger.warning(f"Encountered errors while saving files: {error_files}")
        elif not saved_files and not error_files:
             logger.info("No changes detected in displayed files to save.")
             # Optionally show a message indicating nothing was saved
             # messagebox.showinfo("Không có thay đổi", "Không có thay đổi nào cần lưu.", parent=self)


    def replace_all(self):
        """Performs find/replace across ALL files in the directory."""
        find_text = self.entry_find.get()
        replace_text = self.entry_replace.get()

        if not find_text:
            messagebox.showwarning("Thiếu thông tin", "Vui lòng nhập văn bản cần tìm.", parent=self)
            return

        only_first = self.only_first_line.get()
        num_files = len(self.file_list)
        if num_files == 0:
            messagebox.showinfo("Không có file", "Không có file nào trong thư mục để thực hiện thay thế.", parent=self)
            return

        # Confirmation message
        if only_first:
             confirm_msg = f"Bạn có chắc muốn thay thế '{find_text}' bằng '{replace_text}' CHỈ Ở DÒNG ĐẦU TIÊN của tất cả {num_files} file trong thư mục?\nHành động này không thể hoàn tác."
        else:
             confirm_msg = f"Bạn có chắc muốn thay thế TẤT CẢ vý hiện của '{find_text}' bằng '{replace_text}' trong toàn bộ {num_files} file trong thư mục?\nHành động này có thể mất thời gian và không thể hoàn tác."

        if not ConfirmationDialog(self, "Xác nhận thay thế toàn bộ", confirm_msg).result:
            logger.info("User cancelled 'Replace All' operation.")
            return

        logger.info(f"Starting 'Replace All'. Find='{find_text}', Replace='{replace_text}', Only First Line={only_first}")

        # --- Setup Progress Window and Thread ---
        progress_win = tk.Toplevel(self); progress_win.title("Đang thay thế toàn bộ..."); progress_win.geometry("400x130"); progress_win.transient(self); progress_win.grab_set(); progress_win.resizable(False, False);
        status_label = ttk.Label(progress_win, text="Đang chuẩn bị...", wraplength=380); status_label.pack(pady=(10,5), padx=10, anchor='w', fill='x');
        progress_bar = ttk.Progressbar(progress_win, length=380, mode='determinate', maximum=num_files); progress_bar.pack(pady=(0,10), padx=10, fill='x');
        # --- THIS LINE IS CORRECTED ---
        self.update_idletasks(); px=self.winfo_rootx();py=self.winfo_rooty();pw=self.winfo_width();ph=self.winfo_height();dw=progress_win.winfo_width();dh=progress_win.winfo_height();x=px+(pw//2)-(dw//2);y=py+(ph//2)-(dh//2);progress_win.geometry(f'+{x}+{y}');progress_win.update()
        # --- END CORRECTION ---

        replace_queue = queue.Queue() # Use a separate queue for this operation

        # --- Worker Function ---
        def worker():
            total_replacements = 0; files_changed = 0; files_error = 0; changed_paths = set()

            for i, filename in enumerate(self.file_list):
                # Check if progress window closed (basic check)
                # if not progress_win.winfo_exists(): break

                replace_queue.put({'type': 'status', 'text': f"Xử lý: {filename} ({i+1}/{num_files})"})
                file_path = self.folder_path / filename
                original_content = None # Define outside try
                try:
                    read_ok=False
                    encodings = ['utf-8','cp1252','latin-1']
                    for enc in encodings:
                        try:
                            original_content = file_path.read_text(encoding=enc); read_ok=True; break
                        except UnicodeDecodeError: continue
                        except FileNotFoundError: raise # Re-raise FileNotFoundError to be caught below
                    if not read_ok or original_content is None:
                         raise IOError(f"Could not read file with any encoding.") # Custom error

                    new_content = original_content
                    replacements_in_file = 0
                    made_change = False

                    if only_first:
                        lines = original_content.splitlines()
                        if lines: # Check if file is not empty
                            original_first_line = lines[0]
                            # Count replacements on the original first line
                            replacements_in_file = original_first_line.count(find_text)
                            if replacements_in_file > 0:
                                lines[0] = original_first_line.replace(find_text, replace_text)
                                new_content = "\n".join(lines)
                                made_change = True
                    else:
                        # Replace all occurrences in the entire content
                        replacements_in_file = original_content.count(find_text)
                        if replacements_in_file > 0:
                            new_content = original_content.replace(find_text, replace_text)
                            made_change = True

                    # Write back only if changes were made
                    if made_change:
                        file_path.write_text(new_content, encoding="utf-8")
                        total_replacements += replacements_in_file
                        files_changed += 1
                        changed_paths.add(file_path)
                        logger.debug(f"Replaced {replacements_in_file} instance(s) in {filename}")

                except FileNotFoundError:
                    logger.warning(f"File not found during 'Replace All': {filename}")
                    files_error += 1
                except IOError as e: # Catch specific read errors
                    logger.error(f"Read error processing {filename}: {e}")
                    files_error += 1
                except Exception as e:
                    logger.error(f"Error processing {filename} during 'Replace All': {e}", exc_info=True)
                    files_error += 1

                replace_queue.put({'type': 'progress', 'value': i + 1})
                # time.sleep(0.01) # Optional delay

            replace_queue.put({
                'type': 'completion',
                'total_replacements': total_replacements,
                'files_changed': files_changed,
                'files_error': files_error,
                'changed_paths': changed_paths
            })
            logger.info("Replace All worker thread finished.")

        # --- Queue Checker ---
        def check_queue():
            try:
                while True:
                    msg = replace_queue.get_nowait()
                    # Check window existence before updates
                    if not progress_win.winfo_exists(): return

                    if msg['type'] == 'status':
                        if status_label.winfo_exists(): status_label.config(text=msg['text'])
                    elif msg['type'] == 'progress':
                        if progress_bar.winfo_exists(): progress_bar['value'] = msg['value']
                    elif msg['type'] == 'completion':
                        progress_win.destroy()
                        total_rep = msg['total_replacements']; files_ch = msg['files_changed']; files_err = msg['files_error']
                        result_message = f"Hoàn tất thay thế!\n\nĐã thực hiện: {total_rep} lượt thay thế\nTrong: {files_ch} file."
                        if files_err > 0: result_message += f"\nLỗi: {files_err} file (kiểm tra log)."
                        messagebox.showinfo("Thay thế toàn bộ hoàn tất", result_message, parent=self)
                        self.check_and_update_main_reader(msg.get('changed_paths', set()))
                        return # Stop checking
            except queue.Empty:
                if progress_win.winfo_exists(): self.after(100, check_queue)
            except tk.TclError as e:
                logger.error(f"TclError checking Replace All queue (window likely closed): {e}")
                if progress_win.winfo_exists(): progress_win.destroy()
            except Exception as e:
                logger.error(f"Error checking Replace All queue: {e}", exc_info=True)
                if progress_win.winfo_exists(): progress_win.destroy()

        # --- Start Thread and Queue Checker ---
        threading.Thread(target=worker, daemon=True).start()
        self.after(50, check_queue)


    def check_and_update_main_reader(self, changed_paths_set):
        """Checks if currently displayed files were modified and reloads them."""
        if not changed_paths_set: return # Nothing to check

        should_reload = False
        current_file_path = None
        next_file_path = None

        # Get path for the file in the left pane (text1)
        if 0 <= self.current_index < len(self.file_list):
            current_file_path = self.folder_path / self.file_list[self.current_index]

        # Get path for the file in the right pane (text2)
        if 0 <= self.current_index + 1 < len(self.file_list):
            next_file_path = self.folder_path / self.file_list[self.current_index + 1]

        # Check if either displayed file is in the set of changed paths
        if current_file_path and current_file_path in changed_paths_set:
             logger.info(f"Detected change in currently displayed file (left pane): {current_file_path.name}. Triggering reload.")
             should_reload = True
        elif next_file_path and next_file_path in changed_paths_set:
             logger.info(f"Detected change in currently displayed file (right pane): {next_file_path.name}. Triggering reload.")
             should_reload = True

        # Schedule the update_texts method to run on the main thread if needed
        if should_reload:
            # Use 'after' to ensure this runs safely in the Tkinter main loop
            self.after(50, self.update_texts)
        # else:
            # logger.debug("No changes detected in currently displayed files.")


    def update_source_directory(self, new_source_dir):
        new_path = Path(new_source_dir)
        # Compare resolved absolute paths to be sure
        if new_path.resolve() != self.selected_source_dir.resolve():
            logger.info(f"Updating source directory in ReadWindow from '{self.selected_source_dir}' to '{new_path}'")
            self.selected_source_dir = new_path
            self.folder_path = self.selected_source_dir / "translated" # Update the target folder path

            # Reload the file list for the new directory
            self._reload_file_list()

            # Update UI based on whether files were found
            if self.file_list:
                self.current_index = 0 # Reset to first file
                if hasattr(self, 'chapter_dropdown') and self.chapter_dropdown:
                     self.chapter_dropdown.current(0) # Update dropdown selection
                self.update_texts() # Load the first file(s)
            else:
                # No files found in the new directory
                self.current_index = -1
                if hasattr(self, 'chapter_dropdown') and self.chapter_dropdown:
                     self.chapter_dropdown.set("(Không có file)") # Update dropdown text
                self.clear_text_areas()
                self.title("📖 Đọc chương (Thư mục rỗng)") # Update window title
        else:
            logger.debug("Source directory selected is the same as the current one. No change needed in ReadWindow.")


    def clear_text_areas(self):
        """Clears both text widgets safely."""
        try:
            if hasattr(self, 'text1') and self.text1:
                self.text1.config(state=tk.NORMAL)
                self.text1.delete('1.0', tk.END)
                self.text1.edit_modified(False)
                # self.text1.config(state=tk.DISABLED) # Optionally disable after clearing if no file loaded
        except Exception as e: logger.error(f"Error clearing text1: {e}")
        try:
            if hasattr(self, 'text2') and self.text2:
                 self.text2.config(state=tk.NORMAL)
                 self.text2.delete('1.0', tk.END)
                 self.text2.edit_modified(False)
                 # self.text2.config(state=tk.DISABLED)
        except Exception as e: logger.error(f"Error clearing text2: {e}")


    def load_specific_file(self, file_path_to_load):
        """Loads a specific file into the reader, finding its index."""
        target_path = Path(file_path_to_load)
        logger.info(f"Request to load specific file: {target_path}")

        # Ensure the file is within the *current* translated directory
        if not target_path.is_relative_to(self.folder_path):
            logger.warning(f"File '{target_path.name}' is not in the current directory '{self.folder_path}'. Cannot load.")
            messagebox.showwarning("Lỗi", f"File '{target_path.name}' không nằm trong thư mục đang mở.\n({self.folder_path})", parent=self)
            return

        target_filename = target_path.name

        if not self.file_list:
             logger.warning("Cannot load specific file: file list is empty.")
             messagebox.showwarning("Lỗi", "Danh sách file rỗng, không thể tải file.", parent=self)
             return

        try:
            # Find the index of the target filename in the sorted list
            target_index = self.file_list.index(target_filename)

            # Check if index is valid (should be if .index() succeeded)
            if 0 <= target_index < len(self.file_list):
                logger.info(f"Found file '{target_filename}' at index {target_index}. Loading...")
                # TODO: Check for unsaved changes?
                self.current_index = target_index

                # Update dropdown selection if it exists
                if hasattr(self, 'chapter_dropdown') and self.chapter_dropdown.winfo_exists():
                    self.chapter_dropdown.current(self.current_index)

                # Update the text panes
                self.update_texts()

                # Bring the reader window to the front and give it focus
                self.lift()
                self.focus_force()
            else:
                # This case should technically not be reachable if .index() works
                logger.error(f"File '{target_filename}' found by index() but index {target_index} is out of bounds ({len(self.file_list)} files). List inconsistency?")
                messagebox.showerror("Lỗi", f"Lỗi không nhất quán khi tìm file '{target_filename}'.", parent=self)

        except ValueError:
            # Filename not found in the list
            logger.error(f"File '{target_filename}' not found in the current file list.")
            messagebox.showerror("Lỗi", f"File '{target_filename}' không tồn tại trong danh sách file hiện tại.", parent=self)
            # Option: Reload the list and try again?
            # self._reload_file_list()
            # self.load_specific_file(file_path_to_load) # Recursive call - be careful
        except Exception as e:
            logger.error(f"An unexpected error occurred while loading specific file '{target_filename}': {e}", exc_info=True)
            messagebox.showerror("Lỗi", f"Đã xảy ra lỗi không mong muốn khi tải file:\n{e}", parent=self)

    # --- Dictionary Operations ---

    def _select_dictionary(self):
        """Opens a file dialog to select a new dictionary file."""
        logger.debug("Opening file dialog to select dictionary.")
        # Suggest initial directory based on current dictionary or default location
        initial_dir = self.dictionary_path.parent if self.dictionary_path and self.dictionary_path.exists() else Path.cwd()
        try:
            filepath = filedialog.askopenfilename(
                title="Chọn file từ điển CSV",
                initialdir=initial_dir,
                filetypes=[("CSV Files", "*.csv"), ("All Files", "*.*")],
                parent=self # Make dialog modal to this window
            )
        except Exception as e:
            logger.error(f"Error opening file dialog: {e}", exc_info=True)
            messagebox.showerror("Lỗi", f"Không thể mở hộp thoại chọn file.\n{e}", parent=self)
            return

        if filepath:
            new_path = Path(filepath)
            if new_path != self.dictionary_path:
                logger.info(f"Dictionary file selected: {new_path}")
                self.dictionary_path = new_path
                self._update_dictionary_label()
                # TODO: Persist this setting?
                # if self.master and hasattr(self.master, 'settings'):
                #     self.master.settings['dictionary_path'] = str(new_path)
            else:
                logger.debug("Selected dictionary file is the same as the current one.")
        else:
            logger.debug("Dictionary selection cancelled by user.")

    def _edit_dictionary(self):
        """Opens the currently selected dictionary file in the default editor."""
        if not self.dictionary_path:
            messagebox.showwarning("Chưa chọn Từ điển", "Vui lòng chọn một file từ điển trước khi sửa.", parent=self)
            return

        if not self.dictionary_path.is_file():
            messagebox.showerror("Lỗi", f"File từ điển không tồn tại hoặc không phải là file:\n{self.dictionary_path}", parent=self)
            return

        logger.info(f"Attempting to open dictionary for editing: {self.dictionary_path}")
        try:
            if sys.platform == "win32":
                os.startfile(self.dictionary_path)
            elif sys.platform == "darwin": # macOS
                subprocess.run(['open', self.dictionary_path], check=True)
            else: # Linux and other Unix-like
                subprocess.run(['xdg-open', self.dictionary_path], check=True)
        except FileNotFoundError:
             # This can happen if the associated application or xdg-open/open is not found
             logger.error(f"Could not find application to open '{self.dictionary_path.name}'.")
             messagebox.showerror("Lỗi Mở File", f"Không tìm thấy ứng dụng mặc định để mở file .csv.\nHãy mở file thủ công:\n{self.dictionary_path}", parent=self)
        except subprocess.CalledProcessError as e:
            logger.error(f"Error opening dictionary file with system editor: {e}", exc_info=True)
            messagebox.showerror("Lỗi Mở File", f"Lệnh mở file từ điển thất bại.\nLỗi: {e}\n\nĐường dẫn: {self.dictionary_path}", parent=self)
        except Exception as e:
            logger.error(f"Unexpected error opening dictionary file: {e}", exc_info=True)
            messagebox.showerror("Lỗi Không Mong Đợi", f"Lỗi không xác định khi mở file từ điển:\n{e}", parent=self)

    def _load_dictionary(self) -> list[tuple[str, str]] | None:
        """Loads and parses the dictionary file. Returns list of (find, replace) tuples or None on error."""
        if not self.dictionary_path:
            logger.warning("Dictionary path not set.")
            messagebox.showwarning("Thiếu Từ điển", "Chưa có file từ điển nào được chọn.", parent=self)
            return None
        if not self.dictionary_path.is_file():
            logger.error(f"Dictionary file not found: {self.dictionary_path}")
            messagebox.showerror("Lỗi File", f"Không tìm thấy file từ điển:\n{self.dictionary_path}", parent=self)
            return None

        dictionary_rules = []
        try:
            with self.dictionary_path.open('r', encoding='utf-8', newline='') as csvfile:
                # Use csv.reader for robust parsing (handles commas in fields if quoted)
                reader = csv.reader(csvfile)
                line_num = 0
                for row in reader:
                    line_num += 1
                    # --- THIS LINE IS CORRECTED ---
                    # Skip empty rows or rows where the 'find' column is empty after stripping whitespace.
                    # We removed the startswith('#') check because '#' might be a valid character to find.
                    if not row or not row[0].strip():
                         continue
                    # --- END CORRECTION ---

                    # Expecting two columns: find, replace
                    if len(row) >= 2:
                        find_str = row[0]
                        replace_str = row[1] # Use column 2 directly
                        # No need to check if find_str is truthy here, as we already did row[0].strip() above
                        dictionary_rules.append((find_str, replace_str))
                        # else: # This case is now covered by the check above
                        #    logger.warning(f"Dictionary {self.dictionary_path.name} - Line {line_num}: Skipping rule with empty 'find' string.")
                    else:
                        logger.warning(f"Dictionary {self.dictionary_path.name} - Line {line_num}: Skipping invalid row (expected 2+ columns, found {len(row)}): {row}")

            if not dictionary_rules:
                logger.warning(f"Dictionary file loaded but contains no valid rules: {self.dictionary_path}")
                messagebox.showwarning("Từ điển trống", f"File từ điển '{self.dictionary_path.name}' không chứa quy tắc thay thế hợp lệ.", parent=self)
                # Return empty list instead of None if file exists but is empty/invalid
                return []

            logger.info(f"Successfully loaded {len(dictionary_rules)} rules from {self.dictionary_path.name}")
            return dictionary_rules

        except FileNotFoundError: # Should be caught earlier, but for safety
             logger.error(f"Dictionary file not found during load attempt: {self.dictionary_path}")
             messagebox.showerror("Lỗi File", f"Không tìm thấy file từ điển:\n{self.dictionary_path}", parent=self)
             return None
        except UnicodeDecodeError:
            logger.error(f"Encoding error reading dictionary file (must be UTF-8): {self.dictionary_path}")
            messagebox.showerror("Lỗi Encoding", f"File từ điển phải được lưu dưới dạng UTF-8.\n{self.dictionary_path}", parent=self)
            return None
        except csv.Error as e:
             # Provide the line number in the error message
             logger.error(f"CSV parsing error in dictionary file {self.dictionary_path.name}, near line {line_num}: {e}", exc_info=True)
             messagebox.showerror("Lỗi Định Dạng CSV", f"Lỗi định dạng trong file từ điển:\n{self.dictionary_path.name}\nGần dòng: {line_num}\nLỗi: {e}", parent=self)
             return None
        except Exception as e:
            logger.error(f"Unexpected error loading dictionary {self.dictionary_path}: {e}", exc_info=True)
            messagebox.showerror("Lỗi Không Mong Đợi", f"Lỗi không xác định khi đọc file từ điển:\n{e}", parent=self)
            return None

    def find_replace_from_dictionary(self):
        """Initiates the find and replace operation using the loaded dictionary."""
        logger.info("Starting Find & Replace from Dictionary...")

        # 1. Load Dictionary Rules
        dictionary_rules = self._load_dictionary()
        if dictionary_rules is None: # Error loading (message shown by _load_dictionary)
             return
        if not dictionary_rules: # Empty dictionary (message shown by _load_dictionary)
             return

        # 2. Check if there are files to process
        num_files = len(self.file_list)
        if num_files == 0:
            messagebox.showinfo("Không có file", "Không có file nào trong thư mục để thực hiện thay thế.", parent=self)
            return

        # 3. Confirmation
        dict_name = self.dictionary_path.name if self.dictionary_path else "N/A"
        confirm_msg = f"Bạn có chắc muốn áp dụng {len(dictionary_rules)} quy tắc thay thế từ từ điển '{dict_name}' cho TẤT CẢ {num_files} file trong thư mục?\nHành động này không thể hoàn tác."
        if not ConfirmationDialog(self, "Xác nhận Thay thế theo Từ điển", confirm_msg).result:
            logger.info("User cancelled dictionary replacement operation.")
            return

        logger.info(f"Confirmed dictionary replacement using '{dict_name}' ({len(dictionary_rules)} rules) on {num_files} files.")

        # 4. Setup Progress Window and Thread
        progress_win = tk.Toplevel(self); progress_win.title("Thay thế theo Từ điển..."); progress_win.geometry("400x130"); progress_win.transient(self); progress_win.grab_set(); progress_win.resizable(False, False);
        status_label = ttk.Label(progress_win, text="Đang chuẩn bị...", wraplength=380); status_label.pack(pady=(10,5), padx=10, anchor='w', fill='x');
        progress_bar = ttk.Progressbar(progress_win, length=380, mode='determinate', maximum=num_files); progress_bar.pack(pady=(0,10), padx=10, fill='x');
        # --- THIS LINE IS CORRECTED ---
        self.update_idletasks(); px=self.winfo_rootx();py=self.winfo_rooty();pw=self.winfo_width();ph=self.winfo_height();dw=progress_win.winfo_width();dh=progress_win.winfo_height();x=px+(pw//2)-(dw//2);y=py+(ph//2)-(dh//2);progress_win.geometry(f'+{x}+{y}');progress_win.update()
        # --- END CORRECTION ---

        # Use self.dictionary_replace_queue
        self.dictionary_replace_queue = queue.Queue() # Clear previous queue if any

        # Pass rules as argument to worker
        worker_thread = threading.Thread(target=self._run_dictionary_replace_worker, args=(dictionary_rules,), daemon=True)
        worker_thread.start()
        self.after(50, lambda: self._check_dictionary_replace_queue(progress_win, status_label, progress_bar))


    def _run_dictionary_replace_worker(self, dictionary_rules):
        """Worker thread for find/replace using dictionary rules, followed by cleanup."""
        total_replacements_by_dict = 0 # Count only replacements made by dictionary rules
        files_changed = 0 # Count files modified by EITHER dict rules OR cleanup
        files_error = 0
        changed_paths = set()
        num_files = len(self.file_list)
        num_rules = len(dictionary_rules)

        for i, filename in enumerate(self.file_list):
            # Simple check if the associated progress window might have been closed
            # A more robust method would use threading.Event for cancellation
            # For now, we rely on the queue checker stopping if the window is gone.

            status_text = f"File {i+1}/{num_files}: {filename}"
            self.dictionary_replace_queue.put({'type': 'status', 'text': status_text})

            file_path = self.folder_path / filename
            original_content = None # Store original content for final comparison
            try:
                # Read file content
                read_ok=False
                encodings = ['utf-8','cp1252','latin-1']
                for enc in encodings:
                    try:
                        original_content = file_path.read_text(encoding=enc); read_ok=True; break
                    except UnicodeDecodeError: continue
                    except FileNotFoundError: raise # Re-raise FileNotFoundError
                if not read_ok or original_content is None:
                    raise IOError("Could not read file with any encoding.")

                current_content = original_content # Start with original for replacements
                file_made_change_by_dict = False
                replacements_in_this_file = 0

                # --- Apply each dictionary rule sequentially ---
                for rule_idx, (find_str, replace_str) in enumerate(dictionary_rules):
                    if find_str in current_content:
                        count_before = current_content.count(find_str)
                        if count_before > 0:
                             current_content = current_content.replace(find_str, replace_str)
                             replacements_in_this_file += count_before
                             file_made_change_by_dict = True # Mark that dict rules changed content

                # --- Apply post-replacement cleanup ---
                final_content = self._cleanup_blank_lines_after_header(current_content)

                # --- Write back ONLY if final content differs from ORIGINAL content ---
                if final_content != original_content:
                    try:
                        file_path.write_text(final_content, encoding="utf-8")
                        files_changed += 1 # Increment if *any* change happened (dict or cleanup)
                        changed_paths.add(file_path)

                        # Log details and update total dict replacements count
                        if file_made_change_by_dict:
                            logger.debug(f"Applied dictionary rules ({replacements_in_this_file} replacements) and cleanup to {filename}.")
                            total_replacements_by_dict += replacements_in_this_file # Add dict count
                        else:
                            logger.debug(f"Applied cleanup (no dictionary changes needed) to {filename}.")
                    except Exception as write_e:
                         logger.error(f"Error writing changes (dict+cleanup) to {filename}: {write_e}", exc_info=True)
                         files_error += 1
                         # Decrement files_changed if write failed? Or keep it to indicate an attempt?
                         # Let's keep files_changed as it reflects an *intended* change that failed.
                         if file_path in changed_paths: changed_paths.remove(file_path) # Remove from successfully changed set

                # else: logger.debug(f"No overall change to {filename} after dict rules and cleanup.")


            except FileNotFoundError:
                logger.warning(f"File not found during dictionary replacement/cleanup: {filename}")
                files_error += 1
            except IOError as e: # Catch specific read error
                 logger.error(f"Read error processing {filename}: {e}")
                 files_error += 1
            except Exception as e:
                logger.error(f"Error processing {filename} during dictionary replacement/cleanup: {e}", exc_info=True)
                files_error += 1

            # Update progress bar after each file
            self.dictionary_replace_queue.put({'type': 'progress', 'value': i + 1})

        # Signal completion
        self.dictionary_replace_queue.put({
            'type': 'completion',
            'total_replacements': total_replacements_by_dict, # Report only dict replacements
            'files_changed': files_changed, # Report files changed by either step
            'files_error': files_error,
            'changed_paths': changed_paths
        })
        logger.info("Dictionary replacement and cleanup worker thread finished.")


    def _check_dictionary_replace_queue(self, progress_win, status_label, progress_bar):
        """Checks the queue for the dictionary replacement operation."""
        try:
            while True: # Process all messages in the queue currently
                msg = self.dictionary_replace_queue.get_nowait()

                # Ensure widgets still exist before updating
                if not progress_win.winfo_exists(): return # Stop if window is closed

                if msg['type'] == 'status':
                     if status_label.winfo_exists(): status_label.config(text=msg['text'])
                elif msg['type'] == 'progress':
                     if progress_bar.winfo_exists(): progress_bar['value'] = msg['value']
                elif msg['type'] == 'completion':
                    progress_win.destroy() # Close progress window
                    total_rep = msg['total_replacements']; files_ch = msg['files_changed']; files_err = msg['files_error']
                    dict_name = self.dictionary_path.name if self.dictionary_path else "N/A"

                    # --- Adjusted Message ---
                    result_message = f"Hoàn tất thay thế theo Từ điển ('{dict_name}') và Dọn dẹp!\n\n" \
                                     f"Số lượt thay thế theo từ điển: {total_rep}\n" \
                                     f"Số file được sửa đổi (thay thế hoặc dọn dẹp): {files_ch}."
                    # --- End Adjustment ---

                    if files_err > 0:
                        result_message += f"\nLỗi xử lý: {files_err} file (kiểm tra log)."

                    messagebox.showinfo("Thay thế và Dọn dẹp Hoàn tất", result_message, parent=self)
                    # Update reader if needed
                    self.check_and_update_main_reader(msg.get('changed_paths', set()))
                    return # Stop checking queue

                # progress_win.update_idletasks() # Optional: force UI update

        except queue.Empty:
            # Queue empty, schedule next check if window still valid
            if progress_win.winfo_exists():
                 self.after(100, lambda: self._check_dictionary_replace_queue(progress_win, status_label, progress_bar))
        except tk.TclError as e:
            logger.error(f"TclError checking dictionary replace queue (window likely closed): {e}")
            if progress_win.winfo_exists(): progress_win.destroy() # Attempt cleanup
        except Exception as e:
            logger.error(f"Error checking dictionary replace queue: {e}", exc_info=True)
            if progress_win.winfo_exists(): progress_win.destroy() # Attempt cleanup


    # --- END Dictionary Operations ---


    # --- Duplicate Line Removal ---

    def show_duplicate_line_preview(self):
        """Scans files for duplicate first/second or first/third lines (after colon) and shows preview."""
        if not self.file_list:
            messagebox.showwarning("Thông báo", "Không có file nào trong thư mục để rà soát dòng lặp.", parent=self)
            return

        logger.info(f"Scanning for potential duplicate title lines in: {self.folder_path}")
        self.log_to_reader("INFO: Bắt đầu rà soát dòng tiêu đề lặp...") # Log start

        preview_items = []
        files_scanned = 0
        potential_duplicates_found = 0
        lines_to_check = 3 # Check first 3 lines are enough

        # --- Progress Window ---
        prog_win = tk.Toplevel(self); prog_win.title("Đang rà soát dòng lặp..."); prog_win.geometry("400x100"); prog_win.transient(self); prog_win.grab_set(); prog_win.resizable(False, False);
        lbl = ttk.Label(prog_win, text="Quét file...", wraplength=380); lbl.pack(pady=10, padx=10, fill='x');
        bar = ttk.Progressbar(prog_win, length=380, mode='determinate', maximum=len(self.file_list)); bar.pack(pady=5, padx=10, fill='x');
        # Center progress window
        self.update_idletasks(); px=self.winfo_rootx();py=self.winfo_rooty();pw=self.winfo_width();ph=self.winfo_height();dw=prog_win.winfo_width();dh=prog_win.winfo_height();x=px+(pw//2)-(dw//2);y=py+(ph//2)-(dh//2);prog_win.geometry(f'+{x}+{y}');prog_win.update()

        # --- Scan Loop ---
        for i, filename in enumerate(self.file_list):
            if not prog_win.winfo_exists(): break # Stop if window closed

            lbl.config(text=f"Kiểm tra: {filename} ({i+1}/{len(self.file_list)})")
            bar['value'] = i + 1
            prog_win.update_idletasks() # Update UI

            fpath = self.folder_path / filename
            try:
                lines = []; full_content = None; encs = ['utf-8','cp1252','latin-1']; read_ok=False
                # Read initial lines and full content efficiently
                for enc in encs:
                    try:
                        # Read first few lines
                        temp_lines = []
                        with fpath.open('r', encoding=enc) as f:
                             for _ in range(lines_to_check):
                                 line = f.readline()
                                 if line == '': break # End of file
                                 temp_lines.append(line.strip()) # Store stripped lines

                        # If initial read worked, read full content with same encoding
                        full_content = fpath.read_text(encoding=enc)
                        lines = temp_lines # Assign successfully read lines
                        read_ok = True
                        break # Stop trying encodings
                    except (UnicodeDecodeError, FileNotFoundError):
                        continue # Try next encoding or handle file not found
                    except Exception as read_err: # Catch other read errors
                         logger.warning(f"Error reading {filename} during duplicate check ({enc}): {read_err}")
                         full_content = None # Ensure full_content is None on error
                         break # Stop trying encodings for this file

                if not read_ok:
                    logger.warning(f"Could not read {filename} with any encoding for duplicate check.")
                    continue # Skip file if read failed

                files_scanned += 1
                duplicate_line_content = None # Content of the line identified as duplicate
                line_index_to_remove = -1 # 0-based index of the line to remove

                # --- Check for duplicates ---
                if len(lines) >= 2:
                    # Extract title part (text after the first colon, stripped)
                    l1 = lines[0]
                    title1 = l1.split(':', 1)[-1].strip()

                    if title1: # Only proceed if the first line has a non-empty title part
                        # Check line 2 (index 1)
                        if len(lines) >= 2:
                             l2 = lines[1]
                             title2 = l2.split(':', 1)[-1].strip()
                             # Check if titles match and are not empty
                             if title2 and title1 == title2:
                                 duplicate_line_content = l2 # The line to remove is the second line
                                 line_index_to_remove = 1 # Index 1
                                 logger.debug(f"Potential duplicate found (Line 1 vs 2) in {filename}: Title='{title1}'")

                        # Check line 3 (index 2) only if no duplicate found at line 2
                        if duplicate_line_content is None and len(lines) >= 3:
                            l3 = lines[2]
                            title3 = l3.split(':', 1)[-1].strip()
                            # Check if titles match and are not empty
                            if title3 and title1 == title3:
                                duplicate_line_content = l3 # The line to remove is the third line
                                line_index_to_remove = 2 # Index 2
                                logger.debug(f"Potential duplicate found (Line 1 vs 3) in {filename}: Title='{title1}'")

                # If a duplicate was identified
                if duplicate_line_content is not None and full_content is not None:
                    potential_duplicates_found += 1
                    preview_items.append({
                        'path': fpath,
                        'filename': filename,
                        'original_line': l1,                   # Line to keep (first line)
                        'proposed': duplicate_line_content,  # Line to remove (the duplicate)
                        'line_index_to_remove': line_index_to_remove, # Index of line to remove
                        'full_content': full_content        # Store full content for applying fix later
                    })

            except Exception as e:
                logger.error(f"Error scanning {filename} for duplicates: {e}", exc_info=True)

        # Close progress window regardless of outcome
        if prog_win.winfo_exists(): prog_win.destroy()

        # Log summary and show preview or message
        summary_msg = f"Rà soát xong {files_scanned} file. Tìm thấy {potential_duplicates_found} file có khả năng lặp dòng tiêu đề."
        self.log_to_reader(f"INFO: {summary_msg}")
        logger.info(summary_msg)

        if not preview_items:
            messagebox.showinfo("Hoàn tất", "Không tìm thấy dòng tiêu đề lặp nào.", parent=self)
            return

        # Show the specific preview window for duplicate removal
        DuplicatePreviewWindow(self, "Xem trước xóa dòng tiêu đề lặp", preview_items, self.trigger_apply_duplicate_removal)


    def trigger_apply_duplicate_removal(self, items_to_fix):
        """Starts the process to remove duplicate lines identified in the preview."""
        if not items_to_fix:
            logger.info("No items selected or provided for duplicate removal.")
            return

        num_items = len(items_to_fix)
        logger.info(f"Triggering removal of duplicate lines for {num_items} files.")

        # --- Setup Progress Window ---
        prog_win = tk.Toplevel(self); prog_win.title("Đang xóa dòng lặp..."); prog_win.geometry("400x130"); prog_win.transient(self); prog_win.grab_set(); prog_win.resizable(False, False);
        lbl = ttk.Label(prog_win, text="Chuẩn bị...", wraplength=380); lbl.pack(pady=10, padx=10, anchor='w', fill='x');
        bar = ttk.Progressbar(prog_win, length=380, mode='determinate', maximum=num_items); bar.pack(pady=5, padx=10, fill='x');
        # Center window
        self.update_idletasks(); px=self.winfo_rootx();py=self.winfo_rooty();pw=self.winfo_width();ph=self.winfo_height();dw=prog_win.winfo_width();dh=prog_win.winfo_height();x=px+(pw//2)-(dw//2);y=py+(ph//2)-(dh//2);prog_win.geometry(f'+{x}+{y}');prog_win.update()

        # --- Start Worker Thread ---
        # Use self.duplicate_removal_queue
        self.duplicate_removal_queue = queue.Queue() # Ensure fresh queue
        worker_thread = threading.Thread(target=self._run_apply_duplicates_worker, args=(items_to_fix,), daemon=True)
        worker_thread.start()

        # --- Start Queue Checker ---
        self.after(100, lambda: self._check_duplicate_removal_queue(prog_win, lbl, bar))


    def _run_apply_duplicates_worker(self, items_to_fix):
        """Worker thread to perform the actual removal of duplicate lines."""
        fixed_count = 0
        error_count = 0
        skipped_count = 0 # To count cases where content didn't change unexpectedly
        changed_paths = set()
        num_items = len(items_to_fix)

        for i, item_data in enumerate(items_to_fix):
            # Basic validation of required data
            path = item_data.get('path')
            filename = item_data.get('filename', 'N/A')
            line_index_to_remove = item_data.get('line_index_to_remove', -1)
            original_full_content = item_data.get('full_content')

            # Check if progress window closed (simple check)
            # if not progress_win.winfo_exists(): break

            # Update status via queue
            status_text = f"Sửa: {filename} ({i+1}/{num_items})"
            self.duplicate_removal_queue.put({'type': 'status', 'text': status_text})

            if not path or line_index_to_remove == -1 or original_full_content is None:
                logger.error(f"Invalid data received for fixing duplicates in {filename}. Skipping.")
                error_count += 1
                self.duplicate_removal_queue.put({'type': 'progress', 'value': i + 1})
                continue

            try:
                all_lines = original_full_content.splitlines()

                # Validate line index against actual lines read
                if not (0 <= line_index_to_remove < len(all_lines)):
                    logger.warning(f"File {filename} structure seems changed since scan. Invalid line index {line_index_to_remove} for {len(all_lines)} lines. Skipping fix.")
                    error_count += 1 # Treat as error because we can't perform the intended action
                    self.duplicate_removal_queue.put({'type': 'progress', 'value': i + 1})
                    continue

                # Construct new content by excluding the duplicate line
                new_content_lines = []
                for idx, line in enumerate(all_lines):
                     if idx != line_index_to_remove:
                         new_content_lines.append(line)

                # --- Improved logic for adding blank line if necessary ---
                final_lines = []
                if new_content_lines: # If list not empty after removal
                     final_lines.append(new_content_lines[0]) # Add the first line (header)

                     # Check if we need to insert a blank line after the header
                     # We need a blank line if:
                     # 1. There is content *after* the header (i.e., more than 1 line remaining)
                     # 2. The line immediately after the header (index 1 in new_content_lines) is NOT already blank
                     if len(new_content_lines) > 1 and new_content_lines[1].strip():
                          final_lines.append("") # Insert the blank line
                          logger.debug(f"Inserted blank line after header in {filename}")

                     # Add the rest of the lines (from index 1 onwards)
                     if len(new_content_lines) > 1:
                          final_lines.extend(new_content_lines[1:])

                # --- End blank line logic ---

                new_content = "\n".join(final_lines)

                # Compare final content with original before writing
                if new_content != original_full_content:
                    try:
                        path.write_text(new_content, encoding='utf-8')
                        fixed_count += 1
                        changed_paths.add(path)
                        logger.info(f"Successfully removed duplicate line {line_index_to_remove+1} in {filename}")
                    except Exception as write_e:
                        logger.error(f"Error writing fixed content to {filename}: {write_e}", exc_info=True)
                        error_count += 1
                else:
                     # This case means removing the line resulted in no change, which is odd
                     # but could happen if the file only had the header and the duplicate.
                     logger.warning(f"Content unchanged after removing line {line_index_to_remove+1} for {filename}. Skipping write.")
                     skipped_count += 1

            except Exception as e:
                logger.error(f"Unexpected error applying duplicate removal for {filename}: {e}", exc_info=True)
                error_count += 1

            # Update progress bar after processing each item
            self.duplicate_removal_queue.put({'type': 'progress', 'value': i + 1})
            # time.sleep(0.01) # Optional small delay

        # Signal completion to the queue
        self.duplicate_removal_queue.put({
            'type': 'completion',
            'fixed': fixed_count,
            'errors': error_count,
            'skipped': skipped_count, # Files where content didn't change after logic
            'changed_paths': changed_paths
        })
        logger.info("Apply duplicate removal worker finished.")


    def _check_duplicate_removal_queue(self, progress_win, status_label, progress_bar):
        """Checks the queue for the duplicate removal operation."""
        try:
            while True: # Process all available messages
                msg = self.duplicate_removal_queue.get_nowait()

                # Check window status first
                if not progress_win.winfo_exists(): return

                if msg['type'] == 'status':
                    if status_label.winfo_exists(): status_label.config(text=msg['text'])
                elif msg['type'] == 'progress':
                    if progress_bar.winfo_exists(): progress_bar['value'] = msg['value']
                elif msg['type'] == 'completion':
                    progress_win.destroy() # Close the progress window

                    fixed = msg.get('fixed', 0)
                    errors = msg.get('errors', 0)
                    skipped = msg.get('skipped', 0) # Get skipped count from worker

                    res_msg = f"Hoàn tất xóa dòng tiêu đề lặp!\n\nĐã sửa: {fixed} file"
                    if errors > 0: res_msg += f"\nLỗi: {errors} file"
                    if skipped > 0: res_msg += f"\nBỏ qua (không đổi): {skipped} file" # Report skipped count

                    messagebox.showinfo("Xóa dòng lặp hoàn tất", res_msg, parent=self)
                    log_summary = f"INFO: {res_msg.replace('!','').replace('\n\n', '. ').replace('\n', '. ')}"
                    self.log_to_reader(log_summary) # Log summary to reader pane
                    # Update main reader view if necessary
                    self.check_and_update_main_reader(msg.get('changed_paths', set()))
                    return # Stop checking the queue

                # progress_win.update_idletasks() # Can sometimes help responsiveness

        except queue.Empty:
            # If queue is empty, schedule next check if window is still open
            if progress_win.winfo_exists():
                self.after(100, lambda: self._check_duplicate_removal_queue(progress_win, status_label, progress_bar))
        except tk.TclError as e:
             # Catch errors likely due to widgets being destroyed
             logger.error(f"TclError checking duplicate removal queue (window likely closed): {e}")
             if progress_win.winfo_exists(): progress_win.destroy() # Ensure it's closed
        except Exception as e:
             logger.error(f"Unexpected error checking duplicate removal queue: {e}", exc_info=True)
             if progress_win.winfo_exists(): progress_win.destroy() # Ensure it's closed

    # --- END Duplicate Line Removal ---


    def log_to_reader(self, message, level="INFO"):
        """ Safely logs a message to the beginning of the text1 widget. """
        if hasattr(self, 'text1') and self.text1 and self.text1.winfo_exists():
            try:
                timestamp = time.strftime("[%H:%M:%S]")
                # Ensure message ends with a newline
                full_message = f"{timestamp} [{level}] {message.strip()}\n"
                # Schedule the insertion to happen in the main Tkinter thread
                self.after(0, self._insert_log_message, full_message)
            except Exception as e:
                 logger.warning(f"Error preparing log message for reader: {e}")

    def _insert_log_message(self, message):
        """ Inserts the log message into text1 (intended to be called via self.after). """
        try:
            # Check widget existence again right before insertion
            if self.text1 and self.text1.winfo_exists():
                current_state = self.text1.cget('state')
                self.text1.config(state=tk.NORMAL)
                self.text1.insert("1.0", message)
                # Only disable if it wasn't already meant to be normal (e.g., during initial load error)
                # Or maybe always keep it normal for logging? Let's try keeping it normal.
                # self.text1.config(state=current_state) # Restore original state
                # Keep text1 enabled for easier copying of logs if needed?
                # Let's comment out the state restoration for now.
                # self.text1.config(state=tk.DISABLED) # Re-disable after insert?
                self.text1.see("1.0") # Scroll to top to see latest log
        except tk.TclError as e:
            # Catch error if widget is destroyed between scheduling and execution
            logger.warning(f"Could not insert log message into reader (widget destroyed?): {e}")
        except Exception as e:
            logger.error(f"Unexpected error inserting log message: {e}", exc_info=True)


    def on_reader_closing(self):
        """Handles cleanup when the reader window is closed."""
        logger.info("ReadWindow closing process started.")

        # --- Persist Settings (Example) ---
        # Check if the main application window (master) and its settings exist
        if self.master and hasattr(self.master, 'settings') and isinstance(self.master.settings, dict):
            try:
                self.master.settings["reader_font_family"] = self.font_family.get()
                self.master.settings["reader_font_size"] = self.font_size.get()
                # Save dictionary path (convert Path to string for JSON compatibility if saving)
                if self.dictionary_path:
                    self.master.settings["dictionary_path"] = str(self.dictionary_path.resolve())
                else:
                     # Handle case where path is None (e.g., remove the setting or set to empty string)
                     if "dictionary_path" in self.master.settings:
                         del self.master.settings["dictionary_path"] # Or set to ""
                logger.info("Reader settings (font, dictionary path) prepared for saving.")
                # The actual saving should be handled by the main app's closing sequence
                # if hasattr(self.master, 'save_settings'): self.master.save_settings()
            except Exception as e:
                 logger.error(f"Error updating settings during reader closing: {e}", exc_info=True)
        else:
            logger.warning("Could not access master's settings object for saving reader preferences.")

        # --- Stop any running background tasks? (More complex) ---
        # If operations like replace_all could be running, you might need
        # signaling mechanisms (e.g., threading.Event) to request them to stop.
        # For simplicity, we'll assume operations finish quickly or are handled
        # by the user closing the progress window.

        # --- Destroy the window ---
        self.destroy()
        logger.info("ReadWindow destroyed.")