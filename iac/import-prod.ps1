<#
.SYNOPSIS
    Adopt the hand-built production resources into Terraform state.

.DESCRIPTION
    fabric-pause-capacities-flex and its supporting resources were created
    through the portal. This brings them under Terraform without recreating
    them.

    Idempotent: every resource already present in state is skipped, so the
    script is safe to run on every pipeline execution and safe to re-run after
    a partial failure.

    Run `terraform plan` afterwards and read it carefully before applying. See
    docs/terraform-import.md for the diffs that are expected on first plan.

.PARAMETER SubscriptionId
    Subscription containing the resources.

.PARAMETER WhatIf
    Print the terraform import commands without running them.
#>
[CmdletBinding(SupportsShouldProcess)]
param(
    [string] $SubscriptionId = "910ebf13-1058-405d-b6cf-eda03e5288d1",
    [string] $ResourceGroup = "fabricpausecapacitiesapp",
    [string] $VarFile = "envs/prod.tfvars"
)

$ErrorActionPreference = "Stop"

$rgScope = "/subscriptions/$SubscriptionId/resourceGroups/$ResourceGroup"

# Terraform address -> Azure resource ID.
# Ordered parent-first so a failure part-way leaves a coherent state file.
$imports = [ordered]@{
    "azurerm_resource_group.this" = $rgScope

    "azurerm_storage_account.func" =
        "$rgScope/providers/Microsoft.Storage/storageAccounts/fabricpausecapacitiesapp"

    "azurerm_service_plan.func" =
        "$rgScope/providers/Microsoft.Web/serverfarms/ASP-fabricpausecapacitiesapp-cb3e"

    "azurerm_application_insights.func" =
        "$rgScope/providers/Microsoft.Insights/components/fabric-pause-capacities-flex"

    "azurerm_function_app_flex_consumption.func" =
        "$rgScope/providers/Microsoft.Web/sites/fabric-pause-capacities-flex"
}

$state = @(terraform state list 2>$null)

$imported = 0
$skipped = 0

foreach ($address in $imports.Keys) {
    $resourceId = $imports[$address]

    if ($state -contains $address) {
        Write-Host "skip    $address (already in state)" -ForegroundColor DarkGray
        $skipped++
        continue
    }

    if ($PSCmdlet.ShouldProcess($address, "terraform import")) {
        Write-Host "import  $address" -ForegroundColor Cyan
        terraform import -var-file="$VarFile" $address $resourceId
        if ($LASTEXITCODE -ne 0) {
            throw "Import failed for $address. State left intact; re-run to continue."
        }
        $imported++
    }
    else {
        Write-Host "would import $address <- $resourceId"
    }
}

Write-Host ""
Write-Host "Imported $imported resource(s), skipped $skipped already present." -ForegroundColor Green
Write-Host ""
Write-Host "Resources deliberately NOT imported:" -ForegroundColor Yellow
Write-Host "  - the storage container and deployment blob (recreated cleanly by apply)"
Write-Host "  - Log Analytics workspace (prod App Insights is classic, unattached)"
Write-Host "  - action group / alert rules (replaced by alerts.tf; delete the old ones by hand)"
Write-Host "  - orphaned ASP-fabric-pause-capacities-app-fcad and the stale"
Write-Host "    fabricpausecapacitiesapp App Insights component -- both unused, delete separately"
Write-Host ""
Write-Host "Next: terraform plan -var-file=$VarFile" -ForegroundColor Cyan
