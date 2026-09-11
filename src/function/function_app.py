"""Fabric capacity lifecycle: nightly pause, morning resume.

Runs in Azure Functions, deliberately *outside* Fabric, so the thing that
resumes the capacity can never be taken down by the capacity being paused.

Schedule (NCRONTAB is 6-field: {second} {minute} {hour} {day} {month} {day-of-week}):

    pause   0 0 23 * * *   -> 23:00
    resume  0 0 8  * * *   -> 08:00

Both run in the Function App's timezone, which is UTC unless WEBSITE_TIME_ZONE
is set. Pause and resume must agree on this.

Notes on behaviour:

* Both triggers act on *every* capacity in the resource group. This is
  intentional.
* No SKU change is performed. The Airflow workspace shares an F32 with ~80
  other workspaces, so resizing it would degrade all of them.
* Resume records observed readiness timestamps, because Fabric capacity
  resumes are reported to be occasionally flaky and DAG schedules should be
  set relative to measured warm-up rather than a guess.

This module is deliberately thin: it declares the triggers and nothing else.
The work lives in the ``capacity_ops`` package.

``capacity_ops`` is imported *inside* each trigger body rather than at module
scope. The Functions host imports this file to discover the ``@app`` decorators,
so an exception raised here produces an app with zero registered functions --
no host keys, no triggers, and a deploy that looks successful. ``fabric_utils``
is installed from a git branch, so that is a live risk. Deferring the import
turns a dependency failure into one failed invocation, which the "invocation
failed" alert already covers.
"""

import azure.functions as func

app = func.FunctionApp()


@app.timer_trigger(
    schedule="0 0 23 * * *",
    arg_name="myTimer",
    # Must stay False. When True this fires on every restart, deploy and scale
    # event, pausing capacities at arbitrary times of day.
    run_on_startup=False,
    use_monitor=False,
)
def pause_capacities(myTimer: func.TimerRequest) -> None:
    from capacity_ops import identity, operations

    operations.pause_all(identity.build_spn())


@app.timer_trigger(
    schedule="0 0 8 * * *",
    arg_name="myTimer",
    run_on_startup=False,
    use_monitor=False,
)
def resume_capacities(myTimer: func.TimerRequest) -> None:
    from capacity_ops import identity, operations

    operations.resume_all(identity.build_spn())
