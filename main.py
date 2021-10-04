#!/usr/bin/env python

# the imports are needed for Ansible API (to run playbooks)
from __future__ import (absolute_import, division, print_function)
__metaclass__ = type

import json
import shutil

import ansible.constants as C
from ansible.executor.task_queue_manager import TaskQueueManager
from ansible.module_utils.common.collections import ImmutableDict
from ansible.inventory.manager import InventoryManager
from ansible.parsing.dataloader import DataLoader
from ansible.playbook.play import Play
from ansible.plugins.callback import CallbackBase
from ansible.vars.manager import VariableManager
from ansible import context

# the imports needed for flask and HTTP requests
from flask import Flask, request, Response          # used for flask app, receive and response of webhook
import requests                                     # used for HTTP get request to netbox api
from requests.auth import HTTPBasicAuth             # used for creating the basic authentication field in the HTTP header
app = Flask(__name__)


# "configurable" contains the values from the webhook we deem are configurationable for the corresponding model 
# "informational" contains additional information required for configuration
list_of_models =    {
                    'device': 
                                {
                                    'configurable': ['name'],
                                    'informational': ['primary_ip', 'address']
                                },
                    'interface':
                                {
                                    'configurable': ['name', 'type', 'enabled', 'description'],
                                    'informational': ['device', 'url']
                                },
                    'ipaddress':
                                {
                                    'configurable': ['address'],
                                    'informational': ['assigned_object', 'device', 'url']
                                },
                    }


# check if "model" is configurable and returns "True" if match
def check_model(model):
    if model in list_of_models:
        # match
        print(model, 'is configurable')
        return True

# used when event is "updated"
# returns the difference of "prechange" vs "postchange" in a new dict
def compare(snapshots):
    prechange = snapshots['prechange']
    postchange = snapshots['postchange']
    updated_values = {}
    # loops through keys and non-matching values
    for key in prechange:
        if prechange[key] != postchange[key]:
            updated_values[key] = postchange[key]
    return updated_values


# returns the configurable values
def pick_out_values(model, data, values):
    """
    Part 1:
    Loops through the elements in "configurable" in "list_of_models",
    then compares the elements to the elements in "values".
    If the compared values match the values are added to the
    dict "configuration".

    Part 2:


    Returns "config" as a dict with both "configurable" and "informational"
    or returns a value of "None".
    """

    # creates a new dict
    config = {}
    # adds an empty dict to hold the configuration values
    config['configuration'] = {}

    # loop comparing the elements in "configurable" and values
    for element in list_of_models[model]["configurable"]:
        # 
        if element in values:
            # if match value is an empty string
            if values[element] == "":
                continue
            #Key is added in the dictionary config along with a value
            config["configurable"][element] = values[element]

        #when primary ip is assigned to a device
        #adds the key "name" and its value from "data" to config
        #this is done in order to update the devices hostname when a primary ip gets assigned in netbox
        elif "primary_ip6" in values or "primary_ip4" in values:
            config["configurable"][element] = data[element]
    
    print('1',config)
    if config["configurable"] != {}:
        config["informational"] = {}
        info = list_of_models[model]["informational"]
        length = len(info)

        print('2',config)

        for i in range(0, length):                                      #loop på antalet element i info
            if i == 0:                                                      #första varvet:
                config["informational"] = data[info[i]]                           #uppslagning i data, efter element 0 från info. Sparar värdet i conf under nyckeln ["informational"]
                if config["informational"] == None:                                 #if assigned_objects är null, tex ipaddress är inte assigned till en enhet
                    return None                                                         #avslutar funktionen, return None
            else:                                                           #alla andra varv:
                config["informational"] = config["informational"][info[i]]          #uppslagning i conf["informational"], efter nästa element i info. Sparar över i conf. Upprepar för resterande element.
        return config
    return None


def get_api_data(config):
    url = 'https://193.10.237.252' + config["informational"]
    print(url)
    headers =   {
                'Content-Type': "application/json", 
                'Authorization': "Token c788f875f6a0bce55f485051a61dbb67edba0994" 
                }

    api_data = requests.request("GET", url, headers=headers, verify=False)
    api_data = api_data.json()

    print(json.dumps(api_data, indent=4))
    
    if api_data["primary_ip"] != None:
        ip = api_data["primary_ip"]["address"]
        device_name = api_data["name"]
        return ip, device_name
    else:
        return None, None
    


