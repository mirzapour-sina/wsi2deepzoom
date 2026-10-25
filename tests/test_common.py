"""Unit tests for dzsave_v4_gui_common.py — settings validation and helpers."""

import queue
from pathlib import Path
from unittest.mock import MagicMock

import pytest

import dzsave_v4_gui_common as common


# ---------------------------------------------------------------------------
# parse_wsi_extensions
# ---------------------------------------------------------------------------

class TestParseWsiExtensions:
    def test_valid_comma_separated(self):
        result = common.parse_wsi_extensions(".tif, .tiff, .svs")
        assert result == (".tif", ".tiff", ".svs")

    def test_valid_semicolon_separated(self):
        result = common.parse_wsi_extensions(".tif;.tiff;.svs")
        assert result == (".tif", ".tiff", ".svs")

    def test_extension_without_dot_gets_dot(self):
        result = common.parse_wsi_extensions("tif, tiff")
        assert result == (".tif", ".tiff")

    def test_extension_with_asterisk_prefix(self):
        result = common.parse_wsi_extensions("*.tif, *.tiff")
        assert result == (".tif", ".tiff")

    def test_duplicate_extensions_deduplicated(self):
        result = common.parse_wsi_extensions(".tif, .tif, .tiff")
        assert result == (".tif", ".tiff")

    def test_mixed_separators(self):
        result = common.parse_wsi_extensions(".tif, .tiff; .svs")
        assert result == (".tif", ".tiff", ".svs")

    def test_empty_string_raises(self):
        with pytest.raises(ValueError, match="at least one WSI file extension"):
            common.parse_wsi_extensions("")

    def test_whitespace_only_raises(self):
        with pytest.raises(ValueError, match="at least one WSI file extension"):
            common.parse_wsi_extensions("   ")

    def test_invalid_characters_raise(self):
        with pytest.raises(ValueError, match="Invalid WSI file extension"):
            common.parse_wsi_extensions("invalid/ext")

    def test_invalid_backslash_raise(self):
        with pytest.raises(ValueError, match="Invalid WSI file extension"):
            common.parse_wsi_extensions("path\\file.tif")

    def test_invalid_colon_raise(self):
        with pytest.raises(ValueError, match="Invalid WSI file extension"):
            common.parse_wsi_extensions("C:.tif")

    def test_invalid_space_raise(self):
        with pytest.raises(ValueError, match="Invalid WSI file extension"):
            common.parse_wsi_extensions("my ext.tif")

    def test_case_is_lowercased(self):
        result = common.parse_wsi_extensions(".TIF, .Tiff")
        assert result == (".tif", ".tiff")

    def test_ome_tif_extension(self):
        result = common.parse_wsi_extensions(".ome.tif, .ome.tiff")
        assert result == (".ome.tif", ".ome.tiff")


# ---------------------------------------------------------------------------
# find_wsi_files
# ---------------------------------------------------------------------------

class TestFindWsiFiles:
    def test_existing_directory_returns_matching_files(self, tmp_path):
        (tmp_path / "slide1.tif").touch()
        (tmp_path / "slide2.tiff").touch()
        (tmp_path / "not_wsi.txt").touch()
        sub = tmp_path / "subdir"
        sub.mkdir()
        (sub / "slide3.svs").touch()

        result = common.find_wsi_files(tmp_path)
        names = sorted(p.name for p in result)
        assert names == ["slide1.tif", "slide2.tiff", "slide3.svs"]

    def test_nonexistent_directory_raises(self):
        with pytest.raises(ValueError, match="Input folder does not exist"):
            common.find_wsi_files("/nonexistent/path/that/does/not/exist")

    def test_custom_extensions_filter(self, tmp_path):
        (tmp_path / "file1.svs").touch()
        (tmp_path / "file2.tif").touch()
        (tmp_path / "file3.ndpi").touch()

        result = common.find_wsi_files(tmp_path, extensions=[".svs", ".ndpi"])
        names = sorted(p.name for p in result)
        assert names == ["file1.svs", "file3.ndpi"]

    def test_case_insensitive_extension_match(self, tmp_path):
        (tmp_path / "slide.TIF").touch()

        result = common.find_wsi_files(tmp_path, extensions=[".tif"])
        assert len(result) == 1

    def test_permission_error_raises_value_error(self, tmp_path, monkeypatch):
        """rglob raising PermissionError should surface as ValueError."""

        def fake_rglob(self, pattern):
            raise PermissionError("access denied")

        monkeypatch.setattr(Path, "rglob", fake_rglob)

        with pytest.raises(ValueError, match="Permission denied"):
            common.find_wsi_files(tmp_path)


# ---------------------------------------------------------------------------
# validate_settings
# ---------------------------------------------------------------------------

