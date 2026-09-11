# Failure alerting for the pause and resume invocations.
#
# The existing prod rule queries `requests | where success == false` with no
# function-name filter, so it fires for either trigger while being named for
# pause only. This version reports which function failed, which matters now
# that resume exists and polls for up to 15 minutes before giving up.

locals {
  alerting_enabled  = var.alert_email != "" && var.action_group_name != ""
  action_group_name = var.action_group_name != "" ? var.action_group_name : "ag-${var.function_app_name}"
}

resource "azurerm_monitor_action_group" "failures" {
  count = local.alerting_enabled ? 1 : 0

  name                = local.action_group_name
  resource_group_name = azurerm_resource_group.this.name
  short_name          = substr(replace(var.environment, "-", ""), 0, 12)
  tags                = var.tags

  email_receiver {
    name                    = "ops"
    email_address           = var.alert_email
    use_common_alert_schema = true
  }
}

resource "azurerm_monitor_scheduled_query_rules_alert_v2" "invocation_failed" {
  count = local.alerting_enabled ? 1 : 0

  name                = "${var.function_app_name} invocation failed"
  resource_group_name = azurerm_resource_group.this.name
  location            = azurerm_resource_group.this.location
  scopes              = [azurerm_application_insights.func.id]
  severity            = 1
  tags                = var.tags

  evaluation_frequency = "PT5M"
  window_duration      = "PT5M"

  criteria {
    # operation_Name distinguishes pause_capacities from resume_capacities so
    # the alert text says which one broke.
    query = <<-KQL
      requests
      | where success == false
      | summarize failures = count() by operation_Name
    KQL

    time_aggregation_method = "Count"
    threshold               = 0
    operator                = "GreaterThan"

    dimension {
      name     = "operation_Name"
      operator = "Include"
      values   = ["*"]
    }

    failing_periods {
      number_of_evaluation_periods             = 1
      minimum_failing_periods_to_trigger_alert = 1
    }
  }

  action {
    action_groups = [azurerm_monitor_action_group.failures[0].id]
  }
}

# A capacity that fails to resume is not visible as a failed request -- the
# function logs the error and returns normally, by design, so one stuck capacity
# does not abort the rest. Catch that case from the logs instead.
resource "azurerm_monitor_scheduled_query_rules_alert_v2" "capacity_stuck" {
  count = local.alerting_enabled ? 1 : 0

  name                = "${var.function_app_name} capacity did not reach Active"
  resource_group_name = azurerm_resource_group.this.name
  location            = azurerm_resource_group.this.location
  scopes              = [azurerm_application_insights.func.id]
  severity            = 2
  tags                = var.tags

  evaluation_frequency = "PT30M"
  window_duration      = "PT1H"

  criteria {
    query = <<-KQL
      traces
      | where severityLevel >= 3
      | where message has "did not reach Active"
    KQL

    time_aggregation_method = "Count"
    threshold               = 0
    operator                = "GreaterThan"

    failing_periods {
      number_of_evaluation_periods             = 1
      minimum_failing_periods_to_trigger_alert = 1
    }
  }

  action {
    action_groups = [azurerm_monitor_action_group.failures[0].id]
  }
}
