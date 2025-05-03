# D:\Ebooks\Test_dich\core\ebook_creator.py
import tkinter as tk
from tkinter import ttk, filedialog, messagebox, scrolledtext
import os
import re
import uuid
from ebooklib import epub
import mimetypes
import threading
import queue
import traceback

class EbookCreatorApp:
    """
    Lớp ứng dụng chính cho việc tạo Ebook EPUB từ các file text.
    Phiên bản hoàn chỉnh với threading, progress bar, chọn/xóa file,
    xử lý cover, css và fix lỗi ghi file.
    """
    def __init__(self, master, source_dir=None):
        """
        Khởi tạo giao diện người dùng.
        master: Có thể là tk.Tk (chạy độc lập) hoặc tk.Toplevel (gọi từ main GUI).
        source_dir: Đường dẫn thư mục nguồn (nếu gọi từ main GUI).
        """
        self.master = master
        self.master.title("Trình tạo Ebook EPUB (v1.9 - Hoàn chỉnh)")
        self.master.geometry("750x750")
        self.master.wm_attributes("-topmost", False)  # Đảm bảo không luôn ở trên

        self.directory_path = tk.StringVar(value=source_dir or "")
        self.cover_image_path = tk.StringVar()
        self.book_title = tk.StringVar(value="Ebook Tổng hợp")
        self.book_author = tk.StringVar(value="Người tạo Ebook")
        self.chapters_data_cache = []

        self.log_queue = queue.Queue()
        self.is_task_running = False

        # --- Khung chính ---
        main_pane = ttk.PanedWindow(master, orient=tk.HORIZONTAL)
        main_pane.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)

        # --- Khung bên trái: Cài đặt ---
        left_frame = ttk.Frame(main_pane, padding="10")
        main_pane.add(left_frame, weight=1)

        # --- Phần 1: Chọn thư mục ---
        dir_frame = ttk.LabelFrame(left_frame, text="1. Chọn thư mục nguồn", padding="10")
        dir_frame.pack(fill=tk.X, pady=(0, 10))
        self.dir_entry = ttk.Entry(dir_frame, textvariable=self.directory_path, state="readonly", width=30)
        self.dir_entry.pack(side=tk.LEFT, fill=tk.X, expand=True)
        self.browse_dir_button = ttk.Button(dir_frame, text="Chọn...", command=self.select_directory)
        self.browse_dir_button.pack(side=tk.LEFT, padx=(5, 0))

        # --- Phần 2: Thông tin Ebook ---
        self.metadata_frame = ttk.LabelFrame(left_frame, text="2. Thông tin Ebook", padding="10")
        self.metadata_frame.pack(fill=tk.X, pady=(0, 10))
        ttk.Label(self.metadata_frame, text="Tiêu đề sách:").grid(row=0, column=0, padx=5, pady=5, sticky=tk.W)
        self.title_entry = ttk.Entry(self.metadata_frame, textvariable=self.book_title, width=40)
        self.title_entry.grid(row=0, column=1, columnspan=2, padx=5, pady=5, sticky=tk.EW)
        ttk.Label(self.metadata_frame, text="Tác giả:").grid(row=1, column=0, padx=5, pady=5, sticky=tk.W)
        self.author_entry = ttk.Entry(self.metadata_frame, textvariable=self.book_author, width=40)
        self.author_entry.grid(row=1, column=1, columnspan=2, padx=5, pady=5, sticky=tk.EW)

        # --- Phần 3: Chọn ảnh bìa ---
        self.cover_frame = ttk.LabelFrame(left_frame, text="3. Chọn ảnh bìa (Tùy chọn)", padding="10")
        self.cover_frame.pack(fill=tk.X, pady=(0, 10))
        self.cover_entry = ttk.Entry(self.cover_frame, textvariable=self.cover_image_path, state="readonly", width=30)
        self.cover_entry.pack(side=tk.LEFT, fill=tk.X, expand=True)
        self.browse_cover_button = ttk.Button(self.cover_frame, text="Chọn...", command=self.select_cover_image)
        self.browse_cover_button.pack(side=tk.LEFT, padx=(5, 0))

        # --- Phần 4: Danh sách file/chương (Sử dụng Listbox) ---
        toc_frame = ttk.LabelFrame(left_frame, text="4. Danh sách file/chương (Chọn để xóa)", padding="10")
        toc_frame.pack(fill=tk.BOTH, expand=True, pady=(0, 5))

        # Frame chứa Listbox và Scrollbar
        listbox_frame = ttk.Frame(toc_frame)
        listbox_frame.pack(fill=tk.BOTH, expand=True)

        toc_scrollbar = ttk.Scrollbar(listbox_frame, orient="vertical")
        toc_scrollbar.pack(side=tk.RIGHT, fill=tk.Y)

        self.toc_listbox = tk.Listbox(
            listbox_frame,
            selectmode=tk.EXTENDED,
            yscrollcommand=toc_scrollbar.set,
            height=8
        )
        self.toc_listbox.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        toc_scrollbar.config(command=self.toc_listbox.yview)

        # Frame chứa các nút xóa
        toc_button_frame = ttk.Frame(toc_frame)
        toc_button_frame.pack(fill=tk.X, pady=(5, 0))

        self.remove_selected_button = ttk.Button(
            toc_button_frame,
            text="Xóa mục đã chọn",
            command=self.remove_selected_files,
            state=tk.DISABLED
        )
        self.remove_selected_button.pack(side=tk.LEFT, padx=5)

        self.clear_all_button = ttk.Button(
            toc_button_frame,
            text="Xóa tất cả",
            command=self.clear_all_files,
            state=tk.DISABLED
        )
        self.clear_all_button.pack(side=tk.LEFT, padx=5)

        # --- Progress Bar ---
        self.progress_bar = ttk.Progressbar(left_frame, orient="horizontal", length=300, mode="determinate")
        self.progress_bar.pack(pady=(5, 10), fill=tk.X)

        # --- Nút tạo Ebook ---
        self.create_button = ttk.Button(left_frame, text="5. Tạo Ebook EPUB", command=self.start_create_ebook_thread)
        self.create_button.pack(pady=10)

        # --- Khung bên phải: Log ---
        right_frame = ttk.Frame(main_pane, padding="5")
        main_pane.add(right_frame, weight=1)
        log_label_frame = ttk.LabelFrame(right_frame, text="Log/Trạng thái", padding="5")
        log_label_frame.pack(fill=tk.BOTH, expand=True)
        self.log_area = scrolledtext.ScrolledText(log_label_frame, height=15, wrap=tk.WORD, state="disabled", width=40)
        self.log_area.pack(fill=tk.BOTH, expand=True)

        self._log_from_queue("Chào mừng! Hãy thực hiện các bước theo thứ tự.")
        if source_dir:
            self.start_scan_files_thread(source_dir)  # Tự động quét nếu có thư mục

        # Bắt đầu kiểm tra queue định kỳ
        self.master.after(100, self._process_log_queue)

    def _set_ui_state(self, enabled):
        """Bật/Tắt các widget tương tác khi có tác vụ chạy."""
        state = tk.NORMAL if enabled else tk.DISABLED
        self.browse_dir_button.config(state=state)
        self.browse_cover_button.config(state=state)
        self.create_button.config(state=state)
        self.title_entry.config(state=state)
        self.author_entry.config(state=state)
        toc_button_state = tk.NORMAL if enabled and self.toc_listbox.size() > 0 else tk.DISABLED
        self.remove_selected_button.config(state=toc_button_state)
        self.clear_all_button.config(state=toc_button_state)
        self.toc_listbox.config(state=tk.NORMAL if enabled else tk.DISABLED)

    def _log_from_queue(self, message):
        """Ghi log vào Text widget (an toàn để gọi từ main thread)."""
        self.log_area.config(state="normal")
        self.log_area.insert(tk.END, message + "\n")
        self.log_area.see(tk.END)
        self.log_area.config(state="disabled")

    def _process_log_queue(self):
        """Xử lý các thông điệp từ worker thread trong queue."""
        processed_count = 0
        max_process_per_cycle = 20
        try:
            while processed_count < max_process_per_cycle:
                message = self.log_queue.get_nowait()
                processed_count += 1

                if isinstance(message, tuple):
                    msg_type = message[0]
                    if msg_type == 'progress':
                        current, total = message[1], message[2]
                        percentage = (current / total) * 100 if total > 0 else 0
                        self.progress_bar['value'] = percentage
                    elif msg_type == 'toc_data':
                        self.toc_listbox.config(state=tk.NORMAL)
                        self.toc_listbox.delete(0, tk.END)
                        self.chapters_data_cache = message[1]
                        for chapter_info in self.chapters_data_cache:
                            display_text = chapter_info.get('display', chapter_info.get('title', 'N/A'))
                            self.toc_listbox.insert(tk.END, display_text)
                        self.toc_listbox.config(state=tk.NORMAL)
                    elif msg_type == 'scan_done':
                        self._log_from_queue(">>> Quét thư mục hoàn tất.")
                        self.is_task_running = False
                        self._set_ui_state(True)
                        self.progress_bar['value'] = 0
                    elif msg_type == 'epub_done':
                        filepath = message[1]
                        self._log_from_queue(f">>> Tạo EPUB hoàn tất: {filepath}")
                        messagebox.showinfo("Hoàn thành", f"Đã tạo thành công ebook EPUB!\nFile được lưu tại:\n{filepath}")
                        self.is_task_running = False
                        self._set_ui_state(True)
                        self.progress_bar['value'] = 0
                    elif msg_type == 'error':
                        error_msg = message[1]
                        self._log_from_queue(f"*** LỖI: {error_msg}")
                        messagebox.showerror("Lỗi", f"Đã xảy ra lỗi:\n{error_msg}")
                        self.is_task_running = False
                        self._set_ui_state(True)
                        self.progress_bar['value'] = 0
                elif isinstance(message, str):
                    self._log_from_queue(message)

        except queue.Empty:
            pass
        finally:
            if not self.is_task_running:
                toc_button_state = tk.NORMAL if self.toc_listbox.size() > 0 else tk.DISABLED
                self.remove_selected_button.config(state=toc_button_state)
                self.clear_all_button.config(state=toc_button_state)
                self.toc_listbox.config(state=tk.NORMAL)
                self.browse_cover_button.config(state=tk.NORMAL)
            if self.is_task_running or not self.log_queue.empty():
                self.master.after(100, self._process_log_queue)

    def select_directory(self):
        """Mở hộp thoại chọn thư mục và bắt đầu thread quét file."""
        if self.is_task_running:
            messagebox.showwarning("Đang bận", "Một tác vụ khác đang chạy, vui lòng đợi.")
            return
        directory = filedialog.askdirectory(title="Chọn thư mục chứa file .txt")
        if directory:
            self.directory_path.set(directory)
            self._log_from_queue(f"Đã chọn thư mục: {directory}")
            self.toc_listbox.delete(0, tk.END)
            self.chapters_data_cache.clear()
            self.start_scan_files_thread(directory)
        else:
            self._log_from_queue("Hủy chọn thư mục.")
            self.directory_path.set("")
            self.toc_listbox.delete(0, tk.END)
            self.chapters_data_cache.clear()
            self._set_ui_state(True)

    def select_cover_image(self):
        """Chọn ảnh bìa (chạy trên main thread, đủ nhanh)."""
        if self.is_task_running:
            messagebox.showwarning("Đang bận", "Một tác vụ khác đang chạy, vui lòng đợi.")
            return
        filepath = filedialog.askopenfilename(
            title="Chọn ảnh bìa",
            filetypes=[("Image files", "*.jpg *.jpeg *.png"), ("All files", "*.*")]
        )
        if filepath:
            mimetype, encoding = mimetypes.guess_type(filepath)
            is_image = False
            if mimetype and mimetype.startswith('image/'):
                is_image = True
            elif filepath.lower().endswith(('.jpg', '.jpeg', '.png')):
                is_image = True
            if is_image:
                self.cover_image_path.set(filepath)
                self._log_from_queue(f"Đã chọn ảnh bìa hợp lệ: {os.path.basename(filepath)}")
            else:
                messagebox.showwarning("File không hợp lệ", f"File đã chọn không phải là định dạng ảnh được hỗ trợ (JPG, PNG) hoặc không thể nhận diện.\nMimetype: {mimetype}")
                self._log_from_queue(f"LỖI: File ảnh bìa không hợp lệ hoặc không nhận diện được: {os.path.basename(filepath)} (Mimetype: {mimetype})")
                self.cover_image_path.set("")
        else:
            self._log_from_queue("Hủy chọn ảnh bìa.")
            self.cover_image_path.set("")

    def remove_selected_files(self):
        """Xóa các mục được chọn khỏi Listbox và cache."""
        if self.is_task_running: return
        selected_indices = self.toc_listbox.curselection()
        if not selected_indices:
            messagebox.showinfo("Thông báo", "Chưa có mục nào được chọn để xóa.")
            return
        for index in reversed(selected_indices):
            try:
                removed_item = self.chapters_data_cache.pop(index)
                self.toc_listbox.delete(index)
                self._log_from_queue(f"Đã xóa: {removed_item.get('display', removed_item.get('title'))}")
            except IndexError:
                self._log_from_queue(f"Lỗi index khi xóa mục tại vị trí {index}. Có thể danh sách đã thay đổi.")
        self._set_ui_state(True)

    def clear_all_files(self):
        """Xóa tất cả các mục khỏi Listbox và cache."""
        if self.is_task_running: return
        if not self.chapters_data_cache:
            messagebox.showinfo("Thông báo", "Danh sách đang trống.")
            return
        confirmed = messagebox.askyesno("Xác nhận", "Bạn có chắc muốn xóa tất cả các mục khỏi danh sách không?")
        if confirmed:
            self.toc_listbox.delete(0, tk.END)
            self.chapters_data_cache.clear()
            self._log_from_queue("Đã xóa tất cả các mục khỏi danh sách.")
            self._set_ui_state(True)

    def start_scan_files_thread(self, directory):
        """Chuẩn bị và bắt đầu thread quét file."""
        self.is_task_running = True
        self._set_ui_state(False)
        self.progress_bar['value'] = 0
        self._log_from_queue("Bắt đầu quét thư mục...")
        scan_thread = threading.Thread(target=self._worker_scan_files, args=(directory,), daemon=True)
        scan_thread.start()
        self.master.after(100, self._process_log_queue)

    def start_create_ebook_thread(self):
        """Chuẩn bị và bắt đầu thread tạo EPUB."""
        if self.is_task_running:
            messagebox.showwarning("Đang bận", "Một tác vụ khác đang chạy, vui lòng đợi.")
            return
        if not self.chapters_data_cache:
            messagebox.showerror("Lỗi", "Danh sách chương trống. Vui lòng quét thư mục và đảm bảo còn chương để tạo Ebook.")
            self._log_from_queue("LỖI: Không có dữ liệu chương để tạo Ebook (có thể đã bị xóa hết).")
            return
        output_filepath = filedialog.asksaveasfilename(
            title="Lưu Ebook EPUB",
            defaultextension=".epub",
            filetypes=[("EPUB files", "*.epub"), ("All files", "*.*")]
        )
        if not output_filepath:
            self._log_from_queue("Hủy lưu file Ebook.")
            return
        self.is_task_running = True
        self._set_ui_state(False)
        self.progress_bar['value'] = 0
        self._log_from_queue(f"Bắt đầu tạo EPUB: {output_filepath}")
        book_title = self.book_title.get()
        book_author = self.book_author.get()
        cover_path = self.cover_image_path.get()
        chapters_to_process = list(self.chapters_data_cache)
        create_thread = threading.Thread(
            target=self._worker_create_ebook,
            args=(output_filepath, book_title, book_author, cover_path, chapters_to_process),
            daemon=True
        )
        create_thread.start()
        self.master.after(100, self._process_log_queue)

    def _worker_scan_files(self, input_dir):
        """Worker thread để quét file và gửi dữ liệu TOC về queue."""
        try:
            self.log_queue.put(f"Quét file .txt trong: {input_dir}")
            txt_files = sorted([f for f in os.listdir(input_dir) if f.lower().endswith(".txt")])
            total_files = len(txt_files)
            self.log_queue.put(f"Tìm thấy {total_files} file .txt.")

            if total_files == 0:
                self.log_queue.put(('toc_data', []))
                self.log_queue.put(('scan_done',))
                return

            scanned_chapters = []
            for i, filename in enumerate(txt_files):
                filepath = os.path.join(input_dir, filename)
                self.log_queue.put(('progress', i + 1, total_files))

                title = f"Chương {i+1} ({filename})"
                display_title = title
                content_raw = ""
                try:
                    try:
                        with open(filepath, 'r', encoding='utf-8') as f: lines = f.readlines()
                    except UnicodeDecodeError:
                        with open(filepath, 'r', encoding='latin-1') as f: lines = f.readlines()

                    if lines:
                        first_line = lines[0].strip()
                        if first_line:
                            title = first_line
                            display_title = f"{title} ({filename})"
                            content_raw = "".join(lines[1:])
                        else:
                            display_title += " - Không có tiêu đề"
                            content_raw = "".join(lines)
                    else:
                        display_title += " - File rỗng"

                    processed_content = content_raw.strip()
                    scanned_chapters.append({
                        'title': title,
                        'display': display_title,
                        'raw_content': processed_content,
                        'filename': filename
                    })

                except Exception as e:
                    error_msg = f"Lỗi khi đọc file '{filename}': {e}"
                    self.log_queue.put(f"*** LỖI ĐỌC: {error_msg}")
                    error_title = f"LỖI ĐỌC FILE: {filename}"
                    scanned_chapters.append({
                        'title': error_title,
                        'display': error_title,
                        'raw_content': f"Không thể đọc file: {e}",
                        'filename': filename
                    })

            self.log_queue.put(('toc_data', scanned_chapters))
            self.log_queue.put(('scan_done',))

        except Exception as e:
            self.log_queue.put(('error', f"Lỗi nghiêm trọng khi quét thư mục: {e}"))

    def _worker_create_ebook(self, output_filepath, book_title, book_author, cover_path, chapters_to_process):
        """Worker thread để tạo file EPUB - PHIÊN BẢN HOÀN CHỈNH."""
        try:
            total_chapters_in_list = len(chapters_to_process)
            self.log_queue.put(f"Bắt đầu xử lý {total_chapters_in_list} chương...")
            chapters_actually_processed = 0

            self.log_queue.put("Khởi tạo đối tượng sách EPUB...")
            book = epub.EpubBook()
            book_id = str(uuid.uuid4())
            book.set_identifier(book_id)
            book.set_title(book_title or "Ebook Tổng hợp")
            book.set_language('vi')
            book.add_author(book_author or "Người tạo Ebook")

            cover_img_item = None
            if cover_path and os.path.exists(cover_path):
                self.log_queue.put(f"Đang xử lý ảnh bìa từ: {os.path.basename(cover_path)}")
                try:
                    mime_type, _ = mimetypes.guess_type(cover_path)
                    if not mime_type: mime_type = 'image/jpeg'
                    with open(cover_path, 'rb') as f: cover_data = f.read()
                    cover_filename_epub = f"cover{os.path.splitext(cover_path)[1]}"
                    cover_epub_path = f"images/{cover_filename_epub}"
                    cover_img_item = epub.EpubItem(
                        uid="cover-image",
                        file_name=cover_epub_path,
                        media_type=mime_type,
                        content=cover_data
                    )
                    book.add_item(cover_img_item)
                    self.log_queue.put(" -> Đã thêm item ảnh bìa.")
                except Exception as e:
                    self.log_queue.put(f" -> LỖI khi xử lý ảnh bìa: {e}")
                    cover_img_item = None
            else:
                self.log_queue.put("Không có ảnh bìa hoặc file không tồn tại.")

            epub_chapters = []
            self.log_queue.put(f"Bắt đầu vòng lặp xử lý {total_chapters_in_list} chương...")
            for i, chapter_data in enumerate(chapters_to_process):
                chapter_title_for_epub = chapter_data.get('title', f"Chương {i+1}")
                current_chapter_num = i + 1
                self.log_queue.put(('progress', current_chapter_num, total_chapters_in_list))
                if current_chapter_num % 50 == 0 or current_chapter_num == 1 or current_chapter_num == total_chapters_in_list:
                    self.log_queue.put(f"  -> Đang tạo chương [{current_chapter_num}/{total_chapters_in_list}]: {chapter_title_for_epub[:50]}...")

                try:
                    raw_content_for_format = chapter_data.get('raw_content', '')
                    xhtml_body_content = self.format_content_for_xhtml(
                        raw_content_for_format, chapter_title_for_epub
                    )

                    if xhtml_body_content:
                        chap_filename = f'chap_{current_chapter_num}.xhtml'
                        epub_chap = epub.EpubHtml(title=chapter_title_for_epub, file_name=chap_filename, lang='vi')
                        epub_chap.content = xhtml_body_content
                        epub_chap.add_link(href='style/main.css', rel='stylesheet', type='text/css')
                        book.add_item(epub_chap)
                        epub_chapters.append(epub_chap)
                    else:
                        self.log_queue.put(f"      -> Bỏ qua chương '{chapter_title_for_epub}' vì nội dung rỗng.")

                except Exception as e:
                    self.log_queue.put(f"  -> LỖI khi tạo chương '{chapter_title_for_epub}': {e}")

            if not epub_chapters:
                error_message = "Không có chương nội dung nào được tạo thành công."
                self.log_queue.put(f"*** LỖI NGHIÊM TRỌNG: {error_message}")
                self.log_queue.put(('error', error_message))
                return

            self.log_queue.put(f"Số lượng chương hợp lệ thực sự được xử lý và thêm vào EPUB: {len(epub_chapters)}")

            self.log_queue.put("Đang tạo mục lục (TOC)...")
            book.toc = tuple(epub_chapters)

            self.log_queue.put("Đang thêm file điều hướng (NCX, Nav)...")
            book.add_item(epub.EpubNcx())
            book.add_item(epub.EpubNav())

            self.log_queue.put("Đang thêm CSS cơ bản...")
            css_content = 'body { font-family: sans-serif; line-height: 1.6; margin: 1em; } h1 { text-align: center; margin-top: 0; padding-top: 1em; } p { margin-bottom: 1em; text-align: justify; }'
            css_file = epub.EpubItem(uid="style_main", file_name="style/main.css", media_type="text/css", content=css_content.encode('utf-8'))
            book.add_item(css_file)

            self.log_queue.put("Đang xác định thứ tự đọc (Spine)...")
            spine_content = ['nav'] + epub_chapters
            if cover_img_item:
                self.log_queue.put(" -> Ảnh bìa tồn tại, không thêm vào spine (dựa vào metadata).")
            book.spine = spine_content

            self.log_queue.put("Đang ghi file EPUB...")
            try:
                if not book.spine or len(book.spine) <= 1:
                    raise ValueError("Lỗi EPUB: Spine không hợp lệ (thiếu chương nội dung).")
                if not book.toc:
                    raise ValueError("Lỗi EPUB: TOC không được để trống.")
                epub.write_epub(output_filepath, book, {})
                self.log_queue.put(('epub_done', output_filepath))
            except Exception as e:
                error_details = traceback.format_exc()
                self.log_queue.put(f"*** LỖI GHI FILE CHI TIẾT:\n{error_details}")
                self.log_queue.put(('error', f"Lỗi nghiêm trọng khi ghi file EPUB: {e}"))

        except Exception as e:
            error_details = traceback.format_exc()
            self.log_queue.put(f"*** LỖI WORKER THREAD CHI TIẾT:\n{error_details}")
            self.log_queue.put(('error', f"Lỗi không mong muốn trong quá trình tạo EPUB: {e}"))

    def fix_formatting(self, text):
        """Chuẩn hóa khoảng trắng giữa các đoạn văn bản."""
        if not text: return ""
        text = text.replace('\r\n', '\n').replace('\r', '\n')
        blocks = re.split(r'\n\s*\n', text)
        non_empty_blocks = [block.strip() for block in blocks if block.strip()]
        return "\n\n".join(non_empty_blocks)

    def format_content_for_xhtml(self, raw_content, chapter_title):
        """
        Định dạng nội dung thô thành phần body XHTML cho chương EPUB.
        Trả về chuỗi rỗng nếu raw_content đầu vào là rỗng hoặc chỉ chứa khoảng trắng.
        """
        if not raw_content or raw_content.isspace():
            return ""
        fixed_text = self.fix_formatting(raw_content)
        if not fixed_text or fixed_text.isspace():
            return ""
        paragraphs = fixed_text.split('\n\n')
        escaped_title = chapter_title.replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')
        xhtml_content = f'<h1>{escaped_title}</h1>\n'
        for para in paragraphs:
            if para:
                escaped_para = para.replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')
                xhtml_content += f'<p>{escaped_para}</p>\n'
        return xhtml_content

if __name__ == "__main__":
    root = tk.Tk()
    app = EbookCreatorApp(root)
    root.mainloop()