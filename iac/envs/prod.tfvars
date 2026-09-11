# PROD environment.
#
# Names match the resources that already exist and were built by hand, so that
# `terraform import` adopts them rather than proposing a replacement. Do not
# rename anything here without planning a migration -- name is ForceNew on most
# of these resources.

environment     = "prod"
subscription_id = "910ebf13-1058-405d-b6cf-eda03e5288d1"
location        = "eastus2"

resource_group_name = "fabricpausecapacitiesapp"

function_app_name         = "fabric-pause-capacities-flex"
storage_account_name      = "fabricpausecapacitiesapp"
service_plan_name         = "ASP-fabricpausecapacitiesapp-cb3e"
application_insights_name = "fabric-pause-capacities-flex"

# Production capacities live in a different resource group from the app that
# manages them. This is the real blast radius.
fabric_resource_group = "fabric-rg"
website_time_zone     = "UTC"

resume_poll_timeout_seconds = 900

# Set to the Fabric workspace whose Airflow jobs gate the morning DAG run.
healthcheck_workspace_id = ""

key_vault_name           = "kvfabricprodeus2rh"
key_vault_resource_group = "fabric-rg"
spn_secret_name          = "spn-secret"
azure_client_id          = "15a84224-c1e2-45e0-a2f5-fc8f5206f81d"

# Object (principal) ID of the same principal, used for its role assignments.
function_spn_object_id = "557fcf74-476a-4139-8d37-fb6b81cc4b92"
azure_tenant_id        = "35acf02c-4b87-4ae6-9221-ff5cafd430b4"

# No Terraform-owned capacity in prod: the capacities being paused are owned by
# the platform team in fabric-rg, not by this stack.
test_capacity = {
  enabled = false
  name    = ""
}

maximum_instance_count = 100
instance_memory_in_mb  = 2048

tags = {
  environment = "prod"
  service     = "fabric-capacity-pause"
  managed_by  = "terraform"
}
