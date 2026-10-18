import queue
import sys
import threading

from PySide6.QtCore import QTimer, Qt
from PySide6.QtWidgets import (
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
        self.fields = {
            key: QLineEdit(value)
            for key, value in common.DEFAULTS.items()
        }
        self.setWindowTitle("WSI DeepZoom Converter - PySide6")
        self.resize(1000, 900)
        self.setMinimumSize(780, 680)
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
                ("primary_dir", "Primary destination"),
                ("secondary_dir", "Secondary destination"),
            )
        ):
            folder_layout.addWidget(QLabel(label), row, 0)
            folder_layout.addWidget(self.fields[key], row, 1)
            browse = QPushButton("Browse...")
            browse.clicked.connect(lambda checked=False, field=key: self._browse(field))
            folder_layout.addWidget(browse, row, 2)
        folder_layout.setColumnStretch(1, 1)
        layout.addWidget(folders)

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

        self.progress = QProgressBar()
        self.progress.setRange(0, 1)
        self.progress.setValue(0)
        layout.addWidget(self.progress)
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
            )
        except ValueError as error:
            QMessageBox.critical(self, "Check settings", str(error))
            return

        self._set_busy(True)
        self.progress.setRange(0, 1)
        self.progress.setValue(0)
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
                cursor = self.log.textCursor()
                cursor.movePosition(cursor.MoveOperation.End)
                self.log.setTextCursor(cursor)
                self.log.insertPlainText(payload)
                self.log.ensureCursorVisible()
            elif event == "progress":
                current, total, percentage = payload
                self.progress.setRange(0, total)
                self.progress.setValue(current)
                self.status.setText(
                    f"Completed {current} of {total} files ({percentage}%)."
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
