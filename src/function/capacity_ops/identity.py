"""Service principal construction, including the pre-migration env fallback.

``spn_setting`` and its legacy fallback are temporary: they exist only until
Terraform rewrites the production app's settings to the ``FABRIC_SPN_*`` names.
Keeping them here makes that cleanup a single-file deletion.
"""

import logging
import os


def spn_setting(primary, legacy):
    """Read an SPN setting, tolerating the pre-migration name.

    AZURE_CLIENT_ID and AZURE_TENANT_ID are *reserved* by the Azure Identity
    SDK. When AzureWebJobsStorage uses managed identity, the Functions host
    reads AZURE_CLIENT_ID and tries to authenticate as a **user-assigned**
    identity with that client ID. Ours is a service principal, not a
    user-assigned identity on this app, so the host fails with:

        No User Assigned or Delegated Managed Identity found
        for specified ClientId/ResourceId/PrincipalId

    ...which takes out the whole host: no secret repository, no host keys, no
    triggers. The app's own credentials therefore live under FABRIC_SPN_* names.

    The legacy fallback exists only so the un-migrated production app keeps
    working until Terraform rewrites its settings. Setting AZURE_CLIENT_ID is
    safe *there* because prod still uses a storage connection string rather
    than managed identity.
    """
    value = os.getenv(primary)
    if value:
        return value

    value = os.getenv(legacy)
    if value:
        logging.warning(
            "%s is unset; falling back to %s. %s is reserved by the Azure "
            "Identity SDK and breaks managed-identity storage access.",
            primary,
            legacy,
            legacy,
        )
    return value


def build_spn():
    # Imported inside the function to avoid import errors during worker init.
    from fabric_utils.service_principal import ServicePrincipal

    return ServicePrincipal(
        client_id=spn_setting("FABRIC_SPN_CLIENT_ID", "AZURE_CLIENT_ID"),
        tenant_id=spn_setting("FABRIC_SPN_TENANT_ID", "AZURE_TENANT_ID"),
        spn_secret_name=os.getenv("SPN_SECRET_NAME"),
        vault_url=os.getenv("VAULT_URL"),
    )
