# /core/translation_handler.py
import os
import time
import logging
from pathlib import Path
import traceback
import re # Import re for regex operations

# Use absolute imports relative to the project root if running as a package,
# or relative imports if running files directly (adjust based on execution context)
# Assuming running main.py from project root:
from utils.helpers import contains_chinese, split_text
# --- IMPORT DEFAULT CONSTANTS ---
from config_manager import (DEFAULT_PRIMARY_MODEL, DEFAULT_SECONDARY_MODEL,
                            DEFAULT_PROMPT, RETRY_PROMPT, AVAILABLE_MODELS,
                            DEFAULT_ALLOWED_CHINESE_COUNT, DEFAULT_TEMPERATURE,
                            DEFAULT_FINAL_RETRY_MODEL, DEFAULT_REQUEST_TIMEOUT) # Import new default
# -------------------------------

try:
    import google.generativeai as genai
    from google.api_core import exceptions as google_exceptions
except ImportError:
    logging.critical("google-generativeai library not found in translation_handler.")
    raise

logger = logging.getLogger(__name__)

def call_gemini_api(text_chunk, model_name_to_use, prompt_to_use,
                    safety_settings, generation_config,
                    log_func, configure_key_func,
                    temperature=DEFAULT_TEMPERATURE,
                    request_timeout=DEFAULT_REQUEST_TIMEOUT):
    """
    Calls the Gemini API for translation, handling errors and potentially
    triggering key rotation via the provided configure_key_func.
    ALWAYS returns a tuple: (translated_text, error_message).
    """
    logger.debug(f"Calling Gemini API. Model: {model_name_to_use}, Temp: {temperature}, Timeout: {request_timeout}, Chunk: {len(text_chunk)}")
    model = None
    max_api_retries = 2
    api_attempt = 0
    last_error_message = "API call failed without specific error after retries."

    final_generation_config = genai.types.GenerationConfig(
        temperature=temperature
    )

    while api_attempt < max_api_retries:
        api_attempt += 1
        logger.info(f"API Attempt {api_attempt}/{max_api_retries} for chunk: '{text_chunk[:50]}...' with model {model_name_to_use}")
        log_func(f"INFO: Thử gọi API lần {api_attempt}/{max_api_retries} với model {model_name_to_use}", "info")
        try:
            model = genai.GenerativeModel(model_name=model_name_to_use, generation_config=final_generation_config, safety_settings=safety_settings)
            logger.debug("GenerativeModel object created/recreated.")
        except Exception as model_init_e:
            error_msg = f"Lỗi khởi tạo Model ({model_name_to_use}): {model_init_e}"
            log_func(f"ERROR: {error_msg}", "danger")
            logger.error(f"API Fail - Model Init: {error_msg}", exc_info=True)
            last_error_message = error_msg
            log_func(f"WARNING: Lỗi model, đang thử chuyển key...", "warning")
            if configure_key_func():
                logger.info("Switched key on model init error.")
                continue
            else:
                log_func("ERROR: Không còn key sau lỗi model.", "danger")
                logger.error("API Fail: Model init error, no fallback keys.")
                return None, error_msg

        try:
            full_prompt = prompt_to_use.format(text_chunk=text_chunk)
            response = model.generate_content(full_prompt, request_options={'timeout': request_timeout})
            if hasattr(response, 'parts') and response.parts:
                translated_text = response.text
                logger.debug(f"API Success (Att {api_attempt}). Len: {len(translated_text)}")
                if response.prompt_feedback and response.prompt_feedback.block_reason:
                    block_reason = response.prompt_feedback.block_reason
                    block_reason_str = getattr(block_reason, 'name', str(block_reason))
                    logger.warning(f"API Warn: Block reason: {block_reason_str}.")
                    log_func(f"WARNING: Chunk bị chặn bởi filter: {block_reason_str}", "warning")
                return translated_text, None
            elif response.prompt_feedback and response.prompt_feedback.block_reason:
                block_reason = response.prompt_feedback.block_reason
                block_reason_str = getattr(block_reason, 'name', str(block_reason))
                error_msg = f"Blocked by safety filter: {block_reason_str}"
                logger.warning(f"API Blocked (Att {api_attempt}). Reason: {block_reason_str}.")
                log_func(f"WARNING: Prompt bị chặn: {block_reason_str}.", "warning")
                return None, error_msg
            else:
                error_msg = "API no content/error"
                logger.error(f"API Err (Att {api_attempt}): {error_msg}. Resp: {response}.")
                log_func(f"ERROR: API không trả về nội dung.", "danger")
                last_error_message = error_msg
                if api_attempt < max_api_retries:
                    wait_time = 1 * api_attempt
                    logger.info(f"Wait {wait_time}s before retry empty resp...")
                    log_func(f"INFO: Chờ {wait_time}s trước khi thử lại...", "info")
                    time.sleep(wait_time)
                    continue
                else:
                    return None, error_msg
        except google_exceptions.ResourceExhausted as e:
            error_message = f"API Err (Att {api_attempt}): Quota/Rate limit. {e}"
            logger.warning(error_message)
            log_func(f"WARNING: Hết quota/Rate limit. Thử chuyển key.", "warning")
            last_error_message = error_message
            if configure_key_func():
                logger.info("Switched key (ResourceExhausted).")
                continue
            else:
                log_func("ERROR: Không còn key sau lỗi quota.", "danger")
                logger.error("API Fail: Quota exhausted.")
                return None, "Quota exhausted or rate limit hit on all keys"
        except (google_exceptions.InvalidArgument, google_exceptions.PermissionDenied) as e:
            error_type = "Invalid Argument/Permission Denied"
            if isinstance(e, google_exceptions.InvalidArgument) and "api key not valid" in str(e).lower():
                error_type = "API key không hợp lệ"
            elif isinstance(e, google_exceptions.PermissionDenied):
                error_type = "Permission Denied"
            error_message = f"API Err (Att {api_attempt}): {error_type}. {e}"
            logger.error(error_message)
            log_func(f"ERROR: {error_type}. Thử chuyển key.", "danger")
            last_error_message = error_message
            if configure_key_func():
                logger.info(f"Switched key ({error_type}).")
                continue
            else:
                log_func(f"ERROR: Không còn key sau lỗi {error_type}.", "danger")
                logger.error(f"API Fail: {error_type}, no fallback.")
                return None, f"{error_type}, no fallback keys available"
        except google_exceptions.FailedPrecondition as e:
            error_message = f"API Err (Att {api_attempt}): Failed Precondition. {e}"
            logger.error(error_message, exc_info=True)
            log_func(f"ERROR: API Failed Precondition. {e}", "danger")
            return None, error_message
        except google_exceptions.GoogleAPIError as e:
            error_message = f"API Err Chung (Att {api_attempt}): {e}"
            logger.error(error_message, exc_info=True)
            log_func(f"ERROR: Lỗi Google API: {e}", "danger")
            last_error_message = error_message
            if api_attempt < max_api_retries:
                wait_time = 2 ** api_attempt
                logger.info(f"Wait {wait_time}s before retry generic API err...")
                log_func(f"INFO: Chờ {wait_time}s trước khi thử lại...", "info")
                time.sleep(wait_time)
                continue
            else:
                return None, error_message
        except Exception as e:
            error_message = f"Lỗi không xác định API (Att {api_attempt}): {type(e).__name__} - {e}"
            logger.error(error_message, exc_info=True)
            log_func(f"ERROR: Lỗi không xác định API: {e}", "danger")
            last_error_message = error_message
            if api_attempt < max_api_retries:
                wait_time = 2 ** api_attempt
                logger.info(f"Wait {wait_time}s before retry unexpected err...")
                log_func(f"INFO: Chờ {wait_time}s trước khi thử lại...", "info")
                time.sleep(wait_time)
                continue
            else:
                return None, error_message

    final_error_msg = f"Đã đạt số lần thử lại tối đa ({max_api_retries}). Lỗi cuối: {last_error_message}"
    logger.error(f"API Call failed permanently: {final_error_msg} for chunk: '{text_chunk[:50]}...'")
    log_func(f"ERROR: {final_error_msg}", "danger")
    return None, final_error_msg
    # -------------------------

