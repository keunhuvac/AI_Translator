# /gui/widgets.py
import tkinter as tk
from tkinter import ttk
import logging

logger = logging.getLogger(__name__)

class Tooltip:
    def __init__(self, widget, text):
        self.widget = widget
        self.text = text
        self.tooltip = None
        self._enter_id = None
        if self.widget:
            self.widget.bind("<Enter>", self.schedule_tooltip, add='+')
            self.widget.bind("<Leave>", self.cancel_tooltip, add='+')
            self.widget.bind("<ButtonPress>", self.hide_tooltip, add='+')

    def schedule_tooltip(self, event=None):
        self.cancel_tooltip(hide=False)
        self._last_event_x_root = event.x_root if event else self.widget.winfo_rootx() + self.widget.winfo_width() // 2
        self._last_event_y_root = event.y_root if event else self.widget.winfo_rooty() + self.widget.winfo_height()
        self._enter_id = self.widget.after(700, self._display_tooltip)

    def cancel_tooltip(self, event=None, hide=True):
        if self._enter_id:
            try:
                self.widget.after_cancel(self._enter_id)
            except tk.TclError:
                pass
            self._enter_id = None
        if hide:
            self.hide_tooltip()

    def _display_tooltip(self):
        if not self.widget or not self.widget.winfo_exists():
            return
        self.hide_tooltip()
        base_x = getattr(self, '_last_event_x_root', self.widget.winfo_rootx())
        base_y = getattr(self, '_last_event_y_root', self.widget.winfo_rooty() + self.widget.winfo_height()) + 10
        self.tooltip = tk.Toplevel(self.widget)
        self.tooltip.wm_overrideredirect(True)
        self.tooltip.wm_attributes("-topmost", True)
        label = tk.Label(self.tooltip, text=self.text, justify='left',
                         background="#ffffe0", relief='solid', borderwidth=1,
                         font=("Segoe UI", 12, "normal"))
        label.pack(ipadx=2, ipady=1)
        self.tooltip.update_idletasks()
        tip_width = self.tooltip.winfo_width()
        tip_height = self.tooltip.winfo_height()
        screen_width = self.widget.winfo_screenwidth()
        screen_height = self.widget.winfo_screenheight()
        final_x = base_x + 15
        if final_x + tip_width > screen_width - 5:
            final_x = base_x - tip_width - 15
        final_y = base_y
        if final_y + tip_height > screen_height - 5:
            final_y = base_y - tip_height - 25
        try:
            self.tooltip.wm_geometry(f"+{int(final_x)}+{int(final_y)}")
        except tk.TclError:
            logger.warning("TclError setting tooltip geometry.")
            self.hide_tooltip()

    def hide_tooltip(self, event=None):
        if self._enter_id:
            try:
                self.widget.after_cancel(self._enter_id)
            except tk.TclError:
                pass
            self._enter_id = None
        if self.tooltip and self.tooltip.winfo_exists():
            try:
                self.tooltip.destroy()
            except tk.TclError:
                pass
        self.tooltip = None

class ListboxTooltip:
    def __init__(self, listbox_widget, data_list_ref):
        self.listbox = listbox_widget
        self.data_list = data_list_ref
        self.tooltip_window = None
        self._last_tooltip_index = -1
        self._tooltip_after_id = None
        if self.listbox:
            self.listbox.bind("<Motion>", self._on_motion, add='+')
            self.listbox.bind("<Leave>", self._on_leave, add='+')
            self.listbox.bind("<Destroy>", self._on_leave, add='+')

    def _on_motion(self, event):
        try:
            current_index = self.listbox.index(f"@{event.x},{event.y}")
        except tk.TclError:
            current_index = -1
        if current_index != self._last_tooltip_index:
            self._hide_listbox_tooltip()
            self._last_tooltip_index = current_index
            if current_index >= 0:
                if self._tooltip_after_id:
                    try:
                        self.listbox.after_cancel(self._tooltip_after_id)
                    except tk.TclError:
                        pass
                self._tooltip_after_id = self.listbox.after(
                    500,
                    lambda idx=current_index, ev=event: self._show_listbox_tooltip(idx, ev)
                )

    def _on_leave(self, event=None):
        if self._tooltip_after_id:
            try:
                self.listbox.after_cancel(self._tooltip_after_id)
            except tk.TclError:
                pass
            self._tooltip_after_id = None
        self._hide_listbox_tooltip()
        self._last_tooltip_index = -1

    def _show_listbox_tooltip(self, index, event):
        try:
            if 0 <= index < self.listbox.size() and index < len(self.data_list):
                tooltip_text = self.data_list[index]
                if not hasattr(self, '_item_tooltip_instance'):
                    self._item_tooltip_instance = Tooltip(self.listbox, "")
                self._item_tooltip_instance.text = tooltip_text
                x = event.x_root + 15
                y = event.y_root + 10
                self._item_tooltip_instance._display_tooltip()
                if self._item_tooltip_instance.tooltip:
                    self._item_tooltip_instance.tooltip.wm_geometry(f"+{x}+{y}")
            else:
                self._hide_listbox_tooltip()
        except Exception as e:
            logger.error(f"Error in _show_listbox_tooltip: {e}", exc_info=True)
            self._hide_listbox_tooltip()

    def _hide_listbox_tooltip(self):
        if hasattr(self, '_item_tooltip_instance'):
            self._item_tooltip_instance.hide_tooltip()
        self._last_tooltip_index = -1

class ConfirmationDialog(tk.Toplevel):
    def __init__(self, parent, title, message):
        super().__init__(parent)
        self.title(title)
        self.result = False
        self.resizable(False, False)
        self.transient(parent)
        self.grab_set()
        content_frame = ttk.Frame(self, padding="10 10 10 10")
        content_frame.pack(expand=True, fill="both")
        ttk.Label(content_frame, text=message, wraplength=350, justify="left").pack(padx=10, pady=(0, 15))
        button_frame = ttk.Frame(content_frame)
        button_frame.pack(pady=5)
        yes_button = ttk.Button(button_frame, text="Đồng ý", command=self.on_yes, width=12, bootstyle="success")
        yes_button.pack(side="left", padx=10)
        no_button = ttk.Button(button_frame, text="Hủy bỏ", command=self.on_no, width=12, bootstyle="secondary")
        no_button.pack(side="left", padx=10)
        self.update_idletasks()
        parent_x = parent.winfo_rootx()
        parent_y = parent.winfo_rooty()
        parent_width = parent.winfo_width()
        parent_height = parent.winfo_height()
        dialog_width = self.winfo_width()
        dialog_height = self.winfo_height()
        x = parent_x + (parent_width // 2) - (dialog_width // 2)
        y = parent_y + (parent_height // 2) - (dialog_height // 2)
        self.geometry(f'+{x}+{y}')
        self.wait_window(self)

    def on_yes(self):
        self.result = True
        self.destroy()

    def on_no(self):
        self.result = False
        self.destroy()