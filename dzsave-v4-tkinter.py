import queue
import sys
import threading
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

import dzsave_v4_gui_common as common


class DzSaveWindow:
    def __init__(self, root):
        self.root = root
        self.events = queue.Queue()
        self.busy = False
        self.scanned_files = []
        self.values = {
            key: tk.StringVar(value=value)
            for key, value in common.DEFAULTS.items()
        }

        root.title("WSI DeepZoom Converter - Tkinter")
        root.geometry("1000x900")
        root.minsize(780, 680)

        self._build()
        root.after(100, self._poll_events)

    def _build(self):
        main = ttk.Frame(self.root, padding=16)
        main.pack(fill=tk.BOTH, expand=True)
        main.columnconfigure(0, weight=1)

        ttk.Label(main, text="WSI DeepZoom Converter", font=("Segoe UI", 18, "bold")).grid(
            row=0, column=0, sticky="w"
        )
        ttk.Label(
            main,
            text="Convert TIFF slides, generate thumbnails, and copy DeepZoom output.",
        ).grid(row=1, column=0, sticky="w", pady=(3, 14))

        folders = ttk.LabelFrame(main, text="Folders", padding=10)
        folders.grid(row=2, column=0, sticky="ew")
        folders.columnconfigure(1, weight=1)
        for row, (key, label) in enumerate(
            (
                ("input_dir", "Source WSI folder"),
                ("primary_dir", "Primary destination"),
                ("secondary_dir", "Secondary destination"),
            )
        ):
            self._path_row(folders, row, key, label)

        settings = ttk.LabelFrame(main, text="Conversion and thumbnail settings", padding=10)
        settings.grid(row=3, column=0, sticky="new", pady=(12, 0))
        setting_labels = (
            ("jpeg_quality", "DeepZoom JPEG quality"),
            ("thumbnail_size", "Thumbnail max size (px)"),
            ("thumbnail_quality", "Thumbnail JPEG quality"),
        )
        for column, (key, label) in enumerate(setting_labels):
            settings.columnconfigure(column, weight=1)
            cell = ttk.Frame(settings)
            cell.grid(row=0, column=column, sticky="ew", padx=4)
            ttk.Label(cell, text=label).pack(anchor="w")
            ttk.Entry(cell, textvariable=self.values[key], width=10).pack(
                fill=tk.X, pady=(4, 0)
            )

        copy_settings = ttk.LabelFrame(main, text="Robocopy settings", padding=10)
        copy_settings.grid(row=4, column=0, sticky="ew", pady=(8, 0))
        for column, (key, label) in enumerate(
            (
                ("robocopy_threads", "Robocopy threads"),
                ("robocopy_retries", "Retry count"),
                ("robocopy_wait", "Wait between retries (sec)"),
            )
        ):
            copy_settings.columnconfigure(column, weight=1)
            cell = ttk.Frame(copy_settings)
            cell.grid(row=0, column=column, sticky="ew", padx=4)
            ttk.Label(cell, text=label).pack(anchor="w")
            ttk.Entry(cell, textvariable=self.values[key], width=10).pack(
                fill=tk.X, pady=(4, 0)
            )

        selection = ttk.LabelFrame(
            main, text="Found TIFF files (selected files will be converted)", padding=8
        )
        selection.grid(row=5, column=0, sticky="ew", pady=(10, 0))
        selection.columnconfigure(0, weight=1)
        selection.rowconfigure(1, weight=1)
        selection_tools = ttk.Frame(selection)
        selection_tools.grid(row=0, column=0, sticky="ew")
        self.selection_count = tk.StringVar(value="Scan a source folder to list TIFF files.")
        ttk.Label(selection_tools, textvariable=self.selection_count).pack(side=tk.LEFT)
        ttk.Button(selection_tools, text="Select all", command=self._select_all).pack(
            side=tk.RIGHT, padx=(6, 0)
        )
        ttk.Button(selection_tools, text="Select none", command=self._select_none).pack(
            side=tk.RIGHT
        )
        list_frame = ttk.Frame(selection)
        list_frame.grid(row=1, column=0, sticky="ew", pady=(5, 0))
        list_frame.columnconfigure(0, weight=1)
        self.file_list = tk.Listbox(
            list_frame, selectmode=tk.EXTENDED, height=7, exportselection=False
        )
        file_scrollbar = ttk.Scrollbar(
            list_frame, orient=tk.VERTICAL, command=self.file_list.yview
        )
        self.file_list.configure(yscrollcommand=file_scrollbar.set)
        self.file_list.grid(row=0, column=0, sticky="ew")
        file_scrollbar.grid(row=0, column=1, sticky="ns")
        self.file_list.bind("<<ListboxSelect>>", self._update_selection_count)

        activity = ttk.LabelFrame(main, text="Activity", padding=10)
        activity.grid(row=6, column=0, sticky="nsew", pady=(10, 0))
        main.rowconfigure(6, weight=1)
        activity.columnconfigure(0, weight=1)
        activity.rowconfigure(1, weight=1)
        self.status = tk.StringVar(value="Ready. Scan for TIFF files or start conversion.")
        ttk.Label(activity, textvariable=self.status).grid(
            row=0, column=0, sticky="w", pady=(0, 6)
        )

        log_frame = ttk.Frame(activity)
        log_frame.grid(row=1, column=0, sticky="nsew")
        log_frame.columnconfigure(0, weight=1)
        log_frame.rowconfigure(0, weight=1)
        self.log = tk.Text(log_frame, wrap=tk.WORD, state=tk.DISABLED, font=("Consolas", 9))
        scrollbar = ttk.Scrollbar(log_frame, orient=tk.VERTICAL, command=self.log.yview)
        self.log.configure(yscrollcommand=scrollbar.set)
        self.log.grid(row=0, column=0, sticky="nsew")
        scrollbar.grid(row=0, column=1, sticky="ns")

        self.progress = ttk.Progressbar(main, mode="determinate")
        self.progress.grid(row=7, column=0, sticky="ew", pady=(10, 0))
        buttons = ttk.Frame(main)
        buttons.grid(row=8, column=0, sticky="e", pady=(10, 0))
        self.scan_button = ttk.Button(buttons, text="Scan files", command=self.scan)
        self.scan_button.pack(side=tk.LEFT, padx=(0, 8))
        self.start_button = ttk.Button(
            buttons, text="Start conversion", command=self.start_conversion
        )
        self.start_button.pack(side=tk.LEFT)

    def _path_row(self, parent, row, key, label):
        ttk.Label(parent, text=label).grid(
            row=row, column=0, sticky="w", padx=(0, 10), pady=4
        )
        ttk.Entry(parent, textvariable=self.values[key]).grid(
            row=row, column=1, sticky="ew", pady=4
        )
        ttk.Button(
            parent,
            text="Browse...",
            command=lambda: self._browse(key),
        ).grid(row=row, column=2, padx=(8, 0), pady=4)

    def _browse(self, key):
        selected = filedialog.askdirectory(initialdir=self.values[key].get())
        if selected:
            self.values[key].set(selected)

    def _set_busy(self, busy):
        self.busy = busy
        state = tk.DISABLED if busy else tk.NORMAL
        self.scan_button.configure(state=state)
        self.start_button.configure(state=state)
        self.file_list.configure(state=state)

    def _append_log(self, text):
        self.log.configure(state=tk.NORMAL)
        self.log.insert(tk.END, text)
        self.log.see(tk.END)
        self.log.configure(state=tk.DISABLED)

    def scan(self):
        if self.busy:
            return
        folder = self.values["input_dir"].get()
        self.file_list.configure(state=tk.NORMAL)
        self.file_list.delete(0, tk.END)
        self.scanned_files = []
        self.selection_count.set("Scanning for TIFF files...")
        self._set_busy(True)
        self.status.set("Searching for TIFF files...")

        def worker():
            try:
                self.events.put(("scan_done", common.find_wsi_files(folder)))
            except Exception as error:
                self.events.put(("error", str(error)))
                self.events.put(("scan_done", None))

        threading.Thread(target=worker, daemon=True).start()

    def start_conversion(self):
        if self.busy:
            return
        try:
            settings = common.validate_settings(
                {key: variable.get() for key, variable in self.values.items()},
                self._selected_files(),
            )
        except ValueError as error:
            messagebox.showerror("Check settings", str(error))
            return

        self._set_busy(True)
        self.progress.configure(maximum=1, value=0)
        self.status.set("Conversion running...")
        self._append_log("Starting conversion...\n")
        common.run_conversion(settings, self.events)

    def _poll_events(self):
        while True:
            try:
                event, payload = self.events.get_nowait()
            except queue.Empty:
                break

            if event == "log":
                self._append_log(payload)
            elif event == "progress":
                current, total, percentage = payload
                self.progress.configure(maximum=total, value=current)
                self.status.set(
                    f"Completed {current} of {total} files ({percentage}%)."
                )
            elif event == "scan_done":
                self._set_busy(False)
                if payload is not None:
                    self.scanned_files = payload
                    self.file_list.configure(state=tk.NORMAL)
                    for path in payload:
                        self.file_list.insert(tk.END, str(path))
                    self.file_list.selection_set(0, tk.END)
                    self._update_selection_count()
                    self.status.set(f"Found {len(payload):,} TIFF file(s).")
            elif event == "error":
                self._append_log(f"\nError: {payload}\n")
                messagebox.showerror("Operation failed", payload)
            elif event == "done":
                self._set_busy(False)
                self.status.set("Conversion finished. See the activity log for details.")

        self.root.after(100, self._poll_events)

    def _selected_files(self):
        return [self.scanned_files[index] for index in self.file_list.curselection()]

    def _update_selection_count(self, _event=None):
        selected = len(self.file_list.curselection())
        self.selection_count.set(
            f"{selected:,} of {len(self.scanned_files):,} TIFF file(s) selected."
        )

    def _select_all(self):
        self.file_list.selection_set(0, tk.END)
        self._update_selection_count()

    def _select_none(self):
        self.file_list.selection_clear(0, tk.END)
        self._update_selection_count()


def main():
    root = tk.Tk()
    if "--self-test" in sys.argv[1:]:
        root.withdraw()
        DzSaveWindow(root)
        root.update_idletasks()
        root.destroy()
        return
    DzSaveWindow(root)
    root.mainloop()


if __name__ == "__main__":
    main()