#separates prefix and address from each other
#returns both or only address depending on parameters given
def split_address(address, mask=False):
    if address[-2] == '/':
        #prefix is 1 digit
        prefix = address[-1:]
        address = address[:-2]
    elif address[-3] == '/':
        #prefix is 2 digits
        prefix = address[-2:]
        address = address[:-3]
    else:
        #for ipv6 only, when prefix is 3 digits
        prefix = address[-3:]
        address = address[:-4]
    if mask == False:
        return address
    else:
        return address, prefix


# Create a callback plugin so we can capture the output
class ResultsCollectorJSONCallback(CallbackBase):
    """A sample callback plugin used for performing an action as results come in.

    If you want to collect all results into a single object for processing at
    the end of the execution, look into utilizing the ``json`` callback plugin
    or writing your own custom callback plugin.
    """

    def __init__(self, *args, **kwargs):
        super(ResultsCollectorJSONCallback, self).__init__(*args, **kwargs)
        self.host_ok = {}
        self.host_unreachable = {}
        self.host_failed = {}

    def v2_runner_on_unreachable(self, result):
        host = result._host
        self.host_unreachable[host.get_name()] = result

    def v2_runner_on_ok(self, result, *args, **kwargs):
        """Print a json representation of the result.

        Also, store the result in an instance attribute for retrieval later
        """
        host = result._host
        self.host_ok[host.get_name()] = result
        print(json.dumps({host.name: result._result}, indent=4))

    def v2_runner_on_failed(self, result, *args, **kwargs):
        host = result._host
        self.host_failed[host.get_name()] = result

