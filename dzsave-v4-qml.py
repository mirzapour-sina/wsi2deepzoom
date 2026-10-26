import os
import queue
import sys
import threading
import time
from pathlib import Path

os.environ.setdefault("QT_QUICK_CONTROLS_STYLE", "Basic")

from PySide6.QtCore import QObject, QTimer, QUrl, Signal, Slot, Property
from PySide6.QtWidgets import QApplication, QFileDialog, QMessageBox
from PySide6.QtQml import QQmlApplicationEngine

import dzsave_v4_gui_common as common


class DzSaveController(QObject):
    _NUMERIC_RULES = {
        "jpeg_quality": (1, 100, "JPEG quality must be between 1 and 100."),
        "thumbnail_size": (1, None, "Thumbnail size must be at least 1 pixel."),
        "thumbnail_quality": (1, 100, "Thumbnail quality must be between 1 and 100."),
        "robocopy_threads": (1, 128, "Copy threads must be between 1 and 128."),
        "robocopy_retries": (0, None, "Copy retries cannot be negative."),
        "robocopy_wait": (0, None, "Retry wait cannot be negative."),
        "conversion_threads": (1, 128, "Conversion threads must be between 1 and 128."),
    }

    fieldsChanged = Signal()
    destinationsChanged = Signal()
    filesChanged = Signal()
    selectionChanged = Signal()
    statusChanged = Signal()
    logChanged = Signal()
    progressChanged = Signal()
    busyChanged = Signal()
    errorRaised = Signal(str)
    reportChanged = Signal()
    activityChanged = Signal()
    resultsChanged = Signal()
    runSummaryChanged = Signal()
    fieldErrorsChanged = Signal()
    darkModeChanged = Signal()

    def __init__(self):
        super().__init__()
        self.events = queue.Queue()
        self._fields = dict(common.DEFAULTS)
        self._destinations = list(common.DEFAULT_DESTINATIONS)
        self._files = []
        self._status = "Ready. Scan for WSI files or start conversion."
        self._log = ""
        self._progress = 0
        self._progress_max = 1
        self._stage_progress = 0
        self._progress_description = "Ready"
        self._report_path = ""
        self._report_info = "Reports will be saved in the first destination."
        self._run_started_monotonic = None
        self._activity = {
            "file": "—",
            "resolution": "—",
            "load": "—",
            "deepzoom": "—",
            "thumbnail": "—",
            "copy": "—",
            "slide": "—",
            "elapsed": "—",
            "counts": "—",
            "outputs": "—",
        }
        self._results = []
        self._run_summary = "Started: — | Finished: — | Average per file: —"
        self._busy = False
        self._field_errors = {}
        self._dark_mode = False
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._poll_events)
        self._timer.start(100)

    @Property("QVariantMap", notify=fieldsChanged)
    def fields(self):
        return dict(self._fields)

    deepzoomFormatsChanged = Signal()

    @Property("QVariantList", notify=deepzoomFormatsChanged)
    def deepzoomFormats(self):
        return [
            {"value": value, "label": option["label"]}
            for value, option in common.DEEPZOOM_FORMATS.items()
        ]

    @Property("QVariantList", notify=destinationsChanged)
    def destinations(self):
        return list(self._destinations)

    @Slot()
    def addDestination(self):
        self._destinations.append("")
        self.destinationsChanged.emit()

    @Slot(int)
    def removeDestination(self, index):
        if len(self._destinations) > 1 and 0 < index < len(self._destinations):
            self._destinations.pop(index)
            self.destinationsChanged.emit()

    @Slot(int, str)
    def setDestination(self, index, path):
        if 0 <= index < len(self._destinations):
            self._destinations[index] = path
            self.destinationsChanged.emit()

    @Slot(int)
    def browseDestination(self, index):
        if not 0 <= index < len(self._destinations):
            return
        selected = QFileDialog.getExistingDirectory(
            None, "Select destination folder", self._destinations[index]
        )
        if selected:
            self.setDestination(index, selected)

    @Property("QVariantList", notify=filesChanged)
    def scannedFiles(self):
        return list(self._files)

    @Property(str, notify=selectionChanged)
    def selectionSummary(self):
        selected = sum(1 for item in self._files if item["checked"])
        return f"{selected:,} of {len(self._files):,} WSI file(s) selected."

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

    @Property(int, notify=progressChanged)
    def progressPercent(self):
        if self._progress_max <= 0:
            return 0
        return round(self._progress * 100 / self._progress_max)

    @Property(float, notify=progressChanged)
    def stageProgress(self):
        return self._stage_progress

    @Property(int, notify=progressChanged)
    def stagePercent(self):
        return round(self._stage_progress * 25)

    @Property(str, notify=progressChanged)
    def progressDescription(self):
        return self._progress_description

    @Property(bool, notify=busyChanged)
    def isBusy(self):
        return self._busy

    @Property(str, notify=reportChanged)
    def reportInfo(self):
        return self._report_info

    @Property(str, notify=reportChanged)
    def reportPath(self):
        return self._report_path

    @Property("QVariantMap", notify=activityChanged)
    def activityDetails(self):
        return dict(self._activity)

    @Property("QVariantList", notify=resultsChanged)
    def resultRows(self):
        return list(self._results)

    @Property(str, notify=runSummaryChanged)
    def runSummary(self):
        return self._run_summary

    @Property("QVariantMap", notify=fieldErrorsChanged)
    def fieldErrors(self):
        return dict(self._field_errors)

    @Property(bool, notify=darkModeChanged)
    def darkMode(self):
        return self._dark_mode

    @Slot(bool)
    def setDarkMode(self, dark):
        if self._dark_mode == dark:
            return
        self._dark_mode = dark
        self.darkModeChanged.emit()

    @Slot()
    def openReport(self):
        try:
            common.open_report(self._report_path)
        except (OSError, RuntimeError) as error:
            self.errorRaised.emit(str(error))

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
        extensions = self._fields["wsi_extensions"]
        self._set_busy(True)
        self._files = []
        self.filesChanged.emit()
        self.selectionChanged.emit()
        self._status = "Searching for WSI files..."
        self.statusChanged.emit()

        def worker():
            try:
                files = common.find_wsi_files(folder, extensions)
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
            settings = common.validate_settings(
                self._fields,
                self._selected_files(),
                self._destinations,
            )
        except ValueError as error:
            QMessageBox.critical(None, "Check settings", str(error))
            return

        self._set_busy(True)
        self._progress = 0
        self._progress_max = 1
        self._stage_progress = 0
        self._progress_description = "Starting conversion"
        self.progressChanged.emit()
        self._status = "Conversion running..."
        self.statusChanged.emit()
        self._report_path = ""
        self._report_info = "Creating conversion log and Markdown report..."
        self.reportChanged.emit()
        self._run_started_monotonic = None
        self._run_started_at = "—"
        self._run_summary = "Started: — | Finished: — | Average per file: —"
        self.runSummaryChanged.emit()
        self._results = []
        self.resultsChanged.emit()
        self._activity = {
            key: "—" for key in self._activity
        }
        self.activityChanged.emit()
        self._append_log("Starting conversion...\n")
        common.run_conversion(settings, self.events)

    @Slot()
    def requestCancel(self):
        common.request_cancel()
        self._status = "Cancellation requested. Stopping after current file..."
        self.statusChanged.emit()

    @Slot()
    def resetDefaults(self):
        if self._busy:
            return
        self._fields = dict(common.DEFAULTS)
        self.fieldsChanged.emit()
        self._destinations = list(common.DEFAULT_DESTINATIONS)
        self.destinationsChanged.emit()
        self._field_errors = {}
        self.fieldErrorsChanged.emit()
        self._status = "Settings reset to defaults."
        self.statusChanged.emit()

    @Slot(str, str, result=str)
    def validateField(self, key, value):
        """Validate a single field and store its inline error; returns the error message."""
        error = self._check_field(key, value)
        self._field_errors[key] = error or ""
        self.fieldErrorsChanged.emit()
        return error or ""

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

    @Slot()
    def _poll_events(self):
        while True:
            try:
                event, payload = self.events.get_nowait()
            except queue.Empty:
                break

            if event == "log":
                self._append_log(payload)
            elif event == "run_started":
                self._run_started_monotonic = time.perf_counter()
                self._run_started_at = payload.get("started_at", "—")
                self._run_summary = (
                    f"Started: {self._run_started_at} | Finished: In progress"
                )
                self.runSummaryChanged.emit()
                self._report_info = (
                    f"Log: {payload['log_path']} | Report: {payload['report_path']}"
                )
                self.reportChanged.emit()
            elif event == "progress":
                files_total = max(1, payload["files_total"])
                overall = payload["completed_files"] + payload["stage_value"] / 4
                self._progress = round(min(files_total, overall) * 100)
                self._progress_max = files_total * 100
                self._stage_progress = payload["stage_value"]
                self._progress_description = payload["message"]
                self.progressChanged.emit()
                self._status = payload["message"]
                self.statusChanged.emit()
                self._update_activity(payload)
            elif event == "run_report":
                summary = payload["summary"]
                self._report_path = payload["report_path"]
                self._report_info = (
                    f"Report: {payload['report_path']} | Text log: {payload['log_path']}"
                )
                self.reportChanged.emit()
                self._status = (
                    f"Finished: {summary.get('completed', 0)} completed, "
                    f"{summary.get('failed', 0)} failed."
                )
                self.statusChanged.emit()
                self._activity["elapsed"] = common.format_duration(
                    summary.get("duration_seconds")
                )
                self._activity["counts"] = (
                    f"{summary.get('completed', 0)} completed / "
                    f"{summary.get('failed', 0)} failed / "
                    f"{summary.get('total', 0)} total"
                )
                self.activityChanged.emit()
                self._run_summary = (
                    f"Started: {self._run_started_at} | "
                    f"Finished: {payload.get('finished_at', '—')} | "
                    f"Total: {common.format_duration(summary.get('duration_seconds'))} | "
                    f"Average per completed file: "
                    f"{common.format_duration(summary.get('average_seconds'))}"
                )
                self.runSummaryChanged.emit()
                self._results = [
                    {
                        "file": item.get("file", ""),
                        "resolution": item.get("resolution") or "—",
                        "load": common.format_duration(item.get("load_seconds")),
                        "deepzoom": (
                            f"{item.get('deepzoom_status', '—')} "
                            f"({common.format_duration(item.get('deepzoom_seconds'))})"
                        ),
                        "thumbnail": (
                            f"{item.get('thumbnail_status', '—')} "
                            f"({common.format_duration(item.get('thumbnail_seconds'))})"
                        ),
                        "copy": common.format_duration(item.get("copy_seconds")),
                        "total": common.format_duration(item.get("slide_seconds")),
                        "status": item.get("status", ""),
                        "copy_destinations": "; ".join(
                            f"{copy.get('destination')}: {copy.get('status')} "
                            f"({common.format_duration(copy.get('duration_seconds'))})"
                            for copy in item.get("copy_destinations", [])
                        ),
                        "outputs": "; ".join(
                            path
                            for path in (
                                item.get("deepzoom_output"),
                                item.get("thumbnail_output"),
                                *item.get("copy_outputs", []),
                            )
                            if path
                        ),
                        "error": item.get("error", ""),
                    }
                    for item in summary.get("results", [])
                ]
                self.resultsChanged.emit()
            elif event == "scan_done":
                self._set_busy(False)
                if payload is not None:
                    self._files = [
                        {"path": path, "checked": True} for path in payload
                    ]
                    self.filesChanged.emit()
                    self.selectionChanged.emit()
                    self._status = f"Found {len(payload):,} WSI file(s)."
                    self.statusChanged.emit()
            elif event == "error":
                self._append_log(f"\nError: {payload}\n")
                self.errorRaised.emit(payload)
            elif event == "done":
                self._set_busy(False)
                if not self._report_path:
                    self._status = "Conversion ended. Review any error messages."
                    self.statusChanged.emit()
        if self._run_started_monotonic is not None and self._busy:
            self._activity["elapsed"] = common.format_duration(
                time.perf_counter() - self._run_started_monotonic
            )
            self.activityChanged.emit()

    def _update_activity(self, payload):
        metrics = payload.get("metrics", {})
        self._activity["file"] = payload.get("file") or "—"
        self._activity["resolution"] = metrics.get("resolution") or "—"
        self._activity["load"] = common.format_duration(metrics.get("load_seconds"))
        self._activity["deepzoom"] = (
            f"{metrics.get('deepzoom_status', 'Pending')} "
            f"({common.format_duration(metrics.get('deepzoom_seconds'))})"
        )
        self._activity["thumbnail"] = (
            f"{metrics.get('thumbnail_status', 'Pending')} "
            f"({common.format_duration(metrics.get('thumbnail_seconds'))})"
        )
        copies = metrics.get("copy_destinations", [])
        self._activity["copy"] = "; ".join(
            f"{item['status']} {item['destination']} "
            f"({common.format_duration(item.get('duration_seconds'))})"
            for item in copies
        ) or f"Total {common.format_duration(metrics.get('copy_seconds'))}"
        self._activity["slide"] = common.format_duration(metrics.get("slide_seconds"))
        self._activity["elapsed"] = common.format_duration(
            payload.get("run_elapsed_seconds")
        )
        self._activity["counts"] = (
            f"{payload.get('completed_files', 0)} completed / "
            f"{payload.get('files_total', 0)} total"
        )
        self._activity["outputs"] = "\n".join(
            path
            for path in (
                metrics.get("deepzoom_output"),
                metrics.get("thumbnail_output"),
                *metrics.get("copy_outputs", []),
            )
            if path
        ) or "—"
        self.activityChanged.emit()


def main():
    app = QApplication(sys.argv)
    engine = QQmlApplicationEngine()
    controller = DzSaveController()
    engine.rootContext().setContextProperty("controller", controller)
    qml_file = common.APP_DIR / "dzsave-v4.qml"
    qml_modules = common.APP_DIR / "PySide6" / "qml"
    if qml_modules.is_dir():
        engine.addImportPath(str(qml_modules))
    # Also add the installed PySide6 QML modules directory as a fallback
    try:
        import PySide6

        pyside_qml = Path(PySide6.__file__).parent / "qml"
        if pyside_qml.is_dir():
            engine.addImportPath(str(pyside_qml))
    except ImportError:
        pass
    engine.load(QUrl.fromLocalFile(str(qml_file)))
    if not engine.rootObjects():
        raise RuntimeError(f"Could not load QML interface: {qml_file}")

    controller.errorRaised.connect(
        lambda message: QMessageBox.critical(None, "Operation failed", message)
    )
    if "--self-test" in sys.argv[1:]:
        # Run the event loop briefly so QML bindings resolve the controller
        # context property, then quit automatically.
        QTimer.singleShot(3000, lambda: app.quit())
        return app.exec()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
