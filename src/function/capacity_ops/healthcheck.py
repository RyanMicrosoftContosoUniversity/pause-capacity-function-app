"""Post-resume readiness probe against the Fabric REST API."""

import logging
import time
from datetime import UTC, datetime

from . import config


def airflow_health_check(spn):
    """Confirm the workspace serves Airflow job items after resume.

    A capacity reporting Active does not by itself mean workload items are
    serving. Listing Airflow jobs exercises the path the DAGs actually need.
    """
    if not config.HEALTHCHECK_WORKSPACE_ID:
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
        f"{config.HEALTHCHECK_WORKSPACE_ID}/apacheAirflowJobs"
    )

    deadline = time.monotonic() + config.HEALTHCHECK_TIMEOUT_SECONDS
    while time.monotonic() < deadline:
        try:
            response = requests.get(url, headers={"Authorization": f"Bearer {token}"}, timeout=60)
            if response.status_code == 200:
                jobs = response.json().get("value", [])
                observed = datetime.now(UTC)
                logging.info(
                    "Airflow health check passed at %s (%d job(s))",
                    observed.isoformat(),
                    len(jobs),
                )
                return observed
            logging.info("Airflow health check HTTP %s; retrying", response.status_code)
        except Exception as exc:  # noqa: BLE001
            logging.info("Airflow health check error (%s); retrying", exc)
        time.sleep(config.HEALTHCHECK_INTERVAL_SECONDS)

    logging.error(
        "Airflow health check did not pass within %ss", config.HEALTHCHECK_TIMEOUT_SECONDS
    )
    return None
