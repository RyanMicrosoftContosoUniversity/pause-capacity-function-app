"""Tests for the pause and resume orchestration."""


def _install_clients(operations, monkeypatch, clients, resumable=None):
    """Install fake capacities, and by default allow resume to touch them all.

    Resume is gated on ``config.RESUME_CAPACITIES``, so tests that are about
    something *other* than the allow-list have to opt every client in, or they
    would exercise the exclusion path by accident. Pass ``resumable`` to test
    the gate itself.
    """
    monkeypatch.setattr(operations.capacity, "iter_capacity_clients", lambda _spn: iter(clients))
    allow = [c.capacity_name for c in clients] if resumable is None else resumable
    monkeypatch.setattr(operations.config, "RESUME_CAPACITIES", allow)


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


# --- resume allow-list -----------------------------------------------------


def test_resume_only_touches_allow_listed_capacities(operations, fake_client, monkeypatch):
    """The whole reason the allow-list exists: every capacity in the group gets
    paused overnight, but only the named one is allowed to start billing again."""
    wanted = fake_client("uswest3capacity", ["Paused", "Active"])
    other = fake_client("cap-other", ["Paused", "Active"])
    _install_clients(operations, monkeypatch, [wanted, other], resumable=["uswest3capacity"])

    result = operations.resume_all(object())

    assert wanted.resume_calls == 1
    assert other.resume_calls == 0
    assert result.succeeded == ["uswest3capacity"]
    assert result.excluded == ["cap-other"]


def test_resume_leaves_an_excluded_capacity_paused_even_when_it_is_active(
    operations, fake_client, monkeypatch
):
    """An excluded capacity is never inspected, so an Active one is reported as
    excluded rather than skipped. Resume must not adopt capacities it is not
    responsible for."""
    stray = fake_client("cap-other", ["Active"])
    _install_clients(operations, monkeypatch, [stray], resumable=["uswest3capacity"])

    result = operations.resume_all(object())

    assert stray.resume_calls == 0
    assert result.skipped == []
    assert result.excluded == ["cap-other"]


def test_empty_allow_list_resumes_nothing(operations, fake_client, monkeypatch):
    """A cleared or mistyped RESUME_CAPACITIES must fail closed. Resuming
    everything on an empty list would turn a typo into a full day of F-SKU spend."""
    paused = fake_client("uswest3capacity", ["Paused", "Active"])
    _install_clients(operations, monkeypatch, [paused], resumable=[])

    result = operations.resume_all(object())

    assert paused.resume_calls == 0
    assert result.succeeded == []
    assert result.excluded == ["uswest3capacity"]


def test_pause_ignores_the_resume_allow_list(operations, fake_client, monkeypatch):
    """Pause stays unscoped on purpose: a capacity that is off the allow-list is
    exactly the one that must not be left running overnight."""
    off_list = fake_client("cap-other", ["Active"])
    _install_clients(operations, monkeypatch, [off_list], resumable=["uswest3capacity"])

    result = operations.pause_all(object())

    assert off_list.pause_calls == 1
    assert result.succeeded == ["cap-other"]


def test_allow_list_parsing_tolerates_spacing_and_empties(config):
    """The value arrives as one app-setting string, so whitespace around a
    comma must not produce a name that can never match."""
    assert config._parse_capacity_list(" uswest3capacity , other ,") == [
        "uswest3capacity",
        "other",
    ]
    assert config._parse_capacity_list("") == []
