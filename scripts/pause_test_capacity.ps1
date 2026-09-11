<#
.SYNOPSIS
    Pause the integration-test Fabric capacity so it costs nothing while idle.

.DESCRIPTION
    Runs as the final pipeline step with condition: always(), including when the
    tests failed -- a failed run is exactly when a capacity is most likely to be
    left running.

    Never destroys the capacity. Pausing preserves its workspaces and lets the
    next run resume in minutes rather than re-provisioning.

    Exits 0 even on failure to pause, so it cannot mask the real test result by
    turning a passing run red. A warning is emitted instead.
#>
[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)] [string] $SubscriptionId,
    [Parameter(Mandatory = $true)] [string] $ResourceGroup,
    [Parameter(Mandatory = $true)] [string] $CapacityName
)

$ErrorActionPreference = "Continue"

$protected = @("fabric-rg", "fabricpausecapacitiesapp")
if ($protected -contains $ResourceGroup) {
    Write-Error "Refusing to operate on protected resource group '$ResourceGroup'."
    exit 1
}

$capacityId = "/subscriptions/$SubscriptionId/resourceGroups/$ResourceGroup" +
              "/providers/Microsoft.Fabric/capacities/$CapacityName"

$state = az rest --method get `
    --uri "https://management.azure.com$capacityId`?api-version=2023-11-01" `
    --query "properties.state" -o tsv 2>$null

if (-not $state) {
    Write-Warning "Could not read state for $CapacityName; it may not exist yet. Nothing to pause."
    exit 0
}

if ($state -eq "Paused") {
    Write-Host "$CapacityName is already paused."
    exit 0
}

Write-Host "$CapacityName is $state; pausing to stop charges."
az rest --method post `
    --uri "https://management.azure.com$capacityId/suspend?api-version=2023-11-01" | Out-Host

if ($LASTEXITCODE -ne 0) {
    Write-Warning "Failed to pause $CapacityName. It is STILL BILLING -- pause it manually:"
    Write-Warning "  az rest --method post --uri `"https://management.azure.com$capacityId/suspend?api-version=2023-11-01`""
    exit 0
}

Write-Host "Paused $CapacityName."
