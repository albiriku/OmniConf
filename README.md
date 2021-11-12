This script was developed as a solution to achive network automation by utilizing Netbox, Ansible and Restconf.
Changes made in Netbox GUI are communicated to the webinterface of the script by webhooks. Predetermined changes get translated into a configuration in a JSON format. The configuration is sent by Ansible as Restconf and targets a yang data model on the device. Feedback about whether the communication to the device was successful or not is displayed in the terminal. For a more detailed view about the script operations, please look at the source code comments. This script is released as open-source under the GNU GENERAL PUBLIC LICENSE.


Recommended System:

Server:
Ubuntu server 20.04
Specs:
2 CPU
4 GB RAM
25 GB HDD

* Netbox, Ansible and the Script can run on the same system if desired.

PREREQUISITES

Software Components needed (Python 3 required)
1. Netbox
2. Ansible
    2.1 netcommon plugin
3. The script

Python extensions needed (pip install)
4. Requests
5. Flask (Any WSGI might work, but the script was designed with Flask in mind. Using another WSGI might introduce incompatibility or that the user has to accomodate for differences.)


REQUIREMENTS:

Networking Device requirements:
* Restconf support.
* Cisco IOS-XE devices for full support of the automated configuration.

Networking device pre-configuration:
* the devices must have an enbled interface with an reachable IP-address attached.

Network requirements:
* HTTP traffic must be able to flow from the netbox server to the server running ansible/script, and HTTPs traffic from the ansible/script server to the networking devices. 

Ansible requirements:
The following must exist for the networking devices to be configured:
* the netcommon plugin
* the device to conf must exist in the Ansible host inventory file, with the IP-address used as name. (the primary IP-address for the device in Netbox)
* the device must have login credentials in an Ansible var file
* connection parameters for Ansible must exist in an Ansible var file

Netbox requirements:
* A Netbox user token must be generated to be used for the script to grant access to the API.
* Webhooks need to be enabled and sent to the server running Ansible/script for the following module: DCIM > device, DCIM > interface, IPAM > ip-address. Specify the URL for which Flask listens on.

Script requirements:
* must run on the same server as Ansible.
* user specified parameters need to be added to the source code of the script.



INSTALLATION GUIDE:

Install Software:
* install Netbox (https://netbox.readthedocs.io/en/stable/installation/)
* install Ansible (pip install Ansible)
	* install netcommon module (ansible-galaxy collection install ansible.netcommon)
* install Flask (pip install flask)
* install Requests (pip install requests)
* Download the script (git pull)

Setup Ansible
* Add the networking device primary IP-address to the Ansible host inventory file
* Add the login credentials for the device in the appropriate Ansible var file (if it doesnt already exist)
the following parameters should exist in an Ansible var file, with appropriate values:
* ansible_connection: 'ansible.netcommon.httpapi'
* ansible_network_os: 'ansible.netcommon.restconf'
* ansible_user: 'developer'
* ansible_httpapi_port: 443
* ansible_httpapi_password: 'ExamplePassword'
* ansible_httpapi_use_ssl: 'yes'
* ansible_httpapi_validate_certs: false

Setup Netbox
* In the Netbox admin interface: Create a user account for the script and generate a token. It will be used for API interaction.
* In the Netbox admin interface: Enable webhooks for Device, IP-address and Interface modules. Provide the IP-address of the Ansible/script server and then the URL for which Flask listens on.

Setup the Script 
open the script using an editor and specify the user specific parameters in the source code of the script:
* Flask URL (instructs Flask to listen for incoming webhooks on this path, example "/webhook-test". Needs to match the URL path in specified in Netbox)
* Netbox IP-address (the server running Netbox. Will be used by the script to access netbox API to the primary IP-address of the device to conf)
* Netbox token	(will be used to authenticate the API call)
* Path to the Ansible inventory file (will be used when to script runs Ansible) 
* Ansible vault password (if you are using ansible vault to encrypt your ansible var files)

Add device in Netbox:
* create a new device
* create an interface, create an IP-address and assign it to the interface as the primary IP-address of the device. This IP-address will be used in order to send conf to the device.

Run the Script:
* run the scrip with appropriate Flask run command. It will start listening for incoming webhooks.



SCRIPT FUNCTIONS:

The script will send configure via Restconf to the device with according to the following changes:
In Netbox:						On the Device:
* changing the name of a device				* changes the hostname
* creating, updating, deleting an interface 		* creates, updates, deletes the configuration of the interface
* enable/disable interface				* enables/disables the interface
* assigning/removing an interface´s IP-address		* assigs/removes an interface´s IP-address	
							* The conf is automatically saved to startup after each call


IMPORTANT!:

Not all networking devices supports the configuration provided above! It depends on the device´s set of yang data models. If the device supports the listed yang data models, it supports the following configuration:
* hostname: Cisco-IOS-XE-native (cisco only)
* interface and IP-address: ietf-interfaces (vendor neutral)
* saving configuration to startup: cisco-ia (cisco only)


Please alter the source code to fit your needs.
For example you might want to add or remove parameters in the "list_of_models" variable in order to add or remove certain functions. This variable is intended to be customizable, but be aware that you are responsible for any changes made.



TESTED ON:

Server:
* Ubuntu server 20.04.3 LTS
Specs:
* 2 CPU
* 4 GB RAM
* 25 GB HDD

Software:
* Python v. 3.8.10
* Netbox v. 2.11.7
* Ansible v. 4.5.0
    * ansible.netcommon 2.4.0
* Requests v. 2.26.0
* Flask v. 2.0.1

