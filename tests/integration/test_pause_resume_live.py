"""End-to-end pause/resume against the deployed TEST function app.

Opt-in: these are marked ``integration`` and excluded by the default pytest
addopts. Run them with ``pytest -m integration``.

What this actually proves, which unit tests cannot:

* the deployed package indexes both triggers (worker indexing is enabled and
  the Python v2 model is being read correctly)
* the function's service principal can genuinely pause and resume a capacity
  (RBAC on the target resource group is correct)
* a paused capacity comes back Active within the configured timeout

Safety: every capacity touched here lives in the resource group named by
``TEST_CAPACITY_RESOURCE_GROUP``. The test asserts that group is not the
production one before it does anything.
"""

import os
import time

import pytest
import requests
from azure.identity import DefaultAzureCredential

pytestmark = pytest.mark.integration

ARM = "https://management.azure.com"
API_VERSION = "2023-11-01"
SITE_API_VERSION = "2023-12-01"

PRODUCTION_RESOURCE_GROUPS = {"fabric-rg", "fabricpausecapacitiesapp"}

POLL_TIMEOUT_SECONDS = int(os.getenv("INTEGRATION_POLL_TIMEOUT", "600"))
POLL_INTERVAL_SECONDS = 15


def _require(name: str) -> str:
    value = os.getenv(name, "")
    if not value:
        pytest.skip(f"{name} is not set; integration tests need a deployed TEST stack")
    return value


@pytest.fixture(scope="module")
def config():
    cfg = {
        "subscription_id": _require("SUBSCRIPTION_ID"),
        "function_app_name": _require("FUNCTION_APP_NAME"),
        "function_app_rg": _require("FUNCTION_APP_RESOURCE_GROUP"),
        "capacity_name": _require("TEST_CAPACITY_NAME"),
        "capacity_rg": _require("TEST_CAPACITY_RESOURCE_GROUP"),
    }

    # Hard stop: never let an integration run reach a production capacity.
    assert cfg["capacity_rg"] not in PRODUCTION_RESOURCE_GROUPS, (
        f"refusing to run integration tests against {cfg['capacity_rg']!r}, "
        "which is a production resource group"
    )
    return cfg


@pytest.fixture(scope="module")
def token():
    credential = DefaultAzureCredential()
    return credential.get_token(f"{ARM}/.default").token


def _capacity_url(cfg):
    return (
        f"{ARM}/subscriptions/{cfg['subscription_id']}"
        f"/resourceGroups/{cfg['capacity_rg']}"
        f"/providers/Microsoft.Fabric/capacities/{cfg['capacity_name']}"
    )


def _capacity_state(cfg, token):
    response = requests.get(
        f"{_capacity_url(cfg)}?api-version={API_VERSION}",
        headers={"Authorization": f"Bearer {token}"},
        timeout=60,
    )
    response.raise_for_status()
    return response.json()["properties"]["state"]


def _capacity_action(cfg, token, action):
    response = requests.post(
        f"{_capacity_url(cfg)}/{action}?api-version={API_VERSION}",
        headers={"Authorization": f"Bearer {token}"},
        timeout=120,
    )
    response.raise_for_status()


def _wait_for_state(cfg, token, expected, timeout=POLL_TIMEOUT_SECONDS):
    deadline = time.monotonic() + timeout
    last = None
    while time.monotonic() < deadline:
        last = _capacity_state(cfg, token)
        if last == expected:
            return True
        time.sleep(POLL_INTERVAL_SECONDS)
    pytest.fail(f"capacity stayed {last!r}, never reached {expected!r} within {timeout}s")


def _master_key(cfg, token):
    response = requests.post(
        f"{ARM}/subscriptions/{cfg['subscription_id']}"
        f"/resourceGroups/{cfg['function_app_rg']}"
        f"/providers/Microsoft.Web/sites/{cfg['function_app_name']}"
        f"/host/default/listKeys?api-version={SITE_API_VERSION}",
        headers={"Authorization": f"Bearer {token}"},
        timeout=60,
    )
    response.raise_for_status()
    return response.json()["masterKey"]


def _invoke(cfg, master_key, function_name):
    """Fire a timer trigger on demand via the admin API."""
    response = requests.post(
        f"https://{cfg['function_app_name']}.azurewebsites.net" f"/admin/functions/{function_name}",
        headers={"x-functions-key": master_key, "Content-Type": "application/json"},
        json={"input": ""},
        timeout=120,
    )
    assert response.status_code in (
        200,
        202,
    ), f"admin invoke of {function_name} returned {response.status_code}: {response.text}"


def test_both_triggers_are_indexed_on_the_deployed_app(config, token):
    """A Flex deploy can succeed while indexing silently fails, leaving an app
    with zero functions. Assert the host actually sees both."""
    response = requests.get(
        f"{ARM}/subscriptions/{config['subscription_id']}"
        f"/resourceGroups/{config['function_app_rg']}"
        f"/providers/Microsoft.Web/sites/{config['function_app_name']}"
        f"/functions?api-version={SITE_API_VERSION}",
        headers={"Authorization": f"Bearer {token}"},
        timeout=60,
    )
    response.raise_for_status()
    names = {item["properties"]["name"] for item in response.json()["value"]}
    assert {"pause_capacities", "resume_capacities"} <= names, f"indexed functions: {names}"


def test_pause_trigger_pauses_the_test_capacity(config, token):
    if _capacity_state(config, token) != "Active":
        _capacity_action(config, token, "resume")
        _wait_for_state(config, token, "Active")

    _invoke(config, _master_key(config, token), "pause_capacities")
    _wait_for_state(config, token, "Paused")


def test_resume_trigger_brings_the_capacity_back(config, token):
    if _capacity_state(config, token) != "Paused":
        _capacity_action(config, token, "suspend")
        _wait_for_state(config, token, "Paused")

    _invoke(config, _master_key(config, token), "resume_capacities")
    _wait_for_state(config, token, "Active")


def test_pause_is_idempotent(config, token):
    """Pausing an already-paused capacity must be a no-op, not an error. The
    nightly run relies on this whenever a capacity was paused manually."""
    if _capacity_state(config, token) != "Paused":
        _capacity_action(config, token, "suspend")
        _wait_for_state(config, token, "Paused")

    _invoke(config, _master_key(config, token), "pause_capacities")
    time.sleep(30)
    assert _capacity_state(config, token) == "Paused"
