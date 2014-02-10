from flask import Flask, jsonify, request
from flask.ext.sqlalchemy import SQLAlchemy
# from WhatsappEchoClient import WhatsappEchoClient
# from WhatsappListenerClient import WhatsappListenerClient
from Yowsup.connectionmanager import YowsupConnectionManager
from Yowsup.Common.utilities import Utilities
from rq import Queue
from messenger import conn
from logging import StreamHandler

import requests
import os, json, base64, time
import logging, base64



app = Flask(__name__)
app.debug = True
file_handler = StreamHandler()
app.logger.setLevel(logging.DEBUG)  # set the desired logging level here
app.logger.addHandler(file_handler)


db_url = os.getenv('SQLALCHEMY_DATABASE_URI', 'sqlite:///db/dev.db')
app.config['SQLALCHEMY_DATABASE_URI'] = db_url

db = SQLAlchemy(app)
app.db = db


class Message(db.Model):
	id = db.Column(db.Integer, primary_key=True)
	phone_number = db.Column(db.String(80))
	message = db.Column(db.String(255))
	sent = db.Column(db.Boolean())

	def __init__(self, phone_number, message, sent):
		self.phone_number = phone_number
		self.message = message
		self.sent = sent

class Job(db.Model):
	id = db.Column(db.Integer, primary_key=True)
	objectId = db.Column(db.Integer)
	method = db.Column(db.String(255))
	targets = db.Column(db.String(255))
	args = db.Column(db.String(255))
	sent = db.Column(db.Boolean())

	def __init__(self, method, targets, sent, args):
		self.method = method
		self.targets = targets
		self.sent = sent
		self.args = args

