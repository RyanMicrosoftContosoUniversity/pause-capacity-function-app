resource "azurerm_resource_group" "this" {
  name     = var.resource_group_name
  location = var.location
  tags     = var.tags
}

# --- Storage: host runtime state + deployment package ----------------------

resource "azurerm_storage_account" "func" {
  name                     = var.storage_account_name
  resource_group_name      = azurerm_resource_group.this.name
  location                 = azurerm_resource_group.this.location
  account_tier             = "Standard"
  account_replication_type = "LRS"
  min_tls_version          = "TLS1_2"
  tags                     = var.tags

  blob_properties {
    delete_retention_policy {
      days = 7
    }
  }
}

resource "azurerm_storage_container" "deployments" {
  name                  = "deployments"
  storage_account_id    = azurerm_storage_account.func.id
  container_access_type = "private"
}

# --- Telemetry -------------------------------------------------------------

resource "azurerm_log_analytics_workspace" "func" {
  name                = "law-${var.function_app_name}"
  location            = azurerm_resource_group.this.location
  resource_group_name = azurerm_resource_group.this.name
  sku                 = "PerGB2018"
  retention_in_days   = var.log_retention_days
  tags                = var.tags
}

resource "azurerm_application_insights" "func" {
  name                = var.application_insights_name
  location            = azurerm_resource_group.this.location
  resource_group_name = azurerm_resource_group.this.name
  workspace_id        = azurerm_log_analytics_workspace.func.id
  application_type    = "web"
  tags                = var.tags
}

# --- Flex Consumption plan -------------------------------------------------

resource "azurerm_service_plan" "func" {
  name                = var.service_plan_name
  location            = azurerm_resource_group.this.location
  resource_group_name = azurerm_resource_group.this.name
  os_type             = "Linux"
  sku_name            = "FC1"
  tags                = var.tags
}

# --- Deployment package ----------------------------------------------------

data "archive_file" "function_zip" {
  type        = "zip"
  source_dir  = "${path.module}/../src/function"
  output_path = "${path.module}/function.zip"

  excludes = [
    "__pycache__",
    "local.settings.json",
    ".pytest_cache",
    ".ruff_cache",
  ]
}

resource "azurerm_storage_blob" "function_zip" {
  name                   = "function-${data.archive_file.function_zip.output_sha256}.zip"
  storage_account_name   = azurerm_storage_account.func.name
  storage_container_name = azurerm_storage_container.deployments.name
  type                   = "Block"
  source                 = data.archive_file.function_zip.output_path
  content_md5            = data.archive_file.function_zip.output_md5
}

# --- Key Vault access for the function's managed identity ------------------

data "azurerm_key_vault" "spn" {
  name                = var.key_vault_name
  resource_group_name = var.key_vault_resource_group
}

# The SPN client secret is referenced, never copied. Putting the literal value
# in an app setting would also put it in Terraform state in plaintext.
resource "azurerm_role_assignment" "func_kv_secrets" {
  scope                = data.azurerm_key_vault.spn.id
  role_definition_name = "Key Vault Secrets User"
  principal_id         = azurerm_function_app_flex_consumption.func.identity[0].principal_id
}

# --- Function App ----------------------------------------------------------

