# Importing the existing production stack into Terraform

`fabric-pause-capacities-flex` and its supporting resources were built by hand
through the portal before this Terraform existed. `iac/import-prod.ps1` adopts
them into state so that Terraform manages them from then on, without recreating
anything.

Run it once. It is idempotent, so leaving it wired into the pipeline behind the
`importProd` parameter is harmless.

## Procedure

### Bootstrap the deployment identity's RBAC permissions

The `fabric-sc-prod` service connection is a different principal from both the
Function App's managed identity and the runtime Fabric SPN. Its **Contributor**
role can update resources but cannot perform
`Microsoft.Authorization/roleAssignments/write`. This caused build 1074's
production apply to fail on September 14, 2026; the storage deprecation warnings
were not the cause.

Before applying, an administrator with role-assignment write permission at the
following scopes must run:

```powershell
.\iac\bootstrap-prod-rbac.ps1 -WhatIf
.\iac\bootstrap-prod-rbac.ps1
```

The script adds **Role Based Access Control Administrator**, with conditions on
both create and delete, to the production deployment principal:

| Scope | Allowed roles | Allowed recipient |
|---|---|---|
| Storage account `fabricpausecapacitiesapp` | Storage Blob Data Owner, Storage Queue Data Contributor, Storage Table Data Contributor | Production app's current managed identity |
| Key Vault `kvfabricprodeus2rh` | Key Vault Secrets User | Production app's current managed identity |
| Resource group `fabric-rg` | Contributor | Production runtime SPN |

No subscription-wide administrative role is granted, and the deployer cannot
delegate administrative roles through these grants. See Microsoft's
[conditional delegation guidance](https://learn.microsoft.com/en-us/azure/role-based-access-control/delegate-role-assignments-overview).
Existing broader permissions are not removed by this bootstrap.

This is an **administrator bootstrap**, not a pipeline step or a resource in
the application's Terraform state: the deployer must not grant itself access.
Existing matching grants are skipped; different conditions fail for manual
review instead of silently widening permissions. If an identity is replaced,
review the old grants and rerun with the new deployer/runtime object IDs; the
app's managed identity is resolved live. Keep the runtime SPN parameter aligned
with `function_spn_object_id` in `iac/envs/prod.tfvars`.

### Import and deploy

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

The importer also adopts the existing runtime SPN's Contributor assignment on
`fabric-rg`, using its actual Azure assignment ID. Without this import, fixing
the authorization error would expose a `RoleAssignmentExists` conflict.

After a partially failed apply, keep the remote state and rerun the pipeline
with `deployProd=true`, `importProd=true`, `skipInfra=false`, and
`skipIntegration=false` on `main` or a `release/*` branch. A fresh run obtains
new credentials after RBAC propagation and produces a fresh plan; do not reuse
the failed run's saved plan. Retain the `Fabric-Prod` environment approval.
Resources already in state are skipped, so the completed parts of the failed
apply are preserved.

### Deployment storage propagation and stale triggers

Creating an ARM role assignment does not mean the storage data plane accepts
the managed identity immediately. The first production zip deployment in build
1084 failed with `InaccessibleStorageException` and a storage 403, leaving the
old `timer_trigger` indexed. The old provisioner ignored the CLI failure and
accepted any registered function.

`scripts/deploy_function.ps1` now retries that specific storage-access failure
(at most ten deployment attempts, sixty seconds apart). Other deployment
failures are fatal. After a successful deploy, it waits up to twenty indexing
queries, fifteen seconds apart, for **both** `pause_capacities` and
`resume_capacities`; an old `timer_trigger` is never accepted as success.
Terraform waits for all declared runtime RBAC assignments before deployment.
The deployment script's hash is included in the resource triggers, so changing
the deployment logic also replaces an earlier falsely successful deployment.

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
