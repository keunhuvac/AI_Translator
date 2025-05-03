# -*- coding: utf-8 -*-
import tkinter as tk
from tkinter import ttk, filedialog, messagebox, scrolledtext
import os
import re # Import re for natural sort
import uuid
from ebooklib import epub
import mimetypes
import threading
import queue
import traceback # Import traceback để log lỗi chi tiết
import logging # Import logging

logger = logging.getLogger(__name__) # Create logger for this module

# --- NATURAL SORT HELPER FUNCTION ---
def natural_sort_key(s):
    """
    Create a key for natural sorting of strings.
    Example: 'chap10' comes after 'chap2'.
    """
    # Split string into text and number parts, keeping numbers
    parts = [part for part in re.split(r'(\d+)', s) if part]
    # Convert number parts to integers for numerical comparison
    # Convert text parts to lowercase for case-insensitive sorting
    return [int(part) if part.isdigit() else part.lower() for part in parts]
# -------------------------------------

# --- Inherit from ttk.Frame for embedding ---
class EbookCreatorApp(ttk.Frame):
    """
    Main application class for creating EPUB Ebooks from text files.
    Complete version with threading, progress bar, file selection/deletion,
    cover handling, CSS, and file writing fixes.
    """
    def __init__(self, master):
        """
        Initialize the user interface as a Frame widget.
        """
        super().__init__(master) # Initialize the parent Frame
        self.master = master # Keep a reference to the parent window (Tk or Toplevel)

        # --- Initialize variables ---
        self.directory_path = tk.StringVar()
        self.cover_image_path = tk.StringVar()
        self.book_title = tk.StringVar(value="Ebook Tổng hợp")
        self.book_author = tk.StringVar(value="Người tạo Ebook")
        self.chapters_data_cache = []
        self.log_queue = queue.Queue()
        self.is_task_running = False

        # --- Create widgets within this Frame ---
        self._create_widgets()

        # --- Initial log and start queue processing ---
        self._log_from_queue("Chào mừng! Hãy thực hiện các bước theo thứ tự.")
        # Schedule queue check via the master window's mainloop
        self.master.after(100, self._process_log_queue)

    def _create_widgets(self):
        """Creates the UI elements within this Frame."""
        # Use 'self' (the Frame) as the main container
        main_pane = ttk.PanedWindow(self, orient=tk.HORIZONTAL)
        main_pane.pack(fill=tk.BOTH, expand=True, padx=10, pady=10) # Pack into self

        # --- Left Pane: Settings ---
        left_frame = ttk.Frame(main_pane, padding="10")
        main_pane.add(left_frame, weight=1)

        # --- Section 1: Select Directory ---
        dir_frame = ttk.LabelFrame(left_frame, text="1. Chọn thư mục nguồn", padding="10")
        dir_frame.pack(fill=tk.X, pady=(0, 10))
        self.dir_entry = ttk.Entry(dir_frame, textvariable=self.directory_path, state="readonly", width=30)
        self.dir_entry.pack(side=tk.LEFT, fill=tk.X, expand=True)
        self.browse_dir_button = ttk.Button(dir_frame, text="Chọn...", command=self.select_directory)
        self.browse_dir_button.pack(side=tk.LEFT, padx=(5, 0))

        # --- Section 2: Ebook Info ---
        self.metadata_frame = ttk.LabelFrame(left_frame, text="2. Thông tin Ebook", padding="10")
        self.metadata_frame.pack(fill=tk.X, pady=(0, 10))
        ttk.Label(self.metadata_frame, text="Tiêu đề sách:").grid(row=0, column=0, padx=5, pady=5, sticky=tk.W)
        self.title_entry = ttk.Entry(self.metadata_frame, textvariable=self.book_title, width=40)
        self.title_entry.grid(row=0, column=1, columnspan=2, padx=5, pady=5, sticky=tk.EW)
        ttk.Label(self.metadata_frame, text="Tác giả:").grid(row=1, column=0, padx=5, pady=5, sticky=tk.W)
        self.author_entry = ttk.Entry(self.metadata_frame, textvariable=self.book_author, width=40)
        self.author_entry.grid(row=1, column=1, columnspan=2, padx=5, pady=5, sticky=tk.EW)
        self.metadata_frame.columnconfigure(1, weight=1) # Allow entry to expand

        # --- Section 3: Select Cover Image ---
        self.cover_frame = ttk.LabelFrame(left_frame, text="3. Chọn ảnh bìa (Tùy chọn)", padding="10")
        self.cover_frame.pack(fill=tk.X, pady=(0, 10))
        self.cover_entry = ttk.Entry(self.cover_frame, textvariable=self.cover_image_path, state="readonly", width=30)
        self.cover_entry.pack(side=tk.LEFT, fill=tk.X, expand=True)
        self.browse_cover_button = ttk.Button(self.cover_frame, text="Chọn...", command=self.select_cover_image)
        self.browse_cover_button.pack(side=tk.LEFT, padx=(5, 0))

        # --- Section 4: File/Chapter List ---
        toc_frame = ttk.LabelFrame(left_frame, text="4. Danh sách file/chương (Chọn để xóa)", padding="10")
        toc_frame.pack(fill=tk.BOTH, expand=True, pady=(0, 5)) # Expand vertically

        listbox_frame = ttk.Frame(toc_frame)
        listbox_frame.pack(fill=tk.BOTH, expand=True)
        toc_scrollbar = ttk.Scrollbar(listbox_frame, orient="vertical")
        toc_scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        self.toc_listbox = tk.Listbox(listbox_frame, selectmode=tk.EXTENDED, yscrollcommand=toc_scrollbar.set, height=8)
        self.toc_listbox.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        toc_scrollbar.config(command=self.toc_listbox.yview)

        toc_button_frame = ttk.Frame(toc_frame)
        toc_button_frame.pack(fill=tk.X, pady=(5, 0))
        self.remove_selected_button = ttk.Button(toc_button_frame, text="Xóa mục đã chọn", command=self.remove_selected_files, state=tk.DISABLED)
        self.remove_selected_button.pack(side=tk.LEFT, padx=5)
        self.clear_all_button = ttk.Button(toc_button_frame, text="Xóa tất cả", command=self.clear_all_files, state=tk.DISABLED)
        self.clear_all_button.pack(side=tk.LEFT, padx=5)

        # --- Progress Bar ---
        self.progress_bar = ttk.Progressbar(left_frame, orient="horizontal", length=300, mode="determinate")
        self.progress_bar.pack(pady=(5, 10), fill=tk.X)

        # --- Create Ebook Button ---
        self.create_button = ttk.Button(left_frame, text="5. Tạo Ebook EPUB", command=self.start_create_ebook_thread)
        self.create_button.pack(pady=10)

        # --- Right Pane: Log ---
        right_frame = ttk.Frame(main_pane, padding="5")
        main_pane.add(right_frame, weight=1)
        log_label_frame = ttk.LabelFrame(right_frame, text="Log/Trạng thái", padding="5")
        log_label_frame.pack(fill=tk.BOTH, expand=True)
        self.log_area = scrolledtext.ScrolledText(log_label_frame, height=15, wrap=tk.WORD, state="disabled", width=40)
        self.log_area.pack(fill=tk.BOTH, expand=True)

    def _set_ui_state(self, enabled):
        """Enable/disable interactive widgets during task execution."""
        state = tk.NORMAL if enabled else tk.DISABLED
        # Use getattr for safety
        getattr(self, 'browse_dir_button', ttk.Frame(self)).config(state=state)
        getattr(self, 'browse_cover_button', ttk.Frame(self)).config(state=state)
        getattr(self, 'create_button', ttk.Frame(self)).config(state=state)
        getattr(self, 'title_entry', ttk.Frame(self)).config(state=state)
        getattr(self, 'author_entry', ttk.Frame(self)).config(state=state)

        listbox_exists = hasattr(self, 'toc_listbox') and self.toc_listbox
        if listbox_exists:
            try: # Listbox might be destroyed
                self.toc_listbox.config(state=tk.NORMAL if enabled else tk.DISABLED)
                toc_button_state = tk.NORMAL if enabled and self.toc_listbox.size() > 0 else tk.DISABLED
                getattr(self, 'remove_selected_button', ttk.Frame(self)).config(state=toc_button_state)
                getattr(self, 'clear_all_button', ttk.Frame(self)).config(state=toc_button_state)
            except tk.TclError:
                 getattr(self, 'remove_selected_button', ttk.Frame(self)).config(state=tk.DISABLED)
                 getattr(self, 'clear_all_button', ttk.Frame(self)).config(state=tk.DISABLED)
        else:
             getattr(self, 'remove_selected_button', ttk.Frame(self)).config(state=tk.DISABLED)
             getattr(self, 'clear_all_button', ttk.Frame(self)).config(state=tk.DISABLED)

    def _log_from_queue(self, message):
        """Write log message to the ScrolledText widget (main thread safe via queue)."""
        if hasattr(self, 'log_area') and self.log_area and self.log_area.winfo_exists():
            try:
                self.log_area.config(state="normal")
                self.log_area.insert(tk.END, message + "\n")
                self.log_area.see(tk.END) # Scroll to the end
                self.log_area.config(state="disabled")
            except tk.TclError:
                # Handle case where widget is destroyed between check and configure
                logger.warning("Log area widget destroyed while attempting to log.")

    def _process_log_queue(self):
        """Process messages from the worker thread queue."""
        processed_count = 0; max_process_per_cycle = 20
        try:
            while processed_count < max_process_per_cycle:
                message = self.log_queue.get_nowait()
                processed_count += 1
                if isinstance(message, tuple):
                    msg_type = message[0]
                    if msg_type == 'progress':
                        if hasattr(self, 'progress_bar'):
                             current, total = message[1], message[2]
                             percentage = (current / total) * 100 if total > 0 else 0
                             self.progress_bar['value'] = percentage
                    elif msg_type == 'toc_data':
                        if hasattr(self, 'toc_listbox') and self.toc_listbox:
                            try:
                                self.toc_listbox.config(state=tk.NORMAL)
                                self.toc_listbox.delete(0, tk.END)
                                self.chapters_data_cache = message[1]
                                for info in self.chapters_data_cache:
                                     self.toc_listbox.insert(tk.END, info.get('display', info.get('title', 'N/A')))
                                # Don't disable here, _set_ui_state will handle it
                            except tk.TclError: logger.warning("TOC listbox destroyed during update.")
                    elif msg_type == 'scan_done':
                        self._log_from_queue(">>> Quét thư mục hoàn tất.")
                        self.is_task_running = False
                        self._set_ui_state(True)
                        if hasattr(self, 'progress_bar'): self.progress_bar['value'] = 0
                    elif msg_type == 'epub_done':
                        filepath = message[1]; self._log_from_queue(f">>> Tạo EPUB hoàn tất: {filepath}")
                        messagebox.showinfo("Hoàn thành", f"Đã tạo EPUB!\nLưu tại:\n{filepath}", parent=self.master)
                        self.is_task_running = False; self._set_ui_state(True)
                        if hasattr(self, 'progress_bar'): self.progress_bar['value'] = 0
                    elif msg_type == 'error':
                        error_msg = message[1]; tb_str = message[2] if len(message) > 2 else traceback.format_exc()
                        self._log_from_queue(f"*** LỖI: {error_msg}"); logger.error(f"Ebook Creator Error: {error_msg}\n{tb_str}")
                        messagebox.showerror("Lỗi", f"Đã xảy ra lỗi:\n{error_msg}\n\n(Xem log chi tiết)", parent=self.master)
                        self.is_task_running = False; self._set_ui_state(True)
                        if hasattr(self, 'progress_bar'): self.progress_bar['value'] = 0
                elif isinstance(message, str): self._log_from_queue(message)
        except queue.Empty: pass
        except Exception as e: logger.error(f"Error processing log queue: {e}", exc_info=True)
        finally:
            if self.winfo_exists(): # Check if the frame itself still exists
                if not self.is_task_running: self._set_ui_state(True) # Ensure UI is enabled if no task running
                if self.is_task_running or not self.log_queue.empty():
                     # Use master's after method to schedule in the main event loop
                     self.master.after(100, self._process_log_queue)

    # --- Event Handlers (main thread) ---
    def select_directory(self):
        """Mở hộp thoại chọn thư mục và bắt đầu thread quét file."""
        if self.is_task_running:
            messagebox.showwarning("Đang bận", "Đợi tác vụ khác hoàn thành.", parent=self.master)
            return
        directory = filedialog.askdirectory(title="Chọn thư mục chứa file .txt", parent=self.master)
        if directory:
            self.directory_path.set(directory)
            self._log_from_queue(f"Đã chọn thư mục: {directory}")
            # Kiểm tra widget tồn tại trước khi thao tác
            if hasattr(self, 'toc_listbox') and self.toc_listbox.winfo_exists():
                try:
                    self.toc_listbox.delete(0, tk.END)
                except tk.TclError:
                    logger.warning("Error deleting from toc_listbox in select_directory")
            self.chapters_data_cache.clear()
            self.start_scan_files_thread(directory)
        else:
            # Khối else: Người dùng hủy chọn thư mục
            self._log_from_queue("Hủy chọn thư mục.")
            self.directory_path.set("")
            # --- SỬA THỤT LỀ Ở ĐÂY ---
            # Đảm bảo các dòng này thẳng hàng với 2 dòng trên
            if hasattr(self, 'toc_listbox') and self.toc_listbox.winfo_exists():
                try:
                    self.toc_listbox.delete(0, tk.END)
                except tk.TclError:
                     logger.warning("Error deleting from toc_listbox on cancel")
            self.chapters_data_cache.clear()
            self._set_ui_state(True) # Bật lại UI

    def select_cover_image(self):
        if self.is_task_running: messagebox.showwarning("Đang bận", "Đợi tác vụ khác.", parent=self.master); return
        filepath = filedialog.askopenfilename(title="Chọn ảnh bìa (JPG/PNG)", filetypes=[("Ảnh", "*.jpg *.jpeg *.png"), ("Tất cả", "*.*")], parent=self.master)
        if filepath:
            mimetype, _ = mimetypes.guess_type(filepath); is_image = bool(mimetype and mimetype.startswith('image/')) or filepath.lower().endswith(('.jpg', '.jpeg', '.png'))
            if is_image: self.cover_image_path.set(filepath); self._log_from_queue(f"Ảnh bìa hợp lệ: {os.path.basename(filepath)}")
            else: messagebox.showwarning("File không hợp lệ", f"File không phải ảnh JPG/PNG.\nMimetype: {mimetype}", parent=self.master); self._log_from_queue(f"LỖI: Ảnh bìa không hợp lệ: {os.path.basename(filepath)} ({mimetype})"); self.cover_image_path.set("")
        else: self._log_from_queue("Hủy chọn ảnh bìa."); self.cover_image_path.set("")

    def remove_selected_files(self):
        if self.is_task_running or not hasattr(self, 'toc_listbox'): return
        indices = self.toc_listbox.curselection()
        if not indices: messagebox.showinfo("Thông báo", "Chưa chọn mục để xóa.", parent=self.master); return
        for i in sorted(indices, reverse=True):
            try: item = self.chapters_data_cache.pop(i); self.toc_listbox.delete(i); self._log_from_queue(f"Đã xóa: {item.get('display', item.get('title'))}")
            except IndexError: self._log_from_queue(f"Lỗi index xóa mục {i}.")
        self._set_ui_state(True)

    def clear_all_files(self):
        if self.is_task_running or not hasattr(self, 'toc_listbox'): return
        if not self.chapters_data_cache: messagebox.showinfo("Thông báo", "Danh sách trống.", parent=self.master); return
        if messagebox.askyesno("Xác nhận", "Xóa tất cả mục?", parent=self.master):
            self.toc_listbox.delete(0, tk.END); self.chapters_data_cache.clear(); self._log_from_queue("Đã xóa tất cả."); self._set_ui_state(True)

    def start_scan_files_thread(self, directory):
        self.is_task_running = True; self._set_ui_state(False)
        if hasattr(self, 'progress_bar'): self.progress_bar['value'] = 0
        self._log_from_queue("Bắt đầu quét...")
        thread = threading.Thread(target=self._worker_scan_files, args=(directory,), daemon=True); thread.start()
        self.master.after(100, self._process_log_queue)

    def start_create_ebook_thread(self):
        if self.is_task_running: messagebox.showwarning("Đang bận", "Đợi tác vụ khác.", parent=self.master); return
        if not self.chapters_data_cache: messagebox.showerror("Lỗi", "Danh sách chương trống.", parent=self.master); self._log_from_queue("LỖI: Không có dữ liệu chương."); return
        output_fp = filedialog.asksaveasfilename(title="Lưu Ebook EPUB", defaultextension=".epub", filetypes=[("EPUB", "*.epub"), ("Tất cả", "*.*")], parent=self.master)
        if not output_fp: self._log_from_queue("Hủy lưu Ebook."); return
        self.is_task_running = True; self._set_ui_state(False)
        if hasattr(self, 'progress_bar'): self.progress_bar['value'] = 0
        self._log_from_queue(f"Bắt đầu tạo: {output_fp}")
        title = self.book_title.get(); author = self.book_author.get(); cover = self.cover_image_path.get()
        chapters = list(self.chapters_data_cache)
        thread = threading.Thread(target=self._worker_create_ebook, args=(output_fp, title, author, cover, chapters), daemon=True); thread.start()
        self.master.after(100, self._process_log_queue)

    # --- Worker Threads ---
    def _worker_scan_files(self, input_dir):
        """Worker thread to scan files and send TOC data to the queue."""
        try:
            self.log_queue.put(f"Quét .txt trong: {input_dir}")
            try: # Defensive listing
                 all_files = os.listdir(input_dir)
            except OSError as list_err:
                 raise OSError(f"Không thể liệt kê thư mục: {list_err}") from list_err

            txt_filenames_unsorted = [f for f in all_files if f.lower().endswith(".txt") and os.path.isfile(os.path.join(input_dir, f))]
            txt_filenames_sorted = sorted(txt_filenames_unsorted, key=natural_sort_key) # Use natural sort
            total_files = len(txt_filenames_sorted)
            self.log_queue.put(f"Tìm thấy {total_files} file .txt (sắp xếp tự nhiên).")

            if total_files == 0: self.log_queue.put(('toc_data', [])); self.log_queue.put(('scan_done',)); return

            scanned_chapters = []
            for i, filename in enumerate(txt_filenames_sorted):
                filepath = os.path.join(input_dir, filename)
                self.log_queue.put(('progress', i + 1, total_files))
                title = f"Chương {i+1} ({filename})"; display_title = title; content_raw = ""
                try: # Try reading the file
                    lines = None; encodings = ['utf-8', 'cp1252', 'latin-1']
                    read_success = False
                    for enc in encodings:
                        try:
                            with open(filepath, 'r', encoding=enc) as f: lines = f.readlines(); read_success = True; break
                        except UnicodeDecodeError: continue
                        except Exception as read_err: logger.error(f"Read error {filename} ({enc}): {read_err}"); lines = None; break # Break on other read errors
                    if not read_success and lines is None: raise IOError(f"Cannot decode {filename}")

                    if lines:
                        first_line = lines[0].strip()
                        if first_line: title = first_line; display_title = f"{title} ({filename})"; content_raw = "".join(lines[1:])
                        else: display_title += " - Tiêu đề trống"; content_raw = "".join(lines)
                    else: display_title += " - File rỗng"
                    processed_content = content_raw.strip()
                    scanned_chapters.append({'title': title, 'display': display_title, 'raw_content': processed_content, 'filename': filename})
                except Exception as e: # Error processing specific file
                    error_msg = f"Lỗi đọc/xử lý '{filename}': {e}"; self.log_queue.put(f"*** LỖI ĐỌC FILE: {error_msg}")
                    scanned_chapters.append({'title': f"LỖI: {filename}", 'display': f"LỖI: {filename}", 'raw_content': f"Lỗi: {e}", 'filename': filename})

            self.log_queue.put(('toc_data', scanned_chapters)); self.log_queue.put(('scan_done',))
        except FileNotFoundError: self.log_queue.put(('error', f"Lỗi: Thư mục nguồn không tồn tại: {input_dir}", traceback.format_exc()))
        except PermissionError: self.log_queue.put(('error', f"Lỗi: Không quyền truy cập thư mục: {input_dir}", traceback.format_exc()))
        except OSError as os_err: self.log_queue.put(('error', f"Lỗi OS khi quét thư mục: {os_err}", traceback.format_exc()))
        except Exception as e: tb_str = traceback.format_exc(); logger.error(f"Critical scan error {input_dir}: {e}\n{tb_str}"); self.log_queue.put(('error', f"Lỗi nghiêm trọng khi quét: {e}", tb_str))

    def _worker_create_ebook(self, output_filepath, book_title, book_author, cover_path, chapters_to_process):
        """Worker thread to create the EPUB file."""
        try:
            total_chapters = len(chapters_to_process); self.log_queue.put(f"Bắt đầu xử lý {total_chapters} chương...")
            book = epub.EpubBook(); book.set_identifier(str(uuid.uuid4())); book.set_title(book_title or "Ebook"); book.set_language('vi'); book.add_author(book_author or "Creator")

            # Cover handling
            cover_img_item = None
            if cover_path and os.path.exists(cover_path):
                self.log_queue.put(f"Xử lý bìa: {os.path.basename(cover_path)}")
                try:
                    mime, _ = mimetypes.guess_type(cover_path); mime = mime or 'image/jpeg'; fname = f"cover{os.path.splitext(cover_path)[1]}"
                    with open(cover_path, 'rb') as f: cover_content = f.read()
                    cover_img_item = epub.EpubItem(uid="cover-image", file_name=f"images/{fname}", media_type=mime, content=cover_content)
                    book.add_item(cover_img_item)
                    book.set_cover(f"images/{fname}", cover_content) # Set cover metadata
                    self.log_queue.put(" -> Đã thêm item và metadata bìa.")
                except Exception as e: self.log_queue.put(f" -> LỖI xử lý bìa: {e}"); cover_img_item = None
            else: self.log_queue.put("Không có ảnh bìa.")

            # Process chapters
            epub_chapters = []; processed_count = 0
            for i, chap_data in enumerate(chapters_to_process):
                title = chap_data.get('title', f"Chương {i+1}"); num = i + 1
                self.log_queue.put(('progress', num, total_chapters))
                if num % 50 == 0 or num == 1 or num == total_chapters: self.log_queue.put(f"  -> Tạo [{num}/{total_chapters}]: {title[:50]}...")
                try:
                    raw = chap_data.get('raw_content', ''); body = self.format_content_for_xhtml(raw, title)
                    if body:
                        fname = f'chap_{num}.xhtml'
                        chap = epub.EpubHtml(title=title, file_name=fname, lang='vi'); chap.content = body
                        chap.add_link(href='style/main.css', rel='stylesheet', type='text/css')
                        book.add_item(chap); epub_chapters.append(chap); processed_count += 1
                    else: self.log_queue.put(f"      -> Bỏ qua chương rỗng '{title}'.")
                except Exception as e: self.log_queue.put(f"  -> LỖI tạo chương '{title}': {e}")

            if not epub_chapters: raise ValueError("Không tạo được chương nội dung nào.")
            self.log_queue.put(f"Số chương hợp lệ đã xử lý: {processed_count}")

            # TOC, Nav, NCX
            self.log_queue.put("Tạo TOC..."); book.toc = tuple(epub_chapters)
            self.log_queue.put("Thêm Nav/NCX..."); book.add_item(epub.EpubNcx()); book.add_item(epub.EpubNav())

            # CSS
            self.log_queue.put("Thêm CSS..."); css_content = 'body{font-family:sans-serif;line-height:1.6;margin:1em;} h1{text-align:center;margin-top:0;padding-top:1em;} p{margin-bottom:1em;text-align:justify;}'; css = epub.EpubItem(uid="style_main", file_name="style/main.css", media_type="text/css", content=css_content.encode('utf-8')); book.add_item(css)

            # Spine
            self.log_queue.put("Xác định Spine..."); spine = ['nav']
            # Check if cover was successfully set in metadata
            is_cover_set = False
            for item in book.metadata.get('http://www.idpf.org/2007/opf', {}).get('meta', []):
                 if isinstance(item, dict) and item.get('name') == 'cover': is_cover_set = True; break
            if is_cover_set: spine.insert(0, 'cover'); self.log_queue.put(" -> Đã thêm 'cover' vào spine.")
            elif cover_img_item: self.log_queue.put(" -> Ảnh bìa item tồn tại nhưng không có trong metadata cover.")
            spine.extend(epub_chapters); book.spine = spine

            # Write file
            self.log_queue.put("Ghi file EPUB...");
            try:
                if not book.spine or len(book.spine) <= 1: raise ValueError("Spine không hợp lệ.")
                if not book.toc: raise ValueError("TOC trống.")
                epub.write_epub(output_filepath, book, {})
                self.log_queue.put(('epub_done', output_filepath))
            except Exception as write_e: tb_str = traceback.format_exc(); self.log_queue.put(f"*** LỖI GHI FILE:\n{tb_str}"); self.log_queue.put(('error', f"Lỗi ghi EPUB: {write_e}", tb_str))
        except Exception as e: tb_str = traceback.format_exc(); logger.error(f"Worker error: {e}\n{tb_str}"); self.log_queue.put(('error', f"Lỗi worker tạo EPUB: {e}", tb_str))

    # --- Utility Functions ---
    def fix_formatting(self, text):
        if not text: return ""
        text = text.replace('\r\n', '\n').replace('\r', '\n'); blocks = re.split(r'\n\s*\n', text)
        return "\n\n".join([b.strip() for b in blocks if b.strip()])

    def format_content_for_xhtml(self, raw_content, chapter_title):
        if not raw_content or raw_content.isspace(): return ""
        fixed = self.fix_formatting(raw_content)
        if not fixed or fixed.isspace(): return ""
        paras = fixed.split('\n\n')
        title_esc = chapter_title.replace('&', '&').replace('<', '<').replace('>', '>')
        content = f'<h1>{title_esc}</h1>\n'
        for p in paras:
            if p: p_esc = p.replace('&', '&').replace('<', '<').replace('>', '>'); content += f'<p>{p_esc}</p>\n'
        return content

# --- Standalone Execution Block ---
if __name__ == "__main__":
    # Basic logging setup for standalone run
    log_format = '%(asctime)s - %(levelname)s - [%(filename)s:%(lineno)d] - %(message)s'
    logging.basicConfig(level=logging.DEBUG, format=log_format)

    try:
        # Use ttkbootstrap for theming if available
        try:
            import ttkbootstrap as tb
            root = tb.Window(themename="cyborg") # Or another theme
        except ImportError:
            root = tk.Tk() # Fallback to standard Tk
            logging.warning("ttkbootstrap not found, using standard Tk widgets.")

        root.title("Trình tạo Ebook EPUB (Standalone)")
        root.geometry("750x750")

        # Create and pack the application Frame
        app = EbookCreatorApp(root)
        app.pack(fill=tk.BOTH, expand=True)

        root.mainloop()
    except Exception as main_e:
         # Log critical error if app fails to launch
         logging.critical(f"Failed to launch EbookCreatorApp: {main_e}", exc_info=True)
         # Show a simple error message box if possible
         try:
             tk.messagebox.showerror("Lỗi Khởi Động", f"Không thể khởi chạy ứng dụng:\n{main_e}")
         except:
             pass # Ignore if messagebox itself fails