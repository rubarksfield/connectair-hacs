"""Fixtures shared by the genuine Home Assistant integration tests."""

from types import SimpleNamespace

import aiohttp
import aioresponses.core
import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry


@pytest.fixture(autouse=True)
def compatible_mock_response(monkeypatch):
    """Supply aiohttp 3.14's new argument missing from aioresponses 0.7.

    Patch only the HTTP mock's response constructor, retaining aiohttp's
    actual JSON parsing/status behavior and the production client unchanged.
    """

    class MockClientResponse(aiohttp.ClientResponse):
        def __init__(self, *args, **kwargs):
            kwargs.setdefault("stream_writer", SimpleNamespace(output_size=0))
            super().__init__(*args, **kwargs)

    monkeypatch.setattr(aioresponses.core, "ClientResponse", MockClientResponse)


@pytest.fixture
def account_entry(hass):
    entry = MockConfigEntry(domain="connectair", unique_id="account-a", data={})
    entry.add_to_hass(hass)
    return entry