def count_specific_chinese_chars(text):
    """Counts characters within common CJK Unified Ideographs ranges."""
    if not text: return 0
    chinese_pattern = re.compile(r'[\u4e00-\u9fff\u3400-\u4dbf\uF900-\uFAFF]')
    matches = chinese_pattern.findall(text)
    return len(matches)

def format_first_line(text_content, filename):
    """
    Attempts to format the first line of the text content based on the filename.
    Returns the potentially modified text content.
    """
    if not text_content or not filename:
        return text_content # Return original if no content or filename

    lines = text_content.splitlines()
    if not lines:
        return text_content # Return original if no lines

    original_first_line = lines[0]
    line_to_parse = original_first_line.strip()
    existing_title = ""

    # 1. Extract number from filename
    filename_num_pattern = re.compile(r'[Cc](?:hương)?\s*([0-9]+)')
    match_filename = filename_num_pattern.search(filename)
    extracted_number = None
    if match_filename:
        try: extracted_number = int(match_filename.group(1))
        except ValueError: pass

    if extracted_number is None:
        logger.debug(f"FormatFirstLine: No number in filename '{filename}', returning original.")
        return text_content # Cannot format without number

    # 2. Extract title from the *translated* first line
    if not line_to_parse or line_to_parse.startswith("[Lỗi đọc"): # Check for potential read errors passed through
        existing_title = "[Lỗi đọc dòng đầu]"
    else:
        # Try splitting by ':' first, then ','
        parts = line_to_parse.split(':', 1)
        if len(parts) == 2:
            existing_title = parts[1].strip()
        else:
            parts = line_to_parse.split(',', 1)
            if len(parts) == 2:
                existing_title = parts[1].strip()
            else:
                 # If no clear separator, try removing common prefixes BEFORE assigning the whole line
                 prefix_pattern = re.compile(r'^\s*(?:[Qq]uyển|[Cc]hương|[Cc][.:]?)\s*(?:\d+|[\w\s]+)\s*[:;,.-]?\s*')
                 match_prefix = prefix_pattern.match(line_to_parse)
                 if match_prefix:
                     existing_title = line_to_parse[match_prefix.end():].strip()
                 else:
                     existing_title = line_to_parse # Use the whole line if no prefix found

        # Basic cleaning/placeholder for title
        if not existing_title:
            existing_title = "[Không có tiêu đề]"

    # 3. Construct new first line
    new_first_line = f"Chương {extracted_number}: {existing_title}"

    # 4. Replace if different (using normalized comparison)
    norm_orig = ' '.join(original_first_line.split())
    norm_new = ' '.join(new_first_line.split())

    if norm_new != norm_orig:
        logger.debug(f"Formatting first line for '{filename}': '{original_first_line}' -> '{new_first_line}'")
        lines[0] = new_first_line
        return "\n".join(lines)
    else:
        logger.debug(f"First line of '{filename}' already correctly formatted.")
        return text_content # Return original content if no change needed

