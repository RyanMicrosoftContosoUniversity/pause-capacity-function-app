"""What a pause or resume run actually does, across every capacity.

Both operations iterate *every* capacity in the resource group and swallow
per-capacity failures, so one bad capacity cannot leave the rest running
overnight or stop the rest from coming back in the morning. They return the
tally as well as logging it, so callers and tests can inspect the outcome
without scraping log records.
"""

import logging
from datetime import UTC, datetime

from . import capacity, config, healthcheck


class Result:
    """Outcome of a run, bucketed by what happened to each capacity."""

    def __init__(self):
        self.succeeded = []
        self.skipped = []
        self.failed = []


def pause_all(spn) -> Result:
    logging.info("Pause trigger started for resource group %s", config.RESOURCE_GROUP)
    result = Result()

    for capacity_client in capacity.iter_capacity_clients(spn):
        name = capacity_client.capacity_name
        try:
            if capacity.capacity_state(capacity_client) == "Paused":
                logging.info("Capacity %s already paused", name)
                result.skipped.append(name)
                continue
            capacity_client.pause_capacity()
            result.succeeded.append(name)
            logging.info("Paused capacity %s", name)
        except Exception as exc:  # noqa: BLE001
            # One capacity failing must not stop the rest from pausing.
            logging.error("Failed to pause capacity %s: %s", name, exc)
            result.failed.append(name)

    logging.info(
        "Pause complete. paused=%s skipped=%s failed=%s",
        result.succeeded,
        result.skipped,
        result.failed,
    )
    return result


def resume_all(spn) -> Result:
    logging.info("Resume trigger started for resource group %s", config.RESOURCE_GROUP)
    requested_at = datetime.now(UTC)
    result = Result()

    for capacity_client in capacity.iter_capacity_clients(spn):
        name = capacity_client.capacity_name
        try:
            if capacity.capacity_state(capacity_client) == "Active":
                logging.info("Capacity %s already active", name)
                result.skipped.append(name)
                continue
            capacity_client.resume_capacity()
            ready_at = capacity.wait_for_active(capacity_client)
            if ready_at is None:
                result.failed.append(name)
                continue
            result.succeeded.append(name)
            logging.info(
                "Capacity %s resumed. requested=%s ready=%s elapsed=%ss",
                name,
                requested_at.isoformat(),
                ready_at.isoformat(),
                round((ready_at - requested_at).total_seconds()),
            )
        except Exception as exc:  # noqa: BLE001
            logging.error("Failed to resume capacity %s: %s", name, exc)
            result.failed.append(name)

    airflow_ready_at = healthcheck.airflow_health_check(spn)
    logging.info(
        "Resume complete. resumed=%s skipped=%s failed=%s airflow_ready_at=%s",
        result.succeeded,
        result.skipped,
        result.failed,
        airflow_ready_at.isoformat() if airflow_ready_at else "not-verified",
    )
    return result
