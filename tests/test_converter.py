"""Unit tests for dzsave-v4.py — the core WSI-to-DeepZoom converter.

pyvips is mocked (see tests/conftest.py) so the converter logic can be tested
headlessly without libvips installed.
"""

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_wsi(tmp_path, name="slide.tif"):
    wsi = tmp_path / name
    wsi.touch()
    return wsi


def _setup_converter(converter, tmp_path, input_file, dest_dirs=None, **overrides):
    """Common setup for convert_wsi tests."""
    converter.INPUT_DIR = tmp_path
    converter.DESTINATION_DIRS = (
        dest_dirs if dest_dirs is not None else [tmp_path / "output"]
    )
    converter.PROGRESS_CALLBACK = MagicMock()
    converter.LAST_CONVERSION_ERROR = None
    converter.LAST_CONVERSION_DURATION = None
    converter.LAST_CONVERSION_METRICS = {}
    for key, value in overrides.items():
        setattr(converter, key, value)
    return input_file


# ---------------------------------------------------------------------------
# main() — configuration validation
# ---------------------------------------------------------------------------

class TestMainMissingInputDir:
    def test_nonexistent_input_dir_returns_error(self, converter, tmp_path):
        converter.INPUT_DIR = tmp_path / "nonexistent_dir"
        result = converter.main()

        assert result["total"] == 0
        assert result["completed"] == 0
        assert result["failed"] == 0
        assert result["duration_seconds"] == 0
        assert result["error"] is not None
        assert "does not exist" in result["error"]

    def test_existing_input_dir_no_files(self, converter, tmp_path):
        converter.INPUT_DIR = tmp_path
        converter.DESTINATION_DIRS = [tmp_path / "output"]
        result = converter.main()

        assert result["total"] == 0
        assert result["completed"] == 0
        assert result["failed"] == 0


class TestMainInvalidFormat:
    def test_invalid_deepzoom_format_raises(self, converter, tmp_path):
        converter.INPUT_DIR = tmp_path
        converter.DEEPZOOM_FORMAT = "not_a_format"

        with pytest.raises(ValueError, match="Unsupported DeepZoom output format"):
            converter.main()

        converter.DEEPZOOM_FORMAT = "dzi"


# ---------------------------------------------------------------------------
# format_time (defined in dzsave-v4.py)
# ---------------------------------------------------------------------------

class TestFormatTime:
    def test_seconds_only(self, converter):
        assert converter.format_time(42.5) == "00:42.50"

    def test_minutes_and_seconds(self, converter):
        assert converter.format_time(90.5) == "01:30.50"

    def test_hours_minutes_seconds(self, converter):
        assert converter.format_time(3700.25) == "01:01:40.25"

    def test_zero(self, converter):
        assert converter.format_time(0) == "00:00.00"

    def test_large_hours(self, converter):
        assert converter.format_time(90000) == "25:00:00.00"


# ---------------------------------------------------------------------------
# deepzoom_storage_path / deepzoom_save_path / deepzoom_exists / thumbnail_exists
# ---------------------------------------------------------------------------

class TestDeepZoomPaths:
    def test_storage_path_dzi(self, converter):
        result = converter.deepzoom_storage_path(Path("/out/slide"), "dzi")
        assert result == Path("/out/slide.dzi")

    def test_storage_path_szi(self, converter):
        result = converter.deepzoom_storage_path(Path("/out/slide"), "szi")
        assert result == Path("/out/slide.szi")

    def test_storage_path_zip(self, converter):
        result = converter.deepzoom_storage_path(Path("/out/slide"), "zip")
        assert result == Path("/out/slide.zip")

    def test_storage_path_zoomify(self, converter):
        result = converter.deepzoom_storage_path(Path("/out/slide"), "zoomify")
        assert result == Path("/out/slide")

    def test_storage_path_defaults_to_module_format(self, converter):
        result = converter.deepzoom_storage_path(Path("/out/slide"))
        assert result == Path("/out/slide.dzi")

    def test_save_path_dzi_returns_plain_path(self, converter):
        result = converter.deepzoom_save_path(Path("/out/slide"), "dzi")
        assert result == Path("/out/slide")

    def test_save_path_szi_returns_storage_path(self, converter):
        result = converter.deepzoom_save_path(Path("/out/slide"), "szi")
        assert result == Path("/out/slide.szi")

    def test_save_path_zip_returns_storage_path(self, converter):
        result = converter.deepzoom_save_path(Path("/out/slide"), "zip")
        assert result == Path("/out/slide.zip")

    def test_save_path_zoomify_returns_plain_path(self, converter):
        result = converter.deepzoom_save_path(Path("/out/slide"), "zoomify")
        assert result == Path("/out/slide")


