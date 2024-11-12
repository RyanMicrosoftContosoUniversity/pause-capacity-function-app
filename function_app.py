import logging
import azure.functions as func
from fabric_automation_utils.service_principal import ServicePrincipal
from fabric_automation_utils.fabric_capacity import Extract, FabricCapacitiesBySubscription, FabricCapacityMGMT
import json

app = func.FunctionApp()

@app.timer_trigger(schedule="0 23 * * * ", arg_name="myTimer", run_on_startup=False,
              use_monitor=False) 
def timer_trigger(myTimer: func.TimerRequest) -> None:
    config_data = json.loads(open('docs/non-prod-spn-config.json').read())
    spn = ServicePrincipal(
        client_id=config_data['client_id'],
        tenant_id=config_data['tenant_id'],
        spn_secret_name=config_data['spn_secret_name'],
        vault_url=config_data['vault_url']
    )
    subscription_id = '910ebf13-1058-405d-b6cf-eda03e5288d1'
    rg = 'fabric-rg'
    cap_name = 'fabricf2testrh'

    # client = FabricCapacityMGMT(spn=spn, subscription_id=subscription_id, resource_group=rg, capacity_name=cap_name)
    client = FabricCapacitiesBySubscription(spn=spn, subscription_id=subscription_id)

    caps_list = client.list_capacities_by_subscription()

    for item in caps_list:
        # create FabricCapacityMGMT so that the capacity can be paused
        id = Extract.extract_id(item)
        # get subscription_id
        subscription_id = Extract.extract_subscription_id(id)

        # get resource_group
        resource_group = Extract.extract_resource_group(id)

        # get capacity_name
        capacity_name = Extract.extract_capacity(id)

        
        print(item)

        # test values
        print(f'The value for subscription_id is {subscription_id}')
        print(f'The value for resource_group is {resource_group}')
        print(f'The value for capacity_name is {capacity_name}')

        # create FabricCapacityMGMT object
        capacity_client = FabricCapacityMGMT(spn=spn, subscription_id=subscription_id, resource_group=resource_group, capacity_name=capacity_name)

        # pause capacity
        capacity_client.pause_capacity()


