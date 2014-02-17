from sqlalchemy import create_engine
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy import Column, Integer, String, Boolean
from sqlalchemy.orm import sessionmaker
from Yowsup.connectionmanager import YowsupConnectionManager
from Yowsup.Common.utilities import Utilities
import os
import os, json, base64, time, requests
import logging



Base = declarative_base()
logging.basicConfig(filename='logs/production.log',level=logging.DEBUG, format='%(asctime)s %(message)s')


class Message(Base):
	__tablename__ = 'job_messages'
	# __tablename__ = 'message'
	id = Column(Integer, primary_key=True)
	phone_number = Column(String(255))
	message = Column(String(255))
	sent = Column(Boolean())

	def __init__(self, phone_number, message, sent):
		self.phone_number = phone_number
		self.message = message
		self.sent = sent

class Job(Base):
	# __tablename__ = 'job'
	__tablename__ = 'job_logs'
	id = Column(Integer, primary_key=True)

	#objectId = Column(Integer)
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
		# self.metadata = BoundMetaData(self.db)

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
		
		self.cm = connectionManager
		# self.url = os.getenv('SERVER_URL', 'http://localhost:3000')
		# self.url = 'http://localhost:8080'
		
		# self.url = 'http://localhost:3000'
		self.url = os.environ['URL']

		self.post_headers = {'Content-type': 'application/json', 'Accept': 'application/json'}		
		self.done = False

		# messages = self.Session.query(Message).filter_by(sent=True).all()			
		# for instance in self.s.query(Message): 
			# print instance.message

		# for job in self.s.query(Job):
			# print job.method


		


	def login(self, username, password):
		print('In Login')
		self.username = username
		self.password = password

		self.methodsInterface.call("auth_login", (username, self.password))
		self.methodsInterface.call("presence_sendAvailable", ())

		# self.methodsInterface.call("profile_setPicture", (r"logo.jpg",))
		# self.methodsInterface.call("profile_setStatus", ("Sprout is using WhatsApp",))

		while not self.done:
			print('Waiting')		
			messages = self.s.query(Message).filter_by(sent=False).all()			
			if len(messages) > 0:
				print("Messages %s" % len(messages))
			
			for message in messages:
				self.sendMessage(message.phone_number.encode('utf8'), message.message.encode('utf8'))
				message.sent = True

			self.seekJobs()

			# self.sendMessage("61450212500@s.whatsapp.net", "Woosah")
			# self.app.db.session.commit()

			# time.sleep(5)
			raw_input()	
	
	def seekJobs(self):
		# jobs = Job.query.filter_by(sent=False).all()
		jobs = self.s.query(Job).filter_by(sent=False).all()
		if len(jobs) > 0:
			print("Jobs %s" % len(jobs))

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
		
		# self.app.db.session.commit()				
		self.s.commit()			

	def sendMessage(self, target, text):
		print("Message %s " %text)
		jid = target
		print("To %s" %jid)
		self.methodsInterface.call("message_send", (jid, text))	

	def onGroupAddParticipantsSuccess(self, groupJid, jid):
		print("Added participant %s" %jid)
		# check the profile pic
		self.checkProfilePic(jid[0])

	def onGroupCreateSuccess(self, groupJid):
		print("Created with id %s" %groupJid)
		self.methodsInterface.call("group_getInfo", (groupJid,))

	def onGroupGotInfo(self,jid,owner,subject,subjectOwner,subjectTimestamp,creationTimestamp):
		print("Group info %s - %s" %(jid, subject))

		
		put_url = self.url + "/update_group"
		headers = {'Content-type': 'application/json', 'Accept': 'application/json'}
		data = { "name" : subject, "jid" : jid }

		r = requests.post(put_url, data=json.dumps(data), headers=headers)
		print("Updated the group")

	def onGroupCreateFail(self, errorCode):
		print("Error creating a group %s" %errorCode)

	def onSetStatusSuccess(self,jid,messageId):
		print("Set the profile message for %s - %s" %(jid, messageId))

	def onAuthSuccess(self, username):
		# self.app.logger.info('Authenticated')
		logging.info("We are authenticated")
		self.methodsInterface.call("ready")
		self.setStatus(1, "Authenticated")

	def setStatus(self, status, message="Status message"):
		# self.app.logger.info("Setting status %s" %status)
		post_url = self.url + "/status"
		data = { "status" : status, "message" : message }
		r = requests.post(post_url, data=json.dumps(data), headers=self.post_headers)

	def onAuthFailed(self, username, err):
		print('Authentication failed')
		
	def onDisconnected(self, reason):
		logging.info('Disconnected')
		self.setStatus(0, "Got disconnected")
		# self.done = True
		logging.info('About to log in again with %s and %s' %(self.username, self.password))
		self.login(self.username, self.password)

	def onGotProfilePicture(self, jid, imageId, filePath):
		print('Got profile picture')
		# url = os.getenv('SERVER_URL', 'http://localhost:3000')
		url = self.url + "/contacts/" + jid.split("@")[0] + "/upload"
		files = {'file': open(filePath, 'rb')}
		r = requests.post(url, files=files)

	def checkProfilePic(self, jid):
		phone_number = jid.split("@")[0]
		# url = os.getenv('SERVER_URL', 'http://localhost:3000')
		get_url = self.url + "/profile?phone_number=" + phone_number
		headers = {'Content-type': 'application/json', 'Accept': 'application/json'}
		r = requests.get(get_url, headers=headers)
		response = r.json()
		
		if response['profile_url'] == '/missing.png':		
			self.methodsInterface.call("contact_getProfilePicture", (jid,))	

	def onGroupMessageReceived(self, messageId, jid, author, content, timestamp, wantsReceipt, pushName):
		print('Received a message on the group %s' %content)
		print('JID %s - %s - %s' %(jid, pushName, author))

		if wantsReceipt and self.sendReceipts:
			self.methodsInterface.call("message_ack", (jid, messageId))

		headers = {'Content-type': 'application/json', 'Accept': 'application/json' }
		data = { "message" : { "text" : content, "group_jid" : jid, "message_type" : "Text", "whatsapp_message_id" : messageId, "name" : pushName, "jid" : author }}

		# url = os.getenv('SERVER_URL', 'http://localhost:3000')
		post_url = self.url + "/receive_broadcast"
		r = requests.post(post_url, data=json.dumps(data), headers=headers)

		self.checkProfilePic(author)

	def onMessageReceived(self, messageId, jid, messageContent, timestamp, wantsReceipt, pushName, isBroadCast):
		print('Message Received %s' %messageContent)
		phone_number = jid.split("@")[0]
		headers = {'Content-type': 'application/json', 'Accept': 'application/json'}
		data = { "message" : { "text" : messageContent, "phone_number" : phone_number, "message_type" : "Text", "whatsapp_message_id" : messageId, "name" : pushName  }}
		# url = os.getenv('SERVER_URL', 'http://localhost:3000')
		post_url = self.url + "/messages"
		r = requests.post(post_url, data=json.dumps(data), headers=headers)

		if wantsReceipt and self.sendReceipts:
			self.methodsInterface.call("message_ack", (jid, messageId))

		self.checkProfilePic(jid)	

	def onImageReceived(self, messageId, jid, preview, url, size, wantsReceipt, isBroadCast):	
		print('Image Received')	
		phone_number = jid.split("@")[0]

		# post_url = os.getenv('SERVER_URL', 'http://localhost:3000')
		post_url = self.url + "/upload"
		headers = {'Content-type': 'application/json', 'Accept': 'application/json'}
		data = { "message" : { 'url' : url, 'phone_number' : phone_number, "whatsapp_message_id" : messageId, 'name' : '' } }
		r = requests.post(post_url, data=json.dumps(data), headers=headers)

		if wantsReceipt and self.sendReceipts:
			self.methodsInterface.call("message_ack", (jid, messageId))

		self.checkProfilePic(jid)

	def onGotProfilePicture(self, jid, imageId, filePath):
		print('Profile picture received')
		# url = os.getenv('SERVER_URL', 'http://localhost:3000')
		url = self.url + "/contacts/" + jid.split("@")[0] + "/upload"
		files = {'file': open(filePath, 'rb')}
		r = requests.post(url, files=files)

# server = Server('sqlite:///db/dev.db',True, True)
# server = Server('mysql+mysqldb://rails:wxFKW6Fz4B@localhost/rails',True, True)
database_url = os.environ['SQLALCHEMY_DATABASE_URI']
server = Server(database_url,True, True)
login = "254733171036"
password = "+rYGoEyk7y9QBGLCSHuPS2VVZNw="
password = base64.b64decode(bytes(password.encode('utf-8')))
server.login(login, password)

# server = Server('sqlite:///../chatcrm/db/development.sqlite3',True, True)
# server = Server('mysql+mysqldb://wassup:yowsup@localhost/yowsup',True, True)
