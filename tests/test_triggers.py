"""The timer triggers must do nothing but build an SPN and delegate.

Any logic that creeps back into ``function_app.py`` is untestable without the
Functions host, so these tests pin the delegation rather than the behaviour.
Behaviour is covered in ``test_operations.py``.
"""

import pytest


@pytest.fixture
def recorded(monkeypatch):
    from capacity_ops import operations

    calls = {}
    monkeypatch.setattr(operations, "pause_all", lambda spn: calls.setdefault("pause", spn))
    monkeypatch.setattr(operations, "resume_all", lambda spn: calls.setdefault("resume", spn))
    return calls


def test_pause_trigger_delegates_to_operations(function_app, recorded, timer):
    function_app.pause_capacities(timer)

    assert "pause" in recorded
    assert "resume" not in recorded


def test_resume_trigger_delegates_to_operations(function_app, recorded, timer):
    function_app.resume_capacities(timer)

    assert "resume" in recorded
    assert "pause" not in recorded


def test_triggers_pass_a_built_spn(function_app, recorded, timer, monkeypatch):
    """The SPN is built per invocation, not held at module scope, so a rotated
    Key Vault secret is picked up without restarting the app."""
    from capacity_ops import identity

    sentinel = object()
    monkeypatch.setattr(identity, "build_spn", lambda: sentinel)

    function_app.pause_capacities(timer)

    assert recorded["pause"] is sentinel


def test_function_app_does_not_import_dependencies_at_module_scope():
    """Regression guard.

    The Functions host discovers triggers by importing this module. If it pulls
    in ``fabric_utils`` (installed from a git branch) at module scope, a bad
    dependency yields an app with zero registered functions instead of one
    failed invocation.
    """
    from pathlib import Path

    source = (
        Path(__file__).resolve().parents[1] / "src" / "function" / "function_app.py"
    ).read_text()

    module_scope = [
        line
        for line in source.splitlines()
        if line.startswith(("import ", "from ")) and not line.startswith("from __future__")
    ]

    assert module_scope == ["import azure.functions as func"]
