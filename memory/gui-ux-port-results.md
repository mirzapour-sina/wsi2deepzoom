# GUI QML-UX Port Results

**Branch:** opt-1-parallel-wsi  
**Commit:** e81e346 — "Port QML reference UX parity to tkinter, PySide6 and PyQt6 GUIs"  
**Date:** 2026-10-28

## Goal
Port the QML reference version (`dzsave-v4.qml` / `dzsave-v4-qml.py`) UX to the other three widget GUIs (PyQt6, PySide6, Tkinter), then run each GUI to check for UI/UX issues and apply optimizations.

## Changes made (all committed)

### `dzsave_v4_gui_common.py`
- Reordered `validate_settings` so validation runs: input_dir → deepzoom_format → wsi_extensions → numerics → destinations (matches QML ordering; fixes validation-order failures).

### All 3 widget GUIs (`dzsave-v4-pyqt6.py`, `dzsave-v4-pyside6.py`, `dzsave-v4-tkinter.py`)
- Added `"Remove this destination."` tooltip on Remove buttons (QML has it).
- Options toggle text is now dynamic: "Show DeepZoom and Robocopy options" / "Hide DeepZoom and Robocopy options" (PyQt6/PySide6 previously had a static label).
- DeepZoom/Robocopy sub-sections now start **expanded** by default, matching QML's `checked: true`.
- Activity details grid aligned to QML: 4-column grid, "Resolution" label (was "Source resolution"), and "File totals" / "Output paths" as full-width rows.
- Progress rows now show percent labels: "Overall — X%" and "Current slide — X%" (matching QML).

### Tkinter (`dzsave-v4-tkinter.py`) specifically
- DeepZoom format combobox now shows *labels* (not raw keys) like QML, with key→label mapping stored and used on read-back in `start_conversion`.
- Added `_validate_all_fields()` run before starting conversion so inline field errors surface on Start (QML parity).
- DeepZoom/Robocopy sub-sections start visible when the options panel is shown.

## Verification — running each GUI
- `screenshot_gui.py` launched and captured **tkinter, PySide6, and QML** successfully; screenshots saved to `screenshots/`.
- Visually compared all three against the QML reference: layout, toggle states, progress labels, and tooltips now match QML.
- **PyQt6** is not installed in this environment → source-reviewed and `py_compile`-checked (its changes mirror the verified PySide6 implementation).
- Test suite: **81/81 pass** (`python -m pytest tests/ -q`).

## Files changed
- `dzsave-v4-pyqt6.py`
- `dzsave-v4-pyside6.py`
- `dzsave-v4-tkinter.py`
- `dzsave_v4_gui_common.py`
- `memory/session-plan.md` (updated to mark the plan complete)
- `screenshots/tkinter.png`, `screenshots/pyside6.png`, `screenshots/qml.png` (regenerated verification captures)

## Notes / limitations
- PyQt6 could not be executed (module not installed); only compile-checked and source-reviewed.
- Pre-existing untracked files `screenshot_gui.py` and `test_enum.py` were left uncommitted (not part of this task).
- `pyvips` is not installed, so the conversion engine can't actually run end-to-end, but GUI launch/render works.
