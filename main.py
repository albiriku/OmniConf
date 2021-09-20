#!/usr/bin/env python

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


def run_playbook(config, ip, event, model, data, values):
    #removes the mask from ip
    if ip[-2] == '/':
        #removes the last 2 
        ip = ip[:-2]
    elif ip[-3] == '/':
        #removes the last 3
        ip = ip[:-3]
    else:
        #removes the last 4, if mask is 3 digits (ipv6)
        ip = ip[:-4]

    host_list = [ip] 
    # since the API is constructed for CLI it expects certain options to always be set in the context object
    context.CLIARGS = ImmutableDict(connection='smart', module_path=['/home/albiriku/devnet/dne-dna-code/venv-flask/lib/python3.8/site-packages/ansible/modules'], forks=10, verbosity=True, check=False, diff=False)

    # become=None, become_method=None, become_user=None, check=False, diff=False)

    """
    # required for
    # https://github.com/ansible/ansible/blob/devel/lib/ansible/inventory/manager.py#L204
    sources = ','.join(host_list)
    if len(host_list) == 1:
        sources += ','
    """

    # initialize needed objects
    loader = DataLoader() #Takes care of finding and reading yaml, json and ini files
    passwords = dict(vault_pass='secret')

    # Instantiate our ResultsCollectorJSONCallback for handling results as they come in. Ansible expects this to be one of its main display outlets
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
        stdout_callback=results_callback,  # Use our custom callback instead of the ``default`` callback plugin, which prints to stdout
    )

    # create data structure that represents our play, including tasks, this is basically what our YAML loader does internally.
    

    if model == 'interface':
        name = data['name']
        if event == 'created':
            if values['type'] == 'virtual':
                int_type = 'softwareLoopback'
            else:
                int_type = 'ethernetCsmacd'
            payload = {"ietf-interfaces:interface":{ "name": values['name'],
                                                     "description": values['description'],
                                                     "type": f"iana-if-type:{int_type}",
                                                     "enabled": values['enabled']
                                                   }
                      }
            task = dict(action=dict(module='ansible.netcommon.restconf_config', args=dict(path='/data/ietf-interfaces:interfaces', content=json.dumps(payload), method='post')))

        elif event == 'updated':
            payload = {"ietf-interfaces:interface:":config['configurable']}
            task = dict(action=dict(module='ansible.netcommon.restconf_config', args=dict(path=f'/data/ietf-interfaces:interfaces/interface={name}', content=json.dumps(payload), method='patch')))
        
        else:
            task = dict(action=dict(module='ansible.netcommon.restconf_config', args=dict(path=f'/data/ietf-interfaces:interfaces/interface={name}', method='delete')))



    ################
    """
    if event == 'created':
        event = 'post'
    elif event == 'updated':
        event = 'patch'
    elif event == 'deleted':
        event = 'delete'

    if model == 'interface':
        path = '/data/ietf-interfaces:interfaces'
        payload = 'ietf-interfaces:interface'
        target = f'/interface={config[name]}'
    elif model == 'device':
        path = '/data/ietf-devices:devices'
        payload = 'ietf-devices:device'
        target = f'/device={config[name]}'
    elif model == 'ipaddress':
        path = '/data/ietf-ipaddresses:ipaddresses'
        payload = 'ietf-ipaddresses:ipaddress'
        target = f'/ipaddress={config[name]}'

    if event == 'post':
        task = dict(action=dict(module='ansible.netcommon.restconf_config', args=dict(path={path}, content=json_object, method={event})))
    else:
        task = dict(action=dict(module='ansible.netcommon.restconf_config', args=dict(path={path + target}, content=json_object, method={event})))

    config = {payload:}

    config = {"ietf-interfaces:interface":{"name": "Loopback104","description": "Added with RESTCONF v2","type": "iana-if-type:softwareLoopback","enabled": True,"ietf-ip:ipv4":{"address":[{"ip": "172.16.100.10","netmask": "255.255.255.0"}]}}}

    config_put = {"ietf-interfaces:interface:":{"name": "Loopback104","description": "PUT with RESTCONF - YES", "type": "iana-if-type:softwareLoopback","type": "iana-if-type:softwareLoopback","enabled": False,"ietf-ip:ipv4":{"address":[{"ip": "172.16.100.69","netmask": "255.255.255.0"}]}}}

    config_patch = {"ietf-interfaces:interface:":{"enabled": False}}

    json_object = json.dumps(config, indent = 4)
    print(json_object)
    """

    play_source = dict(
    name="Ansible Play",
    hosts=host_list,
    gather_facts='no',
    tasks=[task]

            #dict(action=dict(module='ansible.netcommon.restconf_config', args=dict(path='/data/ietf-interfaces:interfaces', content=json_object, method='post')))
            #dict(action=dict(module='ansible.netcommon.restconf_config', args=dict(path='/data/ietf-interfaces:interfaces/interface=Loopback104', content=json_object, method='put')))
            #dict(action=dict(module='ansible.netcommon.restconf_config', args=dict(path='/data/ietf-interfaces:interfaces/interface=Loopback104', content=json_object, method='patch')))
            #dict(action=dict(module='ansible.netcommon.restconf_config', args=dict(path='/data/ietf-interfaces:interfaces/interface=Loopback104', method='delete')))
            #dict(action=dict(module='ansible.netcommon.restconf_get', args=dict(path='/data/ietf-interfaces:interfaces', content='config')))
            

            #dict(action=dict(module='debug', args=dict(msg='{{result.candidate}}')))
            #dict(action=dict(module='shell', args='ls'), register='shell_out'),
            #dict(action=dict(module='debug', args=dict(msg='{{shell_out.stdout}}'))),
            #dict(action=dict(module='command', args=dict(cmd='/usr/bin/uptime'))),
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

    print("UP ***********")
    for host, result in results_callback.host_ok.items():
        print('{0} >>> {1}'.format(host, result._result['candidate'])) #candidate

    print("FAILED *******")
    for host, result in results_callback.host_failed.items():
        print('{0} >>> {1}'.format(host, result._result['msg']))

    print("DOWN *********")
    for host, result in results_callback.host_unreachable.items():
        print('{0} >>> {1}'.format(host, result._result['msg']))





from flask import Flask, request, Response      #used for flask app, receive and response of webhook
import json                                     #used for handling json objects
import requests                                 #used for HTTP get request to netbox api
from datetime import datetime                   #used for playbook file timestamp
import os                                       #used for directory making
import getpass

app = Flask(__name__)


list_of_models =    {
                    "device": 
                                {
                                    "configurable": ["name"],
                                    "informational": ["primary_ip", "address"]
                                },
                    "interface":
                                {
                                    "configurable": ["enabled", "description"],
                                    "informational": ["device", "url"]
                                },
                    "ipaddress":
                                {
                                    "configurable": ["address", "nat_inside", "roll"],
                                    "informational": ["assigned_object", "device", "url"]
                                },
                    }



#check if model is configurable. Returns model, event, data if so
def check_model(model):
    if model in list_of_models:
        #match
        print(model, "is configurable")
        return True


#returns the difference of prechange vs postchange in a new dict
def compare(snapshots):
    prechange = snapshots["prechange"]
    postchange = snapshots["postchange"]
    updated_values = {}
    #loops through keys and non-matching values
    for key in prechange:
        if prechange[key] != postchange[key]:
            updated_values[key] = postchange[key]
    return updated_values


#returns the configurable values
"""
returns 'config' as a dict with both "configurable" and "informational" as keys
or returns a value of None
"""
def pick_out_values(model, data, values):
    config = {}
    config["configurable"] = {}

    for element in list_of_models[model]["configurable"]:
        if element in values:
            #Key is added in the dictionary "config" along with a value
            config["configurable"][element] = values[element]
    
    print('1',config)
    if "configurable" in config != {}:
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
        return

"""
def create_playbook(config, ip, device_name):
    #timestamp
    dateTimeObj = datetime.now()
    date = (f"{dateTimeObj.year}-{dateTimeObj.month}-{dateTimeObj.day}")
    time = (f"{dateTimeObj.hour}-{dateTimeObj.minute}-{dateTimeObj.second}")
    
    #mkdir
    username = getpass.getuser()
    path = "/home/"+username+"/playbooks/"+date
    print(path)

    if not os.path.exists(path):
        os.makedirs(path)
        print("Directory", path, "created")
    else:
        print("Directory", path, "already exists")

    #mk file
    fil = open(f"{path}/{device_name}_{date}_{time}.yaml", "x")
    fil.write("hej")
    fil.close()
    return
"""
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
        if webhook["snapshots"]["prechange"] == None:
            print()
            print("prechange contains a value of null.")
            print("This occurs when the 'make this the primary IP for the device' option was changed when creating/editing an ipaddress")
            print("which will send a device webhook as well, with the prechange set to null")
            return Response(status=200)
        
        else:
            values = compare(webhook["snapshots"])

    elif event == "created":
        values = webhook["snapshots"]["postchange"]

    elif event == "deleted":
        values = webhook["snapshots"]["prechange"]

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
        device_name = config["configurable"]

    else:
        ip, device_name = get_api_data(config)
        print("device primary IP is", ip)
        if ip == None:
            print()
            print("The targeted device has no primary IP assigned. Nowhere to send conf.")
            return Response(status=200)

    #step 5: create and run playbook
    run_playbook(config, ip, event, model, data, values) #device_name

    return Response(status=200)
