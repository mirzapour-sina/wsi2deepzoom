import argparse
import itertools
import queue
import shutil
import subprocess
import sys
import threading
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

import build_executables as builder


if getattr(sys, "frozen", False):
    ROOT = Path(sys.executable).resolve().parent
else:
    ROOT = Path(__file__).resolve().parent
BUILDER_SCRIPT = ROOT / "build_executables.py"

METHOD_LABELS = {
    "pyinstaller": "PyInstaller",
    "nuitka": "Nuitka",
    "cx-freeze": "cx_Freeze",
}
APP_LABELS = {
    "tkinter": "Tkinter",
    "pyqt6": "PyQt6",
    "pyside6": "PySide6 Widgets",
    "qml": "PySide6 / QML",
}
LAYOUT_LABELS = {
    "onedir": "Onedir",
    "onefile": "One-file",
}


def build_plan(methods, app_keys, layouts):
    jobs = list(itertools.product(methods, app_keys, layouts))
    supported_jobs = [
        job for job in jobs if not (job[0] == "cx-freeze" and job[2] == "onefile")
    ]
    skipped_jobs = [job for job in jobs if job not in supported_jobs]
    return supported_jobs, skipped_jobs


class ExecutableBuilderWindow:
    def __init__(self, root):
        self.root = root
        self.events = queue.Queue()
        self.busy = False
        self.total_jobs = 0
        self.completed_jobs = 0
        self.vips_bin = tk.StringVar()
        self.percent = tk.StringVar(value="0%")
        self.status = tk.StringVar(value="Choose build options to get started.")
        self.method_vars = {
            method: tk.BooleanVar(value=True) for method in builder.METHODS
        }
        self.app_vars = {
            app_key: tk.BooleanVar(value=True) for app_key in builder.APPS
        }
        self.layout_vars = {
            layout: tk.BooleanVar(value=True) for layout in builder.LAYOUTS
        }

        root.title("WSI DeepZoom Executable Builder")
        root.geometry("950x760")
        root.minsize(760, 620)
        root.protocol("WM_DELETE_WINDOW", self._on_close)

        self._build()
        root.after(100, self._poll_events)

    def _build(self):
        main = ttk.Frame(self.root, padding=16)
        main.pack(fill=tk.BOTH, expand=True)
        main.columnconfigure(0, weight=1)
        main.rowconfigure(3, weight=1)
        main.rowconfigure(6, weight=1)

        ttk.Label(
            main,
            text="WSI DeepZoom Executable Builder",
            font=("Segoe UI", 18, "bold"),
        ).grid(row=0, column=0, sticky="w")
        ttk.Label(
            main,
            text=(
                "Select one or more packagers, GUI frontends, and package layouts. "
                "Builds run sequentially and are smoke-tested."
            ),
            wraplength=900,
        ).grid(row=1, column=0, sticky="w", pady=(4, 12))

        vips_frame = ttk.LabelFrame(
            main, text="libvips runtime (optional)", padding=10
        )
        vips_frame.grid(row=2, column=0, sticky="ew", pady=(0, 10))
        vips_frame.columnconfigure(0, weight=1)
        ttk.Entry(vips_frame, textvariable=self.vips_bin).grid(
            row=0, column=0, sticky="ew"
        )
        ttk.Button(
            vips_frame, text="Browse...", command=self._browse_vips
        ).grid(row=0, column=1, padx=(8, 0))
        ttk.Label(
            vips_frame,
            text="Leave blank to detect libvips from VIPS_HOME or PATH.",
        ).grid(row=1, column=0, columnspan=2, sticky="w", pady=(5, 0))

        options = ttk.Frame(main)
        options.grid(row=3, column=0, sticky="nsew")
        for column in range(3):
            options.columnconfigure(column, weight=1, uniform="options")

        self._selection_group(
            options,
            column=0,
            title="Packagers",
            values=builder.METHODS,
            labels=METHOD_LABELS,
            variables=self.method_vars,
        )
        self._selection_group(
            options,
            column=1,
            title="GUI frontends",
            values=tuple(builder.APPS),
            labels=APP_LABELS,
            variables=self.app_vars,
        )
        self._selection_group(
            options,
            column=2,
            title="Package layouts",
            values=builder.LAYOUTS,
            labels=LAYOUT_LABELS,
            variables=self.layout_vars,
        )

        controls = ttk.Frame(main)
        controls.grid(row=4, column=0, sticky="ew", pady=(10, 6))
        controls.columnconfigure(0, weight=1)
        ttk.Label(controls, textvariable=self.status).grid(
            row=0, column=0, sticky="w"
        )
        self.build_button = ttk.Button(
            controls, text="Build selected", command=self._start_build, default="active"
        )
        self.build_button.grid(row=0, column=1, sticky="e")

        progress = ttk.Frame(main)
        progress.grid(row=5, column=0, sticky="ew", pady=(0, 6))
        progress.columnconfigure(1, weight=1)
        ttk.Label(progress, textvariable=self.percent).grid(
            row=0, column=0, sticky="w"
        )
        self.progress = ttk.Progressbar(
            progress, orient=tk.HORIZONTAL, mode="determinate"
        )
        self.progress.grid(row=0, column=1, sticky="ew", padx=(8, 0))

        output_frame = ttk.LabelFrame(main, text="Build output", padding=6)
        output_frame.grid(row=6, column=0, sticky="nsew")
        output_frame.columnconfigure(0, weight=1)
        output_frame.rowconfigure(0, weight=1)
        self.output = tk.Text(
            output_frame,
            height=14,
            wrap=tk.NONE,
            state=tk.DISABLED,
            font=("Consolas", 9),
        )
        vertical = ttk.Scrollbar(
            output_frame, orient=tk.VERTICAL, command=self.output.yview
        )
        horizontal = ttk.Scrollbar(
            output_frame, orient=tk.HORIZONTAL, command=self.output.xview
        )
        self.output.configure(
            yscrollcommand=vertical.set, xscrollcommand=horizontal.set
        )
        self.output.grid(row=0, column=0, sticky="nsew")
        vertical.grid(row=0, column=1, sticky="ns")
        horizontal.grid(row=1, column=0, sticky="ew")

    @staticmethod
    def _selection_group(parent, column, title, values, labels, variables):
        frame = ttk.LabelFrame(parent, text=title, padding=10)
        frame.grid(row=0, column=column, sticky="nsew", padx=(0, 8))
        frame.columnconfigure(0, weight=1)
        for row, value in enumerate(values):
            ttk.Checkbutton(
                frame, text=labels[value], variable=variables[value]
            ).grid(row=row, column=0, sticky="w", pady=2)

        buttons = ttk.Frame(frame)
        buttons.grid(row=len(values), column=0, sticky="w", pady=(8, 0))
        ttk.Button(
            buttons,
            text="All",
            command=lambda: [variables[value].set(True) for value in values],
        ).pack(side=tk.LEFT)
        ttk.Button(
            buttons,
            text="None",
            command=lambda: [variables[value].set(False) for value in values],
        ).pack(side=tk.LEFT, padx=(6, 0))

    def _browse_vips(self):
        selected = filedialog.askdirectory(
            title="Select the libvips bin folder",
            initialdir=self.vips_bin.get() or str(ROOT),
        )
        if selected:
            self.vips_bin.set(selected)

    def _start_build(self):
        if self.busy:
            return

        try:
            python_command = builder_python_command()
        except RuntimeError as error:
            messagebox.showerror("Python 3.10 not found", str(error), parent=self.root)
            return

        methods = [
            method for method, variable in self.method_vars.items() if variable.get()
        ]
        app_keys = [
            app_key for app_key, variable in self.app_vars.items() if variable.get()
        ]
        layouts = [
            layout for layout, variable in self.layout_vars.items() if variable.get()
        ]
        if not methods or not app_keys or not layouts:
            messagebox.showerror(
                "Choose build options",
                "Select at least one packager, GUI frontend, and package layout.",
                parent=self.root,
            )
            return

        vips_bin = self.vips_bin.get().strip()
        if vips_bin and not Path(vips_bin).expanduser().is_dir():
            messagebox.showerror(
                "Invalid libvips folder",
                f"The selected folder does not exist:\n{vips_bin}",
                parent=self.root,
            )
            return

        jobs, skipped = build_plan(methods, app_keys, layouts)
        if not jobs:
            messagebox.showerror(
                "No supported builds",
                "cx_Freeze does not support one-file builds. Select onedir or "
                "another packager to continue.",
                parent=self.root,
            )
            return
        skipped_text = (
            f"\n\n{len(skipped)} cx_Freeze one-file build(s) will be skipped "
            "because cx_Freeze supports onedir only."
            if skipped
            else ""
        )
        if not messagebox.askyesno(
            "Confirm build",
            f"Build {len(jobs)} executable combination(s)?{skipped_text}",
            parent=self.root,
        ):
            return

        self.total_jobs = len(jobs)
        self.completed_jobs = 0
        self.progress.configure(maximum=len(jobs))
        self.progress["value"] = 0
        self.percent.set("0%")
        self.busy = True
        self.build_button.configure(state=tk.DISABLED)
        self._append_output(
            f"Starting {len(jobs)} build(s); {len(skipped)} unsupported combination(s) skipped.\n"
        )
        threading.Thread(
            target=self._build_worker,
            args=(jobs, skipped, vips_bin, python_command),
            daemon=True,
        ).start()

    def _build_worker(self, jobs, skipped, vips_bin, python_command=None):
        successes = []
        failures = []
        try:
            if skipped:
                self.events.put(
                    (
                        "output",
                        "SKIPPED: cx_Freeze one-file builds are unsupported "
                        f"({len(skipped)} combination(s)).\n",
                    )
                )
            for index, (method, app_key, layout) in enumerate(jobs, start=1):
                app_name = builder.APPS[app_key]["name"]
                description = (
                    f"{app_name} with {METHOD_LABELS[method]} "
                    f"({LAYOUT_LABELS[layout]})"
                )
                self.events.put(
                    ("status", f"Building {index} of {len(jobs)}: {description}")
                )
                command = [
                    *(python_command or builder_python_command()),
                    str(BUILDER_SCRIPT),
                    "--method",
                    method,
                    "--gui",
                    app_key,
                    "--layout",
                    layout,
                ]
                if vips_bin:
                    command.extend(["--vips-bin", vips_bin])
                self.events.put(("output", f"\n=== {description} ===\n"))
                try:
                    process = subprocess.Popen(
                        command,
                        cwd=ROOT,
                        stdout=subprocess.PIPE,
                        stderr=subprocess.STDOUT,
                        text=True,
                        encoding="utf-8",
                        errors="replace",
                        bufsize=1,
                    )
                    if process.stdout is None:
                        raise RuntimeError("Could not read builder output.")
                    for line in process.stdout:
                        self.events.put(("output", line))
                    return_code = process.wait()
                    if return_code == 0:
                        successes.append(description)
                    else:
                        failures.append(
                            (description, f"Builder exited with code {return_code}.")
                        )
                        self.events.put(
                            ("output", f"BUILD FAILED (exit code {return_code})\n")
                        )
                except (OSError, RuntimeError) as error:
                    failures.append((description, str(error)))
                    self.events.put(("output", f"BUILD FAILED: {error}\n"))
                self.events.put(("progress", index, len(jobs)))
        finally:
            self.events.put(("finished", (successes, failures, len(skipped))))

    def _poll_events(self):
        try:
            while True:
                event, payload = self.events.get_nowait()
                if event == "output":
                    self._append_output(payload)
                elif event == "status":
                    self.status.set(payload)
                elif event == "progress":
                    completed, total = payload
                    self.completed_jobs = completed
                    self.progress["value"] = completed
                    if total:
                        self.percent.set(
                            f"{completed / total * 100:.0f}% ({completed} of {total})"
                        )
                elif event == "finished":
                    successes, failures, skipped = payload
                    self.progress["value"] = self.total_jobs
                    self.percent.set("100%")
                    self.busy = False
                    self.build_button.configure(state=tk.NORMAL)
                    self.status.set(
                        f"Finished: {len(successes)} succeeded, "
                        f"{len(failures)} failed, {skipped} skipped."
                    )
                    self._append_output(
                        "\n=== Build summary ===\n"
                        f"Succeeded: {len(successes)}\n"
                        f"Failed: {len(failures)}\n"
                        f"Skipped: {skipped}\n"
                    )
                    if failures:
                        details = "\n".join(
                            f"- {description}: {error}"
                            for description, error in failures
                        )
                        messagebox.showerror(
                            "Builds finished with errors",
                            f"{len(successes)} build(s) succeeded and "
                            f"{len(failures)} failed.\n\n{details}",
                            parent=self.root,
                        )
                    else:
                        messagebox.showinfo(
                            "Builds finished",
                            f"{len(successes)} build(s) succeeded.\n"
                            f"{skipped} unsupported combination(s) skipped.",
                            parent=self.root,
                        )
        except queue.Empty:
            pass
        self.root.after(100, self._poll_events)

    def _append_output(self, text):
        self.output.configure(state=tk.NORMAL)
        self.output.insert(tk.END, text)
        self.output.see(tk.END)
        self.output.configure(state=tk.DISABLED)

    def _on_close(self):
        if self.busy:
            messagebox.showinfo(
                "Build in progress",
                "Wait for the selected builds to finish before closing this window.",
                parent=self.root,
            )
            return
        self.root.destroy()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args()
    root = tk.Tk()
    if args.self_test:
        root.withdraw()
        ExecutableBuilderWindow(root)
        root.update_idletasks()
        root.destroy()
        print("Builder GUI self-test passed.")
        return
    ExecutableBuilderWindow(root)
    root.mainloop()


def builder_python_command():
    if not getattr(sys, "frozen", False):
        return [sys.executable]
    launcher = shutil.which("py")
    if launcher is None:
        raise RuntimeError(
            "The packaged builder requires the Windows Python launcher and "
            "Python 3.10 to run the current project build script."
        )
    return [launcher, "-3.10"]


if __name__ == "__main__":
    main()
