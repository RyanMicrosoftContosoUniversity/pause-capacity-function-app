# Persistent Fabric capacity used as the integration-test target.
#
# Lifecycle, deliberately:
#
#   created  by Terraform when absent
#   kept     across applies (prevent_destroy) -- we are not testing deletion,
#            and a destroyed capacity takes its workspaces with it
#   paused   by the pipeline once tests finish, so it costs nothing idle
#
# Terraform does not model the paused/active state, so pausing it out-of-band
# produces no drift on the next plan.

resource "azurerm_fabric_capacity" "test" {
  count = var.test_capacity.enabled ? 1 : 0

  name                = var.test_capacity.name
  resource_group_name = azurerm_resource_group.this.name
  location            = var.location

  # The deploying service principal must be an admin or the pause/resume calls
  # return 401. Extra members can be added for humans who need the portal.
  administration_members = distinct(concat(
    [data.azurerm_client_config.current.object_id],
    var.test_capacity.administration_members,
  ))

  sku {
    name = var.test_capacity.sku
    tier = "Fabric"
  }

  tags = merge(var.tags, {
    purpose = "integration-test-target"
    # Signals to anyone browsing the portal that pausing this is expected and
    # that resuming it is the integration test's job, not an incident.
    lifecycle = "paused-when-idle"
  })

  lifecycle {
    prevent_destroy = true

    # The capacity is paused and resumed constantly by the thing under test.
    # Nothing here should be reconciled on that basis.
    ignore_changes = [tags["lifecycle"]]
  }
}