resource "azurerm_function_app_flex_consumption" "func" {
  name                = var.function_app_name
  location            = azurerm_resource_group.this.location
  resource_group_name = azurerm_resource_group.this.name
  service_plan_id     = azurerm_service_plan.func.id
  tags                = var.tags

  storage_container_type      = "blobContainer"
  storage_container_endpoint  = "${azurerm_storage_account.func.primary_blob_endpoint}${azurerm_storage_container.deployments.name}"
  storage_authentication_type = "SystemAssignedIdentity"

  runtime_name    = "python"
  runtime_version = "3.11"

  maximum_instance_count = var.maximum_instance_count
  instance_memory_in_mb  = var.instance_memory_in_mb

  https_only = true

  identity {
    type = "SystemAssigned"
  }

  app_settings = {
    APPLICATIONINSIGHTS_CONNECTION_STRING = azurerm_application_insights.func.connection_string

    # Required for the Python v2 programming model: the host discovers
    # functions by importing function_app.py and reading its decorators rather
    # than scanning per-function function.json files.
    AzureWebJobsFeatureFlags = "EnableWorkerIndexing"

    # Identity-based host storage. Do NOT also set a bare `AzureWebJobsStorage`,
    # even to "" -- on Flex Consumption an empty value suppresses the
    # identity-based path and silently disables the host's storage access.
    AzureWebJobsStorage__accountName = azurerm_storage_account.func.name

    # NOTE: do not set WEBSITE_RUN_FROM_PACKAGE on Flex Consumption. Flex uses
    # functionAppConfig.deployment.storage (the storage_container_* arguments
    # above); WEBSITE_RUN_FROM_PACKAGE takes precedence and fails the deploy
    # with "RunFromExternalUrlException: Deployment is not needed in this case".

    SUBSCRIPTION_ID       = var.subscription_id
    FABRIC_RESOURCE_GROUP = var.fabric_resource_group
    WEBSITE_TIME_ZONE     = var.website_time_zone

    # Deliberately NOT named AZURE_CLIENT_ID / AZURE_TENANT_ID.
    #
    # Those names are reserved by the Azure Identity SDK. Because
    # AzureWebJobsStorage above uses managed identity, the Functions host reads
    # AZURE_CLIENT_ID and tries to authenticate as a *user-assigned* identity
    # with that client ID. This app has a system-assigned identity, so the host
    # fails with "No User Assigned or Delegated Managed Identity found" and
    # loses access to its own secret repository -- no host keys, no triggers,
    # and listKeys returns "Encountered an error from host runtime".
    FABRIC_SPN_CLIENT_ID = var.azure_client_id
    FABRIC_SPN_TENANT_ID = var.azure_tenant_id

    VAULT_URL       = data.azurerm_key_vault.spn.vault_uri
    SPN_SECRET_NAME = var.spn_secret_name

    HEALTHCHECK_WORKSPACE_ID    = var.healthcheck_workspace_id
    RESUME_POLL_TIMEOUT_SECONDS = tostring(var.resume_poll_timeout_seconds)
  }

  site_config {
    application_insights_connection_string = azurerm_application_insights.func.connection_string
  }
}

# --- Push the package into the app ----------------------------------------
#
# Flex Consumption needs an explicit deploy call to load code into wwwroot; the
# storage_container_* config only tells the app where packages live, it does not
# push one. The azurerm provider has no Flex deploy resource yet.

resource "null_resource" "function_deploy" {
  triggers = {
    zip_sha256      = data.archive_file.function_zip.output_sha256
    function_app_id = azurerm_function_app_flex_consumption.func.id
  }

  provisioner "local-exec" {
    interpreter = ["pwsh", "-NoProfile", "-Command"]
    command     = <<-EOT
      $ErrorActionPreference = 'Continue'
      az functionapp deployment source config-zip `
        --resource-group ${azurerm_resource_group.this.name} `
        --name ${var.function_app_name} `
        --src ${data.archive_file.function_zip.output_path} `
        --build-remote true 2>&1 | Out-Host

      # The CLI's post-deploy host key check sporadically exits 1 even when the
      # zip deploy succeeded. Verify registration instead of trusting the code.
      Start-Sleep -Seconds 30
      $fns = az functionapp function list `
        --resource-group ${azurerm_resource_group.this.name} `
        --name ${var.function_app_name} `
        --query "[].name" -o tsv 2>$null

      if (-not $fns) {
        Write-Error "Deploy verification failed: no functions registered on ${var.function_app_name}"
        exit 1
      }
      Write-Host "Deployed functions: $fns"
    EOT
  }

  depends_on = [
    azurerm_function_app_flex_consumption.func,
    azurerm_storage_blob.function_zip,
    azurerm_role_assignment.func_storage_blob,
  ]
}
