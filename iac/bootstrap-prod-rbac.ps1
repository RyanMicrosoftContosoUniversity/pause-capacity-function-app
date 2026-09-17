<#
.SYNOPSIS
    Grant the PROD deployment identity constrained role-assignment management.

.DESCRIPTION
    Run once as an RBAC administrator, outside the deployment pipeline.
    Contributor cannot grant roles, including the deployer's own permissions.
    Each grant is restricted to the role IDs and recipient required by this
    stack. Existing grants with different conditions require manual review.
    Re-run after recreating the app's managed identity or service connection.
#>
[CmdletBinding(SupportsShouldProcess)]
param(
    [guid] $SubscriptionId = "910ebf13-1058-405d-b6cf-eda03e5288d1",
    [guid] $DeployerObjectId = "e4347f96-6c0e-4329-8f65-bcbcf0c34de6",
    [guid] $FunctionSpnObjectId = "557fcf74-476a-4139-8d37-fb6b81cc4b92"
)

$ErrorActionPreference = "Stop"
$subscriptionScope = "/subscriptions/$SubscriptionId"
$appScope = "$subscriptionScope/resourceGroups/fabricpausecapacitiesapp"
$fabricScope = "$subscriptionScope/resourceGroups/fabric-rg"
$adminRoleId = "f58310d9-a9f6-439a-9e8d-f62e7b41a168"

$principal = az functionapp identity show `
    --subscription $SubscriptionId `
    --resource-group fabricpausecapacitiesapp `
    --name fabric-pause-capacities-flex `
    --query principalId -o tsv
if ($LASTEXITCODE -ne 0 -or -not $principal) {
    throw "Cannot resolve the production Function App's managed identity."
}
$functionPrincipalId = [guid] "$principal"

$grants = @(
    @{
        Scope = "$appScope/providers/Microsoft.Storage/storageAccounts/fabricpausecapacitiesapp"
        Principal = $functionPrincipalId
        # Blob Data Owner, Queue Data Contributor, Table Data Contributor.
        Roles = "b7e6dc6d-f1e8-4753-8033-0f276bb0955b, 974c5e8b-45b9-4653-ba55-5f855dd0fb88, 0a9a7e1f-b9d0-4cc4-a60d-0319b160aaa3"
    }
    @{
        Scope = "$fabricScope/providers/Microsoft.KeyVault/vaults/kvfabricprodeus2rh"
        Principal = $functionPrincipalId
        Roles = "4633458b-17de-408a-b874-0445c86b69e6" # Key Vault Secrets User.
    }
    @{
        Scope = $fabricScope
        Principal = $FunctionSpnObjectId
        Roles = "b24988ac-6180-42a0-ab88-20f7382dd24c" # Contributor.
    }
)

foreach ($grant in $grants) {
    # Writes evaluate request attributes; deletes evaluate the existing resource.
    $condition = @"
((!(ActionMatches{'Microsoft.Authorization/roleAssignments/write'})) OR
 (@Request[Microsoft.Authorization/roleAssignments:RoleDefinitionId] ForAnyOfAnyValues:GuidEquals {$($grant.Roles)}
  AND @Request[Microsoft.Authorization/roleAssignments:PrincipalId] ForAnyOfAnyValues:GuidEquals {$($grant.Principal)}))
AND
((!(ActionMatches{'Microsoft.Authorization/roleAssignments/delete'})) OR
 (@Resource[Microsoft.Authorization/roleAssignments:RoleDefinitionId] ForAnyOfAnyValues:GuidEquals {$($grant.Roles)}
  AND @Resource[Microsoft.Authorization/roleAssignments:PrincipalId] ForAnyOfAnyValues:GuidEquals {$($grant.Principal)}))
"@
    $condition = ($condition -replace '\s+', ' ').Trim()

    $json = az role assignment list `
        --subscription $SubscriptionId `
        --assignee-object-id $DeployerObjectId `
        --scope $grant.Scope `
        --fill-principal-name false -o json
    if ($LASTEXITCODE -ne 0) {
        throw "Cannot read deployment role assignments at $($grant.Scope)."
    }
    $existing = @($json | ConvertFrom-Json | Where-Object {
        $_.scope -eq $grant.Scope -and
        $_.roleDefinitionId -eq "$subscriptionScope/providers/Microsoft.Authorization/roleDefinitions/$adminRoleId"
    })
    if ($existing.Count -gt 0) {
        if ($existing.Count -ne 1 -or $existing[0].conditionVersion -ne "2.0" -or
            ($existing[0].condition -replace '\s+', '') -cne ($condition -replace '\s+', '')) {
            throw "Existing RBAC administrator grant differs at $($grant.Scope). Review it manually; no permissions changed at this scope."
        }
        Write-Host "Already configured: $($grant.Scope)"
        continue
    }

    if ($PSCmdlet.ShouldProcess($grant.Scope, "Delegate roles $($grant.Roles) to $($grant.Principal) via deployer $DeployerObjectId")) {
        az role assignment create `
            --subscription $SubscriptionId `
            --assignee-object-id $DeployerObjectId `
            --assignee-principal-type ServicePrincipal `
            --role $adminRoleId `
            --scope $grant.Scope `
            --condition $condition `
            --condition-version "2.0" `
            --description "Fabric pause PROD Terraform: constrained role management" `
            --output none
        if ($LASTEXITCODE -ne 0) {
            throw "RBAC bootstrap failed at $($grant.Scope). Completed grants are retained; re-run to continue."
        }
        Write-Host "Configured: $($grant.Scope)"
    }
}
