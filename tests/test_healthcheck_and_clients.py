"""Tests for the post-resume Airflow readiness probe and the client factories.

These paths import their dependencies lazily inside the function body, so they
are exercised here by stubbing the modules in ``sys.modules`` rather than by
patching attributes on ``function_app``.
"""

import sys
import types

import pytest
import requests


class _FakeSecret:
    value = "secret-value"


class _FakeSpn:
    tenant_id = "tenant"
    client_id = "client"
    client_secret = _FakeSecret()


class _Response:
    def __init__(self, status_code, payload=None):
        self.status_code = status_code
        self._payload = payload or {}

    def json(self):
        return self._payload


@pytest.fixture
def stub_credential(monkeypatch):
    """Replace ClientSecretCredential so no token is ever requested."""

    class _Token:
        token = "fake-token"

    class _Credential:
        def __init__(self, **kwargs):
            self.kwargs = kwargs

        def get_token(self, _scope):
            return _Token()

    import azure.identity

    monkeypatch.setattr(azure.identity, "ClientSecretCredential", _Credential)
    return _Credential


def test_health_check_returns_timestamp_on_success(function_app, monkeypatch, stub_credential):
    monkeypatch.setattr(function_app, "HEALTHCHECK_WORKSPACE_ID", "ws-123")
    monkeypatch.setattr(
        requests,
        "get",
        lambda *a, **k: _Response(200, {"value": [{"id": "job-1"}]}),
    )

    observed = function_app._airflow_health_check(_FakeSpn())

    assert observed is not None
    assert observed.tzinfo is not None


def test_health_check_gives_up_after_timeout(function_app, monkeypatch, stub_credential):
    """A workspace that never serves Airflow jobs must return None rather than
    blocking the invocation until the host kills it."""
    import itertools

    monkeypatch.setattr(function_app, "HEALTHCHECK_WORKSPACE_ID", "ws-123")
    monkeypatch.setattr(function_app, "HEALTHCHECK_TIMEOUT_SECONDS", 5)
    monkeypatch.setattr(function_app, "HEALTHCHECK_INTERVAL_SECONDS", 1)
    monkeypatch.setattr(requests, "get", lambda *a, **k: _Response(503))

    clock = itertools.count(0, 2)
    monkeypatch.setattr(function_app.time, "monotonic", lambda: next(clock))

    assert function_app._airflow_health_check(_FakeSpn()) is None


def test_health_check_survives_transport_errors(function_app, monkeypatch, stub_credential):
    import itertools

    def _boom(*_args, **_kwargs):
        raise requests.ConnectionError("no route to host")

    monkeypatch.setattr(function_app, "HEALTHCHECK_WORKSPACE_ID", "ws-123")
    monkeypatch.setattr(function_app, "HEALTHCHECK_TIMEOUT_SECONDS", 5)
    monkeypatch.setattr(function_app, "HEALTHCHECK_INTERVAL_SECONDS", 1)
    monkeypatch.setattr(requests, "get", _boom)

    clock = itertools.count(0, 2)
    monkeypatch.setattr(function_app.time, "monotonic", lambda: next(clock))

    assert function_app._airflow_health_check(_FakeSpn()) is None


# --- client factories ------------------------------------------------------


@pytest.fixture
def stub_fabric_utils(monkeypatch):
    """Install a minimal fake fabric_utils package.

    The real one is installed from a git branch, so pinning test behaviour to it
    would make the suite depend on whatever that branch happens to contain.
    """
    captured = {}

    class ServicePrincipal:
        def __init__(self, **kwargs):
            captured["spn_kwargs"] = kwargs

    class Extract:
        @staticmethod
        def extract_id(item):
            return item["id"]

        @staticmethod
        def extract_subscription_id(_rid):
            return "sub"

        @staticmethod
        def extract_resource_group(_rid):
            return "rg"

        @staticmethod
        def extract_capacity(rid):
            return rid.split("/")[-1]

    class FabricCapacitiesBySubscription:
        def __init__(self, **kwargs):
            captured["listing_kwargs"] = kwargs

        def list_capacities_by_resource_group(self):
            return [{"id": "/subscriptions/sub/rg/capacities/cap-a"}]

    class FabricCapacityMGMT:
        def __init__(self, **kwargs):
            captured.setdefault("capacity_kwargs", []).append(kwargs)
            self.capacity_name = kwargs["capacity_name"]

    pkg = types.ModuleType("fabric_utils")
    sp_mod = types.ModuleType("fabric_utils.service_principal")
    sp_mod.ServicePrincipal = ServicePrincipal
    cap_mod = types.ModuleType("fabric_utils.fabric_capacity")
    cap_mod.Extract = Extract
    cap_mod.FabricCapacitiesBySubscription = FabricCapacitiesBySubscription
    cap_mod.FabricCapacityMGMT = FabricCapacityMGMT

    monkeypatch.setitem(sys.modules, "fabric_utils", pkg)
    monkeypatch.setitem(sys.modules, "fabric_utils.service_principal", sp_mod)
    monkeypatch.setitem(sys.modules, "fabric_utils.fabric_capacity", cap_mod)
    return captured