class TestValidateSettings:
    def _base_values(self, tmp_path):
        input_dir = tmp_path / "input"
        input_dir.mkdir()
        return {
            "input_dir": str(input_dir),
            "deepzoom_format": "dzi",
            "wsi_extensions": ".tif, .svs",
            "jpeg_quality": "85",
            "thumbnail_size": "600",
            "thumbnail_quality": "85",
            "robocopy_threads": "16",
            "robocopy_retries": "2",
            "robocopy_wait": "1",
        }

    def test_valid_settings_returns_dict(self, tmp_path):
        input_dir = tmp_path / "input"
        input_dir.mkdir()
        values = {
            "input_dir": str(input_dir),
            "deepzoom_format": "dzi",
            "wsi_extensions": ".tif, .svs",
            "jpeg_quality": "85",
            "thumbnail_size": "600",
            "thumbnail_quality": "85",
            "robocopy_threads": "16",
            "robocopy_retries": "2",
            "robocopy_wait": "1",
        }
        dest = tmp_path / "output"

        settings = common.validate_settings(values, destinations=[str(dest)])

        assert settings["input_dir"] == input_dir
        assert settings["deepzoom_format"] == "dzi"
        assert settings["wsi_extensions"] == (".tif", ".svs")
        assert settings["jpeg_quality"] == 85
        assert settings["thumbnail_size"] == 600
        assert settings["thumbnail_quality"] == 85
        assert settings["robocopy_threads"] == 16
        assert settings["robocopy_retries"] == 2
        assert settings["robocopy_wait"] == 1
        assert settings["destinations"] == [dest]

    def test_missing_input_dir_raises(self, tmp_path):
        values = self._base_values(tmp_path)
        values["input_dir"] = "/nonexistent/path"

        with pytest.raises(ValueError, match="Select an existing input folder"):
            common.validate_settings(values)

    def test_empty_destination_raises(self, tmp_path):
        values = self._base_values(tmp_path)

        with pytest.raises(ValueError, match="Remove empty destination folders"):
            common.validate_settings(values, destinations=[""])

    def test_no_destinations_raises(self, tmp_path):
        values = self._base_values(tmp_path)

        with pytest.raises(ValueError, match="Add at least one destination folder"):
            common.validate_settings(values, destinations=[])

    def test_duplicate_destinations_raise(self, tmp_path):
        values = self._base_values(tmp_path)
        dest = tmp_path / "output"

        with pytest.raises(ValueError, match="listed more than once"):
            common.validate_settings(values, destinations=[str(dest), str(dest)])

    def test_invalid_deepzoom_format_raises(self, tmp_path):
        values = self._base_values(tmp_path)
        values["deepzoom_format"] = "not_a_format"

        with pytest.raises(ValueError, match="Select a supported DeepZoom format"):
            common.validate_settings(values)

    def test_jpeg_quality_above_range_raises(self, tmp_path):
        values = self._base_values(tmp_path)
        values["jpeg_quality"] = "150"

        with pytest.raises(ValueError, match="between 1 and 100"):
            common.validate_settings(values)

    def test_jpeg_quality_below_range_raises(self, tmp_path):
        values = self._base_values(tmp_path)
        values["jpeg_quality"] = "0"

        with pytest.raises(ValueError, match="between 1 and 100"):
            common.validate_settings(values)

    def test_non_numeric_jpeg_quality_raises(self, tmp_path):
        values = self._base_values(tmp_path)
        values["jpeg_quality"] = "abc"

        with pytest.raises(ValueError, match="whole numbers"):
            common.validate_settings(values)

    def test_thumbnail_size_below_one_raises(self, tmp_path):
        values = self._base_values(tmp_path)
        values["thumbnail_size"] = "0"

        with pytest.raises(ValueError, match="at least 1 pixel"):
            common.validate_settings(values)

    def test_thumbnail_quality_out_of_range_raises(self, tmp_path):
        values = self._base_values(tmp_path)
        values["thumbnail_quality"] = "101"

        with pytest.raises(ValueError, match="between 1 and 100"):
            common.validate_settings(values)

    def test_robocopy_threads_above_range_raises(self, tmp_path):
        values = self._base_values(tmp_path)
        values["robocopy_threads"] = "200"

        with pytest.raises(ValueError, match="between 1 and 128"):
            common.validate_settings(values)

    def test_negative_retries_raises(self, tmp_path):
        values = self._base_values(tmp_path)
        values["robocopy_retries"] = "-1"

        with pytest.raises(ValueError, match="cannot be negative"):
            common.validate_settings(values)

    def test_negative_wait_raises(self, tmp_path):
        values = self._base_values(tmp_path)
        values["robocopy_wait"] = "-1"

        with pytest.raises(ValueError, match="cannot be negative"):
            common.validate_settings(values)

    def test_selected_file_outside_input_dir_raises(self, tmp_path):
        input_dir = tmp_path / "input"
        input_dir.mkdir()
        outside_file = tmp_path / "outside.svs"
        outside_file.touch()

        values = {
            "input_dir": str(input_dir),
            "deepzoom_format": "dzi",
            "wsi_extensions": ".tif, .svs",
            "jpeg_quality": "85",
            "thumbnail_size": "600",
            "thumbnail_quality": "85",
            "robocopy_threads": "16",
            "robocopy_retries": "2",
            "robocopy_wait": "1",
        }

        with pytest.raises(ValueError, match="outside the source folder"):
            common.validate_settings(
                values,
                selected_files=[str(outside_file)],
                destinations=[str(tmp_path / "out")],
            )

    def test_selected_file_not_a_file_raises(self, tmp_path):
        input_dir = tmp_path / "input"
        input_dir.mkdir()
        values = {
            "input_dir": str(input_dir),
            "deepzoom_format": "dzi",
            "wsi_extensions": ".tif, .svs",
            "jpeg_quality": "85",
            "thumbnail_size": "600",
            "thumbnail_quality": "85",
            "robocopy_threads": "16",
            "robocopy_retries": "2",
            "robocopy_wait": "1",
        }

        with pytest.raises(ValueError, match="no longer available"):
            common.validate_settings(
                values,
                selected_files=[str(input_dir / "missing.svs")],
                destinations=[str(tmp_path / "out")],
            )

    def test_selected_file_wrong_extension_raises(self, tmp_path):
        input_dir = tmp_path / "input"
        input_dir.mkdir()
        (input_dir / "image.txt").touch()

        values = {
            "input_dir": str(input_dir),
            "deepzoom_format": "dzi",
            "wsi_extensions": ".tif, .svs",
            "jpeg_quality": "85",
            "thumbnail_size": "600",
            "thumbnail_quality": "85",
            "robocopy_threads": "16",
            "robocopy_retries": "2",
            "robocopy_wait": "1",
        }

        with pytest.raises(ValueError, match="extension is not enabled"):
            common.validate_settings(
                values,
                selected_files=[str(input_dir / "image.txt")],
                destinations=[str(tmp_path / "out")],
            )

    def test_no_selected_files_raises(self, tmp_path):
        input_dir = tmp_path / "input"
        input_dir.mkdir()
        values = {
            "input_dir": str(input_dir),
            "deepzoom_format": "dzi",
            "wsi_extensions": ".tif, .svs",
            "jpeg_quality": "85",
            "thumbnail_size": "600",
            "thumbnail_quality": "85",
            "robocopy_threads": "16",
            "robocopy_retries": "2",
            "robocopy_wait": "1",
        }

        with pytest.raises(ValueError, match="Select at least one WSI file"):
            common.validate_settings(
                values,
                selected_files=[],
                destinations=[str(tmp_path / "out")],
            )

    def test_valid_selected_files(self, tmp_path):
        input_dir = tmp_path / "input"
        input_dir.mkdir()
        wsi_file = input_dir / "slide.tif"
        wsi_file.touch()

        values = {
            "input_dir": str(input_dir),
            "deepzoom_format": "dzi",
            "wsi_extensions": ".tif, .svs",
            "jpeg_quality": "85",
            "thumbnail_size": "600",
            "thumbnail_quality": "85",
            "robocopy_threads": "16",
            "robocopy_retries": "2",
            "robocopy_wait": "1",
        }

        settings = common.validate_settings(
            values,
            selected_files=[str(wsi_file)],
            destinations=[str(tmp_path / "out")],
        )

        assert settings["selected_files"] == [wsi_file.resolve()]


