"""Enumerating capacities and reading or awaiting their ARM state."""

import logging
import time
from datetime import UTC, datetime

from . import config


def iter_capacity_clients(spn):
    """Yield a FabricCapacityMGMT for every capacity in the resource group."""
    from fabric_utils.fabric_capacity import (
        Extract,
        FabricCapacitiesBySubscription,
        FabricCapacityMGMT,
    )

    listing_client = FabricCapacitiesBySubscription(
        spn=spn,
        subscription_id=config.subscription_id(),
        rg_name=config.RESOURCE_GROUP,
    )

    for item in listing_client.list_capacities_by_resource_group():
        resource_id = Extract.extract_id(item)
        yield FabricCapacityMGMT(
            spn=spn,
            subscription_id=Extract.extract_subscription_id(resource_id),
            resource_group=Extract.extract_resource_group(resource_id),
            capacity_name=Extract.extract_capacity(resource_id),
        )


def capacity_state(capacity_client) -> str:
    try:
        return capacity_client.get_capacity()["properties"]["state"]
    except Exception as exc:  # noqa: BLE001
        logging.warning("Could not read state for %s: %s", capacity_client.capacity_name, exc)
        return "Unknown"


def wait_for_active(capacity_client):
    """Poll until the capacity reports Active. Returns the observed time."""
    deadline = time.monotonic() + config.RESUME_POLL_TIMEOUT_SECONDS
    while time.monotonic() < deadline:
        state = capacity_state(capacity_client)
        if state == "Active":
            observed = datetime.now(UTC)
            logging.info(
                "Capacity %s is Active at %s",
                capacity_client.capacity_name,
                observed.isoformat(),
            )
            return observed
        logging.info("Capacity %s state=%s; waiting", capacity_client.capacity_name, state)
        time.sleep(config.RESUME_POLL_INTERVAL_SECONDS)
    logging.error(
        "Capacity %s did not reach Active within %ss",
        capacity_client.capacity_name,
        config.RESUME_POLL_TIMEOUT_SECONDS,
    )
    return None