def test_build_spn_reads_credentials_from_environment(function_app, stub_fabric_utils, monkeypatch):
    monkeypatch.setenv("FABRIC_SPN_CLIENT_ID", "client-id")
    monkeypatch.setenv("FABRIC_SPN_TENANT_ID", "tenant-id")
    monkeypatch.setenv("SPN_SECRET_NAME", "secret-name")
    monkeypatch.setenv("VAULT_URL", "https://vault.example/")

    # _build_spn is stubbed by the shared fixture; reach for the real one.
    import importlib

    module = importlib.reload(function_app)
    module._build_spn()

    assert stub_fabric_utils["spn_kwargs"] == {
        "client_id": "client-id",
        "tenant_id": "tenant-id",
        "spn_secret_name": "secret-name",
        "vault_url": "https://vault.example/",
    }


def test_spn_settings_prefer_the_non_reserved_names(function_app, monkeypatch):
    """Regression guard.

    AZURE_CLIENT_ID is reserved by the Azure Identity SDK. With managed-identity
    storage, the Functions host reads it and tries to authenticate as a
    user-assigned identity that does not exist, which kills the host's secret
    repository entirely -- no host keys, no triggers, and listKeys returns
    "Encountered an error from host runtime". The app's own credentials must
    therefore be read from FABRIC_SPN_* first.
    """
    monkeypatch.setenv("FABRIC_SPN_CLIENT_ID", "correct")
    monkeypatch.setenv("AZURE_CLIENT_ID", "reserved-and-wrong")

    assert function_app._spn_setting("FABRIC_SPN_CLIENT_ID", "AZURE_CLIENT_ID") == "correct"


def test_spn_settings_fall_back_for_the_unmigrated_prod_app(function_app, monkeypatch):
    monkeypatch.delenv("FABRIC_SPN_CLIENT_ID", raising=False)
    monkeypatch.setenv("AZURE_CLIENT_ID", "legacy")

    assert function_app._spn_setting("FABRIC_SPN_CLIENT_ID", "AZURE_CLIENT_ID") == "legacy"


def test_spn_settings_returns_none_when_neither_is_set(function_app, monkeypatch):
    monkeypatch.delenv("FABRIC_SPN_CLIENT_ID", raising=False)
    monkeypatch.delenv("AZURE_CLIENT_ID", raising=False)

    assert function_app._spn_setting("FABRIC_SPN_CLIENT_ID", "AZURE_CLIENT_ID") is None


def test_iter_capacity_clients_is_scoped_to_the_configured_resource_group(
    function_app, stub_fabric_utils, monkeypatch
):
    """The listing call must be the resource-group variant. Using the
    subscription-wide one would put every capacity in the blast radius."""
    monkeypatch.setenv("SUBSCRIPTION_ID", "sub-123")
    monkeypatch.setattr(function_app, "RESOURCE_GROUP", "test-capacity-pause-app-rg")

    clients = list(function_app._iter_capacity_clients(object()))

    assert [c.capacity_name for c in clients] == ["cap-a"]
    assert stub_fabric_utils["listing_kwargs"]["rg_name"] == "test-capacity-pause-app-rg"
    assert stub_fabric_utils["listing_kwargs"]["subscription_id"] == "sub-123"
