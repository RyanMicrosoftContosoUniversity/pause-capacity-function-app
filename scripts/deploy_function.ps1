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

    # The ARM role assignment can exist before the storage data plane accepts
    # the managed identity. Retry only this observed deployment failure.
    if ($details -notmatch 'InaccessibleStorageException' -or
        $attempt -eq $MaxDeploymentAttempts) {
        throw "Zip deployment failed for $AppName (exit $deployExitCode). $details"
    }
    Write-Warning "Deployment storage is not accessible yet; retrying in $RetryDelaySeconds seconds."
    Start-Sleep -Seconds $RetryDelaySeconds
}

$expected = @("pause_capacities", "resume_capacities")
for ($attempt = 1; $attempt -le $MaxRegistrationAttempts; $attempt++) {
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
    if ($attempt -lt $MaxRegistrationAttempts) {
        Write-Host "Waiting for function indexing: $($missing -join ', ')."
        Start-Sleep -Seconds $RegistrationDelaySeconds
    }
}

throw "Deployment verification failed for ${AppName}: missing $($missing -join ', '); indexed: $($registered -join ', ')."
