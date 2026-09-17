<#
.SYNOPSIS
    Deploy a Flex Consumption package and require both lifecycle triggers.
#>
[CmdletBinding()]
param(
    [Parameter(Mandatory)] [string] $ResourceGroup,
    [Parameter(Mandatory)] [string] $AppName,
    [Parameter(Mandatory)] [string] $ZipPath,
    [ValidateRange(1, 20)] [int] $MaxDeploymentAttempts = 10,
    [ValidateRange(0, 300)] [int] $RetryDelaySeconds = 60,
    [ValidateRange(1, 40)] [int] $MaxRegistrationAttempts = 20,
    [ValidateRange(0, 300)] [int] $RegistrationDelaySeconds = 15
)

$ErrorActionPreference = "Stop"
$PSNativeCommandUseErrorActionPreference = $false

for ($attempt = 1; $attempt -le $MaxDeploymentAttempts; $attempt++) {
    Write-Host "Deploying $AppName (attempt $attempt/$MaxDeploymentAttempts)."
    $output = @(az functionapp deployment source config-zip `
        --resource-group $ResourceGroup `
        --name $AppName `
        --src $ZipPath `
        --build-remote true `
        --timeout 600 `
        --output none 2>&1)
    $deployExitCode = $LASTEXITCODE
    $details = $output -join [Environment]::NewLine
    Write-Host $details

    if ($deployExitCode -eq 0) {
        break
    }

    # This specific CLI diagnostic occurs after a successful package deploy,
    # not a failed build/upload. Cleanup and an explicit successful trigger
    # sync below are still required; existing function names alone never suffice.
    if ($details.Contains("Deployment was successful but the app appears to be unhealthy.")) {
        Write-Warning "Package deployed; recovering host storage before verifying trigger synchronization."
        break
    }

    # The ARM role assignment can exist before the storage data plane accepts
    # the managed identity. Retry only this observed deployment failure.
    if ($details -notmatch 'InaccessibleStorageException' -or
        $attempt -eq $MaxDeploymentAttempts) {
        throw "Zip deployment failed for $AppName (exit $deployExitCode). $details"
    }
    Write-Warning "Deployment storage is not accessible yet; retrying in $RetryDelaySeconds seconds."
    Start-Sleep -Seconds $RetryDelaySeconds
}

& "$PSScriptRoot/remove_injected_storage_settings.ps1" `
    -ResourceGroup $ResourceGroup -AppName $AppName

$appId = az functionapp show --resource-group $ResourceGroup --name $AppName --query id -o tsv
if ($LASTEXITCODE -ne 0 -or -not $appId) {
    throw "Cannot resolve the resource ID of $AppName."
}

$expected = @("pause_capacities", "resume_capacities")
$registered = @()
$missing = $expected
$syncExitCode = 1
for ($attempt = 1; $attempt -le $MaxRegistrationAttempts; $attempt++) {
    $syncOutput = @(az rest --method post `
        --uri "$appId/syncfunctiontriggers?api-version=2024-04-01" `
        --output none 2>&1)
    $syncExitCode = $LASTEXITCODE
    if ($syncExitCode -eq 0) {
        $registered = @(az functionapp function list `
            --resource-group $ResourceGroup `
            --name $AppName `
            --query "[].name" -o tsv)
        if ($LASTEXITCODE -ne 0) {
            throw "Cannot query registered functions for $AppName."
        }
        $names = @($registered | ForEach-Object { ($_ -split '/')[-1] })
        $missing = @($expected | Where-Object { $names -cnotcontains $_ })
        if ($missing.Count -eq 0) {
            Write-Host "Deployed functions: $($registered -join ', ')"
            return
        }
    } else {
        Write-Warning "Trigger synchronization is not ready: $($syncOutput -join ' ')"
    }
    if ($attempt -lt $MaxRegistrationAttempts) {
        Write-Host "Waiting for function indexing: $($missing -join ', ')."
        Start-Sleep -Seconds $RegistrationDelaySeconds
    }
}

throw "Deployment verification failed for ${AppName}: sync exit $syncExitCode; missing $($missing -join ', '); indexed: $($registered -join ', ')."
