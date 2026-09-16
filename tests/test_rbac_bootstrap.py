"""Exercise the operator scripts without Azure calls or Terraform state changes."""

import json
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
PWSH = shutil.which("pwsh")
pytestmark = pytest.mark.skipif(PWSH is None, reason="PowerShell 7 is required")

AZ_MOCK = r"""
$global:grants = @()
$global:creates = @()
$roleResourceId = '/subscriptions/910ebf13-1058-405d-b6cf-eda03e5288d1/providers/' +
    'Microsoft.Authorization/roleDefinitions/f58310d9-a9f6-439a-9e8d-f62e7b41a168'
function az {
    $global:LASTEXITCODE = 0
    if ($args[0] -eq 'functionapp') {
        if ($mode -eq 'no-identity') { return }
        return '0e907306-e8b1-479f-9873-8a83053f51ea'
    }
    if ($args[0] -ne 'role') { throw "Unexpected az call: $args" }
    $scope = $args[[array]::IndexOf($args, '--scope') + 1]
    if ($args[2] -eq 'list') {
        if ($mode -eq 'list-failure') {
            $global:LASTEXITCODE = 1
            return
        }
        $matching = @($global:grants | Where-Object { $_.scope -eq $scope })
        if ($mode -eq 'broader-grant') {
            $matching = @(@{
                scope = $scope
                roleDefinitionId = $roleResourceId
                condition = $null
                conditionVersion = $null
            })
        }
        return ConvertTo-Json -InputObject $matching -Depth 5 -Compress
    }
    if ($args[2] -ne 'create') { throw "Unexpected az role call: $args" }
    if ($mode -eq 'create-failure') {
        $global:LASTEXITCODE = 1
        return
    }
    $global:creates += ,@($args)
    $global:grants += @{
        scope = $scope
        roleDefinitionId = $roleResourceId
        condition = $args[[array]::IndexOf($args, '--condition') + 1]
        conditionVersion = '2.0'
    }
}
"""


def run_powershell(script):
    return subprocess.run(
        [PWSH, "-NoProfile", "-NonInteractive", "-Command", script],
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )


def bootstrap(mode="", what_if=False):
    path = str(ROOT / "iac" / "bootstrap-prod-rbac.ps1").replace("'", "''")
    invocation = f"& '{path}'" + (" -WhatIf" if what_if else "")
    # Invoke twice: successful bootstrap must not create duplicate assignments.
    result = run_powershell(
        f"$ErrorActionPreference = 'Stop'; $mode = '{mode}';\n"
        + AZ_MOCK
        + f"\n{invocation}\n{invocation}\n"
        + "'CALLS:' + (ConvertTo-Json -InputObject @($global:creates) -Depth 5 -Compress)"
    )
    return result


def calls(result):
    assert result.returncode == 0, result.stdout + result.stderr
    return json.loads(
        next(line[6:] for line in result.stdout.splitlines() if line.startswith("CALLS:"))
    )


def argument(command, name):
    return command[command.index(name) + 1]


def test_bootstrap_is_idempotent_and_constrains_both_actions():
    created = calls(bootstrap())
    assert len(created) == 3
    expected = [
        (
            "/providers/Microsoft.Storage/storageAccounts/fabricpausecapacitiesapp",
            "0e907306-e8b1-479f-9873-8a83053f51ea",
            [
                "b7e6dc6d-f1e8-4753-8033-0f276bb0955b",
                "974c5e8b-45b9-4653-ba55-5f855dd0fb88",
                "0a9a7e1f-b9d0-4cc4-a60d-0319b160aaa3",
            ],
        ),
        (
            "/providers/Microsoft.KeyVault/vaults/kvfabricprodeus2rh",
            "0e907306-e8b1-479f-9873-8a83053f51ea",
            ["4633458b-17de-408a-b874-0445c86b69e6"],
        ),
        (
            "/resourceGroups/fabric-rg",
            "557fcf74-476a-4139-8d37-fb6b81cc4b92",
            ["b24988ac-6180-42a0-ab88-20f7382dd24c"],
        ),
    ]
    for command, (scope_suffix, principal, roles) in zip(created, expected, strict=True):
        assert argument(command, "--scope").endswith(scope_suffix)
        assert argument(command, "--assignee-object-id") == "e4347f96-6c0e-4329-8f65-bcbcf0c34de6"
        assert argument(command, "--assignee-principal-type") == "ServicePrincipal"
        assert argument(command, "--condition-version") == "2.0"
        condition = argument(command, "--condition")
        for action, source in [("write", "@Request"), ("delete", "@Resource")]:
            assert (
                f"ActionMatches{{'Microsoft.Authorization/roleAssignments/{action}'}}" in condition
            )
            assert (
                f"{source}[Microsoft.Authorization/roleAssignments:RoleDefinitionId]" in condition
            )
            assert f"{source}[Microsoft.Authorization/roleAssignments:PrincipalId]" in condition
        assert condition.count(principal) == 2
        for role in roles:
            assert condition.count(role) == 2
        assert argument(command, "--role") not in condition


def test_bootstrap_what_if_does_not_create_assignments():
    assert calls(bootstrap(what_if=True)) == []


@pytest.mark.parametrize(
    ("mode", "message"),
    [
        ("no-identity", "Cannot resolve"),
        ("list-failure", "Cannot read deployment role assignments"),
        ("create-failure", "RBAC bootstrap failed"),
        ("broader-grant", "Existing RBAC administrator grant differs"),
    ],
)
def test_bootstrap_surfaces_failures_and_rejects_broader_grants(mode, message):
    result = bootstrap(mode)
    assert result.returncode != 0
    assert message in result.stderr


@pytest.mark.parametrize("already_imported", [False, True])
def test_prod_import_adopts_existing_contributor_assignment(already_imported):
    path = str(ROOT / "iac" / "import-prod.ps1").replace("'", "''")
    address = "azurerm_role_assignment.spn_capacity_contributor[0]"
    state = [
        "azurerm_resource_group.this",
        "azurerm_storage_account.func",
        "azurerm_service_plan.func",
        "azurerm_application_insights.func",
        "azurerm_function_app_flex_consumption.func",
    ]
    if already_imported:
        state.append(address)
    state_json = json.dumps(state)
    result = run_powershell(f"""
$ErrorActionPreference = 'Stop'
$global:imports = @()
$global:state = '{state_json}' | ConvertFrom-Json
function terraform {{
    $global:LASTEXITCODE = 0
    if ($args[0] -eq 'state') {{ return $global:state }}
    if ($args[0] -ne 'import') {{ throw "Unexpected terraform call: $args" }}
    $global:imports += ,@($args)
}}
& '{path}'
'CALLS:' + (ConvertTo-Json -InputObject @($global:imports) -Depth 5 -Compress)
""")
    imported = calls(result)
    if already_imported:
        assert imported == []
    else:
        assert len(imported) == 1
        assert imported[0][-2] == address
        assert imported[0][-1].endswith(
            "/resourceGroups/fabric-rg/providers/Microsoft.Authorization/roleAssignments/"
            "3996eb6a-409e-4bc0-8a64-bbf3e55ab504"
        )
