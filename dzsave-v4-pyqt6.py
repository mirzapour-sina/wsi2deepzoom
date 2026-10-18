import queue
import sys
import threading

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
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

import dzsave_v4_gui_common as common


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
        central = QWidget()
        self.setCentralWidget(central)
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

        settings_box = QGroupBox("Conversion and thumbnail settings")
        settings_layout = QFormLayout(settings_box)
        labels = (
            ("jpeg_quality", "DeepZoom JPEG quality"),
            ("thumbnail_size", "Thumbnail max size (pixels)"),
            ("thumbnail_quality", "Thumbnail JPEG quality"),
        )
        for key, label in labels:
            settings_layout.addRow(label, self.fields[key])
        layout.addWidget(settings_box)

        copy_box = QGroupBox("Robocopy settings")
        copy_layout = QFormLayout(copy_box)
        for key, label in (
            ("robocopy_threads", "Robocopy threads"),
            ("robocopy_retries", "Retry count"),
            ("robocopy_wait", "Wait between retries (seconds)"),
        ):
            copy_layout.addRow(label, self.fields[key])
        layout.addWidget(copy_box)

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

        activity = QGroupBox("Activity")
        activity_layout = QVBoxLayout(activity)
        self.status = QLabel("Ready. Scan for TIFF files or start conversion.")
        activity_layout.addWidget(self.status)
        self.log = QTextEdit()
        self.log.setReadOnly(True)
        self.log.setFontFamily("Consolas")
        activity_layout.addWidget(self.log, 1)
        layout.addWidget(activity, 1)

        progress_box = QGroupBox("Conversion progress")
        progress_layout = QVBoxLayout(progress_box)
        self.progress_status = QLabel("Ready")
        progress_layout.addWidget(self.progress_status)
        self.progress = QProgressBar()
        self.progress.setRange(0, 1)
        self.progress.setValue(0)
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
            remove.setEnabled(len(self.destination_values) > 1)
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
        if len(self.destination_values) > 1:
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
                self.stage_progress.setValue(4)
                self.status.setText("Conversion finished. See the activity log for details.")


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
