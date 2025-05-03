#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Integrated Novel Downloader GUI
- Supports Piaotia (requests) and Uukanshu (Selenium)
- Maximum 2 concurrent threads: 1 for Piaotia, 1 for Uukanshu
- Optimized chapter scanning for Piaotia
- Persistent queue with URLs retained in list_widget until manually removed
- Fixed stop_download error and ensured both threads run concurrently
- Fixed Piaotia file saving issue by handling 404 errors and validating content
- Fixed Piaotia chapter URL generation to include correct path (html/a/b/c.html)
- Excluded base URL from chapter list to ensure correct chapter numbering
"""
import sys
import os
import json
import time
import re
import warnings
from urllib.parse import urljoin, urlparse, urlunparse
from abc import ABC, abstractmethod
import random

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
from bs4 import BeautifulSoup
from PyQt5.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QLineEdit, QPushButton, QListWidget, QAbstractItemView,
    QMessageBox, QStatusBar, QTextEdit, QComboBox
)
from PyQt5.QtCore import QThread, pyqtSignal
import qdarkstyle

# Optional Selenium imports for Uukanshu
try:
    from selenium.common.exceptions import WebDriverException, TimeoutException
    import undetected_chromedriver as uc
    SELENIUM_AVAILABLE = True
except ImportError:
    SELENIUM_AVAILABLE = False
    uc = None

# Suppress BeautifulSoup warnings
warnings.filterwarnings("ignore", category=UserWarning, module='bs4')

# Settings and constants
SETTINGS_FILE = os.path.join(os.path.expanduser('~'), '.novel_downloader_settings.json')
LOG_FILE_NAME = "download_log.txt"
SAVE_ENCODING = 'utf-8'

# HTTP session configuration for Piaotia
session = requests.Session()
session.headers.update({
    'User-Agent': (
        'Mozilla/5.0 (Windows NT 10.0; Win64; x64) '
        'AppleWebKit/537.36 (KHTML, like Gecko) '
        'Chrome/110.0.0.0 Safari/537.36'
    ),
    'Referer': 'https://www.piaotia.com/',
    'Accept-Language': 'en-US,en;q=0.9',
    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8'
})
retries = Retry(total=5, backoff_factor=0.5, status_forcelist=[429, 500, 502, 503, 504])
session.mount('https://', HTTPAdapter(max_retries=retries))
session.mount('http://', HTTPAdapter(max_retries=retries))

# Helper functions
def sanitize_filename(s):
    return ''.join(c if c.isalnum() or c in ' -_()' else '_' for c in s).strip()

def get_dirs_from_url(url, source):
    parsed = urlparse(url)
    parts = parsed.path.strip('/').split('/')
    if source == 'piaotia':
        if 'html' in parts:
            i = parts.index('html')
            parent = parts[i+1] if i+1 < len(parts) else 'base'
            child = parts[i+2] if i+2 < len(parts) and parts[i+2] != 'index.html' else parent
            return parent, child
        return 'base', 'sub'
    elif source == 'uukanshu':
        site_name = parsed.netloc
        if len(parts) >= 2:
            if parts[0] == 'book' and parts[1].isdigit():
                return site_name, os.path.join('book', parts[1])
            elif parts[0] == 'html' and len(parts) >= 3 and parts[1].isdigit() and parts[2].isdigit():
                return site_name, os.path.join('html', parts[1], parts[2])
            return site_name, os.path.join(*parts[:2])
        return site_name, 'book'
    return 'unknown', 'novel'

def load_downloaded_log(log_filepath):
    downloaded = set()
    if os.path.exists(log_filepath):
        try:
            with open(log_filepath, 'r', encoding=SAVE_ENCODING) as f:
                for line in f:
                    downloaded.add(line.strip())
        except Exception as e:
            print(f"Error reading log {log_filepath}: {e}")
    return downloaded

def log_downloaded_chapter(chapter_url, log_filepath):
    try:
        os.makedirs(os.path.dirname(log_filepath), exist_ok=True)
        with open(log_filepath, 'a', encoding=SAVE_ENCODING) as f:
            f.write(chapter_url + '\n')
    except Exception as e:
        print(f"Error writing log {log_filepath}: {e}")

def get_existing_files(outdir):
    """Lấy danh sách tất cả file .txt trong thư mục đầu ra và lưu vào set."""
    try:
        os.makedirs(outdir, exist_ok=True)
        return set(f for f in os.listdir(outdir) if f.endswith('.txt'))
    except Exception as e:
        print(f"Error listing files in {outdir}: {e}")
        return set()

# Downloader interface
class Downloader(ABC):
    @abstractmethod
    def get_chapter_list(self, index_url):
        pass

    @abstractmethod
    def download_chapter(self, link, idx, total, outdir, existing_files):
        pass

    def stop(self):
        pass

# Piaotia Downloader
class PiaotiaDownloader(Downloader):
    def get_chapter_list(self, index_url):
        try:
            resp = session.get(index_url, timeout=15)
            if resp.status_code != 200:
                raise Exception(f"Index page returned status {resp.status_code}: {index_url}")
            html = resp.content.decode(resp.apparent_encoding or 'utf-8', errors='ignore')
            soup = BeautifulSoup(html, 'html.parser')
            # Xác định base đầy đủ đến phần /a/b/, ví dụ: https://www.piaotia.com/html/8/8973/
            parsed = urlparse(index_url)
            path_parts = parsed.path.strip('/').split('/')
            if len(path_parts) < 3 or path_parts[0] != 'html' or not path_parts[1].isdigit() or not path_parts[2].isdigit():
                raise Exception(f"Invalid index URL format: {index_url}")
            base = f"{parsed.scheme}://{parsed.netloc}/{'/'.join(path_parts[:3])}/"
            seen, chapters = set(), []
            # Xử lý các thẻ <a>
            for a in soup.find_all('a', href=True):
                href = a['href'].strip()
                if not href.endswith('.html') or 'index.html' in href:
                    continue
                # Nếu href chỉ là số chương (e.g., "5863772.html"), nối trực tiếp vào base
                if re.match(r'^\d+\.html$', href):
                    link = urljoin(base, href)
                else:
                    # Nếu href có dạng "8973/5863772.html", dùng urljoin với index_url
                    link = urljoin(index_url, href)
                # Loại bỏ base URL hoặc index_url khỏi danh sách chương
                if link.rstrip('/') in (index_url.rstrip('/'), base.rstrip('/')):
                    continue
                # Đảm bảo link có định dạng html/a/b/c.html
                link_parts = urlparse(link).path.strip('/').split('/')
                if len(link_parts) != 4 or link_parts[0] != 'html' or not link_parts[3].endswith('.html'):
                    continue
                if link not in seen:
                    seen.add(link)
                    chapters.append(link)
            # Xử lý href từ regex
            for m in re.finditer(r'href=["\'](\d+\.html)["\']', html):
                href = m.group(1)
                link = urljoin(base, href)
                if link.rstrip('/') in (index_url.rstrip('/'), base.rstrip('/')):
                    continue
                link_parts = urlparse(link).path.strip('/').split('/')
                if len(link_parts) != 4 or link_parts[0] != 'html' or not link_parts[3].endswith('.html'):
                    continue
                if link not in seen:
                    seen.add(link)
                    chapters.append(link)
            chapters.sort(key=lambda u: int(os.path.basename(u).split('.')[0]))
            # Validate a sample chapter link
            if chapters:
                test_link = chapters[0]
                test_resp = session.head(test_link, timeout=5)
                if test_resp.status_code != 200:
                    raise Exception(f"Sample chapter link invalid (status {test_resp.status_code}): {test_link}")
            return chapters
        except Exception as e:
            raise Exception(f"Piaotia get_chapter_list failed: {e}")

    def download_chapter(self, link, idx, total, outdir, existing_files):
        num = os.path.basename(link).split('.')[0]
        fname = f"C{idx:06d}_{num}.txt"
        if fname in existing_files:
            return f"Skipping existing: {fname}", None
        try:
            resp = session.get(link, timeout=15)
            if resp.status_code != 200:
                raise Exception(f"Chapter returned status {resp.status_code}: {link}")
            html = resp.content.decode(resp.apparent_encoding or 'utf-8', errors='ignore')
            for marker in ['<!-- 翻页上AD开始 -->', '<center></center>']:
                if marker in html:
                    html = html.split(marker)[0]
                    break
            soup = BeautifulSoup(html, 'html.parser')
            h1 = soup.find('h1')
            if not h1:
                raise Exception(f"No chapter title found in {link}")
            if h1.find('a'):
                book = h1.find('a').get_text(strip=True)
                full = h1.get_text(' ', strip=True)
                title = full.split(book, 1)[-1].strip()
            else:
                title = h1.get_text(strip=True) or num
            idx_br = html.find('<br')
            if idx_br == -1:
                raise Exception(f"No chapter content found in {link}")
            content_html = html[idx_br:]
            content_html = re.sub(r'<br\s*/?>', '\n', content_html)
            text = BeautifulSoup(content_html, 'html.parser').get_text()
            lines = [line.lstrip() for line in text.splitlines()]
            while lines and not lines[0]:
                lines.pop(0)
            while lines and not lines[-1]:
                lines.pop()
            if not lines:
                raise Exception(f"Chapter content is empty in {link}")
            content = '\n'.join(lines)
            with open(os.path.join(outdir, fname), 'w', encoding=SAVE_ENCODING) as f:
                f.write(title + '\n\n' + content)
            return f"[{idx}/{total}] Saved: {fname}", None
        except Exception as e:
            return f"Error downloading chapter {num}: {e}", e

# Uukanshu Downloader
class UukanshuDownloader(Downloader):
    def __init__(self):
        self.driver = None
        self.parser = 'lxml' if 'lxml' in sys.modules else 'html.parser'

    def initialize_driver(self):
        if not SELENIUM_AVAILABLE:
            raise Exception("undetected_chromedriver not available")
        options = uc.options.ChromeOptions()
        options.add_argument('--disable-gpu')
        options.add_argument('--no-sandbox')
        options.add_argument('--disable-dev-shm-usage')
        self.driver = uc.Chrome(options=options)
        self.driver.set_page_load_timeout(45)

    def get_chapter_list(self, index_url):
        if not self.driver:
            self.initialize_driver()
        try:
            self.driver.get(index_url)
            time.sleep(10)  # Wait for Cloudflare
            html = self.driver.page_source
            if "Cloudflare" in html[:1000]:
                raise Exception("Cloudflare challenge persists")
            soup = BeautifulSoup(html, self.parser)
            link_selector = 'dd > a[href]'
            list_container_selector = '#chapterList'
            link_pattern = re.compile(r'/book/\d+/\d+\.html$', re.IGNORECASE)
            container = soup.select_one(list_container_selector) or soup
            links = container.select(link_selector)
            base = urlunparse((urlparse(index_url).scheme, urlparse(index_url).netloc, '', '', '', ''))
            chapters = []
            seen = set()
            for link in links:
                href = link.get('href', '')
                if link_pattern.search(href) and href not in seen:
                    full_url = urljoin(base, href)
                    chapters.append(full_url)
                    seen.add(href)
            return sorted(chapters, key=lambda u: int(re.search(r'\d+\.html$', u).group().split('.')[0]))
        except Exception as e:
            raise Exception(f"Error fetching index: {e}")

    def download_chapter(self, link, idx, total, outdir, existing_files):
        log_file = os.path.join(outdir, LOG_FILE_NAME)
        downloaded = load_downloaded_log(log_file)
        if link in downloaded:
            return f"Skipping existing: {link}", None
        url_index = re.search(r'\d+\.html$', link)
        url_index = url_index.group().split('.')[0] if url_index else str(idx)
        fname = f"C{idx:06d}_{url_index}.txt"
        if fname in existing_files:
            return f"Skipping existing: {fname}", None
        try:
            self.driver.get(link)
            time.sleep(random.uniform(0.5, 1.0))
            html = self.driver.page_source
            if "Cloudflare" in html[:1000]:
                return f"Warn: Cloudflare detected at {link}", None
            soup = BeautifulSoup(html, self.parser)
            title_tag = soup.select_one('h1.pt10')
            title = title_tag.get_text(strip=True) if title_tag else f"Chapter {idx}"
            content_box = soup.select_one('div.readcotent')
            if not content_box:
                return f"Warn: Content box not found at {link}", None
            for ad in content_box.select('script, center, div[style*="text-align:center"], a.linkcontent'):
                ad.decompose()
            raw_text = content_box.get_text('\n', strip=True)
            lines = raw_text.splitlines()
            cleaned_lines = []
            unwanted_patterns = [
                r'uu看书', r'uukanshu', r'www\.uukanshu\.com', r'uukanshu\.cc', r'https?://',
                r'最新章节请关注', r'小说.*APP', r'手機用戶請瀏覽', r'm\.uukanshu', r'用戶請瀏覽',
                r'paoshu8', r'pao Shu 8', r'（本章未完，请点击下一页继续阅读）', r'加入书签.*方便阅读',
                r'www\.\.coм', r'Ｍ\.'
            ]
            for line in lines:
                line_stripped = line.strip()
                if not line_stripped or len(line_stripped) < 4:
                    continue
                if any(re.search(p, line_stripped, re.IGNORECASE) for p in unwanted_patterns):
                    continue
                cleaned_lines.append(line_stripped.replace(' ', ' '))
            content = '\n\n'.join(cleaned_lines)
            full_content = f"{title}\n\n{content.strip()}"
            with open(os.path.join(outdir, fname), 'w', encoding=SAVE_ENCODING, errors='replace') as f:
                f.write(full_content)
            log_downloaded_chapter(link, log_file)
            return f"[{idx}/{total}] Saved: {fname}", None
        except Exception as e:
            return f"Error downloading {link}: {e}", e

    def stop(self):
        if self.driver:
            try:
                self.driver.quit()
            except Exception:
                pass
            self.driver = None

# Download Thread
class DownloadThread(QThread):
    progress = pyqtSignal(str)
    finished = pyqtSignal(str, dict)  # Gửi source và item khi hoàn thành

    def __init__(self, item):
        super().__init__()
        self.item = item  # {'url': ..., 'source': ..., 'status': ...}
        self._running = True

    def run(self):
        url, source = self.item['url'], self.item['source']
        self.item['status'] = 'downloading'
        downloader = PiaotiaDownloader() if source == 'piaotia' else UukanshuDownloader()
        self.progress.emit(f"Starting thread for {url} ({source})")
        self.progress.emit(f"Fetching index: {url} ({source})")
        parent, child = get_dirs_from_url(url, source)
        outdir = os.path.join(os.getcwd(), parent, child)
        existing_files = get_existing_files(outdir)
        self.progress.emit(f"Found {len(existing_files)} existing chapters in output directory.")
        try:
            chapters = downloader.get_chapter_list(url)
            total = len(chapters)
            self.progress.emit(f"Found {total} chapters.")
            if len(existing_files) == total:
                self.progress.emit(f"All chapters already downloaded for {url}.")
                self.item['status'] = 'completed'
            else:
                for idx, link in enumerate(chapters, 1):
                    if not self._running:
                        self.progress.emit(f"Stopped downloading {url} ({source})")
                        break
                    msg, error = downloader.download_chapter(link, idx, total, outdir, existing_files)
                    self.progress.emit(msg)
                    if not msg.startswith("Skipping"):
                        time.sleep(random.uniform(0.5, 1.0) if source == 'uukanshu' else 0.5)
                if self._running:
                    self.item['status'] = 'completed'
                    self.progress.emit(f"Completed: {url} ({source})")
                else:
                    self.item['status'] = 'queued'
        except Exception as e:
            self.item['status'] = 'error'
            self.progress.emit(f"Error processing {url}: {e}")
        finally:
            downloader.stop()
        self.finished.emit(source, self.item)

    def stop(self):
        self._running = False

# Main Window
class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Novel Downloader GUI")
        self.resize(800, 600)
        self.all_urls = []  # Lưu tất cả URL và trạng thái
        self.queue = []  # Lưu URL chưa xử lý
        
        # --- BẮT ĐẦU SỬA ĐỔI ---
        self.load_settings() # Tải trạng thái từ lần chạy trước

        # *** THÊM ĐOẠN CODE NÀY ***
        # Reset trạng thái của tất cả các mục về 'queued' khi khởi động ứng dụng
        # Điều này cho phép quét lại hoặc tải lại các mục đã hoàn thành/lỗi
        for item in self.all_urls:
            # Bất kể trạng thái trước đó là gì (completed, error, downloading),
            # đều đặt lại thành 'queued' để sẵn sàng cho lần chạy mới.
            item['status'] = 'queued' 
        # *** KẾT THÚC ĐOẠN CODE THÊM ***

        central = QWidget()
        self.setCentralWidget(central)
        layout = QVBoxLayout(central)
        
        # URL input and source selection
        row = QHBoxLayout()
        self.url_input = QLineEdit()
        self.url_input.setPlaceholderText("Enter index URL (e.g., …/index.html or /book/123/)")
        self.source_combo = QComboBox()
        self.source_combo.addItems(['Piaotia', 'Uukanshu'])
        self.source_combo.setEnabled(SELENIUM_AVAILABLE)
        btn_add = QPushButton("Add to Queue")
        btn_add.clicked.connect(self.add_to_queue)
        row.addWidget(self.url_input)
        row.addWidget(self.source_combo)
        row.addWidget(btn_add)
        layout.addLayout(row)
        
        # Queue list
        self.list_widget = QListWidget()
        self.list_widget.setSelectionMode(QAbstractItemView.SingleSelection)
        layout.addWidget(self.list_widget)
        
        # Queue controls
        ctrl = QHBoxLayout()
        for name, fn in [("Up", self.move_up), ("Down", self.move_down), ("Remove", self.remove_item)]:
            b = QPushButton(name)
            b.clicked.connect(fn)
            ctrl.addWidget(b)
        layout.addLayout(ctrl)
        
        # Start/Stop buttons
        run = QHBoxLayout()
        self.btn_start = QPushButton("Start Download")
        self.btn_stop = QPushButton("Stop")
        self.btn_stop.setEnabled(False)
        self.btn_start.clicked.connect(self.start_download)
        self.btn_stop.clicked.connect(self.stop_download)
        run.addWidget(self.btn_start)
        run.addWidget(self.btn_stop)
        layout.addLayout(run)
        
        # Log area
        self.log = QTextEdit()
        self.log.setReadOnly(True)
        layout.addWidget(self.log)
        
        # Status bar
        self.status = QStatusBar()
        self.setStatusBar(self.status)
        
        # Thread management
        self.piaotia_thread = None
        self.uukanshu_thread = None
        
        # Populate queue list widget VÀ build initial processing queue
        # Đảm bảo queue bắt đầu trống trước khi thêm lại
        self.queue = [] 
        for item in self.all_urls:
            # Trạng thái đã được reset thành 'queued' ở trên
            status = item.get('status', 'queued') # Vẫn lấy status (giờ luôn là 'queued')
            self.list_widget.addItem(f"{item['url']} ({item['source']}) [{status}]")
            # Vì status luôn là 'queued' sau khi reset, tất cả item sẽ được thêm vào queue xử lý
            if status == 'queued': 
                self.queue.append(item) 
        if not SELENIUM_AVAILABLE:
            self.log.append("Warning: Uukanshu support disabled (undetected_chromedriver not found).")

    def add_to_queue(self):
        url = self.url_input.text().strip()
        source = self.source_combo.currentText().lower()
        if not url:
            self.update_status("Please enter a URL.")
            return
        if any(item['url'] == url for item in self.all_urls):
            QMessageBox.warning(self, "Warning", "URL already in queue.")
            return
        if source == 'uukanshu' and not SELENIUM_AVAILABLE:
            QMessageBox.warning(self, "Warning", "Uukanshu support requires undetected_chromedriver.")
            return
        # Khi thêm mới, trạng thái mặc định là 'queued'
        item = {'url': url, 'source': source, 'status': 'queued'}
        self.all_urls.append(item)
        # Thêm vào cả queue xử lý và hiển thị trên list_widget
        self.queue.append(item) 
        self.list_widget.addItem(f"{url} ({source}) [queued]") 
        self.save_settings()
        self.update_status(f"Added to queue: {url} ({source})")

    def move_up(self):
        row = self.list_widget.currentRow()
        if row > 0:
            self.all_urls[row], self.all_urls[row-1] = self.all_urls[row-1], self.all_urls[row]
            item = self.list_widget.takeItem(row)
            self.list_widget.insertItem(row-1, item)
            self.list_widget.setCurrentRow(row-1)
            self._rebuild_queue()
            self.save_settings()

    def move_down(self):
        row = self.list_widget.currentRow()
        if row < self.list_widget.count() - 1 and row != -1:
            self.all_urls[row], self.all_urls[row+1] = self.all_urls[row+1], self.all_urls[row]
            item = self.list_widget.takeItem(row)
            self.list_widget.insertItem(row+1, item)
            self.list_widget.setCurrentRow(row+1)
            self._rebuild_queue()
            self.save_settings()

    def remove_item(self):
        row = self.list_widget.currentRow()
        if row != -1:
            removed = self.all_urls.pop(row)
            self.list_widget.takeItem(row)
            self._rebuild_queue()
            self.save_settings()
            self.update_status(f"Removed: {removed['url']} ({removed['source']})")

    def _rebuild_queue(self):
        """Xây dựng lại self.queue từ self.all_urls, chỉ bao gồm các URL CÓ TRẠNG THÁI 'queued'."""
        # Mặc dù sau khi reset tất cả đều là 'queued', nhưng hàm này có thể được gọi sau khi stop,
        # nên vẫn cần lọc theo trạng thái 'queued'.
        self.queue = [item for item in self.all_urls if item.get('status', 'queued') == 'queued'] 

    def start_download(self):
        if not self.queue:
            self.update_status("No queued URLs to download.")
            return
        if self.piaotia_thread or self.uukanshu_thread:
            self.update_status("Download already in progress.")
            return
        self.btn_start.setEnabled(False)
        self.btn_stop.setEnabled(True)
        self.log.clear()
        self.update_status("Starting download...")
        self._start_next_threads()

    def _start_next_threads(self):
        # Start Piaotia thread if none running and Piaotia URL exists
        if not self.piaotia_thread:
            for item in self.queue:
                if item['source'] == 'piaotia':
                    self.queue.remove(item)
                    row = next(i for i, it in enumerate(self.all_urls) if it['url'] == item['url'])
                    self.list_widget.takeItem(row)
                    self.list_widget.insertItem(row, f"{item['url']} ({item['source']}) [downloading]")
                    self.piaotia_thread = DownloadThread(item)
                    self.piaotia_thread.progress.connect(self.update_status)
                    self.piaotia_thread.finished.connect(self._thread_finished)
                    self.piaotia_thread.start()
                    self.update_status(f"Piaotia thread started for {item['url']}")
                    break

        # Start Uukanshu thread if none running and Uukanshu URL exists
        if not self.uukanshu_thread:
            for item in self.queue:
                if item['source'] == 'uukanshu':
                    self.queue.remove(item)
                    row = next(i for i, it in enumerate(self.all_urls) if it['url'] == item['url'])
                    self.list_widget.takeItem(row)
                    self.list_widget.insertItem(row, f"{item['url']} ({item['source']}) [downloading]")
                    self.uukanshu_thread = DownloadThread(item)
                    self.uukanshu_thread.progress.connect(self.update_status)
                    self.uukanshu_thread.finished.connect(self._thread_finished)
                    self.uukanshu_thread.start()
                    self.update_status(f"Uukanshu thread started for {item['url']}")
                    break

        # Check if all downloads are done
        if not self.piaotia_thread and not self.uukanshu_thread and not self.queue:
            self.download_finished()

    def _thread_finished(self, source, item):
        # Update list_widget with final status
        row = next(i for i, it in enumerate(self.all_urls) if it['url'] == item['url'])
        self.list_widget.takeItem(row)
        self.list_widget.insertItem(row, f"{item['url']} ({item['source']}) [{item['status']}]")
        
        # Clear the finished thread
        if source == 'piaotia':
            self.piaotia_thread = None
        elif source == 'uukanshu':
            self.uukanshu_thread = None
        
        # Save settings and start next threads
        self.save_settings()
        self._start_next_threads()

    def stop_download(self):
        try:
            if self.piaotia_thread:
                self.piaotia_thread.stop()
                self.piaotia_thread.wait()
                row = next(i for i, item in enumerate(self.all_urls) if item['status'] == 'downloading' and item['source'] == 'piaotia')
                self.all_urls[row]['status'] = 'queued'
                self.queue.append(self.all_urls[row])
                self.list_widget.takeItem(row)
                self.list_widget.insertItem(row, f"{self.all_urls[row]['url']} ({self.all_urls[row]['source']}) [queued]")
                self.piaotia_thread = None
                self.update_status("Piaotia thread stopped.")
            if self.uukanshu_thread:
                self.uukanshu_thread.stop()
                self.uukanshu_thread.wait()
                row = next(i for i, item in enumerate(self.all_urls) if item['status'] == 'downloading' and item['source'] == 'uukanshu')
                self.all_urls[row]['status'] = 'queued'
                self.queue.append(self.all_urls[row])
                self.list_widget.takeItem(row)
                self.list_widget.insertItem(row, f"{self.all_urls[row]['url']} ({self.all_urls[row]['source']}) [queued]")
                self.uukanshu_thread = None
                self.update_status("Uukanshu thread stopped.")
            self.btn_start.setEnabled(True)
            self.btn_stop.setEnabled(False)
            self.update_status("Download stopped.")
        except Exception as e:
            self.update_status(f"Error stopping download: {e}")
        finally:
            self.save_settings()

    def download_finished(self):
        self.update_status("All downloads finished.")
        self.btn_start.setEnabled(True)
        self.btn_stop.setEnabled(False)
        self.save_settings()

    def update_status(self, msg):
        self.log.append(msg)
        self.status.showMessage(msg)

    def load_settings(self):
        try:
            with open(SETTINGS_FILE, 'r', encoding=SAVE_ENCODING) as f:
                self.all_urls = json.load(f).get('urls', [])
        except Exception:
            self.all_urls = []

    def save_settings(self):
        try:
            with open(SETTINGS_FILE, 'w', encoding=SAVE_ENCODING) as f:
                json.dump({'urls': self.all_urls}, f, ensure_ascii=False, indent=2)
        except Exception as e:
            QMessageBox.warning(self, 'Error', f"Failed to save settings: {e}")

    def closeEvent(self, event):
        # Ensure threads are stopped before closing
        self.stop_download()
        self.save_settings()
        super().closeEvent(event)

if __name__ == '__main__':
    app = QApplication(sys.argv)
    app.setStyleSheet(qdarkstyle.load_stylesheet_pyqt5())
    window = MainWindow()
    window.show()
    sys.exit(app.exec_())