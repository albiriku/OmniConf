"""
    OmniConf - used with Netbox and Ansible to automate certain device configuration using restconf
    Copyright (C) 2021, Alexander Birgersson & Rickard Kutsomihas.

    This program is free software: you can redistribute it and/or modify
    it under the terms of the GNU General Public License as published by
    the Free Software Foundation, either version 3 of the License, or
    (at your option) any later version.

    This program is distributed in the hope that it will be useful,
    but WITHOUT ANY WARRANTY; without even the implied warranty of
    MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
    GNU General Public License for more details.

    You should have received a copy of the GNU General Public License
    along with this program.  If not, see <http://www.gnu.org/licenses/>.
"""

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
from flask import Flask, request, Response              # used for flask app, receive and response of webhook
import requests                                         # used for HTTP get request to netbox api
from requests.auth import HTTPBasicAuth                 # used for creating the basic authentication field in the HTTP header
app = Flask(__name__)

# IMPORTANT: YOUR user specific settings:
FLASK_PATH = '/webhook-test'                                                # the path that flask listens to for webhooks, which should also be appended to url webhook destination
NETBOX_IP = 'https://X.X.X.X'                                               # ip address to netbox
NETBOX_TOKEN = 'Token c788f875f6a0bce55f485051a61dbb67edba0994'             # user token to be able to communicate with netbox api
ANSIBLE_INVFILE = '/home/albiriku/devnet/dne-dna-code/intro-ansible/hosts'  # path to Ansible inventory file
ANSIBLE_VAULTPASS = 'secret'                                                # ansible vault password for decryption

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
def compare(prechange, postchange):
    updated_values = {}
    # loops through keys and non-matching values
    for key in prechange:
        if prechange[key] != postchange[key]:
            updated_values[key] = postchange[key]
    return updated_values


# returns the configurable values
def pick_out_values(model, data, values):
    """
    This function consists of 2 parts.

    Part 1:
    Loops through the elements in "configurable" in "list_of_models",
    then compares the elements to the elements in "values".
    If the compared values match the values are added to the
    dict "configuration".

    Part 2:
    Either populates "information" with a url to the device in Netbox, 
    or a primary ip address if the model is "device". 
    The url is needed to retrieve the primary ip address to the device
    and the primary ip address is required in order to send the configuration.

    Returns "config" as a dict with both "configurable" and "informational"
    or returns a value of "None".
    """

    # part 1
    # creates a new dict
    config = {}
    # adds a nestled dict to hold the configuration values
    config['configuration'] = {}

    # loop comparing the elements in "configurable" and "values"
    for element in list_of_models[model]['configurable']:
        if element in values:
            # if matched value is an empty string the loop continues with the next iteration
            if values[element] == '':
                continue
            # key and value is added in the dictionary "configuration"
            config['configuration'][element] = values[element]

        # in order to update the devices hostname when a primary ip gets assigned in netbox
        # the key "name" and its value from "data" is added to the configuration dict
        elif 'primary_ip6' in values or 'primary_ip4' in values:
            config['configuration'][element] = data[element]

    # part 2
    # executes only if "configuration" is populated
    if config['configuration'] != {}:
        # creates a second dict in "config", named "information"
        config['information'] = {}
        # the content of "informational" is added to "info" 
        info = list_of_models[model]['informational']
        # the number of elements present in "info"
        length = len(info)

        for i in range(0, length):#loop på antalet element i info
           # during the first iteration 
            if i == 0:
                # the first key in "information" is added
                config['information'] = data[info[i]]
                # if the key value is equal to "None" the function ends and returns "None"
                if config['information'] == None:                               
                    return None                                 

            # performs iterative lookups and overwrites the value in order to perform subsequent lookups in the nestled dicts
            # the element in "info" is matched and replaces key:value pair in "information"
            # "information" ends up with the key corresponding the last element in "info" along with its lookup value
            else:                                           
                config['information'] = config['information'][info[i]]
        return config
    # when no configuration values matched
    return None


