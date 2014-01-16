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
		# page = urllib2.urlopen(url)
    	# pageHeaders = page.headers
    	# contentType = pageHeaders.getheader('content-type')
    	

	def onImageReceived(self, messageId, jid, preview, url, size, wantsReceipt, isBroadCast):
		print("Url is %s" %url)
		print("Wants receipt %s" %wantsReceipt)

		post_url = 'http://localhost:3000/upload'		
		headers = {'Content-type': 'application/json', 'Accept': 'application/json'}
		# headers = { 'Content-type' : contentType }
		# files = {'image': ('image.jpeg', cStringIO.StringIO(preview))}

		# payload = { 'content_type' : contentType }
		data = { "message" : { 'url' : url, 'phone_number' : jid } }
		r = requests.post(post_url, data=json.dumps(data), headers=headers)
		print("Status code %s" %r.status_code)

		if wantsReceipt and self.sendReceipts:
			self.methodsInterface.call("message_ack", (jid, messageId))

	def onMessageReceived(self, messageId, jid, messageContent, timestamp, wantsReceipt, pushName, isBroadCast):
		formattedDate = datetime.datetime.fromtimestamp(timestamp).strftime('%d-%m-%Y %H:%M')
		print("%s [%s]:%s"%(jid, formattedDate, messageContent))

		headers = {'Content-type': 'application/json', 'Accept': 'application/json'}
		data = { "message" : { "text" : messageContent, "phone_number" : jid, "user_id" : 1, "message_type" : "text" }}
		r = requests.post("http://localhost:3000/messages", data=json.dumps(data), headers=headers)

		if wantsReceipt and self.sendReceipts:
			self.methodsInterface.call("message_ack", (jid, messageId))
	


login = "254733171036"
password = "+rYGoEyk7y9QBGLCSHuPS2VVZNw="
password = base64.b64decode(bytes(password.encode('utf-8')))

wa = WhatsappListenerClient(False,True)
wa.login(login, password)






# time.sleep(500)
# while True:
	# raw_input()	