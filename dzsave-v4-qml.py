import queue
import sys
import threading
from pathlib import Path

from PySide6.QtCore import QObject, QTimer, QUrl, Signal, Slot, Property
from PySide6.QtWidgets import QApplication, QFileDialog, QMessageBox
from PySide6.QtQml import QQmlApplicationEngine

import dzsave_v4_gui_common as common


class DzSaveController(QObject):
    fieldsChanged = Signal()
    filesChanged = Signal()
    selectionChanged = Signal()
    statusChanged = Signal()
    logChanged = Signal()
    progressChanged = Signal()
    busyChanged = Signal()
    errorRaised = Signal(str)

    def __init__(self):
        super().__init__()
        self.events = queue.Queue()
        self._fields = dict(common.DEFAULTS)
        self._files = []
        self._status = "Ready. Scan for TIFF files or start conversion."
        self._log = ""
        self._progress = 0
        self._progress_max = 1
        self._busy = False
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._poll_events)
        self._timer.start(100)

    @Property("QVariantMap", notify=fieldsChanged)
    def fields(self):
        return dict(self._fields)

    @Property("QVariantList", notify=filesChanged)
    def scannedFiles(self):
        return list(self._files)

    @Property(str, notify=selectionChanged)
    def selectionSummary(self):
        selected = sum(1 for item in self._files if item["checked"])
        return f"{selected:,} of {len(self._files):,} TIFF file(s) selected."

    @Slot(int, bool)
    def setFileSelected(self, index, checked):
        if 0 <= index < len(self._files) and self._files[index]["checked"] != checked:
            self._files[index]["checked"] = checked
            self.filesChanged.emit()
            self.selectionChanged.emit()

    @Slot(bool)
    def selectAllFiles(self, checked):
        changed = False
        for item in self._files:
            if item["checked"] != checked:
                item["checked"] = checked
                changed = True
        if changed:
            self.selectionChanged.emit()
            self.filesChanged.emit()

    def _selected_files(self):
        return [item["path"] for item in self._files if item["checked"]]

    @Slot(str, result=str)
    def field(self, key):
        return self._fields.get(key, "")

    @Slot(str, str)
    def setField(self, key, value):
        if key in self._fields and self._fields[key] != value:
            self._fields[key] = value
            self.fieldsChanged.emit()

    @Slot(str, result=str)
    def browse(self, key):
        selected = QFileDialog.getExistingDirectory(
            None, "Select folder", self._fields.get(key, "")
        )
        if selected:
            self.setField(key, selected)
        return selected

    @Property(str, notify=statusChanged)
    def statusText(self):
        return self._status

    @Property(str, notify=logChanged)
    def logText(self):
        return self._log

    @Property(int, notify=progressChanged)
    def progressValue(self):
        return self._progress

    @Property(int, notify=progressChanged)
    def progressMaximum(self):
        return self._progress_max

    @Property(bool, notify=busyChanged)
    def isBusy(self):
        return self._busy

    def _set_busy(self, busy):
        if self._busy != busy:
            self._busy = busy
            self.busyChanged.emit()

    def _append_log(self, text):
        self._log += text
        self.logChanged.emit()

    @Slot()
    def scan(self):
        if self._busy:
            return
        folder = self._fields["input_dir"]
        self._set_busy(True)
        self._files = []
        self.filesChanged.emit()
        self.selectionChanged.emit()
        self._status = "Searching for TIFF files..."
        self.statusChanged.emit()

        def worker():
            try:
                files = common.find_wsi_files(folder)
                self.events.put(("scan_done", [str(path) for path in files]))
            except Exception as error:
                self.events.put(("error", str(error)))
                self.events.put(("scan_done", None))

        threading.Thread(target=worker, daemon=True).start()

    @Slot()
    def startConversion(self):
        if self._busy:
            return
        try:
            settings = common.validate_settings(self._fields, self._selected_files())
        except ValueError as error:
            QMessageBox.critical(None, "Check settings", str(error))
            return

        self._set_busy(True)
        self._progress = 0
        self._progress_max = 1
        self.progressChanged.emit()
        self._status = "Conversion running..."
        self.statusChanged.emit()
        self._append_log("Starting conversion...\n")
        common.run_conversion(settings, self.events)

    @Slot()
    def _poll_events(self):
        while True:
            try:
                event, payload = self.events.get_nowait()
            except queue.Empty:
                break

            if event == "log":
                self._append_log(payload)
            elif event == "progress":
                self._progress, self._progress_max, percentage = payload
                self.progressChanged.emit()
                self._status = (
                    f"Completed {self._progress} of {self._progress_max} "
                    f"files ({percentage}%)."
                )
                self.statusChanged.emit()
            elif event == "scan_done":
                self._set_busy(False)
                if payload is not None:
                    self._files = [
                        {"path": path, "checked": True} for path in payload
                    ]
                    self.filesChanged.emit()
                    self.selectionChanged.emit()
                    self._status = f"Found {len(payload):,} TIFF file(s)."
                    self.statusChanged.emit()
            elif event == "error":
                self._append_log(f"\nError: {payload}\n")
                self.errorRaised.emit(payload)
            elif event == "done":
                self._set_busy(False)
                self._status = "Conversion finished. See the activity log for details."
                self.statusChanged.emit()


def main():
    app = QApplication(sys.argv)
    engine = QQmlApplicationEngine()
    controller = DzSaveController()
    engine.rootContext().setContextProperty("controller", controller)
    qml_file = common.APP_DIR / "dzsave-v4.qml"
    qml_modules = common.APP_DIR / "PySide6" / "qml"
    if qml_modules.is_dir():
        engine.addImportPath(str(qml_modules))
    engine.load(QUrl.fromLocalFile(str(qml_file)))
    if not engine.rootObjects():
        raise RuntimeError(f"Could not load QML interface: {qml_file}")

    controller.errorRaised.connect(
        lambda message: QMessageBox.critical(None, "Operation failed", message)
    )
    if "--self-test" in sys.argv[1:]:
        engine.rootObjects()[0].close()
        return 0
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