def run_playbook(config, ip, event, model, data, snapshots):
    # remove mask from ip
    host  = split_address(ip)

    host_list = [host]
    # since the API is constructed for CLI it expects certain options to always be set in the context object
    context.CLIARGS = ImmutableDict(connection='smart', forks=10, verbosity=True, check=False, diff=False)

    # initialize needed objects
    loader = DataLoader() # takes care of finding and reading yaml, json and ini files
    passwords = dict(vault_pass='secret')

    # instantiate our ResultsCollectorJSONCallback for handling results as they come in. Ansible expects this to be one of its main display outlets
    results_callback = ResultsCollectorJSONCallback()

    # create inventory, use path to host config file as source or hosts in a comma separated string
    inventory = InventoryManager(loader=loader, sources='/home/albiriku/devnet/dne-dna-code/intro-ansible/hosts') #sources

    # variable manager takes care of merging all the different sources to give you a unified view of variables available in each context
    variable_manager = VariableManager(loader=loader, inventory=inventory)

    # instantiate task queue manager, which takes care of forking and setting up all objects to iterate over host list and tasks
    # IMPORTANT: This also adds library dirs paths to the module loader
    # IMPORTANT: and so it must be initialized before calling `Play.load()`.
    tqm = TaskQueueManager(
        inventory=inventory,
        variable_manager=variable_manager,
        loader=loader,
        passwords=passwords,
        stdout_callback=results_callback,  # use our custom callback instead of the ``default`` callback plugin, which prints to stdout
    )
    
    # create data structure that represents our play, including tasks, this is basically what our YAML loader does internally.
    # interface configuration
    if model == 'interface':
        name = data['name']
        if "type" in config['configurable']:
            if config['configurable']['type'] == 'virtual':
                config['configurable']['type'] = 'softwareLoopback'
            else:
                config['configurable']['type'] = 'ethernetCsmacd'

        if event == 'created':
            payload = {"ietf-interfaces:interface":config['configurable']}
            task = [dict(action=dict(module='ansible.netcommon.restconf_config', args=dict(path='/data/ietf-interfaces:interfaces', content=json.dumps(payload), method='post')))]

        elif event == 'updated':
            payload = {"ietf-interfaces:interface:":config['configurable']}
            task = [dict(action=dict(module='ansible.netcommon.restconf_config', args=dict(path=f'/data/ietf-interfaces:interfaces/interface={name}', content=json.dumps(payload), method='patch')))]

        elif event == 'deleted':
            task = [dict(action=dict(module='ansible.netcommon.restconf_config', args=dict(path=f'/data/ietf-interfaces:interfaces/interface={name}', method='delete')))]

    # ipaddress configuration
    if model == 'ipaddress':
        # interface name
        name = data['assigned_object']['name']
        # ipv4 or ipv6
        family = data['family']['label'].lower()
        # ip address to conf
        address = config['configurable']['address']

        #ip and mask needs to be separated for payload format
        address, prefix = split_address(address, True)

        if family == 'ipv4':
            # only needed for IPv4, converts prefix to netmask format
            # reference:
            # https://stackoverflow.com/questions/23352028/how-to-convert-a-cidr-prefix-to-a-dotted-quad-netmask-in-python
            prefix = '.'.join([str((m>>(3-i)*8)&0xff) for i,m in enumerate([-1<<(32-int(prefix))]*4)])
            mask = 'netmask'

        elif family == 'ipv6':
            mask = 'prefix-length'

        # payload & task for IPv4 & IPv6
        if event == 'created' or event == 'updated':

            # payload structure same for created and updated
            payload =   { "ietf-interfaces:interface":
                            { f"ietf-ip:{family}":
                                { "address":
                                    [{
                                        "ip": address,
                                        mask: prefix
                                    }]
                                }
                            }
                        }

            if event == 'created':
                # adds the new address to the interface
                task = [dict(action=dict(module='ansible.netcommon.restconf_config', args=dict(path=f'/data/ietf-interfaces:interfaces/interface={name}',
                        content=json.dumps(payload), method='patch')))]

            elif event == 'updated':
                # the target object on the device
                old_address = split_address(snapshots['prechange']['address'])

                # first deletes the old address then adds the new
                task = [dict(action=dict(module='ansible.netcommon.restconf_config', args=dict(path=f'/data/ietf-interfaces:interfaces/interface={name}/ietf-ip:{family}/address={old_address}',
                        method='delete'))),
                        dict(action=dict(module='ansible.netcommon.restconf_config', args=dict(path=f'/data/ietf-interfaces:interfaces/interface={name}',
                        content=json.dumps(payload), method='patch')))]

        elif event == 'deleted':
            # deletes the address
            task = [dict(action=dict(module='ansible.netcommon.restconf_config', args=dict(path=f'/data/ietf-interfaces:interfaces/interface={name}/ietf-ip:{family}/address={address}', method='delete')))]

    if model == 'device':
        if event == 'updated':
            hostname = config["configurable"]["name"]
            hostname = hostname.replace(" ", "-")
            payload = {"Cisco-IOS-XE-native:hostname": f"{hostname}"}

            task = [dict(action=dict(module='ansible.netcommon.restconf_config', args=dict(path='/data/Cisco-IOS-XE-native:native/hostname',
                        content=json.dumps(payload), method='patch')))]

    # create data structure that represents our play, including tasks, this is basically what our YAML loader does internally.
    # generates and runs the playbook with the task given above
    play_source = dict(
    name="Ansible Play",
    hosts=host_list,
    gather_facts='no',
    tasks=task
    )

    # Create play object, playbook objects use .load instead of init or new methods,
    # this will also automatically create the task objects from the info provided in play_source
    play = Play().load(play_source, variable_manager=variable_manager, loader=loader)

    # Actually run it
    try:
        result = tqm.run(play)  # most interesting data for a play is actually sent to the callback's methods
    finally:
        # we always need to cleanup child procs and the structures we use to communicate with them
        tqm.cleanup()
        if loader:
            loader.cleanup_all_tmp_files()

    # Remove ansible tmpdir
    shutil.rmtree(C.DEFAULT_LOCAL_TMP, True)

    # Prints the outcome of playbook that executed
    print("UP ***********")
    for host, result in results_callback.host_ok.items():
        #if result._result['candidate'] == None:
        if not 'candidate' in result._result:
            print('{0} >>> {1} \n{2}'.format(host, result._result['changed'], result._result['invocation']))
        else:
            print('{0} >>> {1}'.format(host, result._result['candidate']))

    print("FAILED *******")
    for host, result in results_callback.host_failed.items():
        print('{0} >>> {1}'.format(host, result._result['msg']))

    print("DOWN *********")
    for host, result in results_callback.host_unreachable.items():
        print('{0} >>> {1}'.format(host, result._result['msg']))


    # Saves the configuration on the device:
    # we couldnt get cisco-ia module to work with the ansible restconf plugin
    # so we use requests to send an HTTP post msg instead of executing a playbook

    # loaded_vars contains all the host variables that ansible loads from the varfiles
    loaded_vars = variable_manager._hostvars
    # restconf username loaded from ansible
    username = loaded_vars[host]['ansible_user']
    # restconf password loaded from ansible
    password = loaded_vars[host]['ansible_httpapi_password']

    # uses cisco-ai module to invoke an RPC that saves the running conf to startup 
    path = 'https://' + host + '/restconf/operations/cisco-ia:save-config'
    header =  {'Content-type': 'application/yang-data+json'}
    # creates a HTTP basic auth field with the restconf user/password
    dev_auth = HTTPBasicAuth(username, password)

    # sends the HTTP post
    saveconf = requests.post(path, headers=header, verify=False, auth=dev_auth)
    # saves the response msg
    saveconf = saveconf.json()
    # prints the response msg
    print(json.dumps(saveconf, indent=4))


