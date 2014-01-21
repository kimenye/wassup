from Yowsup.connectionmanager import YowsupConnectionManager
from Yowsup.Common.utilities import Utilities
import base64, time, os, requests, json


class WhatsappListenerClient:

	def __init__(self, app, keepAlive = False, sendReceipts = False):
		self.sendReceipts = sendReceipts
		self.app = app
		
		connectionManager = YowsupConnectionManager()
		connectionManager.setAutoPong(keepAlive)		

		self.signalsInterface = connectionManager.getSignalsInterface()
		self.methodsInterface = connectionManager.getMethodsInterface()
		
		self.signalsInterface.registerListener("message_received", self.onMessageReceived)
		self.signalsInterface.registerListener("image_received", self.onImageReceived)
		self.signalsInterface.registerListener("auth_success", self.onAuthSuccess)
		self.signalsInterface.registerListener("auth_fail", self.onAuthFailed)
		self.signalsInterface.registerListener("disconnected", self.onDisconnected)

		self.signalsInterface.registerListener("contact_gotProfilePicture", self.onGotProfilePicture)
		
		self.cm = connectionManager
		self.done = False

	def login(self, username, password):
		self.app.logger.info('In Login')
		self.username = username
		# self.password = base64.b64decode(bytes(password.encode('utf-8')))
		self.password = password

		self.methodsInterface.call("auth_login", (username, self.password))

		while not self.done:
			self.app.logger.info('Waiting')
			time.sleep(0.5)

	def sendMessage(self, target, text):
		self.app.logger.info("To send %s " %text)
		jid = "%s@s.whatsapp.net" %target
		self.app.logger.info("Message %s" %jid)
		self.done = True
		self.app.logger.info("Self %s" %self.done)
		self.methodsInterface.call("message_send", (jid, text))

	def onAuthSuccess(self, username):
		self.app.logger.info('Authenticated')
		self.methodsInterface.call("ready")

	def onAuthFailed(self, username, err):
		self.app.logger.info('Authentication failed')
		
	def onDisconnected(self, reason):
		self.app.logger.info('Disconnected')
		# self.login(self.username, self.password)

	def onGotProfilePicture(self, jid, imageId, filePath):
		self.app.logger.info('Got profile picture')
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
		self.app.logger.info('Message Received %s' %messageContent)
		phone_number = jid.split("@")[0]
		headers = {'Content-type': 'application/json', 'Accept': 'application/json'}
		data = { "message" : { "text" : messageContent, "phone_number" : phone_number, "message_type" : "Text", "whatsapp_message_id" : messageId, "name" : pushName }}
		url = os.getenv('SERVER_URL', 'http://localhost:3000')
		post_url = url + "/messages"
		r = requests.post(post_url, data=json.dumps(data), headers=headers)

		if wantsReceipt and self.sendReceipts:
			self.methodsInterface.call("message_ack", (jid, messageId))

		self.checkProfilePic(jid)	

	def onImageReceived(self, messageId, jid, preview, url, size, wantsReceipt, isBroadCast):	
		self.app.logger.info('Image Received')	

	def onGotProfilePicture(self, jid, imageId, filePath):
		self.app.logger.info('Profile picture received')		