class WhatsappListenerClient:

	def __init__(self, app, keepAlive = False, sendReceipts = False):
		self.sendReceipts = sendReceipts
		self.app = app
		
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
		self.url = os.getenv('SERVER_URL', 'http://localhost:3000')
		self.post_headers = {'Content-type': 'application/json', 'Accept': 'application/json'}		
		self.done = False

	def login(self, username, password):
		self.app.logger.info('In Login')
		self.username = username
		self.password = password

		self.methodsInterface.call("auth_login", (username, self.password))
		self.methodsInterface.call("presence_sendAvailable", ())

		while not self.done:
			# self.app.logger.info('Waiting')		
			messages = Message.query.filter_by(sent=False).all()			
			if len(messages) > 0:
				self.app.logger.info("Messages %s" % len(messages))
			
			for message in messages:
				self.sendMessage(message.phone_number.encode('utf8'), message.message.encode('utf8'))
				message.sent = True

			self.seekJobs()

			self.app.db.session.commit()

			time.sleep(5)

	def seekJobs(self):
		jobs = Job.query.filter_by(sent=False).all()
		if len(jobs) > 0:
			self.app.logger.info("Jobs %s" % len(jobs))

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
		
		self.app.db.session.commit()				

	def sendMessage(self, target, text):
		self.app.logger.info("To send %s " %text)
		jid = target
		self.app.logger.info("Message %s" %jid)
		# self.done = True
		# self.app.logger.info("Self %s" %self.done)
		self.methodsInterface.call("message_send", (jid, text))


	def onGroupAddParticipantsSuccess(self, groupJid, jid):
		self.app.logger.info("Added participant %s" %jid)
		# check the profile pic
		self.checkProfilePic(jid)

	def onGroupCreateSuccess(self, groupJid):
		self.app.logger.info("Created with id %s" %groupJid)
		self.methodsInterface.call("group_getInfo", (groupJid,))

	def onGroupGotInfo(self,jid,owner,subject,subjectOwner,subjectTimestamp,creationTimestamp):
		self.app.logger.info("Group info %s - %s" %(jid, subject))

		url = os.getenv('SERVER_URL', 'http://localhost:3000')
		put_url = url + "/update_group"
		headers = {'Content-type': 'application/json', 'Accept': 'application/json'}
		data = { "name" : subject, "jid" : jid }

		r = requests.post(put_url, data=json.dumps(data), headers=headers)
		self.app.logger.info("Updated the group")

	def onGroupCreateFail(self, errorCode):
		self.app.logger.info("Error creating a group %s" %errorCode)

	def onSetStatusSuccess(self,jid,messageId):
		self.app.logger.info("Set the profile message for %s - %s" %(jid, messageId))

	def onAuthSuccess(self, username):
		self.app.logger.info('Authenticated')
		self.methodsInterface.call("ready")
		self.setStatus(1)

	def setStatus(self, status):
		self.app.logger.info("Setting status %s" %status)
		post_url = self.url + "/status"
		data = { "status" : status }
		r = requests.post(post_url, data=json.dumps(data), headers=self.post_headers)

	def onAuthFailed(self, username, err):
		self.app.logger.info('Authentication failed')
		
	def onDisconnected(self, reason):
		self.app.logger.info('Disconnected')
		self.setStatus(0)
		self.done = True

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
		
		if response['profile_url'] == '/assets/missing.png':		
			self.methodsInterface.call("contact_getProfilePicture", (jid,))	

	def onGroupMessageReceived(self, messageId, jid, author, content, timestamp, wantsReceipt, pushName):
		self.app.logger.info('Received a message on the group %s' %content)
		self.app.logger.info('JID %s - %s - %s' %(jid, pushName, author))

		if wantsReceipt and self.sendReceipts:
			self.methodsInterface.call("message_ack", (jid, messageId))

		headers = {'Content-type': 'application/json', 'Accept': 'application/json' }
		data = { "message" : { "text" : content, "group_jid" : jid, "message_type" : "Text", "whatsapp_message_id" : messageId, "name" : pushName, "jid" : author }}

		url = os.getenv('SERVER_URL', 'http://localhost:3000')
		post_url = url + "/receive_broadcast"
		r = requests.post(post_url, data=json.dumps(data), headers=headers)

		self.checkProfilePic(author)

	def onMessageReceived(self, messageId, jid, messageContent, timestamp, wantsReceipt, pushName, isBroadCast):
		self.app.logger.info('Message Received %s' %messageContent)
		phone_number = jid.split("@")[0]
		headers = {'Content-type': 'application/json', 'Accept': 'application/json'}
		data = { "message" : { "text" : messageContent, "phone_number" : phone_number, "message_type" : "Text", "whatsapp_message_id" : messageId, "name" : pushName  }}
		url = os.getenv('SERVER_URL', 'http://localhost:3000')
		post_url = url + "/messages"
		r = requests.post(post_url, data=json.dumps(data), headers=headers)

		if wantsReceipt and self.sendReceipts:
			self.methodsInterface.call("message_ack", (jid, messageId))

		self.checkProfilePic(jid)	

	def onImageReceived(self, messageId, jid, preview, url, size, wantsReceipt, isBroadCast):	
		self.app.logger.info('Image Received')	
		phone_number = jid.split("@")[0]

		post_url = os.getenv('SERVER_URL', 'http://localhost:3000')
		post_url = post_url + "/upload"
		headers = {'Content-type': 'application/json', 'Accept': 'application/json'}
		data = { "message" : { 'url' : url, 'phone_number' : phone_number, "whatsapp_message_id" : messageId, 'name' : '' } }
		r = requests.post(post_url, data=json.dumps(data), headers=headers)

		if wantsReceipt and self.sendReceipts:
			self.methodsInterface.call("message_ack", (jid, messageId))

		self.checkProfilePic(jid)

	def onGotProfilePicture(self, jid, imageId, filePath):
		self.app.logger.info('Profile picture received')
		url = os.getenv('SERVER_URL', 'http://localhost:3000')
		url = url + "/contacts/" + jid.split("@")[0] + "/upload"
		files = {'file': open(filePath, 'rb')}
		r = requests.post(url, files=files)

app.whatsapp = WhatsappListenerClient(app, True, True)

def listen():	
	app.logger.info('Locked and ready to go')	
	login = os.getenv('LOGIN')
	password = os.getenv('PASSWORD')
	password = base64.b64decode(bytes(password.encode('utf-8')))
	app.logger.info("Login: %s" %login)
	app.whatsapp.login(login, password)

q = Queue(connection=conn)
q.enqueue_call(func=listen, timeout=3600)

@app.route('/')
def hello():
	app.logger.info('Hello World!')
	return 'Yo Wassup!'

@app.route('/job', methods=['POST'])
def job():
	method = request.json['job_type']
	args = request.json['args']
	job = Job(method,None,False,args)
	app.logger.info('Job create %s' %method)
	db.session.add(job)
	db.session.commit()
	app.logger.info("Job created %s" %job.id)

	return jsonify(status='ok')

@app.route('/broadcast', methods=['POST', 'GET'])
def broadcast():
	msg = request.json['message']
	jid = request.json['jid']

	message = Message(jid, msg, False)
	db.session.add(message)
	db.session.commit()
	return jsonify(status='ok')

@app.route('/send', methods=['POST', 'GET'])
def send():
	phone_number = request.json['phone_number']
	msg = request.json['message']
	app.logger.info('TO: %s' %phone_number)
	app.logger.info('MSG: %s' %msg)

	phone_number = "%s@s.whatsapp.net" %phone_number
	
	message = Message(phone_number, msg, False)
	db.session.add(message)
	db.session.commit()

	return jsonify(status="ok")