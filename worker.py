from Yowsup.connectionmanager import YowsupConnectionManager
from Yowsup.Common.utilities import Utilities
import threading,time, base64
import os
import datetime, sys
import requests, json
import cStringIO

if sys.version_info >= (3, 0):
	raw_input = input

class WhatsappListenerClient:
	
	def __init__(self, keepAlive = False, sendReceipts = False):
		self.sendReceipts = sendReceipts
		
		connectionManager = YowsupConnectionManager()
		connectionManager.setAutoPong(keepAlive)

		self.signalsInterface = connectionManager.getSignalsInterface()
		self.methodsInterface = connectionManager.getMethodsInterface()
		
		self.signalsInterface.registerListener("message_received", self.onMessageReceived)
		self.signalsInterface.registerListener("image_received", self.onImageReceived)
		self.signalsInterface.registerListener("auth_success", self.onAuthSuccess)
		self.signalsInterface.registerListener("auth_fail", self.onAuthFailed)
		self.signalsInterface.registerListener("disconnected", self.onDisconnected)
		# self.signalsInterface.registerListener("contact_gotProfilePictureId", self.onGotProfilePictureId)
		self.signalsInterface.registerListener("contact_gotProfilePicture", self.onGotProfilePicture)
		
		self.cm = connectionManager
	
	def login(self, username, password):
		self.username = username
		self.methodsInterface.call("auth_login", (username, password))
		
		while True:
			raw_input()	

	def onAuthSuccess(self, username):
		print("Authed %s" % username)
		self.methodsInterface.call("ready")

	def onAuthFailed(self, username, err):
		print("Auth Failed!")

	def onDisconnected(self, reason):
		print("Disconnected because %s" %reason)

	def getContentType(self, url):
		r = requests.get(url)
		return r.headers['content-type']

	def onImageReceived(self, messageId, jid, preview, url, size, wantsReceipt, isBroadCast):
		phone_number = jid.split("@")[0]

		post_url = os.getenv('SERVER_URL', 'http://localhost:3000')
		post_url = post_url + "/upload"
		headers = {'Content-type': 'application/json', 'Accept': 'application/json'}
		data = { "message" : { 'url' : url, 'phone_number' : phone_number, "whatsapp_message_id" : messageId, 'name' : '' } }
		r = requests.post(post_url, data=json.dumps(data), headers=headers)
		# print("Status code %s" %r.status_code)

		if wantsReceipt and self.sendReceipts:
			self.methodsInterface.call("message_ack", (jid, messageId))

		self.checkProfilePic(jid)

	def onGotProfilePicture(self, jid, imageId, filePath):
		print("Url %s" %filePath)
		url = os.getenv('SERVER_URL', 'http://localhost:3000')
		url = url + "/contacts/" + jid.split("@")[0] + "/upload"
		files = {'file': open(filePath, 'rb')}
		r = requests.post(url, files=files)

	def checkProfilePic(self, jid):
		phone_number = jid.split("@")[0]
		url = os.getenv('SERVER_URL', 'http://localhost:3000')
		get_url = url + "/profile?phone_number=" + phone_number
		headers = {'Content-type': 'application/json', 'Accept': 'application/json'}
		r = requests.get(get_url, headers=headers)
		response = r.json()
		
		if response['profile_pic'] == '/profile_pics/original/missing.png':
			self.methodsInterface.call("contact_getProfilePicture", (jid,))	

	def onMessageReceived(self, messageId, jid, messageContent, timestamp, wantsReceipt, pushName, isBroadCast):
				
		phone_number = jid.split("@")[0]
		headers = {'Content-type': 'application/json', 'Accept': 'application/json'}
		data = { "message" : { "text" : messageContent, "phone_number" : phone_number, "message_type" : "Text", "whatsapp_message_id" : messageId, "name" : pushName }}
		url = os.getenv('SERVER_URL', 'http://localhost:3000')
		post_url = url + "/messages"
		r = requests.post(post_url, data=json.dumps(data), headers=headers)

		if wantsReceipt and self.sendReceipts:
			self.methodsInterface.call("message_ack", (jid, messageId))

		self.checkProfilePic(jid)
	


login = "254733171036"
password = "+rYGoEyk7y9QBGLCSHuPS2VVZNw="
password = base64.b64decode(bytes(password.encode('utf-8')))

wa = WhatsappListenerClient(False,True)
wa.login(login, password)






# time.sleep(500)
# while True:
	# raw_input()	