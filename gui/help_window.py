# /gui/help_window.py
import tkinter as tk
from tkinter import ttk, scrolledtext
import logging
from ttkbootstrap import Style

logger = logging.getLogger(__name__)


class HelpWindow(tk.Toplevel):
    """Displays help information."""

    def __init__(self, parent):
        self.parent = parent
        self.window = tk.Toplevel(parent)
        self.window.title("Hướng dẫn sử dụng")
        self.window.geometry("1000x750")
        self.window.transient(parent)
        self.window.wm_attributes("-topmost", False)  # Đảm bảo không luôn ở trên
        # Cấu hình style cho button
        style = Style()
        style.configure('Custom.TButton', font=('TkDefaultFont', 12))
        help_content = """
## AI Novel Translator - Hướng dẫn sử dụng

Chào mừng bạn đến với công cụ dịch truyện AI! Dưới đây là giải thích các chức năng chính:

**I. KHU VỰC CHÍNH:**

*   **Danh sách Thư mục:**
    *   **Tab "Đang xử lý":** Chứa các thư mục truyện gốc (chứa file .txt tiếng Trung) mà bạn muốn dịch.
    *   **Tab "Hoàn thành":** Chứa các thư mục đã được đánh dấu là hoàn thành (thường là sau khi dịch xong).
*   **Các nút điều khiển danh sách (Phía trên danh sách):**
    *   `+` (Thêm thư mục): Mở hộp thoại để chọn thư mục truyện gốc và thêm vào tab "Đang xử lý".
    *   `-` (Xóa thư mục): Xóa các thư mục đã chọn khỏi danh sách ở tab hiện tại (Đang xử lý hoặc Hoàn thành).
    *   `↑` (Di chuyển lên): Di chuyển thư mục được chọn lên trên trong danh sách "Đang xử lý" (thay đổi thứ tự dịch).
    *   `↓` (Di chuyển xuống): Di chuyển thư mục được chọn xuống dưới trong danh sách "Đang xử lý".
    *   `Clr` (Xóa hết DS): Xóa tất cả các thư mục khỏi danh sách "Đang xử lý".
    *   `✓` (Mark Done): Chuyển các thư mục được chọn từ "Đang xử lý" sang "Hoàn thành".
    *   `↩` (Mark Undone): Chuyển các thư mục được chọn từ "Hoàn thành" về lại "Đang xử lý".
*   **Log Theo Dõi:** Hiển thị thông tin trạng thái, tiến trình và lỗi trong quá trình hoạt động.
*   **Các nút hành động chính (Phía dưới danh sách):**
    *   `▶` (Start/Bắt đầu dịch): Bắt đầu quá trình dịch các thư mục trong tab "Đang xử lý". File dịch sẽ được lưu trong thư mục con tên là `translated` bên trong mỗi thư mục gốc.
    *   `⏹` (Stop/Dừng dịch): Yêu cầu dừng quá trình dịch đang chạy (có thể mất một chút thời gian để dừng hoàn toàn).
    *   `📖` (Read/Đọc): Mở cửa sổ đọc cho thư mục đang được chọn trong danh sách (ở tab hiện tại). Cửa sổ này hiển thị song song nội dung file gốc và file đã dịch (nếu có trong thư mục con `translated`).
    *   `📦` (Ebook): Mở công cụ tạo Ebook (.epub) cho thư mục đang được chọn trong tab "Hoàn thành". Công cụ này sẽ quét thư mục con `translated` của thư mục đó.
    *   `✎` (Edit Prompt/Chỉnh sửa prompt): Mở cửa sổ để chỉnh sửa prompt dịch chính (sẽ lưu vào Cài đặt). *Lưu ý: Prompt Retry được sửa trong cửa sổ Cài đặt.*
*   **Tiến độ:**
    *   **Thư mục:** Hiển thị tên thư mục đang xử lý, số file đã dịch / tổng số file nguồn trong thư mục đó, và (Lần thử x/y) nếu đang dịch lại thư mục.
    *   **Session:** Thống kê cho phiên làm việc hiện tại (từ lúc nhấn Start): Số file dịch thành công / Số file đã xử lý (cả lỗi) / Tổng số file cần dịch ban đầu (Thành công/Đã xử lý/Cần dịch) (Thời gian chạy).

**II. CỬA SỔ CÀI ĐẶT:** (Truy cập qua nút "Cài đặt")

*   **Tab "Chung":**
    *   **Giao diện (Theme):** Chọn giao diện màu sắc cho ứng dụng.
    *   **Số luồng dịch tối đa:** Số lượng file được dịch song song. Tăng giá trị này có thể tăng tốc độ nhưng cũng tiêu tốn nhiều tài nguyên và có thể bị giới hạn bởi API key quota/rate limit.
    *   **Ký tự TQ tối đa được phép lưu:** Nếu sau khi dịch và thử lại, số ký tự tiếng Trung còn lại trong file nhỏ hơn hoặc bằng giá trị này, file đó vẫn sẽ được lưu (thay vì bị bỏ qua). Đặt là 0 để yêu cầu loại bỏ hoàn toàn ký tự TQ.
    *   **Số lần dịch lại thư mục:** Nếu một thư mục dịch chưa đủ số file sau lần đầu, ứng dụng sẽ tự động quét và dịch lại các file còn thiếu tối đa số lần được chọn ở đây. (0 = không thử lại).
    *   **Timeout gọi API (giây):** Thời gian tối đa (tính bằng giây) mà ứng dụng sẽ chờ phản hồi từ Google API cho mỗi yêu cầu dịch. Giảm giá trị này có thể giúp thoát khỏi trạng thái chờ đợi nhanh hơn nếu API bị quá tải, nhưng đặt quá thấp có thể gây lỗi timeout không cần thiết.
*   **Tab "Dịch":**
    *   **File API Keys:** Chọn file .txt chứa danh sách các API Key của Google Gemini (mỗi key một dòng). Ứng dụng sẽ tự động xoay vòng key nếu gặp lỗi quota/rate limit hoặc key không hợp lệ.
    *   **Model dịch chính:** Model sử dụng cho lần dịch đầu tiên mỗi file.
    *   **Model retry (lỗi TQ):** Model sử dụng cho các lần thử lại nếu bản dịch đầu còn sót ký tự tiếng Trung (trừ lần cuối).
    *   **Model thử lại cuối (mạnh hơn):** Model sử dụng cho lần thử lại *cuối cùng* nếu các lần trước vẫn còn sót ký tự tiếng Trung. Nên chọn model mạnh hơn (ví dụ: 1.5 Pro) nếu có thể.
    *   **Temperature:** Kiểm soát mức độ "sáng tạo" của AI (0.0 = ít sáng tạo, tuân thủ chặt chẽ; 1.0 = sáng tạo tối đa). Giá trị quanh 0.7 thường cho kết quả cân bằng.
*   **Tab "Prompts":**
    *   Chỉnh sửa nội dung của Prompt dịch chính và Prompt retry. Dùng `{text_chunk}` để chỉ vị trí đoạn văn bản cần dịch sẽ được chèn vào.
*   **Các nút:**
    *   **Đặt lại Mặc định:** Khôi phục tất cả cài đặt về giá trị ban đầu. Cần nhấn "Lưu và Đóng" sau đó để áp dụng.
    *   **Hủy bỏ:** Đóng cửa sổ cài đặt mà không lưu thay đổi.
    *   **Lưu và Đóng:** Lưu tất cả thay đổi cài đặt vào file cấu hình và áp dụng chúng cho phiên làm việc hiện tại.

**III. LƯU Ý:**

*   File cấu hình (`translator_config.json`) và file log lỗi (`translator_log.txt`, `00_dich_loi.txt`) được lưu cùng cấp với file chạy `main.py`.
*   Đảm bảo bạn đã tạo file `your_api_keys.txt` (hoặc tên khác) và chọn nó trong phần Cài đặt.
*   Kết quả dịch được lưu vào thư mục con `translated` bên trong mỗi thư mục truyện gốc.

Chúc bạn dịch truyện vui vẻ!
"""

        self.text_area = scrolledtext.ScrolledText(
            self.window, wrap=tk.WORD, height=20, width=60, state="normal",
            font=('TkDefaultFont', 12)  # Tăng font lên 12
        )
        self.text_area.pack(padx=10, pady=10, fill=tk.BOTH, expand=True)
        self.text_area.insert(tk.END, help_content)
        self.text_area.config(state="disabled")
        # Nút đóng
        close_button = ttk.Button(self.window, text="Đóng", command=self.window.destroy, style='Custom.TButton')
        close_button.pack(pady=5)
        logger.info("Help window opened.")