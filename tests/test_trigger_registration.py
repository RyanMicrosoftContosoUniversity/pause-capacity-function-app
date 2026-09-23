"""Guards on the trigger *registration* itself.

These exist because the failure modes are silent and expensive:

* ``run_on_startup=True`` makes the timer fire on every restart, deploy and
  scale event, pausing capacities at arbitrary times of day. This was a real
  bug, fixed in 3d09f26.
* The schedules are 6-field NCRONTAB. A 5-field cron (the Linux habit) is
  accepted at deploy time but silently shifts the trigger by a field.
* Pause must stay 7-day while resume is weekday-only. Narrowing pause to match
  resume would let a capacity resumed by hand on a Saturday bill until Monday.
"""

import pytest

EXPECTED_SCHEDULES = {
    "pause_capacities": "0 0 23 * * *",
    "resume_capacities": "0 0 8 * * 1-5",
}


def _timer_bindings(function_app):
    # get_functions() records every name it sees in app.functions_bindings and
    # raises on a repeat, so calling it more than once per module import trips a
    # spurious "does not have a unique function name". Clear the cache first.
    function_app.app.functions_bindings = {}

    bindings = {}
    for fn in function_app.app.get_functions():
        for binding in fn.get_bindings():
            raw = binding.get_dict_repr()
            if raw.get("type") == "timerTrigger":
                bindings[fn.get_function_name()] = raw
    return bindings


def test_both_triggers_are_registered(function_app):
    assert set(_timer_bindings(function_app)) == set(EXPECTED_SCHEDULES)


@pytest.mark.parametrize("name,schedule", sorted(EXPECTED_SCHEDULES.items()))
def test_schedule_is_six_field_ncrontab(function_app, name, schedule):
    binding = _timer_bindings(function_app)[name]
    assert binding["schedule"] == schedule
    assert len(binding["schedule"].split()) == 6, "NCRONTAB requires 6 fields"


@pytest.mark.parametrize("name", sorted(EXPECTED_SCHEDULES))
def test_run_on_startup_is_disabled(function_app, name):
    """Regression guard. True here pauses capacities on every deploy."""
    binding = _timer_bindings(function_app)[name]
    assert binding.get("runOnStartup") is False


def test_pause_and_resume_do_not_overlap(function_app):
    bindings = _timer_bindings(function_app)
    pause_hour = int(bindings["pause_capacities"]["schedule"].split()[2])
    resume_hour = int(bindings["resume_capacities"]["schedule"].split()[2])
    assert pause_hour != resume_hour


def test_resume_runs_on_weekdays_only(function_app):
    """Nothing is expected to run at the weekend, so a weekend capacity has to
    be started by hand. NCRONTAB day-of-week is 0-6 with 0 = Sunday."""
    day_of_week = _timer_bindings(function_app)["resume_capacities"]["schedule"].split()[5]
    assert day_of_week == "1-5"


def test_pause_runs_every_day(function_app):
    """Deliberately *not* narrowed to match resume. Pause is the only thing
    that catches a capacity someone resumed by hand on a Saturday; restricting
    it to weekdays would let that capacity bill until Monday night."""
    day_of_week = _timer_bindings(function_app)["pause_capacities"]["schedule"].split()[5]
    assert day_of_week == "*"
