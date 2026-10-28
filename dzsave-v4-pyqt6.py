import queue
import sys
import threading
import time
from pathlib import Path

from PyQt6.QtCore import QTimer, Qt
from PyQt6.QtGui import QKeySequence, QColor, QPalette
from PyQt6.QtWidgets import (
    QApplication,
    QComboBox,
    QFileDialog,
    QFormLayout,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QScrollArea,
    QShortcut,
    QTableWidget,
    QTableWidgetItem,
    QToolButton,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

import dzsave_v4_gui_common as common


def add_collapsible_section(layout, title, widget, expanded=False):
    toggle = QToolButton()
    toggle.setText(("[-] " if expanded else "[+] ") + title)
    toggle.setCheckable(True)
    toggle.setChecked(expanded)
    widget.setVisible(expanded)

    def set_expanded(visible):
        widget.setVisible(visible)
        toggle.setText(("[-] " if visible else "[+] ") + title)

    toggle.toggled.connect(set_expanded)
    layout.addWidget(toggle)
    layout.addWidget(widget)
    return toggle


class DzSaveWindow(QMainWindow):
    _NUMERIC_RULES = {
        "jpeg_quality": (1, 100, "JPEG quality must be between 1 and 100."),
        "thumbnail_size": (1, None, "Thumbnail size must be at least 1 pixel."),
        "thumbnail_quality": (1, 100, "Thumbnail quality must be between 1 and 100."),
        "robocopy_threads": (1, 128, "Copy threads must be between 1 and 128."),
        "robocopy_retries": (0, None, "Copy retries cannot be negative."),
        "robocopy_wait": (0, None, "Retry wait cannot be negative."),
        "conversion_threads": (1, 128, "Conversion threads must be between 1 and 128."),
    }

    def __init__(self):
        super().__init__()
        self.events = queue.Queue()
        self.busy = False
        self.dark_mode = False
        self.scanned_files = []
        self.destination_values = list(common.DEFAULT_DESTINATIONS)
        self.destination_fields = []
        self.fields = {
            key: QLineEdit(value)
            for key, value in common.DEFAULTS.items()
            if key != "deepzoom_format"
        }
        self.field_errors = {}
        self.deepzoom_format = QComboBox()
        for value, option in common.DEEPZOOM_FORMATS.items():
            self.deepzoom_format.addItem(option["label"], value)
        self.setWindowTitle("WSI DeepZoom Converter - PyQt6")
        self.resize(1000, 980)
        self.setMinimumSize(780, 740)
        self._build()

        self.timer = QTimer(self)
        self.timer.timeout.connect(self._poll_events)
        self.timer.start(100)
        self._add_shortcuts()
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
        field = self.fields.get(key)
        error_label = self.field_errors.get(key)
        if field is None or error_label is None:
            return True
        value = field.text()
        error = self._check_field(key, value)
        if error:
            field.setStyleSheet("border: 1px solid #c53030;")
            error_label.setText(error)
        else:
            field.setStyleSheet("")
            error_label.setText("")
        return error is None

    def _validate_all_fields(self):
        """Validate every editable field and return True when all are valid."""
        valid = True
        for key in self.fields:
            if not self._validate_field(key):
                valid = False
        return valid

    def _validate_destination(self, index):
        """Show or clear the inline error label for a destination field."""
        field = self.destination_fields[index]
        error_label = self.destination_errors[index]
        error = self._check_field(f"destination_{index}", field.text())
        if error:
            field.setStyleSheet("border: 1px solid #c53030;")
            error_label.setText(error)
        else:
            field.setStyleSheet("")
            error_label.setText("")
        return error is None

    def _validated_field(self, key):
        """Return a container pairing self.fields[key] with an inline error label."""
        container = QWidget()
        container_layout = QVBoxLayout(container)
        container_layout.setContentsMargins(0, 0, 0, 0)
        container_layout.setSpacing(2)
        container_layout.addWidget(self.fields[key])
        error = QLabel("")
        error.setStyleSheet("color: #c53030; font-size: 8pt;")
        error.setWordWrap(True)
        container_layout.addWidget(error)
        self.field_errors[key] = error
        self.fields[key].editingFinished.connect(
            lambda k=key: self._validate_field(k)
        )
        return container

    def _build(self):
        page_scroll = QScrollArea()
        page_scroll.setWidgetResizable(True)
        page_scroll.setFrameShape(QScrollArea.Shape.NoFrame)
        self.setCentralWidget(page_scroll)
        central = QWidget()
        page_scroll.setWidget(central)
        layout = QVBoxLayout(central)

        title = QLabel("WSI DeepZoom Converter")
        title.setStyleSheet("font-size: 20px; font-weight: bold;")
        layout.addWidget(title)
        layout.addWidget(
            QLabel("Convert TIFF slides, generate thumbnails, and copy DeepZoom output.")
        )

        folders = QGroupBox("Folders")
        folder_layout = QGridLayout(folders)
        for row, (key, label) in enumerate(
            (
                ("input_dir", "Source WSI folder"),
            )
        ):
            folder_layout.addWidget(QLabel(label), row, 0)
            folder_layout.addWidget(self._validated_field(key), row, 1)
            browse = QPushButton("Browse...")
            browse.clicked.connect(lambda checked=False, field=key: self._browse(field))
            folder_layout.addWidget(browse, row, 2)
        folder_layout.setColumnStretch(1, 1)
        layout.addWidget(folders)

        destinations = QGroupBox("Output destinations")
        self.destinations_layout = QVBoxLayout(destinations)
        self._render_destinations()
        layout.addWidget(destinations)

        self.options_toggle = QToolButton()
        self.options_toggle.setCheckable(True)
        self.options_toggle.setText("Show DeepZoom and Robocopy options")
        layout.addWidget(self.options_toggle)
        options_container = QWidget()
        options_layout = QVBoxLayout(options_container)

        settings_box = QGroupBox()
        settings_layout = QFormLayout(settings_box)
        labels = (
            ("jpeg_quality", "DeepZoom JPEG quality"),
            ("thumbnail_size", "Thumbnail max size (pixels)"),
            ("thumbnail_quality", "Thumbnail JPEG quality"),
            ("conversion_threads", "Conversion threads"),
        )
        for key, label in labels:
            settings_layout.addRow(label, self._validated_field(key))
        settings_layout.addRow("DeepZoom output format", self.deepzoom_format)
        settings_layout.addRow(
            "WSI file extensions (comma-separated)",
            self._validated_field("wsi_extensions"),
        )
        settings_layout.addRow(
            QLabel("Extensions must be supported by your installed libvips loaders.")
        )
        add_collapsible_section(
            options_layout, "DeepZoom and thumbnail", settings_box, expanded=True
        )

        copy_box = QGroupBox()
        copy_layout = QFormLayout(copy_box)
        for key, label in (
            ("robocopy_threads", "Robocopy threads"),
            ("robocopy_retries", "Retry count"),
            ("robocopy_wait", "Wait between retries (seconds)"),
        ):
            copy_layout.addRow(label, self._validated_field(key))
        add_collapsible_section(options_layout, "Robocopy", copy_box, expanded=True)
        options_container.setVisible(False)
        self.options_toggle.toggled.connect(options_container.setVisible)
        self.options_toggle.toggled.connect(
            lambda checked: self.options_toggle.setText(
                "Hide DeepZoom and Robocopy options"
                if checked
                else "Show DeepZoom and Robocopy options"
            )
        )
        layout.addWidget(options_container)

        selection = QGroupBox("Found WSI files (checked files will be converted)")
        selection_layout = QVBoxLayout(selection)
        selection_tools = QHBoxLayout()
        self.selection_count = QLabel("Scan a source folder to list WSI files.")
        selection_tools.addWidget(self.selection_count)
        selection_tools.addStretch(1)
        self.select_all_button = QPushButton("Select all")
        self.select_all_button.clicked.connect(lambda: self._set_all_files(True))
        selection_tools.addWidget(self.select_all_button)
        self.select_none_button = QPushButton("Select none")
        self.select_none_button.clicked.connect(lambda: self._set_all_files(False))
        selection_tools.addWidget(self.select_none_button)
        selection_layout.addLayout(selection_tools)
        self.file_list = QListWidget()
        self.file_list.setMinimumHeight(130)
        self.file_list.itemChanged.connect(self._update_selection_count)
        selection_layout.addWidget(self.file_list)
        layout.addWidget(selection)

        activity = QGroupBox()
        activity_layout = QVBoxLayout(activity)
        self.status = QLabel("Ready. Scan for WSI files or start conversion.")
        activity_layout.addWidget(self.status)
        self.log_toggle = QToolButton()
        self.log_toggle.setText("Show detailed text output")
        self.log_toggle.setCheckable(True)
        self.log_toggle.toggled.connect(self._toggle_log)
        activity_layout.addWidget(self.log_toggle)
        report_row = QHBoxLayout()
        self.report_info = QLabel("Reports will be saved in the first destination.")
        self.report_info.setWordWrap(True)
        report_row.addWidget(self.report_info, 1)
        self.open_report_button = QPushButton("Open report")
        self.open_report_button.setEnabled(False)
        self.open_report_button.clicked.connect(self._open_report)
        report_row.addWidget(self.open_report_button)
        activity_layout.addLayout(report_row)
        details = QGroupBox()
        details_grid = QGridLayout(details)
        details_grid.setColumnStretch(1, 1)
        details_grid.setColumnStretch(3, 1)
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
        )
        for index, (key, label) in enumerate(detail_fields):
            row, pair = divmod(index, 2)
            column = pair * 2
            details_grid.addWidget(QLabel(label), row, column)
            value = QLabel("—")
            value.setWordWrap(True)
            details_grid.addWidget(value, row, column + 1)
            self.activity_values[key] = value
        details_grid.addWidget(QLabel("File totals"), 4, 0)
        counts_value = QLabel("—")
        counts_value.setWordWrap(True)
        details_grid.addWidget(counts_value, 4, 1, 1, 3)
        self.activity_values["counts"] = counts_value
        details_grid.addWidget(QLabel("Output paths"), 5, 0)
        outputs_value = QLabel("—")
        outputs_value.setWordWrap(True)
        details_grid.addWidget(outputs_value, 5, 1, 1, 3)
        self.activity_values["outputs"] = outputs_value
        add_collapsible_section(
            activity_layout, "Live conversion details", details
        )
        self.run_summary = QLabel("Started: — | Finished: — | Average per file: —")
        self.run_summary.setWordWrap(True)
        activity_layout.addWidget(self.run_summary)
        results_box = QGroupBox()
        results_layout = QVBoxLayout(results_box)
        self.results_table = QTableWidget(0, 11)
        self.results_table.setHorizontalHeaderLabels(
            [
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
            ]
        )
        self.results_table.setFixedHeight(190)
        self.results_table.verticalHeader().setVisible(False)
        self.results_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.results_table.setWordWrap(False)
        self.results_table.setHorizontalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAsNeeded
        )
        self.results_table.setVerticalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAsNeeded
        )
        self.results_table.setSizeAdjustPolicy(
            QTableWidget.SizeAdjustPolicy.AdjustToContentsOnFirstShow
        )
        results_layout.addWidget(self.results_table)
        add_collapsible_section(activity_layout, "Per-file results", results_box)
        self.log = QTextEdit()
        self.log.setReadOnly(True)
        self.log.setFontFamily("Consolas")
        self.log.setVisible(False)
        self.log.setMaximumHeight(140)
        activity_layout.addWidget(self.log)
        add_collapsible_section(layout, "Activity", activity, expanded=True)

        progress_box = QGroupBox("Conversion progress")
        progress_layout = QVBoxLayout(progress_box)
        overall_row = QHBoxLayout()
        self.progress_status = QLabel("Overall — Ready")
        overall_row.addWidget(self.progress_status)
        self.overall_percent = QLabel("0%")
        overall_row.addWidget(self.overall_percent)
        overall_row.addStretch(1)
        progress_layout.addLayout(overall_row)
        self.progress = QProgressBar()
        self.progress.setRange(0, 1)
        self.progress.setValue(0)
        self.progress.setFormat("%p%")
        progress_layout.addWidget(self.progress)
        slide_row = QHBoxLayout()
        self.slide_status = QLabel("Current slide — Ready")
        slide_row.addWidget(self.slide_status)
        self.stage_percent = QLabel("0%")
        slide_row.addWidget(self.stage_percent)
        slide_row.addStretch(1)
        progress_layout.addLayout(slide_row)
        self.stage_progress = QProgressBar()
        self.stage_progress.setRange(0, 400)
        self.stage_progress.setFormat("%p%")
        progress_layout.addWidget(self.stage_progress)
        layout.addWidget(progress_box)
        buttons = QHBoxLayout()
        buttons.addStretch(1)
        self.scan_button = QPushButton("Scan files")
        self.scan_button.clicked.connect(self.scan)
        buttons.addWidget(self.scan_button)
        self.start_button = QPushButton("Start conversion")
        self.start_button.setStyleSheet(
            "QPushButton {"
            "  background: #2563eb;"
            "  color: white;"
            "  font-weight: bold;"
            "  border-radius: 4px;"
            "  padding: 6px 16px;"
            "}"
            "QPushButton:hover { background: #1d4ed8; }"
            "QPushButton:pressed { background: #1e40af; }"
            "QPushButton:disabled { background: #9ca3af; color: #e5e7eb; }"
        )
        self.start_button.clicked.connect(self.start_conversion)
        buttons.addWidget(self.start_button)
        self.cancel_button = QPushButton("Cancel")
        self.cancel_button.clicked.connect(self._request_cancel)
        self.cancel_button.setEnabled(False)
        buttons.addWidget(self.cancel_button)
        self.reset_button = QPushButton("Reset to defaults")
        self.reset_button.clicked.connect(self._reset_defaults)
        buttons.addWidget(self.reset_button)
        self.dark_toggle = QPushButton("Dark mode")
        self.dark_toggle.setCheckable(True)
        self.dark_toggle.setChecked(False)
        self.dark_toggle.clicked.connect(self._toggle_dark_mode)
        buttons.addWidget(self.dark_toggle)
        layout.addLayout(buttons)
        layout.addStretch(1)

    def _browse(self, key):
        folder = QFileDialog.getExistingDirectory(
            self, "Select folder", self.fields[key].text()
        )
        if folder:
            self.fields[key].setText(folder)

    def _capture_destinations(self):
        self.destination_values = [
            field.text() for field in self.destination_fields
        ]

    def _render_destinations(self):
        while self.destinations_layout.count():
            item = self.destinations_layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()
        self.destination_fields = []
        self.destination_errors = []
        for index, value in enumerate(self.destination_values):
            row_widget = QWidget()
            row = QVBoxLayout(row_widget)
            row.setContentsMargins(0, 0, 0, 0)
            row.setSpacing(2)
            field_row = QHBoxLayout()
            field_row.addWidget(QLabel(f"Destination {index + 1}"))
            field = QLineEdit(value)
            self.destination_fields.append(field)
            field.editingFinished.connect(
                lambda k=index: self._validate_destination(k)
            )
            field_row.addWidget(field, 1)
            browse = QPushButton("Browse...")
            browse.setToolTip("Browse for a destination folder.")
            browse.clicked.connect(
                lambda checked=False, current=index: self._browse_destination(current)
            )
            field_row.addWidget(browse)
            remove = QPushButton("Remove")
            remove.setEnabled(index > 0 and len(self.destination_values) > 1)
            remove.clicked.connect(
                lambda checked=False, current=index: self._remove_destination(current)
            )
            field_row.addWidget(remove)
            remove.setToolTip("Remove this destination.")
            row.addLayout(field_row)
            error = QLabel("")
            error.setStyleSheet("color: #c53030; font-size: 8pt;")
            error.setWordWrap(True)
            row.addWidget(error)
            self.destination_errors.append(error)
            self.field_errors[f"destination_{index}"] = error
            self.destinations_layout.addWidget(row_widget)
        add = QPushButton("Add destination")
        add.setToolTip("Add another output destination.")
        add.clicked.connect(self._add_destination)
        self.destinations_layout.addWidget(add)

    def _browse_destination(self, index):
        field = self.destination_fields[index]
        folder = QFileDialog.getExistingDirectory(self, "Select folder", field.text())
        if folder:
            field.setText(folder)

    def _add_destination(self):
        self._capture_destinations()
        self.destination_values.append("")
        self._render_destinations()

    def _remove_destination(self, index):
        if len(self.destination_values) > 1 and 0 < index < len(self.destination_values):
            self._capture_destinations()
            self.destination_values.pop(index)
            self._render_destinations()

    def _set_busy(self, busy):
        self.busy = busy
        self.scan_button.setEnabled(not busy)
        self.start_button.setEnabled(not busy)
        self.file_list.setEnabled(not busy)
        self.select_all_button.setEnabled(not busy)
        self.select_none_button.setEnabled(not busy)
        self.cancel_button.setEnabled(busy)

    def _request_cancel(self):
        common.request_cancel()
        self.status.setText("Cancellation requested. Stopping after current file...")

    def _reset_defaults(self):
        if self.busy:
            return
        for key, field in self.fields.items():
            field.setText(common.DEFAULTS.get(key, ""))
        index = self.deepzoom_format.findData(common.DEFAULTS["deepzoom_format"])
        if index >= 0:
            self.deepzoom_format.setCurrentIndex(index)
        self.destination_values = list(common.DEFAULT_DESTINATIONS)
        self._render_destinations()
        for key, error in self.field_errors.items():
            error.setText("")
            field = self.fields.get(key)
            if field is not None:
                field.setStyleSheet("")
        self.status.setText("Settings reset to defaults.")

    def _toggle_dark_mode(self, checked):
        self.dark_mode = checked
        self.dark_toggle.setText("Light mode" if self.dark_mode else "Dark mode")
        self._apply_dark_mode(self.dark_mode)

    def _apply_dark_mode(self, dark):
        app = QApplication.instance()
        if app is None:
            return
        palette = QPalette()
        if dark:
            palette.setColor(QPalette.ColorRole.Window, QColor(43, 43, 43))
            palette.setColor(QPalette.ColorRole.WindowText, QColor(255, 255, 255))
            palette.setColor(QPalette.ColorRole.Base, QColor(30, 30, 30))
            palette.setColor(QPalette.ColorRole.AlternateBase, QColor(58, 58, 58))
            palette.setColor(QPalette.ColorRole.Text, QColor(255, 255, 255))
            palette.setColor(QPalette.ColorRole.Button, QColor(58, 58, 58))
            palette.setColor(QPalette.ColorRole.ButtonText, QColor(255, 255, 255))
            palette.setColor(QPalette.ColorRole.Highlight, QColor(42, 130, 218))
            palette.setColor(QPalette.ColorRole.HighlightedText, QColor(255, 255, 255))
        app.setPalette(palette)

    def _add_shortcuts(self):
        self.shortcut_escape = QShortcut(QKeySequence(Qt.Key.Key_Escape), self)
        self.shortcut_escape.activated.connect(self._on_escape)
        self.shortcut_f5 = QShortcut(QKeySequence(Qt.Key.Key_F5), self)
        self.shortcut_f5.activated.connect(self._on_f5)
        self.shortcut_reset = QShortcut(QKeySequence("Ctrl+R"), self)
        self.shortcut_reset.activated.connect(self._on_reset_shortcut)

    def _add_tooltips(self):
        self.scan_button.setToolTip("Scan the source folder for WSI files.")
        self.start_button.setToolTip("Start conversion of the selected WSI files (F5).")
        self.cancel_button.setToolTip("Cancel the running conversion after the current file (Escape).")
        self.reset_button.setToolTip("Reset all settings to their default values (Ctrl+R).")
        self.open_report_button.setToolTip("Open the generated conversion report.")
        self.log_toggle.setToolTip("Show or hide the detailed text output.")
        self.dark_toggle.setToolTip("Toggle dark mode.")

    def _on_escape(self):
        if self.cancel_button.isEnabled():
            self._request_cancel()

    def _on_f5(self):
        if self.start_button.isEnabled():
            self.start_conversion()

    def _on_reset_shortcut(self):
        if self.reset_button.isEnabled():
            self._reset_defaults()

    def _set_all_files(self, checked):
        state = Qt.CheckState.Checked if checked else Qt.CheckState.Unchecked
        for index in range(self.file_list.count()):
            self.file_list.item(index).setCheckState(state)

    def _update_selection_count(self, _item=None):
        selected = sum(
            self.file_list.item(index).checkState() == Qt.CheckState.Checked
            for index in range(self.file_list.count())
        )
        self.selection_count.setText(
            f"{selected:,} of {len(self.scanned_files):,} WSI file(s) selected."
        )

    def _selected_files(self):
        return [
            self.file_list.item(index).data(Qt.ItemDataRole.UserRole)
            for index in range(self.file_list.count())
            if self.file_list.item(index).checkState() == Qt.CheckState.Checked
        ]

    def scan(self):
        if self.busy:
            return
        self._set_busy(True)
        self.scanned_files = []
        self.file_list.clear()
        self._update_selection_count()
        self.status.setText("Searching for WSI files...")
        folder = self.fields["input_dir"].text()
        extensions = self.fields["wsi_extensions"].text()

        def worker():
            try:
                self.events.put(("scan_done", common.find_wsi_files(folder, extensions)))
            except Exception as error:
                self.events.put(("error", str(error)))
                self.events.put(("scan_done", None))

        threading.Thread(target=worker, daemon=True).start()

    def start_conversion(self):
        if self.busy:
            return
        self._validate_all_fields()
        try:
            settings = common.validate_settings(
                {
                    **{key: field.text() for key, field in self.fields.items()},
                    "deepzoom_format": self.deepzoom_format.currentData(),
                },
                self._selected_files(),
                [field.text() for field in self.destination_fields],
            )
        except ValueError as error:
            QMessageBox.critical(self, "Check settings", str(error))
            return

        self._set_busy(True)
        self.progress.setRange(0, 1)
        self.progress.setValue(0)
        self.stage_progress.setValue(0)
        self.progress_status.setText("Overall — Starting conversion")
        self.overall_percent.setText("0%")
        self.slide_status.setText("Current slide — Starting conversion")
        self.stage_percent.setText("0%")
        self.status.setText("Conversion running...")
        self.report_info.setText("Creating conversion log and Markdown report...")
        self.open_report_button.setEnabled(False)
        self.open_report_path = None
        self.run_started_monotonic = None
        self.run_started_at = "—"
        self.run_summary.setText("Started: — | Finished: — | Average per file: —")
        self.results_table.setRowCount(0)
        for value in self.activity_values.values():
            value.setText("—")
        self.log.clear()
        self.log.append("Starting conversion...")
        common.run_conversion(settings, self.events)

    def _poll_events(self):
        while True:
            try:
                event, payload = self.events.get_nowait()
            except queue.Empty:
                break

            if event == "log":
                self.log.moveCursor(self.log.textCursor().MoveOperation.End)
                self.log.insertPlainText(payload)
                self.log.ensureCursorVisible()
            elif event == "run_started":
                self.run_started_monotonic = time.perf_counter()
                self.run_started_at = payload.get("started_at", "—")
                self.run_summary.setText(
                    f"Started: {self.run_started_at} | Finished: In progress"
                )
                self.report_info.setText(
                    f"Log: {payload['log_path']} | Report: {payload['report_path']}"
                )
            elif event == "progress":
                total = max(1, payload["files_total"])
                overall = (
                    payload["completed_files"] + payload["stage_value"] / 4
                )
                self.progress.setRange(0, total * 100)
                self.progress.setValue(round(min(total, overall) * 100))
                self.stage_progress.setValue(round(payload["stage_value"] * 100))
                self.progress_status.setText(f"Overall — {payload['message']}")
                self.overall_percent.setText(
                    f"{round(min(total, overall) / total * 100)}%"
                )
                self.slide_status.setText(f"Current slide — {payload['message']}")
                self.stage_percent.setText(
                    f"{round(payload['stage_value'] / 4 * 100)}%"
                )
                self.status.setText(payload["message"])
                self._update_activity(payload)
            elif event == "run_report":
                summary = payload["summary"]
                self.open_report_path = payload["report_path"]
                self.report_info.setText(
                    f"Report: {payload['report_path']} | Text log: {payload['log_path']}"
                )
                self.open_report_button.setEnabled(True)
                self.activity_values["elapsed"].setText(
                    common.format_duration(summary.get("duration_seconds"))
                )
                self.activity_values["counts"].setText(
                    f"{summary.get('completed', 0)} completed / "
                    f"{summary.get('failed', 0)} failed / "
                    f"{summary.get('total', 0)} total"
                )
                self.run_summary.setText(
                    f"Started: {self.run_started_at} | "
                    f"Finished: {payload.get('finished_at', '—')} | "
                    f"Total: {common.format_duration(summary.get('duration_seconds'))} | "
                    f"Average per completed file: "
                    f"{common.format_duration(summary.get('average_seconds'))}"
                )
                self._populate_results(summary.get("results", []))
                self.status.setText(
                    f"Finished: {summary.get('completed', 0)} completed, "
                    f"{summary.get('failed', 0)} failed."
                )
            elif event == "scan_done":
                self._set_busy(False)
                if payload is not None:
                    self.scanned_files = payload
                    self.file_list.blockSignals(True)
                    self.file_list.clear()
                    for path in payload:
                        item = QListWidgetItem(str(path))
                        item.setData(Qt.ItemDataRole.UserRole, str(path))
                        item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
                        item.setCheckState(Qt.CheckState.Checked)
                        self.file_list.addItem(item)
                    self.file_list.blockSignals(False)
                    self._update_selection_count()
                    self.status.setText(f"Found {len(payload):,} WSI file(s).")
            elif event == "error":
                self.log.append(f"\nError: {payload}")
                QMessageBox.critical(self, "Operation failed", payload)
            elif event == "done":
                self._set_busy(False)
                self.stage_progress.setValue(400)
                self.overall_percent.setText("100%")
                self.stage_percent.setText("100%")
                if not self.open_report_path:
                    self.status.setText("Conversion ended. Review any error messages.")
        if self.run_started_monotonic is not None and self.busy:
            self.activity_values["elapsed"].setText(
                common.format_duration(time.perf_counter() - self.run_started_monotonic)
            )

    def _update_activity(self, payload):
        metrics = payload.get("metrics", {})
        self.activity_values["file"].setText(
            payload.get("file") or "—"
        )
        self.activity_values["resolution"].setText(metrics.get("resolution") or "—")
        self.activity_values["load"].setText(
            common.format_duration(metrics.get("load_seconds"))
        )
        self.activity_values["deepzoom"].setText(
            f"{metrics.get('deepzoom_status', 'Pending')} "
            f"({common.format_duration(metrics.get('deepzoom_seconds'))})"
        )
        self.activity_values["thumbnail"].setText(
            f"{metrics.get('thumbnail_status', 'Pending')} "
            f"({common.format_duration(metrics.get('thumbnail_seconds'))})"
        )
        copies = metrics.get("copy_destinations", [])
        copy_summary = "; ".join(
            f"{item['status']} {item['destination']} "
            f"({common.format_duration(item.get('duration_seconds'))})"
            for item in copies
        )
        self.activity_values["copy"].setText(
            copy_summary
            or f"Total {common.format_duration(metrics.get('copy_seconds'))}"
        )
        self.activity_values["slide"].setText(
            common.format_duration(metrics.get("slide_seconds"))
        )
        if payload.get("run_elapsed_seconds") is not None:
            self.activity_values["elapsed"].setText(
                common.format_duration(payload["run_elapsed_seconds"])
            )
        self.activity_values["counts"].setText(
            f"{payload.get('completed_files', 0)} completed / "
            f"{payload.get('files_total', 0)} total"
        )
        self.activity_values["outputs"].setText(
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
        self.results_table.setRowCount(len(results))
        for row, item in enumerate(results):
            values = (
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
            )
            for column, text in enumerate(values):
                self.results_table.setItem(row, column, QTableWidgetItem(str(text)))

    def _toggle_log(self, visible):
        self.log.setVisible(visible)
        self.log_toggle.setText(
            "Hide detailed text output" if visible else "Show detailed text output"
        )

    def _open_report(self):
        try:
            common.open_report(self.open_report_path)
        except (OSError, RuntimeError) as error:
            QMessageBox.critical(self, "Could not open report", str(error))


def main():
    app = QApplication(sys.argv)
    window = DzSaveWindow()
    if "--self-test" in sys.argv[1:]:
        window.close()
        return
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