class TestDeepZoomExists:
    def test_dzi_exists_with_descriptor_and_tiles(self, converter, tmp_path):
        output_path = tmp_path / "slide"
        (tmp_path / "slide.dzi").touch()
        (tmp_path / "slide_files").mkdir()

        assert converter.deepzoom_exists(output_path) is True

    def test_dzi_missing_descriptor(self, converter, tmp_path):
        output_path = tmp_path / "slide"
        (tmp_path / "slide_files").mkdir()

        assert converter.deepzoom_exists(output_path) is False

    def test_dzi_missing_tiles_folder(self, converter, tmp_path):
        output_path = tmp_path / "slide"
        (tmp_path / "slide.dzi").touch()

        assert converter.deepzoom_exists(output_path) is False

    def test_dzi_missing_both(self, converter, tmp_path):
        output_path = tmp_path / "slide"

        assert converter.deepzoom_exists(output_path) is False

    def test_szi_file_exists(self, converter, tmp_path):
        output_path = tmp_path / "slide"
        (tmp_path / "slide.szi").touch()

        assert converter.deepzoom_exists(output_path, "szi") is True

    def test_zip_file_exists(self, converter, tmp_path):
        output_path = tmp_path / "slide"
        (tmp_path / "slide.zip").touch()

        assert converter.deepzoom_exists(output_path, "zip") is True

    def test_directory_format_exists_with_content(self, converter, tmp_path):
        output_path = tmp_path / "slide"
        output_dir = tmp_path / "slide"
        output_dir.mkdir()
        (output_dir / "some_file").touch()

        assert converter.deepzoom_exists(output_path, "zoomify") is True

    def test_directory_format_empty_is_not_exists(self, converter, tmp_path):
        output_path = tmp_path / "slide"
        output_dir = tmp_path / "slide"
        output_dir.mkdir()

        assert converter.deepzoom_exists(output_path, "zoomify") is False

    def test_directory_format_missing(self, converter, tmp_path):
        output_path = tmp_path / "slide"

        assert converter.deepzoom_exists(output_path, "zoomify") is False

    def test_thumbnail_exists(self, converter, tmp_path):
        folder = tmp_path / "slide"
        folder.mkdir()
        (folder / "thumbnail.jpg").touch()

        assert converter.thumbnail_exists(folder) is True

    def test_thumbnail_missing(self, converter, tmp_path):
        folder = tmp_path / "slide"
        folder.mkdir()

        assert converter.thumbnail_exists(folder) is False


# ---------------------------------------------------------------------------
# convert_wsi — successful conversion
# ---------------------------------------------------------------------------