def translate_file_task(source_path, target_path, app_state):
    """
    Task to translate a single file. Saves if errors occur based on settings.
    Does NOT clean junk chars from the first line anymore.
    """
    start_time = time.time()
    filename = os.path.basename(source_path)
    logger.info(f"Starting translation task for: {filename}")

    # Access App State
    log_message = app_state.get('log_message')
    configure_next_api_key = app_state.get('configure_next_api_key')
    stop_event = app_state.get('stop_event')
    get_primary_model = app_state.get('get_primary_model')  # Lấy hàm để truy cập động
    get_secondary_model = app_state.get('get_secondary_model')  # Lấy hàm để truy cập động
    get_final_retry_model = app_state.get('get_final_retry_model')  # Lấy hàm để truy cập động
    prompt = app_state.get('translation_prompt', DEFAULT_PROMPT)
    retry_prompt = app_state.get('retry_prompt', RETRY_PROMPT)
    allowed_chinese_count = app_state.get('allowed_chinese_count', DEFAULT_ALLOWED_CHINESE_COUNT)
    temperature_to_use = app_state.get('temperature', DEFAULT_TEMPERATURE)
    request_timeout = app_state.get('request_timeout', DEFAULT_REQUEST_TIMEOUT)

    # Lấy model động tại thời điểm chạy
    primary_model = get_primary_model()
    secondary_model = get_secondary_model()
    final_retry_model = get_final_retry_model()

    # Validate parameters
    if primary_model not in AVAILABLE_MODELS:
        error_msg = f"Invalid primary_model {primary_model}, not in available models"
        logger.error(error_msg)
        log_message(f"ERROR: {error_msg}", "danger")
        return source_path, False, error_msg
    if secondary_model not in AVAILABLE_MODELS:
        error_msg = f"Invalid secondary_model {secondary_model}, not in available models"
        logger.error(error_msg)
        log_message(f"ERROR: {error_msg}", "danger")
        return source_path, False, error_msg
    if final_retry_model not in AVAILABLE_MODELS:
        error_msg = f"Invalid final_retry_model {final_retry_model}, not in available models"
        logger.error(error_msg)
        log_message(f"ERROR: {error_msg}", "danger")
        return source_path, False, error_msg
    if not (0.0 <= temperature_to_use <= 2.0):
        logger.warning(f"Invalid temperature {temperature_to_use}, using default {DEFAULT_TEMPERATURE}")
        temperature_to_use = DEFAULT_TEMPERATURE
    if not isinstance(allowed_chinese_count, int) or allowed_chinese_count < 0:
        logger.warning(f"Invalid allowed_chinese_count {allowed_chinese_count}, using default {DEFAULT_ALLOWED_CHINESE_COUNT}")
        allowed_chinese_count = DEFAULT_ALLOWED_CHINESE_COUNT
    if not isinstance(request_timeout, (int, float)) or request_timeout <= 0:
        logger.warning(f"Invalid request_timeout {request_timeout}, using default {DEFAULT_REQUEST_TIMEOUT}")
        request_timeout = DEFAULT_REQUEST_TIMEOUT

    # Check essential functions
    if not all([log_message, configure_next_api_key, stop_event, get_primary_model, get_secondary_model, get_final_retry_model]):
        missing = [name for name, val in [
            ('log_message', log_message),
            ('configure_next_api_key', configure_next_api_key),
            ('stop_event', stop_event),
            ('get_primary_model', get_primary_model),
            ('get_secondary_model', get_secondary_model),
            ('get_final_retry_model', get_final_retry_model)
        ] if not val]
        error_msg = f"Lỗi Task: Thiếu app_state: {', '.join(missing)}"
        logger.error(error_msg)
        return source_path, False, error_msg

    log_message(f"INFO: Bắt đầu dịch file: {filename}", "info")

    try:
        # Read Source File
        logger.debug(f"Reading source: {source_path}")
        source_file = Path(source_path)
        original_content = ""
        try:
            if not source_file.is_file():
                raise FileNotFoundError("Source path not file.")
            encodings_to_try = ['utf-8', 'cp1252', 'latin-1', 'gbk']
            read_success = False
            for enc in encodings_to_try:
                try:
                    original_content = source_file.read_text(encoding=enc)
                    logger.debug(f"Read {filename} with {enc}.")
                    read_success = True
                    break
                except UnicodeDecodeError:
                    logger.warning(f"{enc.upper()} decode failed for {filename}.")
            if not read_success:
                raise UnicodeDecodeError("All encodings failed.")
        except FileNotFoundError:
            logger.error(f"Not Found Error: {source_path}")
            log_message(f"ERROR: Không tìm thấy file: {filename}", "danger")
            return source_path, False, "Source file not found"
        except PermissionError:
            logger.error(f"Permission Error read: {source_path}")
            log_message(f"ERROR: Không quyền đọc: {filename}", "danger")
            return source_path, False, "Permission denied reading source"
        except UnicodeDecodeError as e:
            logger.error(f"Encoding Error read {filename}: {e}")
            log_message(f"ERROR: Lỗi encoding đọc {filename}.", "danger")
            return source_path, False, f"Encoding error: {e}"
        except Exception as e:
            logger.error(f"Error read source {filename}: {e}", exc_info=True)
            log_message(f"ERROR: Lỗi đọc nguồn {filename}: {e}", "danger")
            return source_path, False, f"Error reading source: {e}"
        if not original_content.strip():
            logger.info(f"Skipping empty file: {filename}")
            log_message(f"SKIP: File '{filename}' rỗng.", "skip")
            return source_path, True, "Skipped: Empty file"

        # Split into Chunks
        logger.debug(f"Splitting text for {filename}")
        try:
            chunks = split_text(original_content)
            if not chunks:
                logger.warning(f"{filename} zero chunks.")
                log_message(f"WARNING: '{filename}' không có chunk.", "warning")
                return source_path, True, "Skipped: No translatable chunks"
        except Exception as split_e:
            logger.error(f"Error splitting {filename}: {split_e}", exc_info=True)
            log_message(f"ERROR: Lỗi chia chunk {filename}: {split_e}", "danger")
            return source_path, False, f"Error splitting text: {split_e}"

        # Prepare for API Call
        if 'genai' not in globals():
            logger.critical("Genai missing.")
            log_message("ERROR: Lỗi thư viện Gemini.", "danger")
            return source_path, False, "Gemini library missing"
        generation_config_base = genai.types.GenerationConfig()
        safety_settings = [{"category": f"HARM_CATEGORY_{cat}", "threshold": "BLOCK_MEDIUM_AND_ABOVE"} for cat in ["HARASSMENT", "HATE_SPEECH", "SEXUALLY_EXPLICIT", "DANGEROUS_CONTENT"]]

        translated_chunks = []
        translation_error_occurred = False
        total_chunks = len(chunks)
        logger.info(f"Translating {total_chunks} chunks {filename} Temp={temperature_to_use:.2f}")

        # Translate Chunks Loop
        for i, chunk in enumerate(chunks):
            if stop_event.is_set():
                logger.info(f"Stop requested {filename}")
                log_message(f"INFO: Tạm dừng {filename}.", "info")
                return source_path, False, "Stopped by user"
            translated_chunk, err = call_gemini_api(chunk, primary_model, prompt, safety_settings, generation_config_base, log_message, configure_next_api_key, temperature=temperature_to_use, request_timeout=request_timeout)
            if err:
                logger.error(f"Err chunk {i+1}/{total_chunks} {filename} (Pri): {err}")
                log_message(f"ERROR: Lỗi chunk {i+1}/{total_chunks} ({primary_model}): {err}", "danger")
                translation_error_occurred = True
                translated_chunks.append(f"\n--- ERROR CHUNK {i+1}: {err} ---\n")
                continue
            chinese_retry_count = 0
            max_chinese_retries = 2
            chunk_still_has_chinese = contains_chinese(translated_chunk)
            while chunk_still_has_chinese and chinese_retry_count < max_chinese_retries:
                chinese_retry_count += 1
                logger.warning(f"Chinese detected chunk {i+1} {filename}. Retry {chinese_retry_count}/{max_chinese_retries}...")
                log_message(f"WARNING: Ký tự TQ chunk {i+1} {filename}. Retry {chinese_retry_count}...", "warning")
                model_to_use_for_retry = secondary_model
                if chinese_retry_count == max_chinese_retries:
                    model_to_use_for_retry = final_retry_model
                    logger.info(f"Using final retry model '{final_retry_model}' for retry {chinese_retry_count}.")
                    log_message(f"INFO: Dùng model retry cuối '{final_retry_model}'...", "info")
                translated_chunk_retry, err_retry = call_gemini_api(chunk, model_to_use_for_retry, retry_prompt, safety_settings, generation_config_base, log_message, configure_next_api_key, temperature=temperature_to_use, request_timeout=request_timeout)
                if err_retry:
                    logger.error(f"Err retry chunk {i+1} {filename} (Sec): {err_retry}")
                    log_message(f"ERROR: Lỗi retry chunk {i+1} ({model_to_use_for_retry}): {err_retry}", "danger")
                    translation_error_occurred = True
                    break
                else:
                    if not contains_chinese(translated_chunk_retry):
                        logger.info(f"Retry {chinese_retry_count} ok chunk {i+1}.")
                        translated_chunk = translated_chunk_retry
                        chunk_still_has_chinese = False
                        break
                    else:
                        logger.warning(f"Retry {chinese_retry_count} chunk {i+1} still has Chinese.")
                        translated_chunk = translated_chunk_retry
            translated_chunks.append(translated_chunk)

        # Combine and Post-Process
        final_translation = "\n".join(translated_chunks).strip()
        save_file = True
        final_status_message = "Success"
        remaining_chinese_count = 0
        if translation_error_occurred:
            save_file = False
            final_status_message = "Skipped: Translation Error"
            logger.error(f"Task {filename} fail API errors. Skip save.")
            log_message(f"ERROR: Dịch {filename} lỗi API. Không lưu.", "danger")
        else:
            remaining_chinese_count = count_specific_chinese_chars(final_translation)
            logger.info(f"'{filename}': Remaining CN chars = {remaining_chinese_count}")
            if remaining_chinese_count > allowed_chinese_count:
                save_file = False
                final_status_message = f"Skipped: {remaining_chinese_count} CN Chars (>{allowed_chinese_count})"
                logger.warning(f"Task {filename} {remaining_chinese_count} CN chars remain (>{allowed_chinese_count}). Skip save.")
                log_message(f"WARNING: Chương {filename} còn {remaining_chinese_count} ký tự TQ (>{allowed_chinese_count}). Không lưu.", "warning")
            elif remaining_chinese_count > 0:
                final_status_message = f"Success (with {remaining_chinese_count} CN chars)"
                logger.warning(f"Saving {filename} despite {remaining_chinese_count} CN chars (<={allowed_chinese_count}).")
                log_message(f"WARNING: Lưu {filename} dù còn {remaining_chinese_count} ký tự TQ (<={allowed_chinese_count}).", "warning")

        # Write Output File
        if save_file:
            target_file = Path(target_path)
            logger.debug(f"Prep write: {target_path}")
            try:
                target_file.parent.mkdir(parents=True, exist_ok=True)
                target_file.write_text(final_translation, encoding='utf-8')
                logger.info(f"Success saved {filename} ({final_status_message})")
                log_level = "success" if remaining_chinese_count == 0 else "warning"
                log_message(f"{log_level.upper()}: Đã dịch và lưu: {filename} ({final_status_message})", log_level)
            except PermissionError:
                logger.error(f"Permission Error write: {target_path}")
                log_message(f"ERROR: Không quyền ghi: {filename}", "danger")
                return source_path, False, "Permission denied writing target"
            except OSError as e:
                logger.error(f"OS Error write {filename}: {e}", exc_info=True)
                log_message(f"ERROR: Lỗi OS ghi {filename}: {e}", "danger")
                return source_path, False, f"OS error writing target: {e}"
            except Exception as e:
                logger.error(f"Error write {filename}: {e}", exc_info=True)
                log_message(f"ERROR: Lỗi ghi {filename}: {e}", "danger")
                return source_path, False, f"Error writing target: {e}"
        else:
            logger.info(f"Skipped save {filename} due to status: {final_status_message}")

        end_time = time.time()
        duration = end_time - start_time
        logger.info(f"Finished task {filename} in {duration:.2f}s. Status: {final_status_message}")
        task_success = save_file or final_status_message in ["Skipped: Empty file", "Skipped: No translatable chunks"]
        return source_path, task_success, final_status_message

    except Exception as e:
        filename_local = os.path.basename(source_path)
        tb_str = traceback.format_exc()
        logger.critical(f"Unexpected critical error task {filename_local}: {e}\n{tb_str}")
        if 'log_message' in locals() and callable(log_message):
            log_message(f"CRITICAL ERROR: Lỗi file {filename_local}: {e}", "danger")
        else:
            logger.critical(f"CRITICAL ERROR task (log unavailable): {e}\n{tb_str}")
        return source_path, False, f"Unexpected task error: {e}"