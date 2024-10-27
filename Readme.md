**How to Install required Python libraries**
**Goto API Folder**
pip install -r requirements.txt


**How to Open Python service to be accessible from Expo App**
---DONT FORGET TO RESTART PYTHON SERVICE ONCE CHANGES ARE APPLIED
---PLEASE VERIFY BY USING IP BASED URL FROM BROWSER
--- LIKE http://192.168.1.9:5000/users
**CHATGPT PROMPT**
I have started my python service like python app.py
help me to make sure that service is accissibleby IP

**Firewall and Network Settings**
Ensure that your machine's firewall is not blocking incoming connections to the Flask service. On different platforms, you may need to configure this differently:

**For Linux (Ubuntu) Firewall:**
Use ufw to allow the port (e.g., 5000):

bash
Copy code
sudo ufw allow 5000/tcp

**For Windows Firewall:**
Go to Control Panel > System and Security > Windows Defender Firewall.
Click on Advanced settings.
In the left pane, click Inbound Rules, then New Rule... in the right pane.
Select Port, then specify TCP and the port you are using (e.g., 5000).
Follow the steps to allow connections.
**For macOS Firewall:**
Go to System Preferences > Security & Privacy > Firewall.
If the firewall is on, click the lock icon to make changes.
Click Firewall Options, then allow incoming connections for Python or specify the port.
**Start the Flask App**
Now, run your Flask app again using:

bash
Copy code
python app.py
This will start the Flask app and bind it to 0.0.0.0, making it accessible over the network.

**Access Flask Service via IP**
To access the Flask service from another device on your network, use the IP address of the machine where Flask is running, followed by the port.

For example, if the IP of your machine is 192.168.1.100 and Flask is running on port 5000, access the service like this:

bash
Copy code
http://192.168.1.100:5000