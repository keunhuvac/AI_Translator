import os
import re
import tkinter as tk
from tkinter import filedialog, messagebox, ttk, simpledialog
import pandas as pd


def load_dictionary(path):
    if not os.path.isfile(path):
        return {}
    df = pd.read_csv(path)
    return dict(zip(df['find'], df['replace'].fillna('')))


def save_csv_header_lines(directory, output_path):
    rows = []
    for filename in os.listdir(directory):
        if filename.endswith(".txt"):
            filepath = os.path.join(directory, filename)
            with open(filepath, 'r', encoding='utf-8') as f:
                first_line = f.readline().strip()
                rows.append({'filename': filename, 'header': first_line})
    pd.DataFrame(rows).to_csv(output_path, index=False, encoding='utf-8-sig')


def apply_replacements(text, dictionary, only_first_line=False):
    lines = text.splitlines()
    if only_first_line and lines:
        lines[0] = replace_line(lines[0], dictionary)
    else:
        lines = [replace_line(line, dictionary) for line in lines]
    return '\n'.join(lines)


def replace_line(line, dictionary):
    for k, v in dictionary.items():
        line = line.replace(k, v)
    return line


def remove_empty_first_lines(filepath):
    with open(filepath, 'r', encoding='utf-8') as f:
        lines = f.readlines()
    while lines and lines[0].strip() == '':
        lines.pop(0)
    with open(filepath, 'w', encoding='utf-8') as f:
        f.writelines(lines)


def delete_first_line_by_excel(directory, excel_path):
    df = pd.read_excel(excel_path)
    for fname in df.iloc[:, 0].dropna():
        path = os.path.join(directory, fname)
        if os.path.isfile(path):
            with open(path, 'r', encoding='utf-8') as f:
                lines = f.readlines()
            with open(path, 'w', encoding='utf-8') as f:
                f.writelines(lines[1:])


def contains_chinese(text):
    return re.findall(r'[\u4e00-\u9fff]', text)


