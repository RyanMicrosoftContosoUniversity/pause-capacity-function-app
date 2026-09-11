"""Tests for the pause and resume orchestration."""


def _install_clients(operations, monkeypatch, clients):
    monkeypatch.setattr(operations.capacity, "iter_capacity_clients", lambda _spn: iter(clients))


# --- pause -----------------------------------------------------------------


def test_pause_pauses_active_capacities(operations, fake_client, monkeypatch):
    active = fake_client("cap-active", ["Active"])
    _install_clients(operations, monkeypatch, [active])

    result = operations.pause_all(object())

    assert active.pause_calls == 1
    assert result.succeeded == ["cap-active"]


def test_pause_skips_already_paused(operations, fake_client, monkeypatch):
    paused = fake_client("cap-paused", ["Paused"])
    _install_clients(operations, monkeypatch, [paused])

    result = operations.pause_all(object())

    assert paused.pause_calls == 0, "pausing an already-paused capacity wastes an ARM call"
    assert result.skipped == ["cap-paused"]


def test_one_failing_capacity_does_not_stop_the_rest(operations, fake_client, monkeypatch):
    """The whole point of the per-capacity try/except: a bad capacity must not
    leave the remaining capacities running overnight."""
    doomed = fake_client("cap-doomed", ["Active"], fail_on={"pause"})
    healthy = fake_client("cap-healthy", ["Active"])
    _install_clients(operations, monkeypatch, [doomed, healthy])

    result = operations.pause_all(object())

    assert healthy.pause_calls == 1
    assert result.failed == ["cap-doomed"]


def test_pause_does_not_raise_when_every_capacity_fails(operations, fake_client, monkeypatch):
    """An unhandled exception would mark the invocation failed and trigger the
    'failed fabric capacity pause' alert for a condition already logged."""
    doomed = fake_client("cap-doomed", ["Active"], fail_on={"pause"})
    _install_clients(operations, monkeypatch, [doomed])

    result = operations.pause_all(object())

    assert result.failed == ["cap-doomed"]


# --- resume ----------------------------------------------------------------


def test_resume_resumes_paused_capacity(operations, fake_client, monkeypatch):
    paused = fake_client("cap-paused", ["Paused", "Active"])
    _install_clients(operations, monkeypatch, [paused])

    result = operations.resume_all(object())

    assert paused.resume_calls == 1
    assert result.succeeded == ["cap-paused"]


def test_resume_skips_already_active(operations, fake_client, monkeypatch):
    active = fake_client("cap-active", ["Active"])
    _install_clients(operations, monkeypatch, [active])

    result = operations.resume_all(object())

    assert active.resume_calls == 0
    assert result.skipped == ["cap-active"]


def test_resume_continues_after_a_capacity_never_becomes_active(
    operations, fake_client, monkeypatch
):
    from datetime import UTC, datetime

    stuck = fake_client("cap-stuck", ["Paused"])
    healthy = fake_client("cap-healthy", ["Paused", "Active"])
    _install_clients(operations, monkeypatch, [stuck, healthy])
    monkeypatch.setattr(
        operations.capacity,
        "wait_for_active",
        lambda client: None if client is stuck else datetime.now(UTC),
    )

    result = operations.resume_all(object())

    assert healthy.resume_calls == 1
    assert result.succeeded == ["cap-healthy"]
    assert result.failed == ["cap-stuck"]


def test_resume_runs_the_airflow_health_check(operations, fake_client, monkeypatch):
    """The probe is the only signal that workload items are actually serving,
    so it must run even when every capacity was already Active."""
    calls = []
    monkeypatch.setattr(
        operations.healthcheck, "airflow_health_check", lambda spn: calls.append(spn)
    )
    _install_clients(operations, monkeypatch, [fake_client("cap-active", ["Active"])])

    operations.resume_all(object())

    assert len(calls) == 1
