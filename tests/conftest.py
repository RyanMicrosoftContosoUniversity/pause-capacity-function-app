"""Shared fixtures.

``function_app`` and the ``capacity_ops`` package live under ``src/function`` so
the deployment package stays free of test and tooling files.

``capacity_ops`` imports ``fabric_utils`` lazily inside the functions that need
it, so importing these modules here needs no Azure credentials.
"""

import sys
import time
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
def config(monkeypatch):
    """The settings module, pinned to test values and never really sleeping.

    Config is read from the environment at import, so values are pinned here
    rather than left to whatever the developer's shell happens to export.
    """
    from capacity_ops import config as module

    monkeypatch.setattr(module, "RESOURCE_GROUP", "test-capacity-pause-app-rg")
    monkeypatch.setenv("SUBSCRIPTION_ID", "00000000-0000-0000-0000-000000000000")
    monkeypatch.setattr(time, "sleep", lambda _seconds: None)
    return module


@pytest.fixture
def capacity(config):
    from capacity_ops import capacity as module

    return module


@pytest.fixture
def healthcheck(config):
    from capacity_ops import healthcheck as module

    return module


@pytest.fixture
def identity(config):
    from capacity_ops import identity as module

    return module


@pytest.fixture
def operations(config, monkeypatch):
    """The orchestration module with the Airflow probe stubbed out.

    Tests that exercise the probe itself use the ``healthcheck`` fixture.
    """
    from capacity_ops import healthcheck
    from capacity_ops import operations as module

    monkeypatch.setattr(healthcheck, "airflow_health_check", lambda _spn: None)
    return module


@pytest.fixture
def function_app(monkeypatch):
    """Import function_app with a stubbed SPN builder.

    The triggers import ``capacity_ops`` lazily, so the stub goes on the package
    rather than on ``function_app`` itself.
    """
    from capacity_ops import identity

    monkeypatch.setattr(identity, "build_spn", lambda: object())

    import function_app as module

    return module


@pytest.fixture
def timer():
    class _Timer:
        past_due = False

    return _Timer()
