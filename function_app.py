import logging
import azure.functions as func
import os

app = func.FunctionApp()

@app.timer_trigger(schedule="0 0 23 * * *", arg_name="myTimer", run_on_startup=True,
              use_monitor=False) 
def timer_trigger(myTimer: func.TimerRequest) -> None:
    # Import inside the function to avoid import errors during worker initialization
    from fabric_utils.service_principal import ServicePrincipal
    from fabric_utils.fabric_capacity import Extract, FabricCapacitiesBySubscription, FabricCapacityMGMT
    
    logging.info('Python timer trigger function started.')

    spn = ServicePrincipal(
        client_id= os.getenv('AZURE_CLIENT_ID'),
        tenant_id= os.getenv('AZURE_TENANT_ID'),
        spn_secret_name=os.getenv('SPN_SECRET_NAME'),
        vault_url=os.getenv('VAULT_URL')
    )
    subscription_id = os.getenv('SUBSCRIPTION_ID')

    client = FabricCapacitiesBySubscription(spn=spn, subscription_id=subscription_id, rg_name='fabric-rg')

    caps_list = client.list_capacities_by_resource_group()

    for item in caps_list:
        # create FabricCapacityMGMT so that the capacity can be paused
        id = Extract.extract_id(item)
        # get subscription_id
        subscription_id = Extract.extract_subscription_id(id)

        # get resource_group
        resource_group = Extract.extract_resource_group(id)

        # get capacity_name
        capacity_name = Extract.extract_capacity(id)


        # test values
        print(f'The value for subscription_id is {subscription_id}')
        print(f'The value for resource_group is {resource_group}')
        print(f'The value for capacity_name is {capacity_name}')

        # create FabricCapacityMGMT object
        capacity_client = FabricCapacityMGMT(spn=spn, subscription_id=subscription_id, resource_group=resource_group, capacity_name=capacity_name)

        # pause capacity
        capacity_client.pause_capacity()