# ---------------------------------------------------------------------------
# QueueWriter
# ---------------------------------------------------------------------------

class TestQueueWriter:
    def _make_writer(self):
        events = queue.Queue()
        log_file = MagicMock()
        return common.QueueWriter(events, log_file), events

    def test_send_line_skips_overall_progress(self):
        writer, events = self._make_writer()

        writer._send_line("Overall progress: 50%")
        assert events.qsize() == 0

        writer._send_line("Converting slide 1 of 3\n")
        assert events.qsize() == 1
        assert events.get() == ("log", "Converting slide 1 of 3\n")

    def test_write_buffers_until_newline(self):
        writer, events = self._make_writer()

        writer.write("Hello ")
        assert events.qsize() == 0
        assert writer.buffer == "Hello "

        writer.write("World\n")
        assert events.qsize() == 1
        assert events.get() == ("log", "Hello World\n")
        assert writer.buffer == ""

    def test_flush_sends_remaining_buffer(self):
        writer, events = self._make_writer()

        writer.write("Remaining text")
        assert events.qsize() == 0
        writer.flush()
        assert events.qsize() == 1
        assert events.get() == ("log", "Remaining text")
        assert writer.buffer == ""


# ---------------------------------------------------------------------------
# format_duration
# ---------------------------------------------------------------------------

class TestFormatDuration:
    def test_none_returns_dash(self):
        assert common.format_duration(None) == "—"

    def test_numeric_value(self):
        assert common.format_duration(42.5) == "42.50 s"

    def test_zero(self):
        assert common.format_duration(0) == "0.00 s"