class TestConvertWsiSuccess:
    def test_successful_single_destination(self, converter, pyvips_mock, mock_image, tmp_path):
        pyvips_mock.reset_mock(return_value=True, side_effect=True)
        pyvips_mock.Image.new_from_file.return_value = mock_image
        mock_image.dzsave = MagicMock()
        mock_image.thumbnail_image = MagicMock()

        input_file = _make_wsi(tmp_path)
        _setup_converter(converter, tmp_path, input_file)

        result = converter.convert_wsi(input_file, 1, 1)

        assert result is not None
        assert result > 0
        pyvips_mock.Image.new_from_file.assert_called_once_with(
            str(input_file), access="random"
        )
        mock_image.dzsave.assert_called_once()
        mock_image.thumbnail_image.assert_called_once()

    def test_skips_deepzoom_when_already_exists(self, converter, pyvips_mock, mock_image, tmp_path):
        pyvips_mock.reset_mock(return_value=True, side_effect=True)
        pyvips_mock.Image.new_from_file.return_value = mock_image
        mock_image.dzsave = MagicMock()
        mock_image.thumbnail_image = MagicMock()

        input_file = _make_wsi(tmp_path)
        output_dir = tmp_path / "output"
        output_dir.mkdir()
        wsi_name = input_file.stem

        # convert_wsi uses primary_folder = output_dir / wsi_name (relative
        # to INPUT_DIR, which is tmp_path here)
        primary_folder = output_dir / wsi_name
        primary_folder.mkdir(parents=True, exist_ok=True)

        # Create .dzi descriptor and _files folder
        (primary_folder / f"{wsi_name}.dzi").touch()
        (primary_folder / f"{wsi_name}_files").mkdir()
        # Create thumbnail so it's also skipped
        (primary_folder / "thumbnail.jpg").touch()

        _setup_converter(converter, tmp_path, input_file, dest_dirs=[output_dir])
        converter.DEEPZOOM_FORMAT = "dzi"

        result = converter.convert_wsi(input_file, 1, 1)

        assert result is not None
        # Both outputs already exist, so the image is not loaded at all
        pyvips_mock.Image.new_from_file.assert_not_called()
        mock_image.dzsave.assert_not_called()
        # Thumbnail already exists so thumbnail_image is not called
        mock_image.thumbnail_image.assert_not_called()

    def test_sets_progress_callback(self, converter, pyvips_mock, mock_image, tmp_path):
        pyvips_mock.reset_mock(return_value=True, side_effect=True)
        pyvips_mock.Image.new_from_file.return_value = mock_image
        mock_image.dzsave = MagicMock()
        mock_image.thumbnail_image = MagicMock()

        input_file = _make_wsi(tmp_path)
        _setup_converter(converter, tmp_path, input_file)

        converter.convert_wsi(input_file, 1, 1)

        # PROGRESS_CALLBACK should have been invoked at multiple stages
        assert converter.PROGRESS_CALLBACK.call_count > 0
        # Check that a "complete" event was sent
        stage_events = [
            call.args[0]["stage"] for call in converter.PROGRESS_CALLBACK.call_args_list
        ]
        assert "complete" in stage_events


# ---------------------------------------------------------------------------
# convert_wsi — error handling
# ---------------------------------------------------------------------------

