# Importing the existing production stack into Terraform

`fabric-pause-capacities-flex` and its supporting resources were built by hand
through the portal before this Terraform existed. `iac/import-prod.ps1` adopts
them into state so that Terraform manages them from then on, without recreating
anything.

Run it once. It is idempotent, so leaving it wired into the pipeline behind the
`importProd` parameter is harmless.

## Procedure

```powershell
cd iac

terraform init `
  -backend-config=backends/prod.hcl `
  -backend-config="resource_group_name=terraform-rg" `
  -backend-config="storage_account_name=terraformsaeheus2" `
  -backend-config="container_name=tf-state-container"

# Preview without touching state
./import-prod.ps1 -WhatIf

./import-prod.ps1

terraform plan -var-file=envs/prod.tfvars `
  -var="azure_client_id=<spn-client-id>" `
  -var="key_vault_name=kvfabricprodeus2rh"
```

**Read the plan before applying.** Import only records that a resource exists; it
does not reconcile configuration. The first plan will therefore show real diffs.

## What the first plan is expected to show

These are intentional changes, not import errors:

| Change | Why | Risk |
|---|---|---|
| `https_only: false -> true` | The existing app accepts plain HTTP. | None. The triggers are timer-based; nothing calls it over HTTP. |
| `storage_authentication_type -> SystemAssignedIdentity` | Prod currently authenticates to its deployment container with `DEPLOYMENT_STORAGE_CONNECTION_STRING`. | **Breaks deploys until the role assignments in `rbac.tf` propagate.** Apply during a window where a failed deploy is acceptable, and confirm the app still indexes both functions afterwards. |
| `AZURE_CLIENT_SECRET` removed from app settings | The secret is currently stored in plaintext in app configuration. The code reads it from Key Vault via `VAULT_URL` + `SPN_SECRET_NAME`. | Verify the function's managed identity has **Key Vault Secrets User** on `kvfabricprodeus2rh` before applying. `rbac.tf` creates this, but propagation can take a few minutes. |
| Log Analytics workspace created | Prod App Insights is a classic component with no workspace. | None; the existing component is retained and linked. |
| New alert rules added | `alerts.tf` replaces the untargeted `success == false` rule with per-function rules. | None. Delete the old rules by hand afterwards. |
| Tags added | Nothing is currently tagged. | None. |

## Deliberately not imported

Left out of the script, each for a reason:

- **Storage container and deployment blob** — recreated cleanly by `apply`; the
  existing `app-package-*` container is superseded.
- **Action group `fabric-pause-fail`, scheduled query rule
  `failed fabric capacity pause`, activity log alert
  `fabric-pause-app-server-down`** — superseded by `alerts.tf`. Remove them
  manually once the new rules are confirmed firing.
- **`ASP-fabric-pause-capacities-app-fcad`** — an orphaned service plan with no
  apps on it. Delete separately.
- **`fabricpausecapacitiesapp` App Insights component** and its Failure
  Anomalies rule — a stale component with no telemetry in 30 days. Delete
  separately.

## If an import goes wrong

Imports are recorded one at a time, so a failure part-way leaves earlier imports
intact. Re-running skips what is already present.

To back a single resource out of state without touching Azure:

```powershell
terraform state rm azurerm_function_app_flex_consumption.func
```

`terraform state rm` only forgets the resource; it never deletes it.
