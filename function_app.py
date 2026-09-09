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
"""

import logging
import os
import time
from datetime import datetime, timezone

import azure.functions as func

app = func.FunctionApp()

RESOURCE_GROUP = os.getenv("FABRIC_RESOURCE_GROUP", "fabric-rg")

# How long to wait for a resumed capacity to report Active.
RESUME_POLL_TIMEOUT_SECONDS = int(os.getenv("RESUME_POLL_TIMEOUT_SECONDS", "900"))
RESUME_POLL_INTERVAL_SECONDS = int(os.getenv("RESUME_POLL_INTERVAL_SECONDS", "20"))

# Optional: workspace to health-check after resume.
HEALTHCHECK_WORKSPACE_ID = os.getenv("HEALTHCHECK_WORKSPACE_ID", "")
HEALTHCHECK_TIMEOUT_SECONDS = int(os.getenv("HEALTHCHECK_TIMEOUT_SECONDS", "600"))
HEALTHCHECK_INTERVAL_SECONDS = int(os.getenv("HEALTHCHECK_INTERVAL_SECONDS", "30"))


def _build_spn():
    # Imported inside functions to avoid import errors during worker init.
    from fabric_utils.service_principal import ServicePrincipal

    return ServicePrincipal(
        client_id=os.getenv("AZURE_CLIENT_ID"),
        tenant_id=os.getenv("AZURE_TENANT_ID"),
        spn_secret_name=os.getenv("SPN_SECRET_NAME"),
        vault_url=os.getenv("VAULT_URL"),
    )


def _iter_capacity_clients(spn):
    """Yield a FabricCapacityMGMT for every capacity in the resource group."""
    from fabric_utils.fabric_capacity import (
        Extract,
        FabricCapacitiesBySubscription,
        FabricCapacityMGMT,
    )

    subscription_id = os.getenv("SUBSCRIPTION_ID")
    listing_client = FabricCapacitiesBySubscription(
        spn=spn, subscription_id=subscription_id, rg_name=RESOURCE_GROUP
    )

    for item in listing_client.list_capacities_by_resource_group():
        resource_id = Extract.extract_id(item)
        yield FabricCapacityMGMT(
            spn=spn,
            subscription_id=Extract.extract_subscription_id(resource_id),
            resource_group=Extract.extract_resource_group(resource_id),
            capacity_name=Extract.extract_capacity(resource_id),
        )


def _capacity_state(capacity_client) -> str:
    try:
        return capacity_client.get_capacity()["properties"]["state"]
    except Exception as exc:  # noqa: BLE001
        logging.warning(
            "Could not read state for %s: %s", capacity_client.capacity_name, exc
        )
        return "Unknown"


def _wait_for_active(capacity_client):
    """Poll until the capacity reports Active. Returns the observed time."""
    deadline = time.monotonic() + RESUME_POLL_TIMEOUT_SECONDS
    while time.monotonic() < deadline:
        state = _capacity_state(capacity_client)
        if state == "Active":
            observed = datetime.now(timezone.utc)
            logging.info(
                "Capacity %s is Active at %s",
                capacity_client.capacity_name,
                observed.isoformat(),
            )
            return observed
        logging.info(
            "Capacity %s state=%s; waiting", capacity_client.capacity_name, state
        )
        time.sleep(RESUME_POLL_INTERVAL_SECONDS)
    logging.error(
        "Capacity %s did not reach Active within %ss",
        capacity_client.capacity_name,
        RESUME_POLL_TIMEOUT_SECONDS,
    )
    return None


def _airflow_health_check(spn):
    """Confirm the workspace serves Airflow job items after resume.

    A capacity reporting Active does not by itself mean workload items are
    serving. Listing Airflow jobs exercises the path the DAGs actually need.
    """
    if not HEALTHCHECK_WORKSPACE_ID:
        logging.info("HEALTHCHECK_WORKSPACE_ID not set; skipping Airflow health check")
        return None

    import requests
    from azure.identity import ClientSecretCredential

    credential = ClientSecretCredential(
        tenant_id=spn.tenant_id,
        client_id=spn.client_id,
        client_secret=spn.client_secret.value,
    )
    token = credential.get_token("https://api.fabric.microsoft.com/.default").token
    url = (
        f"https://api.fabric.microsoft.com/v1/workspaces/"
        f"{HEALTHCHECK_WORKSPACE_ID}/apacheAirflowJobs"
    )

    deadline = time.monotonic() + HEALTHCHECK_TIMEOUT_SECONDS
    while time.monotonic() < deadline:
        try:
            response = requests.get(
                url, headers={"Authorization": f"Bearer {token}"}, timeout=60
            )
            if response.status_code == 200:
                jobs = response.json().get("value", [])
                observed = datetime.now(timezone.utc)
                logging.info(
                    "Airflow health check passed at %s (%d job(s))",
                    observed.isoformat(),
                    len(jobs),
                )
                return observed
            logging.info("Airflow health check HTTP %s; retrying", response.status_code)
        except Exception as exc:  # noqa: BLE001
            logging.info("Airflow health check error (%s); retrying", exc)
        time.sleep(HEALTHCHECK_INTERVAL_SECONDS)

    logging.error(
        "Airflow health check did not pass within %ss", HEALTHCHECK_TIMEOUT_SECONDS
    )
    return None


@app.timer_trigger(
    schedule="0 0 23 * * *",
    arg_name="myTimer",
    # Must stay False. When True this fires on every restart, deploy and scale
    # event, pausing capacities at arbitrary times of day.
    run_on_startup=False,
    use_monitor=False,
)
def pause_capacities(myTimer: func.TimerRequest) -> None:
    logging.info("Pause trigger started for resource group %s", RESOURCE_GROUP)
    spn = _build_spn()

    paused, skipped, failed = [], [], []
    for capacity_client in _iter_capacity_clients(spn):
        name = capacity_client.capacity_name
        try:
            if _capacity_state(capacity_client) == "Paused":
                logging.info("Capacity %s already paused", name)
                skipped.append(name)
                continue
            capacity_client.pause_capacity()
            paused.append(name)
            logging.info("Paused capacity %s", name)
        except Exception as exc:  # noqa: BLE001
            # One capacity failing must not stop the rest from pausing.
            logging.error("Failed to pause capacity %s: %s", name, exc)
            failed.append(name)

    logging.info(
        "Pause complete. paused=%s skipped=%s failed=%s", paused, skipped, failed
    )


@app.timer_trigger(
    schedule="0 0 8 * * *",
    arg_name="myTimer",
    run_on_startup=False,
    use_monitor=False,
)
def resume_capacities(myTimer: func.TimerRequest) -> None:
    logging.info("Resume trigger started for resource group %s", RESOURCE_GROUP)
    requested_at = datetime.now(timezone.utc)
    spn = _build_spn()

    resumed, skipped, failed = [], [], []
    for capacity_client in _iter_capacity_clients(spn):
        name = capacity_client.capacity_name
        try:
            if _capacity_state(capacity_client) == "Active":
                logging.info("Capacity %s already active", name)
                skipped.append(name)
                continue
            capacity_client.resume_capacity()
            ready_at = _wait_for_active(capacity_client)
            if ready_at is None:
                failed.append(name)
                continue
            resumed.append(name)
            logging.info(
                "Capacity %s resumed. requested=%s ready=%s elapsed=%ss",
                name,
                requested_at.isoformat(),
                ready_at.isoformat(),
                round((ready_at - requested_at).total_seconds()),
            )
        except Exception as exc:  # noqa: BLE001
            logging.error("Failed to resume capacity %s: %s", name, exc)
            failed.append(name)

    airflow_ready_at = _airflow_health_check(spn)
    logging.info(
        "Resume complete. resumed=%s skipped=%s failed=%s airflow_ready_at=%s",
        resumed,
        skipped,
        failed,
        airflow_ready_at.isoformat() if airflow_ready_at else "not-verified",
    )


