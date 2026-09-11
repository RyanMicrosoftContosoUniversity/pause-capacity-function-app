variable "environment" {
  type        = string
  description = "Deployment environment. Drives naming and guard rails."

  validation {
    condition     = contains(["test", "prod"], var.environment)
    error_message = "environment must be either 'test' or 'prod'."
  }
}

variable "subscription_id" {
  type        = string
  description = "Subscription hosting the Function App and (for test) the Fabric capacity."
}

variable "location" {
  type        = string
  description = "Azure region for all resources in this stack."
  default     = "eastus2"
}

variable "resource_group_name" {
  type        = string
  description = "Resource group that holds the Function App stack."
}

variable "tags" {
  type        = map(string)
  description = "Tags applied to every resource that supports them."
  default     = {}
}

# --- Function App ----------------------------------------------------------

variable "function_app_name" {
  type        = string
  description = "Name of the Flex Consumption Function App."
}

variable "storage_account_name" {
  type        = string
  description = "Storage account backing the Function App host and deployment container."
}

variable "service_plan_name" {
  type        = string
  description = "Flex Consumption (FC1) service plan name."
}

variable "application_insights_name" {
  type        = string
  description = "Application Insights component for function telemetry."
}

variable "instance_memory_in_mb" {
  type        = number
  description = "Per-instance memory for Flex Consumption."
  default     = 2048
}

variable "maximum_instance_count" {
  type        = number
  description = "Flex Consumption scale ceiling."
  default     = 100
}

variable "log_retention_days" {
  type        = number
  description = "Log Analytics retention for the workspace backing App Insights."
  default     = 30
}

# --- Behaviour of the deployed app -----------------------------------------

variable "fabric_resource_group" {
  type        = string
  description = <<-EOT
    Resource group whose Fabric capacities the app pauses and resumes.

    This is the app's entire blast radius: both triggers act on EVERY capacity
    in this group. The test environment must point at its own resource group so
    a test run can never pause a production capacity.
  EOT
}

variable "website_time_zone" {
  type        = string
  description = "Timezone the NCRONTAB schedules are evaluated in. Pause and resume must agree."
  default     = "UTC"
}

variable "healthcheck_workspace_id" {
  type        = string
  description = "Fabric workspace polled for Airflow readiness after resume. Empty disables the check."
  default     = ""
}

variable "resume_poll_timeout_seconds" {
  type        = number
  description = "How long resume waits for a capacity to report Active."
  default     = 900
}

# --- Service principal / secrets -------------------------------------------

variable "key_vault_name" {
  type        = string
  description = "Key Vault holding the service principal secret."
}

variable "key_vault_resource_group" {
  type        = string
  description = "Resource group of the Key Vault (it is shared, so it lives elsewhere)."
}

variable "spn_secret_name" {
  type        = string
  description = "Name of the Key Vault secret holding the SPN client secret."
}

variable "azure_client_id" {
  type        = string
  description = "Client ID of the service principal the function authenticates as."
}

variable "azure_tenant_id" {
  type        = string
  description = "Tenant ID of the service principal."
}

variable "function_spn_object_id" {
  type        = string
  description = <<-EOT
    Object ID (not client ID) of the service principal in azure_client_id.

    When set, Terraform grants it Contributor on fabric_resource_group so the
    code can pause and resume capacities. Leave empty if that grant is managed
    elsewhere.
  EOT
  default     = ""
}

# --- Test Fabric capacity --------------------------------------------------

variable "test_capacity" {
  type = object({
    enabled                = bool
    name                   = string
    sku                    = optional(string, "F2")
    administration_members = optional(list(string), [])
  })

  description = <<-EOT
    Persistent Fabric capacity used as the pause/resume target for integration
    tests. Created if absent and never destroyed by Terraform; the pipeline
    pauses it after each run so it costs nothing while idle.

    Disabled in prod, where the capacities being managed live in a separate
    resource group and are not owned by this stack.
  EOT

  default = {
    enabled = false
    name    = ""
  }

  validation {
    condition     = !var.test_capacity.enabled || length(var.test_capacity.name) > 0
    error_message = "test_capacity.name is required when test_capacity.enabled is true."
  }
}

# --- Alerting --------------------------------------------------------------

variable "alert_email" {
  type        = string
  description = "Address notified when a pause or resume invocation fails. Empty disables alerting."
  default     = ""
}

variable "action_group_name" {
  type        = string
  description = "Action group name for failure notifications."
  default     = ""
}
