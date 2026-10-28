---
name: session-plan
description: Plan for syncing widget GUIs to QML reference and checking UX
metadata:
  type: project
---

## Goal
Port remaining QML (dzsave-v4.qml / dzsave-v4-qml.py) reference behavior to the tkinter, PySide6 and PyQt6 GUIs, then run each GUI to check for UX issues and apply optimizations.

## Status
COMPLETE — committed on branch opt-1-parallel-wsi.

## Changes made
1. dzsave_v4_gui_common.py: reorder validate_settings so input_dir → deepzoom_format → wsi_extensions → numerics → destinations (fixes validation ordering; all 81 tests pass).
2. All 3 widget GUIs: add "Remove this destination." tooltip on Remove buttons (QML parity).
3. tkinter: deepzoom_format combobox shows labels like QML (not raw keys), with key→label mapping on read-back.
4. All 3 widget GUIs: options toggle text now dynamic ("Show/Hide DeepZoom and Robocopy options"); deepzoom/robocopy sub-sections start expanded like QML (checked: true).
5. All 3 widget GUIs: activity details grid aligned to QML (4-column; "Resolution" label; "File totals" and "Output paths" as full-width rows); progress rows show percent labels ("Overall — X%", "Current slide — X%").
6. tkinter: _validate_all_fields run before start so inline errors show on Start (QML parity).
7. Verified: tkinter, PySide6 and QML launch and render (screenshot_gui.py); PyQt6 source-reviewed + compiles (not installed here). Tests: 81/81 pass.