"""
Below is the flask app code that receives the webhook.
Calls the functions responsible for each step.
If a function returns a value of None, the webhook wont be processed futher.
In the code this is represented as a "return Response(=200)", which is a
HTTP response to the HTTP webhook POST. Functions and
terms are further explained in conjunction with the functions,
the comments beside the code only serves the purpose to explain the code as is.
"""

@app.route('/webhook-test', methods=['POST'])
def respond():
    webhook = request.json                                                              #the variable "webhook" is created containing the incoming webhook data in a json dictionary
    model = webhook["model"]                                                            #a lookup in the dictionary is made and the data saved in a variable
    data = webhook["data"]
    snapshots = webhook["snapshots"]

    print(json.dumps(webhook, indent=4))

    #step 1: check if model is configurable
    if check_model(model) == True:
        event = webhook["event"]

    #if model is not configurable
    else:
        #log and stop
        print("det funka inte")
        return Response(status=200)

    #step 2: check event
    if event == "updated":
        if snapshots["prechange"] == None:
            print()
            print("prechange contains a value of null.")
            print("This occurs when the 'make this the primary IP for the device' option was changed when creating/editing an ipaddress")
            print("which will send a device webhook as well, with the prechange set to null")
            return Response(status=200)
        
        else:
            values = compare(snapshots)

    elif event == "created":
        values = snapshots["postchange"]

    elif event == "deleted":
        # when interface is deleted, netbox sends a delete webhook for the ipaddress as well, with empty post- and prechange.
        # in this case the address is removed along with the interface on the device. No futher action is needed.
        if snapshots["prechange"] == None:
            return Response(status=200)

        else:
            values = snapshots["prechange"]

    #step 3: get configurable values and api url if more info needed  
    print(values)
    config = pick_out_values(model, data, values)
    print("slutresultat: ", config)

    if config == None:
        print()
        print("config == None. No configurable values were returned from the 'pick_out_values' function,")
        print("device has no primary IP assigned to it, or")
        print("assigned_objects contains a value of null. This occurs when a webhook is triggered for an ipaddress which has not been assigned to a device")
        print("no configuration needed, because the change doesnt relate to a device.")
        return Response(status=200)

    #step 4: api get request for target IP address & device name (included in the webhook for device model)
    if model == "device":
        ip = config["informational"]
        device_name = config["configurable"]["name"]

    else:
        ip, device_name = get_api_data(config)
        print("device primary IP is", ip)
        if ip == None:
            print()
            print("The targeted device has no primary IP assigned. Nowhere to send conf.")
            return Response(status=200)

    #step 5: create and run playbook
    run_playbook(config, ip, event, model, data, snapshots)

    return Response(status=200)