# performs a HTTP GET request to netbox api for the devices' primary ip address
def get_api_data(config):
    # consist of the ip address to netbox and the url to the device
    url = NETBOX_IP + config['information']
    # HTTP header
    headers =   {
                'Content-Type': 'application/json', 
                'Authorization': NETBOX_TOKEN 
                }
    # performs the GET request
    api_data = requests.request('GET', url, headers=headers, verify=False)
    # response data as json
    api_data = api_data.json()

    # returns the primary ip address if its present on the device
    # otherwise returns "None"
    if api_data['primary_ip'] != None:
        ip = api_data['primary_ip']['address']
        return ip
    else:
        return None
    

# this function separates prefix and address from each other
# returns both or only address depending on parameters given
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


# this class is taken from the Ansible python API example: "https://docs.ansible.com/ansible/latest/dev_guide/developing_api.html"
# create a callback plugin so we can capture the output
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

# this code is also taken from "https://docs.ansible.com/ansible/latest/dev_guide/developing_api.html"
# but it has been heavily edited
# this function creates and runs an Ansible play
def run_playbook(config, ip, event, model, data, prechange):
    """
    Part 1:
    Apart from "host" this part consist of the orignal code,
    although some parameters have been changed as well.
    Initializes and loads necessary data for Ansible to operate.

    Part 2:
    Creates the data structure that represents our play, including tasks, this is basically what our YAML loader does internally.
    The Ansible restconf_config module is used for each play (task), which yang data model used might differ between the plays.
    The task and payload is defined using prior extrapolated data where the task that will be performed by the device is decided by the event,
    i.e. a "deleted" event will result in a "delete" task being executed. Appropriate parameters for the event are also specified in the task,
    such as "path" or "method". The payload consists of the appropriate yang-data-model used and the configuration dict.

    Part 3: 
    Compiles and executes the Ansible playbook and reports back the result.

    Part 4:
    Saves the configuration on the device to startup-config.
    This doesnt seem to be doable with the ansible restconf plugin using the cisco-ia module, 
    so we use requests to send a HTTP post msg instead of executing it as a playbook.
    """

    # part 1
    # removes mask from the ip
    host = split_address(ip)

    # since the API is constructed for CLI it expects certain options to always be set in the context object
    context.CLIARGS = ImmutableDict(connection='smart', forks=10, verbosity=True, check=False, diff=False)

    # initialize needed objects
    loader = DataLoader() # takes care of finding and reading yaml, json and ini files
    passwords = dict(vault_pass=ANSIBLE_VAULTPASS)

    # instantiate our ResultsCollectorJSONCallback for handling results as they come in. Ansible expects this to be one of its main display outlets
    results_callback = ResultsCollectorJSONCallback()

    # create inventory, use path to host config file as source or hosts in a comma separated string
    inventory = InventoryManager(loader=loader, sources=ANSIBLE_INVFILE)

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

    # part 2
    # interface configuration
    # uses the ietf-yang-data-model interfaces-module
    if model == 'interface':
        # name of the target interface 
        # used in the path when altering an existing interface
        name = data['name']
        # first checks if 'type' exist in conf, then converts the interface type
        # from a netbox value to a value supported by the ietf-interface module 
        if 'type' in config['configuration']:
            # "virtual" gets converted to "softwareLoopback"
            if config['configuration']['type'] == 'virtual':
                config['configuration']['type'] = 'softwareLoopback'
            # other types gets converted to "ethernetCsmacd"
            else:
                config['configuration']['type'] = 'ethernetCsmacd'

        # when interface is created in netbox
        if event == 'created':
            # "configuration" dict as payload
            payload = {"ietf-interfaces:interface":config['configuration']}
            # this task will create the interface on the device
            task = [dict(action=dict(module='ansible.netcommon.restconf_config', args=dict(path='/data/ietf-interfaces:interfaces', content=json.dumps(payload), method='post')))]

        # when interface is edited in netbox
        elif event == 'updated':
            payload = {"ietf-interfaces:interface:":config['configuration']}
            # updates the interface on the device
            task = [dict(action=dict(module='ansible.netcommon.restconf_config', args=dict(path=f'/data/ietf-interfaces:interfaces/interface={name}', content=json.dumps(payload), method='patch')))]

        # when interface is deleted in netbox
        elif event == 'deleted':
            # deletes the interface on the device
            task = [dict(action=dict(module='ansible.netcommon.restconf_config', args=dict(path=f'/data/ietf-interfaces:interfaces/interface={name}', method='delete')))]

    # ipaddress configuration
    if model == 'ipaddress':
        # the target interface
        name = data['assigned_object']['name']
        # ipv4 or ipv6
        family = data['family']['label'].lower()
        # ip address to conf
        address = config['configuration']['address']

        # ip and mask needs to be separated for the payload format
        address, prefix = split_address(address, True)

        # only needed for IPv4, converts prefix to netmask format
        if family == 'ipv4':
            # reference: https://stackoverflow.com/questions/23352028/how-to-convert-a-cidr-prefix-to-a-dotted-quad-netmask-in-python
            prefix = '.'.join([str((m>>(3-i)*8)&0xff) for i,m in enumerate([-1<<(32-int(prefix))]*4)])
            mask = 'netmask'

        elif family == 'ipv6':
            mask = 'prefix-length'

        # payload & task for IPv4 & IPv6
        if event == 'created' or event == 'updated':

            # payload structure same for created and updated
            payload =   { 'ietf-interfaces:interface':
                            { f'ietf-ip:{family}':
                                { 'address':
                                    [{
                                        'ip': address,
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
                old_address = split_address(prechange['address'])

                # first deletes the old address then adds the new address
                task = [dict(action=dict(module='ansible.netcommon.restconf_config', args=dict(path=f'/data/ietf-interfaces:interfaces/interface={name}/ietf-ip:{family}/address={old_address}',
                        method='delete'))),
                        dict(action=dict(module='ansible.netcommon.restconf_config', args=dict(path=f'/data/ietf-interfaces:interfaces/interface={name}',
                        content=json.dumps(payload), method='patch')))]

        elif event == 'deleted':
            # deletes the address
            task = [dict(action=dict(module='ansible.netcommon.restconf_config', args=dict(path=f'/data/ietf-interfaces:interfaces/interface={name}/ietf-ip:{family}/address={address}', method='delete')))]

    # device configuration (hostname only)
    # uses the Cisco IOS XE native yang data model
    if model == 'device':
        # during device creation in netbox no primary ip address is associated with the device
        # therefore hostname can only be configured on the physical device via an update
        # hostname will be updated on the device when a primary ip gets assigned as well
        if event == 'updated':
            hostname = config['configuration']['name']
            # blank space not supported as a part of the devices' hostname
            hostname = hostname.replace(" ", "-")
            payload = {'Cisco-IOS-XE-native:hostname': f'{hostname}'}

            task = [dict(action=dict(module='ansible.netcommon.restconf_config', args=dict(path='/data/Cisco-IOS-XE-native:native/hostname',
                        content=json.dumps(payload), method='patch')))]

    # part 3
    # generates and runs the playbook with the task given above
    play_source = dict(
    name='Ansible Play',
    hosts=[host],
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
    print('SUCCESSFUL ***********')
    for host, result in results_callback.host_ok.items():
        # when a playbook performs delete
        if not 'candidate' in result._result:
            print('{0} >>> {1} \n{2}'.format(host, result._result['changed'], result._result['invocation']))
        # when a playbook performs create/update
        else:
            print('{0} >>> {1}'.format(host, result._result['candidate']))

    print('FAILED *******')
    # failed to execute the play
    for host, result in results_callback.host_failed.items():
        print('{0} >>> {1}'.format(host, result._result['msg']))

    print('UNREACHABLE *********')
    # couldnt reach the host
    for host, result in results_callback.host_unreachable.items():
        print('{0} >>> {1}'.format(host, result._result['msg']))

    # part 4
    # saves the configuration on the device
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


# the parameters which flask listens to for webhooks
@app.route(FLASK_PATH, methods=['POST'])
def respond():
    """
    This functions runs when receiving a webhook.
    Below is the flask app code that receives the webhook.
    Calls the functions responsible for each step.
    If a function returns a value of None, the webhook wont be processed futher.
    In the code this is represented as a "return Response(=200)", which is a 
    HTTP response to the HTTP webhook POST. 
    Functions and terms are further explained in conjunction with the functions
    
    First of all the received webhook is stored in a variable and
    some of its' important parts are stored in other variables.
    These variables are used in different functions to extract data.

    Step 1 calls the function "check_model" which uses the "model"
    part of the webhook in order to check if the model is configurable.
    This is arbitrarily predetermined in the dict "list_of_models".
    If model is determined to be configurable the "event" value of the webhook
    is saved to be processed in step 2. Undetermined configurability will end the process.

    Step 2 compares the different events in the webhook. If event is "updated" then the function "compare()"
    is called, which compares the "prechange" part of the webhook with the "postchange" part.
    The differences between the pre- and postchange are saved in the "values" variable.
    If the event is "created" the "postchange" is saved in "values".
    If the event is "deleted" the "prechange" is saved in "values".

    Step 3 configurable values are selected by calling the "pick_out_values()" function with the arguments
    "data", "model" and "values". The function will also return a url to a device in Netbox when "model" is not "device".
    If no configurable values can be selected, the process end.

    Step 4 depending on what model is being configured the retrieval of ip address differ. If the model is "device" the 
    address is included in the webhook, otherwise the url to the device has to be used and then via Netbox API retrieve the 
    address from the device. If the device doesnt have a primary ip address assigned to it, the process will end.

    Step 5 is the last step. Calls the "run_playbook()" function in order to create and run an Ansible playbook with data from previous steps.
    The configuration will be saved on the device. The function only offers full support for Cisco IOS XE devices. For other devices support might vary.
    """

    # the webhook payload is stored in "webhook"
    webhook = request.json
    # the model which the webhook originated from
    model = webhook['model']
    # the data portion of the webhook
    data = webhook['data']
    # post- and prechange information    
    prechange = webhook['snapshots']['prechange']
    postchange = webhook['snapshots']['postchange']

    print(json.dumps(webhook, indent = 4))

    # step 1: check if model is configurable
    if check_model(model) == True:
        event = webhook['event']

    # if model is not configurable
    else:
        # ends
        print('model not configurable')
        return Response(status=200)

    # step 2: check event
    if event == 'updated':
        if prechange == None:
            # when prechange contains a value of null
            # this occurs when the "make this the primary IP for the device" option was changed when creating/editing an ipaddress
            # which will send a device webhook as well, with the prechange set to null
            return Response(status=200)
        
        else:
            values = compare(prechange, postchange)

    elif event == 'created':
        values = postchange

    elif event == 'deleted':
        if prechange == None:
            # when interface is deleted, netbox sends a delete webhook for the ipaddress as well, with empty post- and prechange.
            # in this case the address will be removed along with the interface on the device, which mean no futher action is needed.
            return Response(status=200)

        else:
            values = prechange

    #step 3: get configurable values and api url if more info needed  
    config = pick_out_values(model, data, values)
    print('Configurable values: ', config)

    if config == None:
        # no configurable values were returned from the "pick_out_values" function
        # this can also happen when:
        # 1. the device has no primary IP assigned to it, or
        # 2. a webhook is triggered for an ipaddress which has not been assigned to a device, assigned_objects contains a value of null
        # in this case no configuration has been made, because the change doesnt relate to a device
        return Response(status=200)

    #step 4: api get request to retrive device primary IP address (included in the webhook for device model)
    if model == 'device':
        ip = config['information']

    else:
        ip = get_api_data(config)
        print('device primary IP is', ip)
        if ip == None:
            print()
            print('The targeted device has no primary IP assigned. Nowhere to send conf.')
            return Response(status=200)

    #step 5: create and run playbook
    run_playbook(config, ip, event, model, data, prechange)

    return Response(status=200)
