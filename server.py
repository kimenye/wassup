from sqlalchemy import create_engine
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy import Column, Integer, String, Boolean
from sqlalchemy.orm import sessionmaker
from Yowsup.connectionmanager import YowsupConnectionManager
from Yowsup.Common.utilities import Utilities
from Yowsup.Media.uploader import MediaUploader
import os, json, base64, time, requests, hashlib
import logging



Base = declarative_base()
logging.basicConfig(filename='logs/production.log',level=logging.DEBUG, format='%(asctime)s %(message)s')


class Message(Base):
	__tablename__ = 'job_messages'
	id = Column(Integer, primary_key=True)
	phone_number = Column(String(255))
	message = Column(String(255))
	sent = Column(Boolean())

	def __init__(self, phone_number, message, sent):
		self.phone_number = phone_number
		self.message = message
		self.sent = sent

class Job(Base):
	__tablename__ = 'job_logs'
	id = Column(Integer, primary_key=True)

	method = Column(String(255))
	targets = Column(String(255))
	args = Column(String(255))
	sent = Column(Boolean())

	def __init__(self, method, targets, sent, args):
		self.method = method
		self.targets = targets
		self.sent = sent
		self.args = args

class Server:
	def __init__(self, url, keepAlive = False, sendReceipts = False):
		self.sendReceipts = sendReceipts
		self.keepAlive = keepAlive
		self.db = create_engine(url, echo=False)

		self.Session = sessionmaker(bind=self.db)
		self.s = self.Session()

		connectionManager = YowsupConnectionManager()
		connectionManager.setAutoPong(keepAlive)		

		self.signalsInterface = connectionManager.getSignalsInterface()
		self.methodsInterface = connectionManager.getMethodsInterface()
		
		self.signalsInterface.registerListener("message_received", self.onMessageReceived)
		self.signalsInterface.registerListener("group_messageReceived", self.onGroupMessageReceived)
		self.signalsInterface.registerListener("image_received", self.onImageReceived)
		self.signalsInterface.registerListener("auth_success", self.onAuthSuccess)
		self.signalsInterface.registerListener("auth_fail", self.onAuthFailed)
		self.signalsInterface.registerListener("disconnected", self.onDisconnected)

		self.signalsInterface.registerListener("contact_gotProfilePicture", self.onGotProfilePicture)
		self.signalsInterface.registerListener("profile_setStatusSuccess", self.onSetStatusSuccess)
		self.signalsInterface.registerListener("group_createSuccess", self.onGroupCreateSuccess)
		self.signalsInterface.registerListener("group_createFail", self.onGroupCreateFail)
		self.signalsInterface.registerListener("group_gotInfo", self.onGroupGotInfo)
		self.signalsInterface.registerListener("group_addParticipantsSuccess", self.onGroupAddParticipantsSuccess)

		self.signalsInterface.registerListener("media_uploadRequestSuccess", self.onUploadSuccess)
		self.signalsInterface.registerListener("media_uploadRequestFailed", self.onUploadFailed)
		
		self.cm = connectionManager
		self.url = os.environ['URL']

		self.post_headers = {'Content-type': 'application/json', 'Accept': 'application/json'}		
		self.done = False

	def onUploadFailed(self, hash):
		logging.info("Upload failed")

	def onUploadSuccess(self, hash, url, removeFrom):
		logging.info("The url is %s " %url)


	def login(self, username, password):
		logging.info('In Login')
		self.username = username
		self.password = password

		self.methodsInterface.call("auth_login", (username, self.password))
		self.methodsInterface.call("presence_sendAvailable", ())

		while not self.done:
			logging.info('Waiting')		
			messages = self.s.query(Message).filter_by(sent=False).all()			
			if len(messages) > 0:
				logging.info("Messages %s" % len(messages))
			
			for message in messages:
				self.sendMessage(message.phone_number.encode('utf8'), message.message.encode('utf8'))
				message.sent = True

			self.seekJobs()
			time.sleep(10)
	
	def seekJobs(self):
		jobs = self.s.query(Job).filter_by(sent=False).all()
		if len(jobs) > 0:
			logging.info("Jobs %s" % len(jobs))

		for job in jobs:
			if job.method == "profile_setStatus":
				self.methodsInterface.call(job.method.encode('utf8'), (job.args.encode('utf8'),))
				job.sent = True
			elif job.method == "group_create":
				self.methodsInterface.call(job.method.encode('utf8'), (job.args.encode('utf8'),))
				job.sent = True
			elif job.method == "group_addParticipants":
				params = job.args.encode('utf8').split(",")
				self.methodsInterface.call(job.method.encode('utf8'), (params[0], [params[1] + "@s.whatsapp.net"],))
				job.sent = True
			elif job.method == "contact_getProfilePicture":
				self.methodsInterface.call("contact_getProfilePicture", (job.args.encode('utf8'),))
				job.sent = True
		
		self.s.commit()			

	def sendMessage(self, target, text):
		logging.info("Message %s " %text)
		jid = target
		logging.info("To %s" %jid)
		self.methodsInterface.call("message_send", (jid, text))	

	def onGroupAddParticipantsSuccess(self, groupJid, jid):
		logging.info("Added participant %s" %jid)
		# check the profile pic
		self.checkProfilePic(jid[0])

	def onGroupCreateSuccess(self, groupJid):
		logging.info("Created with id %s" %groupJid)
		self.methodsInterface.call("group_getInfo", (groupJid,))

	def onGroupGotInfo(self,jid,owner,subject,subjectOwner,subjectTimestamp,creationTimestamp):
		logging.info("Group info %s - %s" %(jid, subject))

		
		put_url = self.url + "/update_group"
		headers = {'Content-type': 'application/json', 'Accept': 'application/json'}
		data = { "name" : subject, "jid" : jid }

		r = requests.post(put_url, data=json.dumps(data), headers=headers)
		logging.info("Updated the group")

	def onGroupCreateFail(self, errorCode):
		logging.info("Error creating a group %s" %errorCode)

	def onSetStatusSuccess(self,jid,messageId):
		logging.info("Set the profile message for %s - %s" %(jid, messageId))

	def onAuthSuccess(self, username):
		logging.info("We are authenticated")
		self.methodsInterface.call("ready")
		self.setStatus(1, "Authenticated")

		logo_url = os.environ['LOGO_PIC']
		status = os.environ['STATUS_MSG']

		logging.info("The pic is %s" %logo_url)
		logging.info("Status MSG %s" %status)

		self.methodsInterface.call("profile_setPicture", (logo_url,))
		self.methodsInterface.call("profile_setStatus", (status,))

		# url = "https://mms879.whatsapp.net/d/ZxYtUVSq4hoysA0Lyh0_dL-eziQABPNAt55gSg/Amu8_dr4eyj3NrbygVuKPXPz-r_REAMkT13mGFxgufEC.jpg"
		# url = "http://s3-ap-southeast-1.amazonaws.com/yowsup/assets/files/000/000/020/original/satisfy_customer_early.jpg"
		# thumb = "https://mms879.whatsapp.net/d/ZxYtUVSq4hoysA0Lyh0_dL-eziQABPNAt55gSg/Amu8_dr4eyj3NrbygVuKPXPz-r_REAMkT13mGFxgufEC.jpg"
		# base633 = "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"
		# self.methodsInterface.call("message_imageSend", ("61450212500@s.whatsapp.net", url, "File", "230", base633 ))

		# self.methodsInterface.call("media_requestUpload", (base633, "image", "39761"))

		# local_path = "logo.jpg"
		# mtype = "image"
		# sha1 = hashlib.sha256()
		# fp = open("logo.jpg", 'rb')

		# sha1.update(fp.read())
		# hsh = base64.b64encode(sha1.digest())
		# self.methodsInterface.call("media_requestUpload", (hsh, mtype, os.path.getsize(local_path)))

		# self.methodsInterface.call("contact_getProfilePicture", ("254733171036@s.whatsapp.net",))	
        

	def setStatus(self, status, message="Status message"):
		logging.info("Setting status %s" %status)
		post_url = self.url + "/status"
		data = { "status" : status, "message" : message }
		r = requests.post(post_url, data=json.dumps(data), headers=self.post_headers)

	def onAuthFailed(self, username, err):
		logging.info('Authentication failed')
		
	def onDisconnected(self, reason):
		logging.info('Disconnected')
		self.setStatus(0, "Got disconnected")
		# self.done = True
		logging.info('About to log in again with %s and %s' %(self.username, self.password))
		self.login(self.username, self.password)

	def onGotProfilePicture(self, jid, imageId, filePath):
		logging.info('Got profile picture')
		url = self.url + "/contacts/" + jid.split("@")[0] + "/upload"
		files = {'file': open(filePath, 'rb')}
		r = requests.post(url, files=files)

	def checkProfilePic(self, jid):
		phone_number = jid.split("@")[0]
		get_url = self.url + "/profile?phone_number=" + phone_number
		headers = {'Content-type': 'application/json', 'Accept': 'application/json'}
		r = requests.get(get_url, headers=headers)
		response = r.json()
		
		if response['profile_url'] == '/missing.png':		
			self.methodsInterface.call("contact_getProfilePicture", (jid,))	

	def onGroupMessageReceived(self, messageId, jid, author, content, timestamp, wantsReceipt, pushName):
		logging.info('Received a message on the group %s' %content)
		logging.info('JID %s - %s - %s' %(jid, pushName, author))

		if wantsReceipt and self.sendReceipts:
			self.methodsInterface.call("message_ack", (jid, messageId))

		headers = {'Content-type': 'application/json', 'Accept': 'application/json' }
		data = { "message" : { "text" : content, "group_jid" : jid, "message_type" : "Text", "whatsapp_message_id" : messageId, "name" : pushName, "jid" : author }}

		post_url = self.url + "/receive_broadcast"
		r = requests.post(post_url, data=json.dumps(data), headers=headers)

		self.checkProfilePic(author)

	def onMessageReceived(self, messageId, jid, messageContent, timestamp, wantsReceipt, pushName, isBroadCast):
		logging.info('Message Received %s' %messageContent)
		phone_number = jid.split("@")[0]
		headers = {'Content-type': 'application/json', 'Accept': 'application/json'}
		data = { "message" : { "text" : messageContent, "phone_number" : phone_number, "message_type" : "Text", "whatsapp_message_id" : messageId, "name" : pushName  }}
		post_url = self.url + "/messages"
		r = requests.post(post_url, data=json.dumps(data), headers=headers)

		if wantsReceipt and self.sendReceipts:
			self.methodsInterface.call("message_ack", (jid, messageId))

		self.checkProfilePic(jid)	

	def onImageReceived(self, messageId, jid, preview, url, size, wantsReceipt, isBroadCast):	
		logging.info('Image Received')	
		phone_number = jid.split("@")[0]

		# print preview
		post_url = self.url + "/upload"
		headers = {'Content-type': 'application/json', 'Accept': 'application/json'}
		data = { "message" : { 'url' : url, 'phone_number' : phone_number, "whatsapp_message_id" : messageId, 'name' : '' } }
		r = requests.post(post_url, data=json.dumps(data), headers=headers)

		if wantsReceipt and self.sendReceipts:
			self.methodsInterface.call("message_ack", (jid, messageId))

		self.checkProfilePic(jid)

	def onGotProfilePicture(self, jid, imageId, filePath):
		logging.info('Profile picture received')
		# url = os.getenv('SERVER_URL', 'http://localhost:3000')
		url = self.url + "/contacts/" + jid.split("@")[0] + "/upload"
		files = {'file': open(filePath, 'rb')}
		r = requests.post(url, files=files)


database_url = os.environ['SQLALCHEMY_DATABASE_URI']
server = Server(database_url,True, True)
login = os.environ['TEL_NUMBER']
password = os.environ['PASS']
password = base64.b64decode(bytes(password.encode('utf-8')))
server.login(login, password)
