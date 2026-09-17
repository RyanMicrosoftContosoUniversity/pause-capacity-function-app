<#
.SYNOPSIS
    Remove platform-injected connection strings from identity-based host storage.
#>
[CmdletBinding()]
param(
    [Parameter(Mandatory)] [string] $ResourceGroup,
    [Parameter(Mandatory)] [string] $AppName
)

$ErrorActionPreference = "Stop"
$PSNativeCommandUseErrorActionPreference = $false
$injected = @(az functionapp config appsettings list `
    --resource-group $ResourceGroup `
    --name $AppName `
    --query "[?name=='AzureWebJobsStorage' || name=='DEPLOYMENT_STORAGE_CONNECTION_STRING'].name" `
    -o tsv)
if ($LASTEXITCODE -ne 0) {
    throw "Cannot inspect injected storage settings on $AppName."
}
if ($injected.Count -eq 0) {
    Write-Host "No injected storage settings present."
    return
}

Write-Host "Removing injected settings: $($injected -join ', ')"
az functionapp config appsettings delete `
    --resource-group $ResourceGroup `
    --name $AppName `
    --setting-names $injected `
    --output none
if ($LASTEXITCODE -ne 0) {
    throw "Cannot remove injected storage settings from $AppName."
}
