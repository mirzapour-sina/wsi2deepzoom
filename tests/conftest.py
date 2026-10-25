"""Shared fixtures and configuration for the WSI to DeepZoom converter test suite.

The converter module (dzsave-v4.py) imports pyvips at the top level. Since pyvips
is not installed in the test environment, we inject a MagicMock into sys.modules
before loading the module so the converter logic can be tested headlessly.
"""

import importlib
import sys
from pathlib import Path
from unittest.mock import MagicMock

import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

# ---------------------------------------------------------------------------
# Mock pyvips before the converter module is loaded (it imports pyvips at top)
# ---------------------------------------------------------------------------

mock_pyvips = MagicMock()
sys.modules["pyvips"] = mock_pyvips

_converter_module = None


def _load_converter():
    """Load dzsave-v4.py as a module with a mocked pyvips."""
    global _converter_module
    if _converter_module is None:
        spec = importlib.util.spec_from_file_location(
            "dzsave_v4_converter_test",
            PROJECT_ROOT / "dzsave-v4.py",
        )
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        _converter_module = module
    return _converter_module


@pytest.fixture
def converter():
    """The loaded dzsave-v4 converter module (with mocked pyvips)."""
    return _load_converter()


@pytest.fixture
def pyvips_mock():
    """The mocked pyvips module."""
    return mock_pyvips


@pytest.fixture
def mock_image():
    """A mocked pyvips image with sensible default dimensions."""
    image = MagicMock()
    image.width = 10000
    image.height = 5000
    return image


@pytest.fixture
def temp_dir(tmp_path):
    """A temporary directory path."""
    return tmp_path
