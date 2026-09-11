"""Tests for the helpers that decide what state a capacity is in."""

import itertools


def test_capacity_state_reads_arm_state(function_app, fake_client):
    client = fake_client("cap1", ["Active"])
    assert function_app._capacity_state(client) == "Active"


def test_capacity_state_returns_unknown_when_arm_errors(function_app, fake_client):
    """A lookup failure must not raise; the caller treats Unknown as 'not ready'."""
    client = fake_client("cap1", ["Active"], fail_on={"get"})
    assert function_app._capacity_state(client) == "Unknown"


def test_wait_for_active_returns_timestamp_once_active(function_app, fake_client):
    client = fake_client("cap1", ["Paused", "Provisioning", "Active"])
    observed = function_app._wait_for_active(client)
    assert observed is not None
    assert observed.tzinfo is not None, "timestamp must be timezone-aware"


def test_wait_for_active_gives_up_and_returns_none(function_app, fake_client, monkeypatch):
    """A capacity that never reaches Active must time out rather than hang."""
    monkeypatch.setattr(function_app, "RESUME_POLL_TIMEOUT_SECONDS", 5)
    monkeypatch.setattr(function_app, "RESUME_POLL_INTERVAL_SECONDS", 1)

    clock = itertools.count(0, 2)
    monkeypatch.setattr(function_app.time, "monotonic", lambda: next(clock))

    client = fake_client("cap1", ["Provisioning"])
    assert function_app._wait_for_active(client) is None


def test_wait_for_active_tolerates_transient_lookup_errors(function_app, fake_client, monkeypatch):
    """Unknown is not Active, so polling continues rather than declaring success."""
    monkeypatch.setattr(function_app, "RESUME_POLL_TIMEOUT_SECONDS", 5)
    monkeypatch.setattr(function_app, "RESUME_POLL_INTERVAL_SECONDS", 1)

    clock = itertools.count(0, 2)
    monkeypatch.setattr(function_app.time, "monotonic", lambda: next(clock))

    client = fake_client("cap1", ["Active"], fail_on={"get"})
    assert function_app._wait_for_active(client) is None
