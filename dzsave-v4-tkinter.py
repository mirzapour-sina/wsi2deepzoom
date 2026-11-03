import queue
import sys
import threading
import time
from pathlib import Path

import tkinter as tk
from tkinter import filedialog, messagebox, ttk

import dzsave_v4_gui_common as common


class ToolTip:
    """Small hover tooltip for widgets that lack a native tooltip."""

    def __init__(self, widget, text):
        self.widget = widget
        self.text = text
        self.tip = None
        widget.bind("<Enter>", self._show)
        widget.bind("<Leave>", self._hide)

    def _show(self, _event=None):
        if self.tip or not self.text:
            return
        x = self.widget.winfo_rootx() + 22
        y = self.widget.winfo_rooty() + self.widget.winfo_height() + 6
        self.tip = tw = tk.Toplevel(self.widget)
        tw.wm_overrideredirect(True)
        tw.wm_geometry(f"+{x}+{y}")
        label = tk.Label(
            tw,
            text=self.text,
            background="#ffffe0",
            relief=tk.SOLID,
            borderwidth=1,
            font=("Segoe UI", 9),
        )
        label.pack(ipadx=1)

    def _hide(self, _event=None):
        if self.tip:
            self.tip.destroy()
            self.tip = None


class DzSaveWindow:
    _NUMERIC_RULES = {
        "jpeg_quality": (1, 100, "JPEG quality must be between 1 and 100."),
        "thumbnail_size": (1, None, "Thumbnail size must be at least 1 pixel."),
        "thumbnail_quality": (1, 100, "Thumbnail quality must be between 1 and 100."),
        "robocopy_threads": (1, 128, "Copy threads must be between 1 and 128."),
        "robocopy_retries": (0, None, "Copy retries cannot be negative."),
        "robocopy_wait": (0, None, "Retry wait cannot be negative."),
        "conversion_threads": (1, 128, "Conversion threads must be between 1 and 128."),
    }

    def __init__(self, root):
        self.root = root
        self.events = queue.Queue()
        self.busy = False
        self.dark_mode = False
        self.run_started_monotonic = None
        self.run_started_at = "—"
        self.scanned_files = []
        self.destinations = [
            tk.StringVar(value=path) for path in common.DEFAULT_DESTINATIONS
        ]
        self.values = {
            key: tk.StringVar(value=value)
            for key, value in common.DEFAULTS.items()
        }
        self.field_entries = {}
        self.field_errors = {}

        root.title("WSI DeepZoom Converter - Tkinter")
        root.geometry("1000x980")
        root.minsize(780, 740)

        self._build()
        root.after(100, self._poll_events)
        root.bind("<Escape>", self._on_escape)
        root.bind("<F5>", self._on_f5)
        root.bind("<Control-r>", self._on_reset_shortcut)
        self._add_tooltips()

    def _check_field(self, key, value):
        """Return an inline error message for a field value, or None when valid."""
        if key == "input_dir":
            if not Path(value).expanduser().is_dir():
                return "Select an existing input folder."
            return None
        if key == "wsi_extensions":
            try:
                common.parse_wsi_extensions(value)
            except ValueError as error:
                return str(error)
            return None
        if key in self._NUMERIC_RULES:
            minimum, maximum, message = self._NUMERIC_RULES[key]
            try:
                number = int(value)
            except (TypeError, ValueError):
                return "Enter a whole number."
            if number < minimum or (maximum is not None and number > maximum):
                return message
            return None
        if key.startswith("destination_"):
            if not value.strip():
                return "Enter a destination folder."
            return None
        return None

    def _validate_field(self, key):
        """Show or clear the inline error label for a single field."""
        entry = self.field_entries.get(key)
        error_label = self.field_errors.get(key)
        if entry is None or error_label is None:
            return True
        value = self.values[key].get()
        error = self._check_field(key, value)
        if error:
            error_label.config(text=error)
        else:
            error_label.config(text="")
        return error is None

    def _validate_destination(self, index):
        """Show or clear the inline error label for a destination field."""
        value = self.destinations[index].get()
        error = self._check_field(f"destination_{index}", value)
        self.destination_errors[index].config(text=error or "")
        return error is None

    def _validate_all_fields(self):
        """Validate every editable field and return True when all are valid."""
        valid = True
        for key in list(self.field_entries):
            if key.startswith("destination_"):
                continue
            if not self._validate_field(key):
                valid = False
        for index in range(len(self.destinations)):
            if not self._validate_destination(index):
                valid = False
        return valid

    def _format_key_for_label(self, label):
        """Return the DeepZoom format key matching the shown label, unchanged if unknown."""
        if label in self.format_labels:
            return self.format_keys[self.format_labels.index(label)]
        return label

    def _build(self):
        page = ttk.Frame(self.root)
        page.pack(fill=tk.BOTH, expand=True)
        canvas = tk.Canvas(page, highlightthickness=0)
        scrollbar = ttk.Scrollbar(page, orient=tk.VERTICAL, command=canvas.yview)
        canvas.configure(yscrollcommand=scrollbar.set)
        canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        main = ttk.Frame(canvas, padding=16)
        self.page_content = main
        self.page_canvas = canvas
        self.page_window = canvas.create_window((0, 0), window=main, anchor="nw")
        main.bind(
            "<Configure>",
            lambda _event: canvas.configure(scrollregion=canvas.bbox("all")),
        )
        canvas.bind(
            "<Configure>",
            lambda event: canvas.itemconfigure(self.page_window, width=event.width),
        )
        self.root.bind_all("<MouseWheel>", self._scroll_page)
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
        self._path_row(folders, 0, "input_dir", "Source WSI folder")
        destinations = ttk.LabelFrame(folders, text="Output destinations", padding=6)
        destinations.grid(row=1, column=0, columnspan=3, sticky="ew", pady=(6, 0))
        destinations.columnconfigure(0, weight=1)
        self.destinations_frame = ttk.Frame(destinations)
        self.destinations_frame.grid(row=0, column=0, sticky="ew")
        self.destinations_frame.columnconfigure(1, weight=1)
        self.add_destination_button = ttk.Button(
            destinations,
            text="Add destination",
            command=self._add_destination,
        )
        self.add_destination_button.grid(row=1, column=0, sticky="e", pady=(5, 0))
        ToolTip(self.add_destination_button, "Add another output destination.")
        self._render_destinations()

        self.options_visible = False
        self.options_toggle = ttk.Button(
            main,
            text="Show DeepZoom and Robocopy options",
            command=self._toggle_options,
        )
        self.options_toggle.grid(row=3, column=0, sticky="w", pady=(10, 0))
        options = ttk.Frame(main)
        self.options_frame = options
        options.grid(row=4, column=0, sticky="ew", pady=(6, 0))
        options.grid_remove()
        options.columnconfigure(0, weight=1)

        settings = ttk.LabelFrame(options, padding=10)
        self.settings_frame = settings
        self.settings_toggle = ttk.Button(
            options,
            text="Show DeepZoom and thumbnail options",
            command=lambda: self._toggle_grid_widget(
                settings, self.settings_toggle,
                "Show DeepZoom and thumbnail options",
                "Hide DeepZoom and thumbnail options",
            ),
        )
        self.settings_toggle.configure(text="Hide DeepZoom and thumbnail options")
        self.settings_toggle.grid(row=0, column=0, sticky="w")
        settings.grid(row=1, column=0, sticky="ew")
        format_keys = tuple(common.DEEPZOOM_FORMATS)
        format_labels = tuple(
            option["label"] for option in common.DEEPZOOM_FORMATS.values()
        )
        self.format_keys = format_keys
        self.format_labels = format_labels

        setting_labels = (
            ("jpeg_quality", "DeepZoom JPEG quality"),
            ("thumbnail_size", "Thumbnail max size (px)"),
            ("thumbnail_quality", "Thumbnail JPEG quality"),
            ("conversion_threads", "Conversion threads"),
        )
        for column, (key, label) in enumerate(setting_labels):
            settings.columnconfigure(column, weight=1)
            cell = ttk.Frame(settings)
            cell.grid(row=0, column=column, sticky="ew", padx=4)
            ttk.Label(cell, text=label).pack(anchor="w")
            entry = ttk.Entry(cell, textvariable=self.values[key], width=10)
            entry.pack(fill=tk.X, pady=(4, 0))
            entry.bind("<FocusOut>", lambda _event, k=key: self._validate_field(k))
            self.field_entries[key] = entry
            error = tk.Label(cell, text="", foreground="#c53030", font=("Segoe UI", 8))
            error.pack(anchor="w", pady=(1, 0))
            self.field_errors[key] = error
        ttk.Label(settings, text="DeepZoom output format").grid(
            row=1, column=0, sticky="w", padx=4, pady=(10, 0)
        )
        self.format_combo = ttk.Combobox(
            settings,
            textvariable=self.values["deepzoom_format"],
            values=format_labels,
            state="readonly",
        )
        self.format_combo.grid(row=2, column=0, sticky="ew", padx=4, pady=(4, 0))
        try:
            default_index = format_keys.index(common.DEFAULTS["deepzoom_format"])
        except ValueError:
            default_index = 0
        self.format_combo.current(default_index)
        ttk.Label(settings, text="WSI file extensions (comma-separated)").grid(
            row=1, column=1, columnspan=2, sticky="w", padx=4, pady=(10, 0)
        )
        entry = ttk.Entry(settings, textvariable=self.values["wsi_extensions"])
        entry.grid(row=2, column=1, columnspan=2, sticky="ew", padx=4, pady=(4, 0))
        entry.bind("<FocusOut>", lambda _event: self._validate_field("wsi_extensions"))
        self.field_entries["wsi_extensions"] = entry
        error = tk.Label(settings, text="", foreground="#c53030", font=("Segoe UI", 8))
        error.grid(row=3, column=1, columnspan=2, sticky="w", pady=(1, 0))
        self.field_errors["wsi_extensions"] = error
        ttk.Label(
            settings,
            text="Extensions must be supported by your installed libvips loaders.",
        ).grid(row=4, column=1, columnspan=2, sticky="w", padx=4, pady=(2, 0))

        copy_settings = ttk.LabelFrame(options, padding=10)
        self.copy_settings_frame = copy_settings
        self.copy_toggle = ttk.Button(
            options,
            text="Show Robocopy options",
            command=lambda: self._toggle_grid_widget(
                copy_settings, self.copy_toggle,
                "Show Robocopy options", "Hide Robocopy options"
            ),
        )
        self.copy_toggle.configure(text="Hide Robocopy options")
        self.copy_toggle.grid(row=2, column=0, sticky="w", pady=(8, 0))
        copy_settings.grid(row=3, column=0, sticky="ew")
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
            entry = ttk.Entry(cell, textvariable=self.values[key], width=10)
            entry.pack(fill=tk.X, pady=(4, 0))
            entry.bind("<FocusOut>", lambda _event, k=key: self._validate_field(k))
            self.field_entries[key] = entry
            error = tk.Label(cell, text="", foreground="#c53030", font=("Segoe UI", 8))
            error.pack(anchor="w", pady=(1, 0))
            self.field_errors[key] = error

        selection = ttk.LabelFrame(
            main,
            text="Found WSI files (selected files will be converted)",
            padding=8,
        )
        self.selection_frame = selection
        selection.grid(row=5, column=0, sticky="ew", pady=(10, 0))
        selection.columnconfigure(0, weight=1)
        selection.rowconfigure(1, weight=1)
        selection_tools = ttk.Frame(selection)
        selection_tools.grid(row=0, column=0, sticky="ew")
        self.selection_count = tk.StringVar(value="Scan a source folder to list WSI files.")
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

        self.activity_toggle = ttk.Button(
            main,
            text="Hide Activity",
            command=lambda: self._toggle_grid_widget(
                activity, self.activity_toggle, "Show Activity", "Hide Activity"
            ),
        )
        self.activity_toggle.grid(row=6, column=0, sticky="w", pady=(10, 0))
        activity = ttk.LabelFrame(main, padding=10)
        activity.grid(row=7, column=0, sticky="ew")
        activity.columnconfigure(0, weight=1)
        activity.rowconfigure(8, weight=1)
        self.status = tk.StringVar(value="Ready. Scan for WSI files or start conversion.")
        ttk.Label(activity, textvariable=self.status).grid(
            row=0, column=0, sticky="w", pady=(0, 6)
        )

        self.log_visible = False
        self.open_report_path = None
        self.log_toggle = ttk.Button(
            activity,
            text="Show detailed text output",
            command=self._toggle_log,
        )
        self.log_toggle.grid(row=1, column=0, sticky="w", pady=(0, 5))
        report_frame = ttk.Frame(activity)
        report_frame.grid(row=2, column=0, sticky="ew", pady=(0, 5))
        self.report_info = tk.StringVar(value="Reports will be saved in the first destination.")
        ttk.Label(report_frame, textvariable=self.report_info).pack(side=tk.LEFT, fill=tk.X, expand=True)
        self.open_report_button = ttk.Button(
            report_frame, text="Open report", command=self._open_report, state=tk.DISABLED
        )
        self.open_report_button.pack(side=tk.RIGHT)

        metrics_frame = ttk.LabelFrame(activity, padding=6)
        self.metrics_frame = metrics_frame
        self.details_toggle = ttk.Button(
            activity,
            text="Show live conversion details",
            command=lambda: self._toggle_grid_widget(
                metrics_frame, self.details_toggle,
                "Show live conversion details",
                "Hide live conversion details",
            ),
        )
        self.details_toggle.grid(row=3, column=0, sticky="w")
        metrics_frame.grid(row=4, column=0, sticky="ew", pady=(0, 6))
        metrics_frame.grid_remove()
        metrics_frame.columnconfigure(1, weight=1)
        metrics_frame.columnconfigure(3, weight=1)
        self.activity_values = {}
        detail_fields = (
            ("file", "Current file"),
            ("resolution", "Resolution"),
            ("load", "Source load"),
            ("deepzoom", "DeepZoom"),
            ("thumbnail", "Thumbnail"),
            ("copy", "Copy"),
            ("slide", "Slide total"),
            ("elapsed", "Run elapsed"),
            ("counts", "File totals"),
            ("outputs", "Output paths"),
        )
        for index, (key, label) in enumerate(detail_fields[:8]):
            row, pair = divmod(index, 2)
            column = pair * 2
            ttk.Label(metrics_frame, text=label).grid(
                row=row, column=column, sticky="nw", padx=(0, 5), pady=2
            )
            value = tk.StringVar(value="—")
            ttk.Label(metrics_frame, textvariable=value, wraplength=320).grid(
                row=row, column=column + 1, sticky="nw", padx=(0, 12), pady=2
            )
            self.activity_values[key] = value
        ttk.Label(metrics_frame, text="File totals").grid(
            row=4, column=0, sticky="nw", padx=(0, 5), pady=2
        )
        self.activity_values["counts"] = tk.StringVar(value="—")
        ttk.Label(
            metrics_frame,
            textvariable=self.activity_values["counts"],
            wraplength=650,
        ).grid(row=4, column=1, columnspan=3, sticky="nw", padx=(0, 12), pady=2)
        ttk.Label(metrics_frame, text="Output paths").grid(
            row=5, column=0, sticky="nw", padx=(0, 5), pady=2
        )
        self.activity_values["outputs"] = tk.StringVar(value="—")
        ttk.Label(
            metrics_frame,
            textvariable=self.activity_values["outputs"],
            wraplength=650,
        ).grid(row=5, column=1, columnspan=3, sticky="nw", padx=(0, 12), pady=2)
        self.run_summary = tk.StringVar(
            value="Started: — | Finished: — | Average per file: —"
        )
        ttk.Label(activity, textvariable=self.run_summary, wraplength=920).grid(
            row=5, column=0, sticky="ew", pady=(0, 6)
        )

        results_frame = ttk.LabelFrame(activity, padding=4)
        self.results_frame = results_frame
        self.results_toggle = ttk.Button(
            activity,
            text="Show per-file results",
            command=lambda: self._toggle_grid_widget(
                results_frame, self.results_toggle,
                "Show per-file results", "Hide per-file results"
            ),
        )
        self.results_toggle.grid(row=6, column=0, sticky="w")
        results_frame.grid(row=7, column=0, sticky="ew", pady=(0, 6))
        results_frame.grid_remove()
        results_frame.columnconfigure(0, weight=1)
        columns = (
            "file",
            "resolution",
            "load",
            "deepzoom",
            "thumbnail",
            "copy",
            "total",
            "status",
            "copy_destinations",
            "outputs",
            "error",
        )
        self.results_table = ttk.Treeview(
            results_frame, columns=columns, show="headings", height=5
        )
        headings = (
            "File",
            "Resolution",
            "Load",
            "DeepZoom",
            "Thumbnail",
            "Copy",
            "Total",
            "Status",
            "Copy destinations",
            "Output paths",
            "Error",
        )
        for column, heading in zip(columns, headings):
            self.results_table.heading(column, text=heading)
            self.results_table.column(column, width=100, stretch=True)
        self.results_table.column("file", width=210)
        self.results_table.column("copy_destinations", width=220)
        self.results_table.column("outputs", width=260)
        self.results_table.column("error", width=180)
        results_scrollbar = ttk.Scrollbar(
            results_frame, orient=tk.HORIZONTAL, command=self.results_table.xview
        )
        results_vertical_scrollbar = ttk.Scrollbar(
            results_frame, orient=tk.VERTICAL, command=self.results_table.yview
        )
        self.results_table.configure(
            xscrollcommand=results_scrollbar.set,
            yscrollcommand=results_vertical_scrollbar.set,
        )
        self.results_table.grid(row=0, column=0, sticky="ew")
        results_vertical_scrollbar.grid(row=0, column=1, sticky="ns")
        results_scrollbar.grid(row=1, column=0, sticky="ew")

        log_frame = ttk.Frame(activity)
        self.log_frame = log_frame
        log_frame.grid(row=8, column=0, sticky="nsew")
        log_frame.columnconfigure(0, weight=1)
        log_frame.rowconfigure(0, weight=1)
        self.log = tk.Text(log_frame, wrap=tk.WORD, state=tk.DISABLED, font=("Consolas", 9))
        scrollbar = ttk.Scrollbar(log_frame, orient=tk.VERTICAL, command=self.log.yview)
        self.log.configure(yscrollcommand=scrollbar.set)
        self.log.grid(row=0, column=0, sticky="nsew")
        scrollbar.grid(row=0, column=1, sticky="ns")
        log_frame.grid_remove()

        progress_frame = ttk.LabelFrame(main, text="Conversion progress", padding=8)
        self.progress_frame = progress_frame
        progress_frame.grid(row=8, column=0, sticky="ew", pady=(10, 0))
        progress_frame.columnconfigure(0, weight=1)
        self.progress_status = tk.StringVar(value="Overall — Ready")
        ttk.Label(progress_frame, textvariable=self.progress_status).grid(
            row=0, column=0, columnspan=2, sticky="w"
        )
        self.progress = ttk.Progressbar(progress_frame, mode="determinate")
        self.progress.grid(row=1, column=0, sticky="ew", pady=(4, 6))
        self.overall_percentage = tk.StringVar(value="0%")
        ttk.Label(progress_frame, textvariable=self.overall_percentage, width=5).grid(
            row=1, column=1, sticky="e", padx=(8, 0)
        )
        ttk.Label(progress_frame, text="Current slide").grid(
            row=2, column=0, columnspan=2, sticky="w"
        )
        self.stage_progress = ttk.Progressbar(
            progress_frame, mode="determinate", maximum=4
        )
        self.stage_progress.grid(row=3, column=0, sticky="ew", pady=(4, 0))
        self.stage_percentage = tk.StringVar(value="0%")
        ttk.Label(progress_frame, textvariable=self.stage_percentage, width=5).grid(
            row=3, column=1, sticky="e", padx=(8, 0)
        )
        buttons = ttk.Frame(main)
        buttons.grid(row=9, column=0, sticky="e", pady=(10, 0))
        self.scan_button = ttk.Button(buttons, text="Scan files", command=self.scan)
        self.scan_button.pack(side=tk.LEFT, padx=(0, 8))
        self.start_button = tk.Button(
            buttons,
            text="Start conversion",
            command=self.start_conversion,
            bg="#2563eb",
            fg="white",
            activebackground="#1d4ed8",
            activeforeground="white",
            disabledforeground="#9ca3af",
            font=("Segoe UI", 9, "bold"),
            relief=tk.RAISED,
            bd=1,
            padx=16,
            pady=3,
            cursor="hand2",
        )
        self.start_button.pack(side=tk.LEFT)
        self.cancel_button = ttk.Button(
            buttons, text="Cancel", command=self._request_cancel, state=tk.DISABLED
        )
        self.cancel_button.pack(side=tk.LEFT, padx=(8, 0))
        self.reset_button = ttk.Button(
            buttons, text="Reset to defaults", command=self._reset_defaults
        )
        self.reset_button.pack(side=tk.LEFT, padx=(8, 0))
        self.dark_toggle = ttk.Button(
            buttons, text="Dark mode", command=self._toggle_dark_mode
        )
        self.dark_toggle.pack(side=tk.LEFT, padx=(8, 0))
        ToolTip(self.dark_toggle, "Toggle dark mode.")

    def _path_row(self, parent, row, key, label):
        ttk.Label(parent, text=label).grid(
            row=row, column=0, sticky="w", padx=(0, 10), pady=4
        )
        entry = ttk.Entry(parent, textvariable=self.values[key])
        entry.grid(row=row, column=1, sticky="ew", pady=4)
        entry.bind("<FocusOut>", lambda _event, k=key: self._validate_field(k))
        self.field_entries[key] = entry
        error = tk.Label(parent, text="", foreground="#c53030", font=("Segoe UI", 8))
        error.grid(row=row + 1, column=1, columnspan=2, sticky="w", pady=(1, 0))
        self.field_errors[key] = error
        ttk.Button(
            parent,
            text="Browse...",
            command=lambda: self._browse(key),
        ).grid(row=row, column=2, padx=(8, 0), pady=4)

    @staticmethod
    def _toggle_grid_widget(widget, toggle, show_text, hide_text):
        if widget.winfo_manager():
            widget.grid_remove()
            toggle.configure(text=show_text)
        else:
            widget.grid()
            toggle.configure(text=hide_text)

    def _render_destinations(self):
        for child in self.destinations_frame.winfo_children():
            child.destroy()
        self.destination_entries = []
        self.destination_errors = []
        for index, value in enumerate(self.destinations):
            ttk.Label(self.destinations_frame, text=f"Destination {index + 1}").grid(
                row=index, column=0, sticky="w", padx=(0, 10), pady=3
            )
            entry = ttk.Entry(self.destinations_frame, textvariable=value)
            entry.grid(row=index, column=1, sticky="ew", pady=3)
            entry.bind(
                "<FocusOut>", lambda _event, i=index: self._validate_destination(i)
            )
            self.destination_entries.append(entry)
            self.field_entries[f"destination_{index}"] = entry
            error = tk.Label(
                self.destinations_frame,
                text="",
                foreground="#c53030",
                font=("Segoe UI", 8),
            )
            error.grid(row=index, column=1, columnspan=2, sticky="w", pady=(1, 0))
            self.destination_errors.append(error)
            self.field_errors[f"destination_{index}"] = error
            browse_button = ttk.Button(
                self.destinations_frame,
                text="Browse...",
                command=lambda path=value: self._browse_destination(path),
            )
            browse_button.grid(row=index, column=2, padx=(8, 0), pady=3)
            ToolTip(browse_button, "Browse for a destination folder.")
            remove_button = ttk.Button(
                self.destinations_frame,
                text="Remove",
                command=lambda item=value: self._remove_destination(item),
                state=(
                    tk.NORMAL
                    if index > 0 and len(self.destinations) > 1
                    else tk.DISABLED
                ),
            )
            remove_button.grid(row=index, column=3, padx=(6, 0), pady=3)
            ToolTip(remove_button, "Remove this destination.")

    def _browse_destination(self, value):
        selected = filedialog.askdirectory(initialdir=value.get())
        if selected:
            value.set(selected)

    def _add_destination(self):
        self.destinations.append(tk.StringVar())
        self._render_destinations()

    def _remove_destination(self, value):
        if len(self.destinations) > 1 and value is not self.destinations[0]:
            self.destinations.remove(value)
            self._render_destinations()

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
        self.cancel_button.configure(state=tk.NORMAL if busy else tk.DISABLED)

    def _request_cancel(self):
        common.request_cancel()
        self.status.set("Cancellation requested. Stopping after current file...")

    def _reset_defaults(self):
        if self.busy:
            return
        for key, variable in self.values.items():
            variable.set(common.DEFAULTS.get(key, ""))
        self.destinations = [
            tk.StringVar(value=path) for path in common.DEFAULT_DESTINATIONS
        ]
        self._render_destinations()
        for key, error in self.field_errors.items():
            error.config(text="")
        self.status.set("Settings reset to defaults.")

    def _toggle_dark_mode(self):
        self.dark_mode = not self.dark_mode
        self.dark_toggle.configure(text="Light mode" if self.dark_mode else "Dark mode")
        self._apply_dark_mode(self.dark_mode)

    def _apply_dark_mode(self, dark):
        if dark:
            bg, fg = "#2b2b2b", "#e5e7eb"
            entry_bg, entry_fg = "#3a3a3a", "#e5e7eb"
            select_bg = "#3a7ca5"
            trough = "#2b2b2b"
        else:
            bg, fg = "#f5f7fa", "#111827"
            entry_bg, entry_fg = "#ffffff", "#111827"
            select_bg = "#cce8ff"
            trough = "#f5f7fa"

        style = ttk.Style(self.root)
        style.configure("TFrame", background=bg)
        style.configure("TLabel", background=bg, foreground=fg)
        style.configure("TLabelFrame", background=bg, foreground=fg)
        style.configure("TEntry", fieldbackground=entry_bg, foreground=entry_fg)
        style.configure("TButton", background=entry_bg, foreground=fg)
        style.configure("TCombobox", fieldbackground=entry_bg, foreground=fg)
        style.configure("TProgressbar", background=select_bg, troughcolor=trough)
        style.map(
            "TButton",
            background=[("active", "#4a4a4a" if dark else "#e5e7eb")],
        )

        self.root.configure(bg=bg)
        self.page_canvas.configure(bg=bg, highlightbackground=bg)
        self.page_content.configure(style="TFrame")
        self.log.configure(bg=entry_bg, fg=entry_fg, insertbackground=fg)
        self.file_list.configure(
            bg=entry_bg, fg=entry_fg, selectbackground=select_bg
        )
        for error in self.field_errors.values():
            error.configure(bg=bg)

    def _on_escape(self, _event):
        if self.cancel_button.instate(["!disabled"]):
            self._request_cancel()
        return "break"

    def _on_f5(self, _event):
        if self.start_button.instate(["!disabled"]):
            self.start_conversion()
        return "break"

    def _on_reset_shortcut(self, _event):
        if self.reset_button.instate(["!disabled"]):
            self._reset_defaults()
        return "break"

    def _add_tooltips(self):
        ToolTip(self.scan_button, "Scan the source folder for WSI files.")
        ToolTip(self.start_button, "Start conversion of the selected WSI files (F5).")
        ToolTip(self.cancel_button, "Cancel the running conversion after the current file (Escape).")
        ToolTip(self.reset_button, "Reset all settings to their default values (Ctrl+R).")
        ToolTip(self.open_report_button, "Open the generated conversion report.")
        ToolTip(self.log_toggle, "Show or hide the detailed text output.")
        ToolTip(self.details_toggle, "Show or hide live conversion details.")
        ToolTip(self.results_toggle, "Show or hide per-file conversion results.")

    def _append_log(self, text):
        self.log.configure(state=tk.NORMAL)
        self.log.insert(tk.END, text)
        self.log.see(tk.END)
        self.log.configure(state=tk.DISABLED)

    def scan(self):
        if self.busy:
            return
        self._scroll_to_widget(self.selection_frame)
        folder = self.values["input_dir"].get()
        extensions = self.values["wsi_extensions"].get()
        self.file_list.configure(state=tk.NORMAL)
        self.file_list.delete(0, tk.END)
        self.scanned_files = []
        self.selection_count.set("Scanning for WSI files...")
        self._set_busy(True)
        self.status.set("Searching for WSI files...")

        def worker():
            try:
                self.events.put(
                    (
                        "scan_done",
                        common.find_wsi_files(folder, extensions),
                    )
                )
            except Exception as error:
                self.events.put(("error", str(error)))
                self.events.put(("scan_done", None))

        threading.Thread(target=worker, daemon=True).start()

    def start_conversion(self):
        if self.busy:
            return
        if not self._validate_all_fields():
            return
        try:
            form_values = {
                key: variable.get() for key, variable in self.values.items()
            }
            form_values["deepzoom_format"] = self._format_key_for_label(
                form_values["deepzoom_format"]
            )
            settings = common.validate_settings(
                form_values,
                self._selected_files(),
                [destination.get() for destination in self.destinations],
            )
        except ValueError as error:
            messagebox.showerror("Check settings", str(error))
            return

        ok, message = common.check_resources(
            [destination.get() for destination in self.destinations]
        )
        if not ok:
            messagebox.showwarning("Insufficient resources", message)
            return

        # Ask how to handle WSI files that already have a complete DeepZoom
        # + thumbnail in the primary destination, before starting conversion.
        existing, total = common.count_existing_conversions(
            settings, self._selected_files()
        )
        if existing > 0:
            answer = messagebox.askyesnocancel(
                "DeepZoom output already exists",
                (
                    f"{existing} of {total} selected WSI file(s) already have a "
                    "complete DeepZoom + thumbnail in the primary destination.\n\n"
                    "Yes = Overwrite all existing output.\n"
                    "No = Skip all existing output.\n"
                    "Cancel = Abort conversion."
                ),
            )
            if answer is None:
                return
            settings["force_overwrite"] = bool(answer)

        self._scroll_to_widget(self.progress_frame)
        self._set_busy(True)
        self.progress.configure(maximum=1, value=0)
        self.stage_progress.configure(value=0)
        self.overall_percentage.set("0%")
        self.stage_percentage.set("0%")
        self.progress_status.set("Overall — Starting conversion")
        self.status.set("Conversion running...")
        self.report_info.set("Creating conversion log and Markdown report...")
        self.open_report_button.configure(state=tk.DISABLED)
        self.open_report_path = None
        self.run_started_monotonic = None
        self.run_started_at = "—"
        self.run_summary.set("Started: — | Finished: — | Average per file: —")
        for value in self.activity_values.values():
            value.set("—")
        for item in self.results_table.get_children():
            self.results_table.delete(item)
        self.log.configure(state=tk.NORMAL)
        self.log.delete("1.0", tk.END)
        self.log.configure(state=tk.DISABLED)
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
            elif event == "run_started":
                self.run_started_monotonic = time.perf_counter()
                self.run_started_at = payload.get("started_at", "—")
                self.run_summary.set(
                    f"Started: {self.run_started_at} | Finished: In progress"
                )
                self.report_info.set(
                    f"Log: {payload['log_path']} | Report: {payload['report_path']}"
                )
            elif event == "progress":
                total = max(1, payload["files_total"])
                overall = (
                    payload["completed_files"] + payload["stage_value"] / 4
                )
                self.progress.configure(maximum=total, value=min(total, overall))
                self.stage_progress.configure(value=payload["stage_value"])
                self.overall_percentage.set(
                    f"{round(min(total, overall) / total * 100)}%"
                )
                self.stage_percentage.set(
                    f"{round(payload['stage_value'] / 4 * 100)}%"
                )
                self.progress_status.set(
                    f"Overall — {payload['message']} — "
                    f"{payload['completed_files']} of {payload['files_total']} files complete"
                )
                self.status.set(payload["message"])
                self._update_activity(payload)
            elif event == "run_report":
                summary = payload["summary"]
                self.report_info.set(
                    f"Report: {payload['report_path']} | Text log: {payload['log_path']}"
                )
                self.open_report_path = payload["report_path"]
                self.open_report_button.configure(state=tk.NORMAL)
                self.activity_values["elapsed"].set(
                    common.format_duration(summary.get("duration_seconds"))
                )
                self.activity_values["counts"].set(
                    f"{summary.get('completed', 0)} completed / "
                    f"{summary.get('failed', 0)} failed / "
                    f"{summary.get('total', 0)} total"
                )
                self.run_summary.set(
                    f"Started: {self.run_started_at} | "
                    f"Finished: {payload.get('finished_at', '—')} | "
                    f"Total: {common.format_duration(summary.get('duration_seconds'))} | "
                    f"Average per completed file: "
                    f"{common.format_duration(summary.get('average_seconds'))}"
                )
                self._populate_results(summary.get("results", []))
                self.status.set(
                    f"Finished: {summary.get('completed', 0)} completed, "
                    f"{summary.get('failed', 0)} failed."
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
                    self.status.set(f"Found {len(payload):,} WSI file(s).")
            elif event == "error":
                self._append_log(f"\nError: {payload}\n")
                messagebox.showerror("Operation failed", payload)
            elif event == "done":
                self._set_busy(False)
                self.stage_progress.configure(value=4)
                self.overall_percentage.set("100%")
                self.stage_percentage.set("100%")
                if not getattr(self, "open_report_path", None):
                    self.status.set("Conversion ended. Review any error messages.")

        if self.run_started_monotonic is not None and self.busy:
            self.activity_values["elapsed"].set(
                common.format_duration(time.perf_counter() - self.run_started_monotonic)
            )
        self.root.after(100, self._poll_events)

    def _update_activity(self, payload):
        metrics = payload.get("metrics", {})
        self.activity_values["file"].set(
            payload.get("file") or "—"
        )
        self.activity_values["resolution"].set(metrics.get("resolution") or "—")
        self.activity_values["load"].set(
            common.format_duration(metrics.get("load_seconds"))
        )
        self.activity_values["deepzoom"].set(
            f"{metrics.get('deepzoom_status', 'Pending')} "
            f"({common.format_duration(metrics.get('deepzoom_seconds'))})"
        )
        self.activity_values["thumbnail"].set(
            f"{metrics.get('thumbnail_status', 'Pending')} "
            f"({common.format_duration(metrics.get('thumbnail_seconds'))})"
        )
        copies = metrics.get("copy_destinations", [])
        copy_summary = "; ".join(
            f"{item['status']} {item['destination']} "
            f"({common.format_duration(item.get('duration_seconds'))})"
            for item in copies
        )
        self.activity_values["copy"].set(
            copy_summary
            or f"Total {common.format_duration(metrics.get('copy_seconds'))}"
        )
        self.activity_values["slide"].set(
            common.format_duration(metrics.get("slide_seconds"))
        )
        if payload.get("run_elapsed_seconds") is not None:
            self.activity_values["elapsed"].set(
                common.format_duration(payload["run_elapsed_seconds"])
            )
        self.activity_values["counts"].set(
            f"{payload.get('completed_files', 0)} completed / "
            f"{payload.get('files_total', 0)} total"
        )
        self.activity_values["outputs"].set(
            "\n".join(
                path
                for path in (
                    metrics.get("deepzoom_output"),
                    metrics.get("thumbnail_output"),
                    *metrics.get("copy_outputs", []),
                )
                if path
            )
            or "—"
        )

    def _populate_results(self, results):
        for item in results:
            self.results_table.insert(
                "",
                tk.END,
                values=(
                    item.get("file", ""),
                    item.get("resolution") or "—",
                    common.format_duration(item.get("load_seconds")),
                    f"{item.get('deepzoom_status', '—')} "
                    f"({common.format_duration(item.get('deepzoom_seconds'))})",
                    f"{item.get('thumbnail_status', '—')} "
                    f"({common.format_duration(item.get('thumbnail_seconds'))})",
                    common.format_duration(item.get("copy_seconds")),
                    common.format_duration(item.get("slide_seconds")),
                    item.get("status", ""),
                    "; ".join(
                        f"{copy.get('destination')}: {copy.get('status')} "
                        f"({common.format_duration(copy.get('duration_seconds'))})"
                        for copy in item.get("copy_destinations", [])
                    ),
                    "; ".join(
                        path
                        for path in (
                            item.get("deepzoom_output"),
                            item.get("thumbnail_output"),
                            *item.get("copy_outputs", []),
                        )
                        if path
                    ),
                    item.get("error", ""),
                ),
            )

    def _toggle_log(self):
        self.log_visible = not self.log_visible
        if self.log_visible:
            self.log_frame.grid()
            self.log_frame.master.rowconfigure(8, weight=1)
            self.log_toggle.configure(text="Hide detailed text output")
        else:
            self.log_frame.grid_remove()
            self.log_frame.master.rowconfigure(8, weight=0)
            self.log_toggle.configure(text="Show detailed text output")

    def _toggle_options(self):
        self.options_visible = not self.options_visible
        if self.options_visible:
            self.options_frame.grid()
            self.options_toggle.configure(text="Hide DeepZoom and Robocopy options")
        else:
            self.options_frame.grid_remove()
            self.options_toggle.configure(text="Show DeepZoom and Robocopy options")
        self.root.after_idle(
            lambda: self.page_canvas.configure(
                scrollregion=self.page_canvas.bbox("all")
            )
        )

    def _scroll_page(self, event):
        if event.delta:
            self.page_canvas.yview_scroll(-int(event.delta / 120), "units")

    def _scroll_to_widget(self, widget):
        content_height = max(1, self.page_content.winfo_height())
        self.page_canvas.yview_moveto(widget.winfo_y() / content_height)

    def _open_report(self):
        try:
            common.open_report(self.open_report_path)
        except (OSError, RuntimeError) as error:
            messagebox.showerror("Could not open report", str(error))

    def _selected_files(self):
        return [self.scanned_files[index] for index in self.file_list.curselection()]

    def _update_selection_count(self, _event=None):
        selected = len(self.file_list.curselection())
        self.selection_count.set(
            f"{selected:,} of {len(self.scanned_files):,} WSI file(s) selected."
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
