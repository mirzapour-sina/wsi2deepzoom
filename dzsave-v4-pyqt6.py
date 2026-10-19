import queue
import sys
import threading
import time

from PyQt6.QtCore import QTimer, Qt
from PyQt6.QtWidgets import (
    QApplication,
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
    def __init__(self):
        super().__init__()
        self.events = queue.Queue()
        self.busy = False
        self.scanned_files = []
        self.destination_values = list(common.DEFAULT_DESTINATIONS)
        self.destination_fields = []
        self.fields = {
            key: QLineEdit(value)
            for key, value in common.DEFAULTS.items()
        }
        self.setWindowTitle("WSI DeepZoom Converter - PyQt6")
        self.resize(1000, 980)
        self.setMinimumSize(780, 740)
        self._build()

        self.timer = QTimer(self)
        self.timer.timeout.connect(self._poll_events)
        self.timer.start(100)

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
            folder_layout.addWidget(self.fields[key], row, 1)
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
        self.options_toggle.setText("Advanced DeepZoom and Robocopy options")
        self.options_toggle.setCheckable(True)
        layout.addWidget(self.options_toggle)
        options_container = QWidget()
        options_layout = QVBoxLayout(options_container)

        settings_box = QGroupBox()
        settings_layout = QFormLayout(settings_box)
        labels = (
            ("jpeg_quality", "DeepZoom JPEG quality"),
            ("thumbnail_size", "Thumbnail max size (pixels)"),
            ("thumbnail_quality", "Thumbnail JPEG quality"),
        )
        for key, label in labels:
            settings_layout.addRow(label, self.fields[key])
        add_collapsible_section(
            options_layout, "DeepZoom and thumbnail", settings_box
        )

        copy_box = QGroupBox()
        copy_layout = QFormLayout(copy_box)
        for key, label in (
            ("robocopy_threads", "Robocopy threads"),
            ("robocopy_retries", "Retry count"),
            ("robocopy_wait", "Wait between retries (seconds)"),
        ):
            copy_layout.addRow(label, self.fields[key])
        add_collapsible_section(options_layout, "Robocopy", copy_box)
        options_container.setVisible(False)
        self.options_toggle.toggled.connect(options_container.setVisible)
        layout.addWidget(options_container)

        selection = QGroupBox("Found TIFF files (checked files will be converted)")
        selection_layout = QVBoxLayout(selection)
        selection_tools = QHBoxLayout()
        self.selection_count = QLabel("Scan a source folder to list TIFF files.")
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
        self.status = QLabel("Ready. Scan for TIFF files or start conversion.")
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
        self.activity_values = {}
        detail_fields = (
            ("file", "Current file"),
            ("resolution", "Source resolution"),
            ("load", "Source load"),
            ("deepzoom", "DeepZoom"),
            ("thumbnail", "Thumbnail"),
            ("copy", "Copy"),
            ("slide", "Slide total"),
            ("elapsed", "Run elapsed"),
            ("counts", "File totals"),
            ("outputs", "Output paths"),
        )
        for index, (key, label) in enumerate(detail_fields):
            row, pair = divmod(index, 2)
            column = pair * 2
            details_grid.addWidget(QLabel(label), row, column)
            value = QLabel("—")
            value.setWordWrap(True)
            details_grid.addWidget(value, row, column + 1)
            self.activity_values[key] = value
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
        self.progress_status = QLabel("Ready")
        progress_layout.addWidget(self.progress_status)
        self.progress = QProgressBar()
        self.progress.setRange(0, 1)
        self.progress.setValue(0)
        self.progress.setFormat("%p%")
        progress_layout.addWidget(self.progress)
        progress_layout.addWidget(QLabel("Current slide"))
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
        self.start_button.clicked.connect(self.start_conversion)
        buttons.addWidget(self.start_button)
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
        for index, value in enumerate(self.destination_values):
            row_widget = QWidget()
            row = QHBoxLayout(row_widget)
            row.addWidget(QLabel(f"Destination {index + 1}"))
            field = QLineEdit(value)
            self.destination_fields.append(field)
            row.addWidget(field, 1)
            browse = QPushButton("Browse...")
            browse.clicked.connect(
                lambda checked=False, current=index: self._browse_destination(current)
            )
            row.addWidget(browse)
            remove = QPushButton("Remove")
            remove.setEnabled(index > 0 and len(self.destination_values) > 1)
            remove.clicked.connect(
                lambda checked=False, current=index: self._remove_destination(current)
            )
            row.addWidget(remove)
            self.destinations_layout.addWidget(row_widget)
        add = QPushButton("Add destination")
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
            f"{selected:,} of {len(self.scanned_files):,} TIFF file(s) selected."
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
        self.status.setText("Searching for TIFF files...")
        folder = self.fields["input_dir"].text()

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
                {key: field.text() for key, field in self.fields.items()},
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
        self.progress_status.setText("Starting conversion")
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
                self.progress_status.setText(
                    f"{payload['message']} — "
                    f"{payload['completed_files']} of {payload['files_total']} files complete"
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
                    self.status.setText(f"Found {len(payload):,} TIFF file(s).")
            elif event == "error":
                self.log.append(f"\nError: {payload}")
                QMessageBox.critical(self, "Operation failed", payload)
            elif event == "done":
                self._set_busy(False)
                self.stage_progress.setValue(400)
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