class TextToolApp:
    def __init__(self, root):
        self.root = root
        self.root.title("Text File Tool")

        self.directory = ""
        self.dict_path = ""

        self.var_only_first_line = tk.BooleanVar()
        self.var_remove_empty_first = tk.BooleanVar()

        self.create_widgets()

    def create_widgets(self):
        frame = tk.Frame(self.root)
        frame.pack(padx=10, pady=10)

        tk.Button(frame, text="Chọn Thư Mục", command=self.select_directory).grid(row=0, column=0)
        tk.Button(frame, text="Chọn Từ Điển CSV", command=self.select_dict).grid(row=0, column=1)

        tk.Checkbutton(frame, text="Chỉ thay dòng đầu", variable=self.var_only_first_line).grid(row=1, column=0, sticky='w')
        tk.Checkbutton(frame, text="Xóa dòng đầu nếu là dòng trắng", variable=self.var_remove_empty_first).grid(row=1, column=1, sticky='w')

        tk.Button(frame, text="Tìm & Thay theo từ điển", command=self.replace_all).grid(row=2, column=0, pady=5)
        tk.Button(frame, text="Xuất dòng đầu ra CSV", command=self.export_headers).grid(row=2, column=1, pady=5)
        tk.Button(frame, text="Xóa dòng đầu theo Excel", command=self.delete_by_excel).grid(row=3, column=0, pady=5)
        tk.Button(frame, text="Chỉnh sửa Từ Điển", command=self.edit_dictionary).grid(row=3, column=1, pady=5)
        tk.Button(frame, text="Kiểm tra ký tự Trung Quốc", command=self.check_chinese_chars).grid(row=4, column=0, columnspan=2, pady=5)

        manual_frame = tk.LabelFrame(self.root, text="Tìm và thay cụm từ bất kỳ")
        manual_frame.pack(fill='x', padx=10, pady=5)

        tk.Label(manual_frame, text="Tìm: ").grid(row=0, column=0)
        self.entry_find = tk.Entry(manual_frame, width=30)
        self.entry_find.grid(row=0, column=1, padx=5)

        tk.Label(manual_frame, text="Thay bằng: ").grid(row=0, column=2)
        self.entry_replace = tk.Entry(manual_frame, width=30)
        self.entry_replace.grid(row=0, column=3, padx=5)

        tk.Button(manual_frame, text="Thay thế cụm từ", command=self.manual_replace).grid(row=0, column=4, padx=5)

        self.log_text = tk.Text(self.root, height=10, wrap='word')
        self.log_text.pack(fill='both', padx=10, pady=5)

    def log(self, message):
        self.log_text.insert(tk.END, message + "\n")
        self.log_text.see(tk.END)

    def select_directory(self):
        self.directory = filedialog.askdirectory()
        messagebox.showinfo("Thư mục đã chọn", self.directory)

    def select_dict(self):
        self.dict_path = filedialog.askopenfilename(filetypes=[("CSV files", "*.csv")])
        messagebox.showinfo("Từ điển đã chọn", self.dict_path)

    def replace_all(self):
        if not self.directory or not self.dict_path:
            messagebox.showwarning("Lỗi", "Hãy chọn thư mục và từ điển CSV")
            return
        dictionary = load_dictionary(self.dict_path)
        self.log_text.delete('1.0', tk.END)

        for filename in os.listdir(self.directory):
            if filename.endswith(".txt"):
                filepath = os.path.join(self.directory, filename)
                with open(filepath, 'r', encoding='utf-8') as f:
                    content = f.read()
                new_content = apply_replacements(content, dictionary, self.var_only_first_line.get())
                with open(filepath, 'w', encoding='utf-8') as f:
                    f.write(new_content)

                if self.var_remove_empty_first.get():
                    remove_empty_first_lines(filepath)

                self.log(f"Đã xử lý (từ điển): {filename}")

        messagebox.showinfo("Hoàn thành", "Đã thay thế xong tất cả!")

    def manual_replace(self):
        find_text = self.entry_find.get()
        replace_text = self.entry_replace.get()
        if not self.directory or not find_text:
            messagebox.showwarning("Thiếu thông tin", "Hãy nhập cụm từ cần tìm và chọn thư mục")
            return

        self.log_text.delete('1.0', tk.END)
        for filename in os.listdir(self.directory):
            if filename.endswith(".txt"):
                filepath = os.path.join(self.directory, filename)
                with open(filepath, 'r', encoding='utf-8') as f:
                    content = f.read()

                if self.var_only_first_line.get():
                    lines = content.splitlines()
                    if lines:
                        lines[0] = lines[0].replace(find_text, replace_text)
                    new_content = '\n'.join(lines)
                else:
                    new_content = content.replace(find_text, replace_text)

                with open(filepath, 'w', encoding='utf-8') as f:
                    f.write(new_content)

                if self.var_remove_empty_first.get():
                    remove_empty_first_lines(filepath)

                self.log(f"Đã xử lý (thủ công): {filename}")

        messagebox.showinfo("Hoàn thành", "Đã thay thế cụm từ thành công!")

    def export_headers(self):
        output_path = filedialog.asksaveasfilename(defaultextension=".csv", filetypes=[("CSV", "*.csv")])
        if output_path:
            save_csv_header_lines(self.directory, output_path)
            messagebox.showinfo("Hoàn thành", f"Đã lưu ra {output_path}")
            self.log(f"Đã xuất dòng đầu ra CSV: {output_path}")

    def delete_by_excel(self):
        excel_path = filedialog.askopenfilename(filetypes=[("Excel", "*.xlsx *.xls")])
        if excel_path:
            delete_first_line_by_excel(self.directory, excel_path)
            messagebox.showinfo("Hoàn thành", "Đã xóa dòng đầu theo Excel")
            self.log(f"Đã xóa dòng đầu theo file Excel: {excel_path}")

    def edit_dictionary(self):
        if not self.dict_path or not os.path.isfile(self.dict_path):
            messagebox.showwarning("Lỗi", "Chưa chọn hoặc không tìm thấy file từ điển CSV.")
            return

        dict_window = tk.Toplevel(self.root)
        dict_window.title("Chỉnh sửa Từ điển")

        tree = ttk.Treeview(dict_window, columns=('find', 'replace'), show='headings')
        tree.heading('find', text='Find')
        tree.heading('replace', text='Replace')
        tree.pack(fill='both', expand=True)

        try:
            df = pd.read_csv(self.dict_path)
        except Exception as e:
            messagebox.showerror("Lỗi", f"Không đọc được file: {e}")
            dict_window.destroy()
            return

        for _, row in df.iterrows():
            tree.insert('', 'end', values=(row['find'], row['replace'] if pd.notna(row['replace']) else ''))

        btn_frame = tk.Frame(dict_window)
        btn_frame.pack(pady=5)

        def add_entry():
            find = simpledialog.askstring("Thêm từ", "Nhập từ cần tìm:")
            if not find:
                return
            replace = simpledialog.askstring("Thay bằng", "Nhập từ thay thế (bỏ trống để xóa):")
            tree.insert('', 'end', values=(find, replace or ''))

        def delete_selected():
            for item in tree.selection():
                tree.delete(item)

        def save_changes():
            entries = []
            for item in tree.get_children():
                find, replace = tree.item(item)['values']
                entries.append({'find': find, 'replace': replace})
            new_df = pd.DataFrame(entries)
            new_df.to_csv(self.dict_path, index=False)
            messagebox.showinfo("Đã lưu", "Từ điển đã được lưu lại.")
            dict_window.destroy()
            self.log("Đã cập nhật từ điển CSV")

        tk.Button(btn_frame, text="Thêm", command=add_entry).grid(row=0, column=0, padx=5)
        tk.Button(btn_frame, text="Xóa", command=delete_selected).grid(row=0, column=1, padx=5)
        tk.Button(btn_frame, text="Lưu", command=save_changes).grid(row=0, column=2, padx=5)

    def check_chinese_chars(self):
        if not self.directory:
            messagebox.showwarning("Thiếu thư mục", "Hãy chọn thư mục chứa các file")
            return

        result_window = tk.Toplevel(self.root)
        result_window.title("Danh sách file chứa ký tự Trung Quốc")

        tree = ttk.Treeview(result_window, columns=('filename', 'count'), show='headings')
        tree.heading('filename', text='Tên File')
        tree.heading('count', text='Số ký tự Trung Quốc')
        tree.pack(fill='both', expand=True)

        for filename in os.listdir(self.directory):
            if filename.endswith(".txt"):
                path = os.path.join(self.directory, filename)
                with open(path, 'r', encoding='utf-8') as f:
                    content = f.read()
                chinese_chars = contains_chinese(content)
                if chinese_chars:
                    tree.insert('', 'end', values=(filename, len(chinese_chars)))

        def open_file():
            selected = tree.selection()
            if not selected:
                return
            filename = tree.item(selected[0])['values'][0]
            path = os.path.join(self.directory, filename)
            with open(path, 'r', encoding='utf-8') as f:
                content = f.read()

            view_window = tk.Toplevel(result_window)
            view_window.title(f"Xem: {filename}")

            text_widget = tk.Text(view_window, wrap='word')
            text_widget.pack(fill='both', expand=True)

            text_widget.insert(tk.END, content)
            for match in re.finditer(r'[\u4e00-\u9fff]', content):
                start = f"1.0+{match.start()}c"
                end = f"1.0+{match.end()}c"
                text_widget.tag_add("highlight", start, end)

            text_widget.tag_config("highlight", background="yellow", foreground="red")

        tk.Button(result_window, text="Xem nội dung", command=open_file).pack(pady=5)


if __name__ == "__main__":
    root = tk.Tk()
    app = TextToolApp(root)
    root.mainloop()
