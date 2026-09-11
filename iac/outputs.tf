output "function_app_name" {
  description = "Name of the deployed Function App."
  value       = azurerm_function_app_flex_consumption.func.name
}

output "function_app_hostname" {
  description = "Default hostname, used by the pipeline smoke stage."
  value       = azurerm_function_app_flex_consumption.func.default_hostname
}

output "function_principal_id" {
  description = "System-assigned identity of the Function App."
  value       = azurerm_function_app_flex_consumption.func.identity[0].principal_id
}

output "application_insights_app_id" {
  description = "App Insights application ID, used to query invocation results in CI."
  value       = azurerm_application_insights.func.app_id
}

output "managed_resource_group" {
  description = "Resource group whose capacities this deployment pauses and resumes."
  value       = var.fabric_resource_group
}

output "test_capacity_name" {
  description = "Name of the integration-test capacity, or empty in environments without one."
  value       = var.test_capacity.enabled ? azurerm_fabric_capacity.test[0].name : ""
}

output "test_capacity_id" {
  description = "Resource ID of the integration-test capacity, consumed by the pause/resume test stage."
  value       = var.test_capacity.enabled ? azurerm_fabric_capacity.test[0].id : ""
}
