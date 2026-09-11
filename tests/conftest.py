"""Shared fixtures.

``function_app`` lives under ``src/function`` so the deployment package stays
free of test and tooling files. It imports ``fabric_utils`` lazily inside each
function, so importing the module here needs no Azure credentials.
"""

import sys
from pathlib import Path

import pytest

FUNCTION_ROOT = Path(__file__).resolve().parents[1] / "src" / "function"
sys.path.insert(0, str(FUNCTION_ROOT))


class FakeCapacityClient:
    """Stands in for FabricCapacityMGMT.

    ``states`` is consumed one entry per ``get_capacity`` call, which lets a test
    describe a capacity that is Paused, then Provisioning, then Active. The last
    value repeats once exhausted.
    """

    def __init__(self, name, states, fail_on=None):
        self.capacity_name = name
        self._states = list(states)
        self._fail_on = fail_on or set()
        self.pause_calls = 0
        self.resume_calls = 0

    def get_capacity(self):
        if "get" in self._fail_on:
            raise RuntimeError("ARM lookup failed")
        state = self._states[0] if len(self._states) == 1 else self._states.pop(0)
        return {"properties": {"state": state}}

    def pause_capacity(self):
        if "pause" in self._fail_on:
            raise RuntimeError("pause failed")
        self.pause_calls += 1

    def resume_capacity(self):
        if "resume" in self._fail_on:
            raise RuntimeError("resume failed")
        self.resume_calls += 1


@pytest.fixture
def fake_client():
    return FakeCapacityClient


@pytest.fixture
def function_app(monkeypatch):
    """Import function_app with a stubbed SPN builder and no real sleeping."""
    monkeypatch.setenv("FABRIC_RESOURCE_GROUP", "test-capacity-pause-app-rg")
    monkeypatch.setenv("SUBSCRIPTION_ID", "00000000-0000-0000-0000-000000000000")

    import function_app as module

    monkeypatch.setattr(module, "_build_spn", lambda: object())
    monkeypatch.setattr(module.time, "sleep", lambda _seconds: None)
    return module


@pytest.fixture
def timer():
    class _Timer:
        past_due = False

    return _Timer()
