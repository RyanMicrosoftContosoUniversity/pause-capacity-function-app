"""Tests for the pause and resume timer triggers."""


def _install_clients(function_app, monkeypatch, clients):
    monkeypatch.setattr(function_app, "_iter_capacity_clients", lambda _spn: iter(clients))


# --- pause -----------------------------------------------------------------


def test_pause_pauses_active_capacities(function_app, fake_client, monkeypatch, timer):
    active = fake_client("cap-active", ["Active"])
    _install_clients(function_app, monkeypatch, [active])

    function_app.pause_capacities(timer)

    assert active.pause_calls == 1


def test_pause_skips_already_paused(function_app, fake_client, monkeypatch, timer):
    paused = fake_client("cap-paused", ["Paused"])
    _install_clients(function_app, monkeypatch, [paused])

    function_app.pause_capacities(timer)

    assert paused.pause_calls == 0, "pausing an already-paused capacity wastes an ARM call"


def test_one_failing_capacity_does_not_stop_the_rest(function_app, fake_client, monkeypatch, timer):
    """The whole point of the per-capacity try/except: a bad capacity must not
    leave the remaining capacities running overnight."""
    doomed = fake_client("cap-doomed", ["Active"], fail_on={"pause"})
    healthy = fake_client("cap-healthy", ["Active"])
    _install_clients(function_app, monkeypatch, [doomed, healthy])

    function_app.pause_capacities(timer)

    assert healthy.pause_calls == 1


def test_pause_does_not_raise_when_every_capacity_fails(
    function_app, fake_client, monkeypatch, timer
):
    """An unhandled exception would mark the invocation failed and trigger the
    'failed fabric capacity pause' alert for a condition already logged."""
    doomed = fake_client("cap-doomed", ["Active"], fail_on={"pause"})
    _install_clients(function_app, monkeypatch, [doomed])

    function_app.pause_capacities(timer)


# --- resume ----------------------------------------------------------------


def test_resume_resumes_paused_capacity(function_app, fake_client, monkeypatch, timer):
    paused = fake_client("cap-paused", ["Paused", "Active"])
    _install_clients(function_app, monkeypatch, [paused])
    monkeypatch.setattr(function_app, "_airflow_health_check", lambda _spn: None)

    function_app.resume_capacities(timer)

    assert paused.resume_calls == 1


def test_resume_skips_already_active(function_app, fake_client, monkeypatch, timer):
    active = fake_client("cap-active", ["Active"])
    _install_clients(function_app, monkeypatch, [active])
    monkeypatch.setattr(function_app, "_airflow_health_check", lambda _spn: None)

    function_app.resume_capacities(timer)

    assert active.resume_calls == 0


def test_resume_continues_after_a_capacity_never_becomes_active(
    function_app, fake_client, monkeypatch, timer
):
    stuck = fake_client("cap-stuck", ["Paused"])
    healthy = fake_client("cap-healthy", ["Paused", "Active"])
    _install_clients(function_app, monkeypatch, [stuck, healthy])
    monkeypatch.setattr(
        function_app,
        "_wait_for_active",
        lambda client: None if client is stuck else object(),
    )
    monkeypatch.setattr(function_app, "_airflow_health_check", lambda _spn: None)

    function_app.resume_capacities(timer)

    assert healthy.resume_calls == 1


def test_airflow_health_check_skipped_when_workspace_unset(function_app, monkeypatch):
    monkeypatch.setattr(function_app, "HEALTHCHECK_WORKSPACE_ID", "")
    assert function_app._airflow_health_check(object()) is None
