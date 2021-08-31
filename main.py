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
                                    "configurable": ["enabled"],
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
    for element in list_of_models[model]["configurable"]:
        if element in values:
            config["configurable"] = {}
            #Key is added in the dictionary "config" along with a value
            config["configurable"][element] = values[element]
    

    if "configurable" in config == True:
        config["informational"] = {}
        info = list_of_models[model]["informational"]
        length = len(info)

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
        print("config == None. No configurable values were returned from the 'pick_out_values' function, or")
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

    #step 5: playbook
    create_playbook(config, ip, device_name)

    return Response(status=200)
