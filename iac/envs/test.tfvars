# TEST environment.
#
# Everything here is self-contained: the app pauses capacities in
# test-capacity-pause-app-rg, which is also where its own test capacity lives.
# There is no path from a test run to a production capacity.

environment     = "test"
subscription_id = "910ebf13-1058-405d-b6cf-eda03e5288d1"
location        = "eastus2"

resource_group_name = "test-capacity-pause-app-rg"

function_app_name         = "fabric-pause-capacities-test"
storage_account_name      = "stfabpausetesteus2"
service_plan_name         = "asp-fabric-pause-capacities-test"
application_insights_name = "appi-fabric-pause-capacities-test"

# The app's blast radius. Identical to resource_group_name on purpose.
fabric_resource_group = "test-capacity-pause-app-rg"
website_time_zone     = "UTC"

# Keep the test loop short; prod waits the full 15 minutes.
resume_poll_timeout_seconds = 300

# Airflow health check is a prod concern; there is no Airflow workspace in test.
healthcheck_workspace_id = ""

key_vault_name           = "kvfabricnonprodeus2rh"
key_vault_resource_group = "fabric-rg"
spn_secret_name          = "fabric-automation-spn-secret"
azure_client_id          = "__SET_IN_PIPELINE__"
azure_tenant_id          = "35acf02c-4b87-4ae6-9221-ff5cafd430b4"

test_capacity = {
  enabled = true
  name    = "fabpausetestcap"
  sku     = "F2"
}

maximum_instance_count = 40
instance_memory_in_mb  = 2048

tags = {
  environment = "test"
  service     = "fabric-capacity-pause"
  managed_by  = "terraform"
}
