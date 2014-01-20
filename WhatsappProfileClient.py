import os
parentdir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
os.sys.path.insert(0,parentdir)
import time, base64

from Yowsup.connectionmanager import YowsupConnectionManager

class WhatsappProfileClient:
	def __init__(self, phone_number):
		connectionManager = YowsupConnectionManager()
		self.signalsInterface = connectionManager.getSignalsInterface()
		self.methodsInterface = connectionManager.getMethodsInterface()

		self.signalsInterface.registerListener("auth_success", self.onAuthSuccess)
		self.signalsInterface.registerListener("auth_fail", self.onAuthFailed)
		self.signalsInterface.registerListener("disconnected", self.onDisconnected)
		# self.signalsInterface.registerListener("profile_setPictureSuccess", self.onSetProfilePicture)
		# self.signalsInterface.registerListener("profile_setPictureError", self.onSetProfilePictureError)
		self.signalsInterface.registerListener("contact_gotProfilePicture", self.onGotProfilePicture)
		# self.signalsInterface.registerListener("profile_setStatusSuccess", self.onSetStatusSuccess)
		self.phone_number = phone_number
		self.done = False		

	def login(self, username, password):
		self.username = username
		self.methodsInterface.call("auth_login", (username, password))

		while not self.done:
			time.sleep(0.5)

	def onAuthFailed(self, username, err):
		print("Auth Failed!")

	def onDisconnected(self, reason):
		print("Disconnected because %s" %reason)

	def onSetProfilePictureError(self, errorCode):
		print("Fail to set pic: " % errorCode)
		self.done = True

	def onGotProfilePicture(self, filePath):
		print("Got the profile pic %s" %filePath)
		self.done = True

	def onSetProfilePicture(self):
		print("GETTING MY PICTURE")
		self.done = True

	def onSetStatusSuccess(self, jId, messageId):
		print("Set the status")
		self.done = True

	def onAuthSuccess(self, username):
		print("Authed %s" % username)		
		self.methodsInterface.call("contact_getProfilePicture", (self.phone_number,))
		# self.methodsInterface.call("profile_setPicture",('logo.jpg',))
		# self.done = True


login = "254733171036"
password = "+rYGoEyk7y9QBGLCSHuPS2VVZNw="
password = base64.b64decode(bytes(password.encode('utf-8')))

wa = WhatsappProfileClient("61450212500")
wa.login(login, password)
