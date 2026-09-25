"""Fixtures for aisstream.io tests."""
from __future__ import annotations

from unittest.mock import patch

import pytest


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations):
    """Load custom_components/ in every test."""
    yield


@pytest.fixture(autouse=True)
def no_websocket():
    """Never open a real connection to aisstream.io."""
    with patch("custom_components.aisstream.coordinator.AISStreamClient.start"):
        yield
