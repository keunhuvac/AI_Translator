#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Standalone GUI Downloader for m.20xs.org
Separate Scan and Download Tasks - Handles Split Chapters during Download
Allows loading existing scan files.
"""
import sys
import os
import re
import time
import random
import json
from urllib.parse import urljoin, urlparse, urlunparse

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
from bs4 import BeautifulSoup
import warnings

from PyQt5.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QLineEdit, QPushButton, QTextEdit, QStatusBar, QMessageBox, QLabel,
    QFileDialog
)
from PyQt5.QtCore import QThread, pyqtSignal, Qt
import qdarkstyle # Optional styling

# Suppress BeautifulSoup warnings
warnings.filterwarnings("ignore", category=UserWarning, module='bs4')

# --- Constants ---
SAVE_ENCODING = 'utf-8'
MAX_CHAPTERS_SCAN = 20000
BASE_URL_PATTERN = r"https?://m\.20xs\.org"
DEFAULT_DELAY_SCAN = (0.1, 0.3)
DEFAULT_DELAY_DOWNLOAD = (0.2, 0.5)
APP_NAME = "20xs.org Downloader (Scan & Download)"
SCAN_RESULTS_DIR = "_scan_results"

# --- HTTP Session Configuration ---
session = requests.Session()
session.headers.update({
    'User-Agent': (
        'Mozilla/5.0 (iPhone; CPU iPhone OS 13_5 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/13.1.1 Mobile/15E148 Safari/604.1'
    ),
    'Referer': 'https://m.20xs.org/',
    'Accept-Language': 'en-US,en;q=0.9,vi-VN;q=0.8,vi;q=0.7',
    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8'
})
retries = Retry(total=5, backoff_factor=0.6, status_forcelist=[429, 500, 502, 503, 504])
adapter = HTTPAdapter(max_retries=retries)
session.mount('https://', adapter)
session.mount('http://', adapter)

# --- Helper Functions ---
def sanitize_filename(s):
    return ''.join(c if c.isalnum() or c in ' -_()' or '\u4e00' <= c <= '\u9fff' else '_' for c in s).strip('_').strip()

def get_book_id_from_url(url):
    try:
        parsed = urlparse(url)
        parts = parsed.path.strip('/').split('/')
        if len(parts) >= 1 and parts[0].isdigit(): return parts[0]
    except Exception: pass
    return None

def get_dirs_from_book_id(book_id):
    if not book_id: return "m.20xs.org", "20xs_unknown"
    site_name = "m.20xs.org"; safe_book_id_dir = sanitize_filename(f"20xs_book_{book_id}")
    return site_name, safe_book_id_dir

def get_scan_result_filepath(book_id):
    if not book_id: return None
    safe_book_id_file = sanitize_filename(book_id)
    filename = f"_scan_results_{safe_book_id_file}.json"
    return os.path.join(SCAN_RESULTS_DIR, filename)

def get_existing_files(outdir):
    try:
        if not os.path.isdir(outdir): return set()
        return set(f for f in os.listdir(outdir) if f.endswith('.txt'))
    except Exception as e: print(f"Error listing files in {outdir}: {e}"); return set()

def decode_html(response):
    try: return response.content.decode('gbk', errors='strict')
    except UnicodeDecodeError:
        try: return response.content.decode('utf-8', errors='strict')
        except UnicodeDecodeError:
            enc = response.apparent_encoding or 'gbk'; return response.content.decode(enc, errors='ignore')
    except Exception as e: print(f"Error decoding {response.url}: {e}"); return None

# --- Scan Thread ---
class ScanThread(QThread):
    progress = pyqtSignal(str)
    finished = pyqtSignal(bool, str)

    def __init__(self, first_page_or_chapter_url):
        super().__init__()
        self.start_url = first_page_or_chapter_url; self._running = True

    def stop(self): self.progress.emit("[Scan] Stop signal..."); self._running = False

    def run(self):
        all_chapter_urls = []; scan_filepath = None; success = False; book_id = None; base_url = None; total_pages = 0
        try:
            parsed_start = urlparse(self.start_url); base_url = f"{parsed_start.scheme}://{parsed_start.netloc}/"
            book_id = get_book_id_from_url(self.start_url)
            if not book_id: raise ValueError("Cannot determine Book ID.")
            scan_filepath = get_scan_result_filepath(book_id)
            if not scan_filepath: raise ValueError("Cannot generate scan file path.")
            self.progress.emit(f"[Scan] Start Book ID: {book_id}"); self.progress.emit(f"[Scan] Save to: {scan_filepath}")
            first_page_url = urljoin(base_url, f"/{book_id}_1/"); self.progress.emit(f"[Scan] Accessing: {first_page_url}")
            try:
                resp_page1 = session.get(first_page_url, timeout=15); resp_page1.raise_for_status()
                html_page1 = decode_html(resp_page1);
                if not html_page1: raise Exception("Decode fail page 1.")
                soup_page1 = BeautifulSoup(html_page1, 'lxml')
                page_options = soup_page1.select('select option[value*="_"]')
                if not page_options:
                     list_items = soup_page1.find_all('li', attrs={'chapter-id': True})
                     if list_items: total_pages = 1
                     else:
                         chapter_links = soup_page1.select('ul.list li a[href*="/{}/"]'.format(book_id))
                         if chapter_links: total_pages = 1
                         else: raise Exception("Cannot find pages or chapters.")
                else:
                     max_page = 0
                     for option in page_options:
                         match = re.search(rf"/{book_id}_(\d+)/?", option.get('value', ''))
                         if match: max_page = max(max_page, int(match.group(1)))
                     total_pages = max_page
                if total_pages == 0: raise Exception("Cannot get total pages.")
                self.progress.emit(f"[Scan] Found {total_pages} pages.")
            except Exception as e: self.progress.emit(f"[Scan Error] Get pages fail: {e}"); self.finished.emit(False, None); return

            processed_chapters_count = 0; unique_urls = set()
            for page_num in range(1, total_pages + 1):
                if not self._running: self.progress.emit("[Scan] Stopping..."); self.finished.emit(False, None); return
                page_url = urljoin(base_url, f"/{book_id}_{page_num}/"); self.progress.emit(f"[Scan] Page {page_num}/{total_pages}: {page_url}")
                try:
                    delay = random.uniform(*DEFAULT_DELAY_SCAN); time.sleep(delay)
                    resp_page = session.get(page_url, timeout=15); resp_page.raise_for_status()
                    html_page = decode_html(resp_page)
                    if not html_page: self.progress.emit(f"[Scan Warn] Skip page {page_num}: decode fail."); continue
                    soup_page = BeautifulSoup(html_page, 'lxml')
                    chapter_links_on_page = []
                    list_items = soup_page.find_all('li', attrs={'chapter-id': True})
                    selector = 'ul.list li a[href]' if not list_items else None # Fallback selector
                    items_to_check = list_items if list_items else soup_page.select(selector) if selector else []

                    for item in items_to_check:
                         link_tag = item.find('a', href=True) if list_items else item # Find 'a' if item is 'li', else item is 'a'
                         if link_tag:
                              href = link_tag.get('href', '').strip()
                              if href.startswith(f"/{book_id}/") and href.endswith('.html'): chapter_links_on_page.append(href)

                    if not chapter_links_on_page: self.progress.emit(f"[Scan Warn] No links page {page_num}."); continue
                    page_added_count = 0
                    for href in chapter_links_on_page:
                        full_url = urljoin(base_url, href)
                        if full_url not in unique_urls: unique_urls.add(full_url); all_chapter_urls.append(full_url); page_added_count += 1
                    processed_chapters_count += page_added_count
                except requests.exceptions.RequestException as req_err: self.progress.emit(f"[Scan Warn] Skip page {page_num}: Net error {req_err}.")
                except Exception as e: self.progress.emit(f"[Scan Warn] Skip page {page_num}: Error {e}.")

            if not self._running: self.finished.emit(False, None); return
            if all_chapter_urls:
                final_count = len(all_chapter_urls); self.progress.emit(f"[Scan] Finished. Found {final_count} unique URLs.")
                try:
                    os.makedirs(SCAN_RESULTS_DIR, exist_ok=True)
                    def get_chap_id(url): match = re.search(r'/(\d+)(?:_\d+)?\.html$', url); return int(match.group(1).replace('_','')) if match else 0
                    all_chapter_urls.sort(key=get_chap_id)
                    save_data = {'book_id': book_id, 'first_url': self.start_url, 'chapters': all_chapter_urls}
                    with open(scan_filepath, 'w', encoding=SAVE_ENCODING) as f: json.dump(save_data, f, indent=2, ensure_ascii=False)
                    self.progress.emit(f"[Scan] Results saved: {scan_filepath}"); success = True
                except Exception as e: self.progress.emit(f"[Scan Error] Save fail: {e}"); success = False
            else: self.progress.emit("[Scan] No chapters found."); success = False
        except Exception as e: self.progress.emit(f"[Scan Critical Error] {e}"); import traceback; self.progress.emit(traceback.format_exc()); success = False
        finally: self.progress.emit(f"[Scan] === Thread Finish (Success: {success}) ==="); self.finished.emit(success, scan_filepath if success else None)

# --- Download Thread ---
class DownloadThread(QThread):
    progress = pyqtSignal(str)
    finished = pyqtSignal(bool)

    def __init__(self, scan_data):
        super().__init__(); self.scan_data = scan_data; self._running = True; self.current_chapter_parts_content = {}

    def stop(self): self.progress.emit("[Download] Stop signal..."); self._running = False

    def run(self):
        success = True; download_count = 0; error_count = 0; skip_count = 0
        try:
            book_id = self.scan_data.get('book_id'); chapter_urls = self.scan_data.get('chapters', []); total_chapters = len(chapter_urls)
            if not book_id or not chapter_urls: self.progress.emit("[Download Error] Invalid scan data."); self.finished.emit(False); return
            self.progress.emit(f"[Download] Start Book ID: {book_id} ({total_chapters} chapters)")
            site_dir, novel_dir = get_dirs_from_book_id(book_id); base_output_path = os.getcwd()
            output_directory = os.path.join(base_output_path, sanitize_filename(site_dir), sanitize_filename(novel_dir))
            self.progress.emit(f"[Info] Output: {output_directory}"); os.makedirs(output_directory, exist_ok=True)
            existing_files = get_existing_files(output_directory); self.progress.emit(f"[Info] Found {len(existing_files)} existing files.")

            for i, base_url in enumerate(chapter_urls):
                # --- LOGGING THÊM ---
                self.progress.emit(f"--- Starting Chapter {i+1}/{total_chapters} (URL: {base_url}) ---")
                # --- HẾT LOGGING ---
                if not self._running: success = False; break
                idx = i + 1; self.current_chapter_parts_content.clear()
                msg, error = self._download_chapter_with_splits(base_url, idx, total_chapters, output_directory, existing_files, book_id)
                # --- LOGGING THÊM ---
                status_log = "ERROR" if error else "Skipped" if "Skipping" in msg else "Success"
                self.progress.emit(f"--- Finished Chapter {idx} ({status_log}) ---")
                # --- HẾT LOGGING ---
                if "Skipping existing" in msg:
                     skip_count += 1
                     if skip_count == 1 or skip_count % 50 == 0 or idx == total_chapters: self.progress.emit(f"[Info] ({skip_count} skipped)...")
                elif error: error_count += 1; self.progress.emit(f"[Download Error] {msg} (Base: {base_url})")
                else: download_count += 1; self.progress.emit(msg)

            if not self._running: final_message = "Download stopped by user."; success = False
            elif error_count > 0: final_message = f"Download finished with {error_count} errors."
            else: final_message = "Download completed successfully."; success = True
            self.progress.emit("-" * 20); self.progress.emit(final_message)
            self.progress.emit(f"Summary: Downloads: {download_count}, Skipped: {skip_count}, Errors: {error_count}")
        except Exception as e: self.progress.emit(f"[Download Critical Error] {e}"); import traceback; self.progress.emit(traceback.format_exc()); success = False
        finally: self.finished.emit(success)

    def _fetch_and_parse_chapter_part(self, part_url, book_id):
        """Fetches, decodes, parses a chapter part. Returns (soup, next_part_url for the SAME chapter)."""
        self.progress.emit(f"    [Fetch Part] Attempting URL: {part_url}") # Giữ log này

        if part_url in self.current_chapter_parts_content:
             self.progress.emit(f"    [Fetch Part] Cache hit for: {part_url}")
             return self.current_chapter_parts_content[part_url]
        if not self._running: return None, None

        try:
            delay = random.uniform(*DEFAULT_DELAY_DOWNLOAD); time.sleep(delay)
            # self.progress.emit(f"    [Fetch Part] Requesting after {delay:.2f}s delay...") # Giảm log nếu muốn
            resp = session.get(part_url, timeout=15)
            # self.progress.emit(f"    [Fetch Part] Received Status {resp.status_code} for {part_url}") # Giảm log nếu muốn
            if resp.status_code == 404: self.progress.emit(f"[Warn] Part 404: {part_url}"); return None, None
            resp.raise_for_status()

            # self.progress.emit(f"    [Fetch Part] Decoding HTML for {part_url}...") # Giảm log nếu muốn
            html_content = decode_html(resp)
            if not html_content: self.progress.emit(f"[Warn] Part decode fail: {part_url}"); return None, None
            # self.progress.emit(f"    [Fetch Part] Parsing HTML for {part_url}...") # Giảm log nếu muốn
            soup = BeautifulSoup(html_content, 'lxml')
            # self.progress.emit(f"    [Fetch Part] HTML parsed. Finding next link...") # Giảm log nếu muốn

            next_part_url = None
            pager_div = soup.find('div', class_='pager')
            if pager_div:
                pager_links = pager_div.find_all('a', href=True)
                if len(pager_links) >= 3:
                    next_link = pager_links[2]; href = next_link['href'].strip(); text = next_link.get_text(strip=True)
                    if href and ('下一页' in text or '下一章' in text):
                        potential_next_url = urljoin(part_url, href)
                        potential_next_path = urlparse(potential_next_url).path

                        # --- LOGIC KIỂM TRA PHẦN TIẾP THEO ---
                        # 1. Trích xuất ID chương gốc từ part_url hiện tại
                        current_match = re.search(rf"/{book_id}/(\d+)(?:_\d+)?\.html$", part_url)
                        if current_match:
                            base_chap_id = current_match.group(1) # ID gốc, ví dụ: "20141750"

                            # 2. Kiểm tra xem potential_next_url có cùng book_id và base_chap_id không, và có dạng _X không
                            next_match = re.search(rf"/{book_id}/{base_chap_id}_(\d+)\.html$", potential_next_path)
                            if next_match:
                                # Nó là một phần tiếp theo (_X) của cùng chương gốc
                                next_part_index = int(next_match.group(1))
                                # Có thể thêm kiểm tra index > index hiện tại nếu cần, nhưng thường không cần thiết
                                next_part_url = potential_next_url
                                self.progress.emit(f"    [Fetch Part] Valid next part ({base_chap_id}_{next_part_index}) found: {next_part_url}")
                            # else: # In ra nếu link next không khớp định dạng _X
                            #     self.progress.emit(f"    [Fetch Part] Next link '{potential_next_path}' is not a split part of '{base_chap_id}'.")
                        # else: # Không trích xuất được ID gốc từ URL hiện tại (lỗi?)
                        #      self.progress.emit(f"    [Fetch Part] Warning: Could not extract base chapter ID from current part URL: {part_url}")
                        # --- KẾT THÚC LOGIC KIỂM TRA ---

            # if not next_part_url: self.progress.emit(f"    [Fetch Part] No valid *next split part* link found.") # Cập nhật log

            result = (soup, next_part_url); self.current_chapter_parts_content[part_url] = result; return result
        except requests.exceptions.RequestException as req_err: self.progress.emit(f"    [Fetch Part] Network Error: {req_err}"); return None, None
        except Exception as e: self.progress.emit(f"    [Fetch Part] Unexpected Error: {e}"); import traceback; self.progress.emit(traceback.format_exc()); return None, None

    def _extract_content_from_soup(self, soup, title):
        """Extracts and cleans content text from soup."""
        # --- LOGGING ---
        # self.progress.emit(f"      [Extract Content] Starting extraction...") # Optional, can be noisy
        # ---
        content_div = soup.find('div', id='booktxt') or soup.find('div', class_='content')
        if not content_div:
             # --- LOGGING ---
             self.progress.emit(f"      [Extract Content] Error: Content div not found.")
             # ---
             return ""
        # --- LOGGING ---
        # self.progress.emit(f"      [Extract Content] Content div found. Cleaning junk...")
        # ---
        for junk in content_div.select('script, ins, iframe, center, div[style*="display:none"]'): junk.decompose()
        for br in content_div.find_all('br'): br.replace_with('\n')
        # --- LOGGING ---
        # self.progress.emit(f"      [Extract Content] Getting text...")
        # ---
        text = content_div.get_text(separator='\n', strip=True); lines = text.splitlines(); cleaned = []
        unwanted = [r'm?\.?20xs\.org', r'二十小说', r'最新网址', r'章节错误.*点此举报', r'记住网址', r'加入书签', r'推荐本书', r'返回目录', r'上一页', r'下一页', r'温馨提示', r'重要提示', r'（本章未完.*点击下一页）', r'^\s*天才一秒记住.*', ]
        title_clean = title.strip() if title else ""
        temp = []
        # --- LOGGING ---
        # self.progress.emit(f"      [Extract Content] Cleaning {len(lines)} lines...")
        # ---
        for line in lines:
            line = line.strip()
            if not line or (title_clean and line == title_clean): continue
            if any(re.search(p, line, re.IGNORECASE) for p in unwanted): continue
            temp.append(line.replace(' ', ' '))
        # --- LOGGING ---
        # self.progress.emit(f"      [Extract Content] Finished cleaning. Result length: {len(temp)} lines.")
        # ---
        return '\n'.join(temp) # Return joined text

    def _download_chapter_with_splits(self, base_url, idx, total, outdir, existing_files, book_id):
        """Downloads a chapter, handling potential splits."""
        # --- LOGGING ---
        self.progress.emit(f"    [DL Split] Processing Base URL: {base_url}")
        # ---
        match = re.search(r'/(\d+)(?:_\d+)?\.html$', base_url); base_id = match.group(1) if match else f"idx{idx}"
        fname = f"C{idx:06d}_{base_id}.txt"; fpath = os.path.join(outdir, fname)
        if fname in existing_files:
            # --- LOGGING ---
            # self.progress.emit(f"    [DL Split] File exists: {fname}") # Optional, noisy
            # ---
            return f"Skipping existing: {fname}", None

        parts = []; title = f"Chapter {idx}_{base_id}"; url = base_url; p_idx = 1
        while url and self._running:
             # --- LOGGING ---
             self.progress.emit(f"    [DL Split] Fetching part {p_idx}: {url}")
             # ---
             soup, next_url_found = self._fetch_and_parse_chapter_part(url, book_id)
             if soup:
                # --- LOGGING ---
                self.progress.emit(f"    [DL Split] Part {p_idx} fetched successfully. Extracting content...")
                # ---
                if p_idx == 1:
                    t_tag = soup.find('h1', class_='headline') or soup.find('h1')
                    if t_tag: title = t_tag.get_text(strip=True); self.progress.emit(f"      [Title Found] {title}")

                content = self._extract_content_from_soup(soup, title if p_idx > 1 else None)
                if content:
                     # --- LOGGING ---
                     self.progress.emit(f"      [Content Extracted] Part {p_idx} length: {len(content)} chars.")
                     # ---
                     parts.append(content)
                else:
                     self.progress.emit(f"      [Content Warning] Part {p_idx} content empty after cleaning.")

                url = next_url_found # Move to next part or None
                p_idx += 1
             else:
                 # --- LOGGING ---
                 self.progress.emit(f"    [DL Split] Failed to fetch/parse part {p_idx}. Stopping processing for this chapter.")
                 # ---
                 url = None # Stop loop for this chapter

        # --- Sau vòng lặp while ---
        # --- LOGGING ---
        self.progress.emit(f"    [DL Split] Finished fetching parts. Total parts processed: {p_idx - 1}. Combining content...")
        # ---

        if not self._running: return "Stopped during processing", True
        if not parts: existing_files.add(fname); self.progress.emit(f"    [DL Split] Error: No content parts found for {base_id}."); return f"No content for {base_id}", True

        raw = '\n\n'.join(parts).strip(); lines = raw.splitlines()
        # --- LOGGING ---
        # self.progress.emit(f"    [DL Split] Combined content length: {len(raw)} chars, {len(lines)} lines.")
        # ---
        if lines and ".20xs.org" in lines[-1]:
            # --- LOGGING ---
            # self.progress.emit(f"    [DL Split] Removing last line: {lines[-1]}")
            # ---
            cleaned = "\n".join(lines[:-1])
        else: cleaned = "\n".join(lines)

        if not cleaned: existing_files.add(fname); self.progress.emit(f"    [DL Split] Error: Content empty after final clean {base_id}."); return f"Empty after final clean {base_id}", True

        full = f"{title}\n\n{cleaned}\n"
        # --- LOGGING ---
        self.progress.emit(f"    [DL Split] Saving file: {fname}")
        # ---
        try:
            os.makedirs(os.path.dirname(fpath), exist_ok=True);
            with open(fpath, 'w', encoding=SAVE_ENCODING) as f: f.write(full)
            existing_files.add(fname); msg = f"[{idx}/{total}] Saved: {fname}"
            if p_idx > 2: msg += f" ({p_idx - 1} parts)"
            # --- LOGGING ---
            self.progress.emit(f"    [DL Split] File saved successfully.")
            # ---
            return msg, None
        except Exception as e: existing_files.add(fname); self.progress.emit(f"    [DL Split] Error saving file: {e}"); return f"Error saving {fname}: {e}", e

# --- Main GUI Window ---
class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__(); self.setWindowTitle(APP_NAME); self.resize(700, 500)
        self.scan_thread = None; self.download_thread = None; self.last_scanned_book_id = None; self.loaded_scan_data = None
        central = QWidget(); self.setCentralWidget(central); layout = QVBoxLayout(central)
        in_layout = QHBoxLayout(); self.url_label = QLabel("First Chapter URL / Book Index URL:"); self.url_input = QLineEdit()
        self.url_input.setPlaceholderText("https://m.20xs.org/BOOK_ID/CHAPTER_ID.html or /BOOK_ID_1/")
        self.url_input.textChanged.connect(self.update_button_states) # Connect text change
        in_layout.addWidget(self.url_label); in_layout.addWidget(self.url_input); layout.addLayout(in_layout)
        btn_layout = QHBoxLayout(); self.scan_button = QPushButton("Scan Chapters"); self.browse_button = QPushButton("Browse Scan File...")
        self.download_button = QPushButton("Start Download"); self.stop_download_button = QPushButton("Stop Download")
        self.download_button.setEnabled(False); self.stop_download_button.setEnabled(False)
        btn_layout.addWidget(self.scan_button); btn_layout.addWidget(self.browse_button); btn_layout.addWidget(self.download_button); btn_layout.addWidget(self.stop_download_button); layout.addLayout(btn_layout)
        self.log_output = QTextEdit(); self.log_output.setReadOnly(True); layout.addWidget(self.log_output)
        self.status_bar = QStatusBar(); self.setStatusBar(self.status_bar)
        self.scan_button.clicked.connect(self.start_scan); self.browse_button.clicked.connect(self.browse_and_load_scan_file); self.download_button.clicked.connect(self.start_download); self.stop_download_button.clicked.connect(self.stop_download)
        self.update_status("Ready.", 0); self.update_button_states()

    def update_status(self, msg, timeout=3000): self.status_bar.showMessage(msg, timeout)
    def update_log(self, msg): self.log_output.append(msg); sb = self.log_output.verticalScrollBar(); sb.setValue(sb.maximum()); self.update_status(msg.split('\n')[-1])
    def validate_url_for_scan(self, url):
        if not url: QMessageBox.warning(self, "Input Error", "Enter URL."); return None, None
        parsed = urlparse(url)
        if not parsed.scheme or not parsed.netloc or not re.match(BASE_URL_PATTERN, f"{parsed.scheme}://{parsed.netloc}"): QMessageBox.warning(self, "Input Error", f"URL must be from {BASE_URL_PATTERN}."); return None, None
        book_id = get_book_id_from_url(url);
        if not book_id: QMessageBox.warning(self, "Input Error", "Cannot get Book ID."); return None, None
        if not parsed.path.endswith('.html') and not re.match(rf"^/{book_id}(?:_\d+)?/?$", parsed.path): QMessageBox.warning(self, "Input Error", "URL path invalid."); return None, None
        return book_id, url

    def update_button_states(self): # Hàm cập nhật trạng thái nút chung
        # --- SỬA ĐỔI Ở ĐÂY ---
        scan_running = bool(self.scan_thread and self.scan_thread.isRunning())
        download_running = bool(self.download_thread and self.download_thread.isRunning())
        # --- KẾT THÚC SỬA ĐỔI ---
        process_running = scan_running or download_running

        url = self.url_input.text().strip()
        book_id = get_book_id_from_url(url)
        scan_file = get_scan_result_filepath(book_id)
        scan_file_exists = bool(scan_file and os.path.exists(scan_file))
        # Kiểm tra data_loaded cẩn thận hơn, đảm bảo book_id khớp nếu có
        data_loaded = False
        if self.loaded_scan_data and isinstance(self.loaded_scan_data, dict):
             loaded_book_id = self.loaded_scan_data.get('book_id')
             # So sánh ID dưới dạng chuỗi để tránh lỗi type
             if loaded_book_id is not None and book_id is not None and str(loaded_book_id) == str(book_id):
                  data_loaded = True
             elif loaded_book_id is not None and book_id is None: # Data loaded, but no URL input/no book_id from URL
                  data_loaded = True # Allow downloading loaded data even if URL input is empty/different

        can_scan = bool(book_id)
        can_download = scan_file_exists or data_loaded

        self.scan_button.setEnabled(can_scan and not process_running)
        self.browse_button.setEnabled(not process_running) # Luôn bật browse khi không chạy gì
        self.download_button.setEnabled(can_download and not process_running)
        self.stop_download_button.setEnabled(download_running) # Chỉ bật stop khi đang download

    def update_button_states_on_url_change(self):
         self.update_button_states() # Gọi hàm chung

    def start_scan(self):
        if self.scan_thread and self.scan_thread.isRunning(): QMessageBox.warning(self, "Busy", "Scan running."); return
        if self.download_thread and self.download_thread.isRunning(): QMessageBox.warning(self, "Busy", "Download running."); return
        url = self.url_input.text().strip(); book_id, validated_url = self.validate_url_for_scan(url);
        if not book_id: return
        scan_filepath = get_scan_result_filepath(book_id)
        if scan_filepath and os.path.exists(scan_filepath):
             reply = QMessageBox.question(self, "Confirm Overwrite", f"Scan file exists:\n{scan_filepath}\nOverwrite?", QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
             if reply == QMessageBox.No: self.update_log("Scan cancelled."); return
        self.log_output.clear(); self.update_log(f"Starting scan: {validated_url}"); self.update_status("Scanning...")
        self.scan_button.setEnabled(False); self.browse_button.setEnabled(False); self.download_button.setEnabled(False); self.stop_download_button.setEnabled(False)
        self.scan_thread = ScanThread(validated_url); self.scan_thread.progress.connect(self.update_log); self.scan_thread.finished.connect(self.on_scan_finished); self.scan_thread.start()

    def browse_and_load_scan_file(self):
        start_dir = SCAN_RESULTS_DIR if os.path.isdir(SCAN_RESULTS_DIR) else os.getcwd()
        filepath, _ = QFileDialog.getOpenFileName(self, "Select Scan Result File", start_dir, "Scan Results (*_scan_results_*.json);;All Files (*)")
        if filepath:
            self.update_log(f"Loading scan file: {filepath}")
            try:
                with open(filepath, 'r', encoding=SAVE_ENCODING) as f: scan_data = json.load(f)
                if not isinstance(scan_data, dict) or 'book_id' not in scan_data or 'chapters' not in scan_data or not isinstance(scan_data['chapters'], list): raise ValueError("Invalid format.")
                self.loaded_scan_data = scan_data; book_id = scan_data.get('book_id'); self.update_log(f"Loaded Book ID: {book_id}. Found {len(scan_data['chapters'])} chapters.")
                self.update_status("Scan file loaded.", 0); self.last_scanned_book_id = str(book_id)
                # Optionally update URL input to reflect loaded book?
                # Example: Construct a dummy URL for the loaded book ID
                # self.url_input.setText(f"https://m.20xs.org/{book_id}/") # Update input field
                # self.update_button_states() # Update buttons after potentially changing URL input
                self.download_button.setEnabled(True) # Explicitly enable download after successful load

            except Exception as e: self.loaded_scan_data = None; self.download_button.setEnabled(False); QMessageBox.critical(self, "File Error", f"Error reading {filepath}: {e}"); self.update_status("Error loading file.", 0); self.last_scanned_book_id = None
        else: self.update_log("File selection cancelled.")

    def on_scan_finished(self, success, scan_filepath):
        self.scan_thread = None; current_book_id = get_book_id_from_url(self.url_input.text().strip())
        can_interact = bool(current_book_id); self.scan_button.setEnabled(can_interact); self.browse_button.setEnabled(can_interact)
        if success and scan_filepath:
            self.update_log("Scan completed."); self.update_status("Scan complete.", 0); QMessageBox.information(self, "Scan Complete", f"Saved to:\n{scan_filepath}")
            self.download_button.setEnabled(True); self.last_scanned_book_id = current_book_id
            try: # Auto-load data
                 with open(scan_filepath, 'r', encoding=SAVE_ENCODING) as f: self.loaded_scan_data = json.load(f); self.update_log("Results auto-loaded.")
            except Exception as e: self.update_log(f"Warn: Could not auto-load: {e}"); self.loaded_scan_data = None; self.download_button.setEnabled(False)
        else:
            self.update_log("Scan failed/stopped."); self.update_status("Scan failed/stopped.", 0); QMessageBox.warning(self, "Scan Failed", "Scan failed or stopped.")
            scan_file_exists = bool(current_book_id and get_scan_result_filepath(current_book_id) and os.path.exists(get_scan_result_filepath(current_book_id)))
            self.download_button.setEnabled(scan_file_exists); self.last_scanned_book_id = None; self.loaded_scan_data = None
        self.update_button_states() # Ensure correct final state

    def start_download(self):
        if self.download_thread and self.download_thread.isRunning(): QMessageBox.warning(self, "Busy", "Download running."); return
        if self.scan_thread and self.scan_thread.isRunning(): QMessageBox.warning(self, "Busy", "Scan running."); return
        if not self.loaded_scan_data: QMessageBox.warning(self, "No Data", "Load scan file first."); return
        scan_data = self.loaded_scan_data; book_id = scan_data.get('book_id')
        self.update_log(f"Start download Book ID: {book_id} (using loaded data)")
        self.scan_button.setEnabled(False); self.browse_button.setEnabled(False); self.download_button.setEnabled(False); self.stop_download_button.setEnabled(True); self.update_status("Downloading...")
        self.download_thread = DownloadThread(scan_data); self.download_thread.progress.connect(self.update_log); self.download_thread.finished.connect(self.on_download_finished); self.download_thread.start()

    def stop_download(self):
        if self.download_thread and self.download_thread.isRunning(): self.download_thread.stop(); self.update_status("Stop signal sent..."); self.stop_download_button.setEnabled(False)
        else: self.update_log("No download to stop.")

    def on_download_finished(self, success):
        self.download_thread = None; final_message = "Download process finished."
        if success: final_message = "Download completed successfully."; QMessageBox.information(self, "Download Complete", final_message)
        else:
            log_text = self.log_output.toPlainText()
            if "stopped by user" in log_text[-150:]: final_message = "Download stopped by user."; QMessageBox.warning(self, "Download Stopped", final_message)
            else: final_message = "Download finished with errors."; QMessageBox.critical(self, "Download Error", final_message)
        self.update_log(final_message); self.update_status("Ready.", 0)
        self.update_button_states() # Update buttons based on final state

    def closeEvent(self, event):
        running_thread, action = (self.scan_thread, "scan") if self.scan_thread and self.scan_thread.isRunning() else (self.download_thread, "download") if self.download_thread and self.download_thread.isRunning() else (None, "")
        if running_thread:
            reply = QMessageBox.question(self, 'Confirm Exit', f"A {action} process running. Stop & exit?", QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
            if reply == QMessageBox.Yes:
                if action == "scan": running_thread.stop()
                else: self.stop_download()
                running_thread.wait(500); event.accept()
            else: event.ignore()
        else: event.accept()

# --- Main Application Execution ---
if __name__ == '__main__':
    app = QApplication(sys.argv)
    try: app.setStyleSheet(qdarkstyle.load_stylesheet_pyqt5())
    except Exception as e: print(f"Could not apply QDarkStyle: {e}.")
    window = MainWindow()
    window.show()
    sys.exit(app.exec_())