class TestConvertWsiErrors:
    def test_pyvips_load_error_reported(self, converter, pyvips_mock, tmp_path):
        pyvips_mock.reset_mock(return_value=True, side_effect=True)
        pyvips_mock.Image.new_from_file.side_effect = Exception("Cannot load file")

        input_file = _make_wsi(tmp_path)
        _setup_converter(converter, tmp_path, input_file)

        result = converter.convert_wsi(input_file, 1, 1)

        assert result is None
        assert converter.LAST_CONVERSION_ERROR is not None
        assert "Cannot load file" in converter.LAST_CONVERSION_ERROR
        # Progress callback should have received an "error" event
        stages = [
            call.args[0]["stage"] for call in converter.PROGRESS_CALLBACK.call_args_list
        ]
        assert "error" in stages

    def test_dzsave_error_reported(self, converter, pyvips_mock, mock_image, tmp_path):
        pyvips_mock.reset_mock(return_value=True, side_effect=True)
        pyvips_mock.Image.new_from_file.return_value = mock_image
        mock_image.dzsave = MagicMock(side_effect=Exception("dzsave failed"))
        mock_image.thumbnail_image = MagicMock()

        input_file = _make_wsi(tmp_path)
        _setup_converter(converter, tmp_path, input_file)

        result = converter.convert_wsi(input_file, 1, 1)

        assert result is None
        assert converter.LAST_CONVERSION_ERROR is not None
        assert "dzsave failed" in converter.LAST_CONVERSION_ERROR

    def test_thumbnail_creation_error_reported(self, converter, pyvips_mock, mock_image, tmp_path):
        pyvips_mock.reset_mock(return_value=True, side_effect=True)
        pyvips_mock.Image.new_from_file.return_value = mock_image
        mock_image.dzsave = MagicMock()
        mock_image.thumbnail_image = MagicMock(side_effect=Exception("thumbnail failed"))

        input_file = _make_wsi(tmp_path)
        output_dir = tmp_path / "output"
        output_dir.mkdir()
        wsi_name = input_file.stem
        (output_dir / f"{wsi_name}.dzi").touch()
        (output_dir / f"{wsi_name}_files").mkdir()
        # thumbnail.jpg does NOT exist, so thumbnail creation is attempted

        _setup_converter(converter, tmp_path, input_file, dest_dirs=[output_dir])
        converter.DEEPZOOM_FORMAT = "dzi"

        result = converter.convert_wsi(input_file, 1, 1)

        assert result is None
        assert converter.LAST_CONVERSION_ERROR is not None
        assert "thumbnail failed" in converter.LAST_CONVERSION_ERROR

    def test_robocopy_failure_reported(self, converter, pyvips_mock, mock_image, tmp_path):
        pyvips_mock.reset_mock(return_value=True, side_effect=True)
        pyvips_mock.Image.new_from_file.return_value = mock_image
        mock_image.dzsave = MagicMock()
        mock_image.thumbnail_image = MagicMock()

        input_file = _make_wsi(tmp_path)
        wsi_name = input_file.stem
        primary = tmp_path / "primary"
        secondary = tmp_path / "secondary"
        primary.mkdir()
        secondary.mkdir()

        # convert_wsi uses primary_folder = primary / wsi_name (relative
        # to INPUT_DIR, which is tmp_path here)
        primary_folder = primary / wsi_name
        primary_folder.mkdir(parents=True, exist_ok=True)

        # Create primary DeepZoom output so copy step runs
        (primary_folder / f"{wsi_name}.dzi").touch()
        (primary_folder / f"{wsi_name}_files").mkdir()
        (primary_folder / "thumbnail.jpg").touch()

        _setup_converter(
            converter,
            tmp_path,
            input_file,
            dest_dirs=[primary, secondary],
        )
        converter.DEEPZOOM_FORMAT = "dzi"

        # Make robocopy fail
        with patch.object(converter.subprocess, "run") as mock_run:
            mock_run.return_value = MagicMock(returncode=8, stdout="", stderr="robocopy error")
            result = converter.convert_wsi(input_file, 1, 1)

        assert result is not None
        # A copy failure to one destination does not fail the whole slide;
        # the failure is recorded per-destination and conversion continues.
        assert converter.LAST_CONVERSION_ERROR is None
        copy_statuses = [
            copy["status"] for copy in converter.LAST_CONVERSION_METRICS[
                "copy_destinations"
            ]
        ]
        assert any("Failed" in status for status in copy_statuses)


# ---------------------------------------------------------------------------
# report_progress
# ---------------------------------------------------------------------------

class TestReportProgress:
    def test_calls_progress_callback(self, converter, tmp_path):
        events = []
        converter.PROGRESS_CALLBACK = lambda progress: events.append(progress)
        converter.RUN_START_PERF = None

        converter.report_progress("preparing", 0, 4, message="Starting")

        assert len(events) == 1
        assert events[0]["stage"] == "preparing"
        assert events[0]["stage_value"] == 0
        assert events[0]["current"] == 0
        assert events[0]["total"] == 4
        assert events[0]["message"] == "Starting"

    def test_report_progress_includes_metrics_copy(self, converter):
        events = []
        converter.PROGRESS_CALLBACK = lambda progress: events.append(progress)
        converter.RUN_START_PERF = None

        metrics = {"load_seconds": 1.5, "deepzoom_status": "Converting"}
        converter.report_progress("deepzoom", 1, 4, message="Converting", metrics=metrics)

        assert events[0]["metrics"]["load_seconds"] == 1.5
        # Should be a deep copy, so mutating the returned metrics doesn't affect caller
        events[0]["metrics"]["load_seconds"] = 999
        assert metrics["load_seconds"] == 1.5
