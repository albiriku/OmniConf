from flask import Flask, request, Response
import json
import requests


app = Flask(__name__)


list_of_models =    {
                    "device": 
                                {
                                    "configurable": ["name"]
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
    #try:
    for key in prechange:
        if prechange[key] != postchange[key]:
            updated_values[key] = postchange[key]
    return updated_values
    #except TypeError:
    #    print("The prechange was empty")


#returns the configurable values
def pick_out_values(model, data, values):
    config = {}
    for element in list_of_models[model]["configurable"]:
        if element in values:
            config["configurable"] = {}
            #Key is added in the dictionary "config" along with a value
            config["configurable"][element] = values[element]

    if not model == "device":
        config["informational"] = {}
        info = list_of_models[model]["informational"]
        length = len(info)

        for i in range(0, length):                                      #loop på antalet element i info
            if i == 0:                                                      #första varvet:
                config["informational"] = data[info[i]]                           #uppslagning i data, efter element 0 från info. Sparar värdet i conf under nyckeln ["informational"]
            else:                                                           #alla andra varv:
                config["informational"] = config["informational"][info[i]]          #uppslagning i conf["informational"], efter nästa element i info. Sparar över i conf. Upprepar för resterande element.
    print("slutresultat: ", config)
    return config


def get_api_data(config):
    url = 'https://193.10.237.252' + config["informational"]
    print(url)
    headers =   {
                'Content-Type': "application/json", 
                'Authorization': "Token c788f875f6a0bce55f485051a61dbb67edba0994" 
                }

    api_data = requests.request("GET", url, headers=headers, verify=False)
    #ip = api_data["primary_ip"]

    print(json.dumps(api_data.json(), indent=4))
    #print(ip)
    #return ip


@app.route('/webhook-test', methods=['POST'])
def respond():
    webhook = request.json
    model = webhook["model"]
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
            print("POST OR PRECHANGE WAS EMPTY BIATCH. now exits")
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

    #step 4: api get request for more info (if needed)
    if "informational" in config:
        info = get_api_data(config)

    return Response(status=200)
