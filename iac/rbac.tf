# Role assignments for the Function App's system-assigned identity.
#
# Two distinct identities are involved and conflating them is the usual source
# of 401s here:
#
#   * the Function App's managed identity -- used by the *host* to reach its own
#     storage account (deployment package, host keys, scale state)
#   * the service principal in AZURE_CLIENT_ID -- used by the *code* to call the
#     Fabric capacity management API
#
# Identity-based host storage (storage_authentication_type =
# "SystemAssignedIdentity") needs all three data-plane roles below. Blob alone
# is not enough: the host also writes queue and table state, and a missing role
# shows up as an app that deploys cleanly then never triggers.

locals {
  func_principal_id = azurerm_function_app_flex_consumption.func.identity[0].principal_id
}

resource "azurerm_role_assignment" "func_storage_blob" {
  scope                = azurerm_storage_account.func.id
  role_definition_name = "Storage Blob Data Owner"
  principal_id         = local.func_principal_id
}

resource "azurerm_role_assignment" "func_storage_queue" {
  scope                = azurerm_storage_account.func.id
  role_definition_name = "Storage Queue Data Contributor"
  principal_id         = local.func_principal_id
}

resource "azurerm_role_assignment" "func_storage_table" {
  scope                = azurerm_storage_account.func.id
  role_definition_name = "Storage Table Data Contributor"
  principal_id         = local.func_principal_id
}

# The service principal the *code* authenticates as needs rights on the
# capacities it pauses. Scoped to the resource group it manages -- never the
# subscription -- so a misconfigured FABRIC_RESOURCE_GROUP cannot reach further
# than intended.
resource "azurerm_role_assignment" "spn_capacity_contributor" {
  count = var.function_spn_object_id == "" ? 0 : 1

  scope                = "/subscriptions/${var.subscription_id}/resourceGroups/${var.fabric_resource_group}"
  role_definition_name = "Contributor"
  principal_id         = var.function_spn_object_id
}
