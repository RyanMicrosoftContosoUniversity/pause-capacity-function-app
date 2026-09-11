"""Manual smoke check: pause every capacity in a named resource group.

This is an operator tool, not a test. It was previously named ``test_fa_code.py``,
which meant pytest collected it and executed the pause at import time -- running
the suite would pause every Fabric capacity in the subscription.

Two things changed to make that impossible:

* the module no longer does anything at import time, and
* the resource group must be passed explicitly; there is no subscription-wide
  default any more.

Usage:

    python scripts/manual_pause_check.py --resource-group test-capacity-pause-app-rg
    python scripts/manual_pause_check.py --resource-group ... --dry-run
"""

import argparse
import logging
import os
import sys

from fabric_utils.fabric_capacity import (
    Extract,
    FabricCapacitiesBySubscription,
    FabricCapacityMGMT,
)
from fabric_utils.service_principal import ServicePrincipal

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")

# Pausing anything in this resource group requires --i-know-what-im-doing.
PROTECTED_RESOURCE_GROUPS = {"fabric-rg"}


def build_spn() -> ServicePrincipal:
    # FABRIC_SPN_* rather than AZURE_*: the latter are reserved by the Azure
    # Identity SDK and break managed-identity storage access in the deployed
    # app. See spn_setting in capacity_ops/identity.py.
    return ServicePrincipal(
        client_id=os.getenv("FABRIC_SPN_CLIENT_ID") or os.getenv("AZURE_CLIENT_ID"),
        tenant_id=os.getenv("FABRIC_SPN_TENANT_ID") or os.getenv("AZURE_TENANT_ID"),
        spn_secret_name=os.getenv("SPN_SECRET_NAME"),
        vault_url=os.getenv("VAULT_URL"),
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--resource-group",
        required=True,
        help="Resource group whose capacities will be paused.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="List capacities and their state without pausing anything.",
    )
    parser.add_argument(
        "--i-know-what-im-doing",
        action="store_true",
        help=f"Required to target a protected group: {sorted(PROTECTED_RESOURCE_GROUPS)}",
    )
    args = parser.parse_args(argv)

    rg = args.resource_group
    if rg in PROTECTED_RESOURCE_GROUPS and not args.i_know_what_im_doing:
        parser.error(
            f"{rg!r} is a protected resource group. Re-run with "
            f"--i-know-what-im-doing if you really mean it."
        )

    subscription_id = os.getenv("SUBSCRIPTION_ID")
    if not subscription_id:
        parser.error("SUBSCRIPTION_ID is not set.")

    spn = build_spn()
    listing_client = FabricCapacitiesBySubscription(
        spn=spn, subscription_id=subscription_id, rg_name=rg
    )

    capacities = list(listing_client.list_capacities_by_resource_group())
    if not capacities:
        logging.warning("No capacities found in resource group %s", rg)
        return 0

    for item in capacities:
        resource_id = Extract.extract_id(item)
        capacity_client = FabricCapacityMGMT(
            spn=spn,
            subscription_id=Extract.extract_subscription_id(resource_id),
            resource_group=Extract.extract_resource_group(resource_id),
            capacity_name=Extract.extract_capacity(resource_id),
        )
        name = capacity_client.capacity_name
        state = capacity_client.get_capacity()["properties"]["state"]

        if args.dry_run:
            logging.info("[dry-run] %s is %s; would pause", name, state)
            continue

        if state == "Paused":
            logging.info("%s already paused", name)
            continue

        capacity_client.pause_capacity()
        logging.info("Paused %s", name)

    return 0


if __name__ == "__main__":
    sys.exit(main())
