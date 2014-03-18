from sqlalchemy import create_engine
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy import Column, Integer, String, Boolean, DateTime
from sqlalchemy.orm import sessionmaker
from Yowsup.connectionmanager import YowsupConnectionManager
from Yowsup.Common.utilities import Utilities
from Yowsup.Media.uploader import MediaUploader
import os, json, base64, time, requests, hashlib, datetime
import logging

import calendar
from datetime import datetime, timedelta


Base = declarative_base()
logging.basicConfig(filename='logs/production.log',level=logging.DEBUG, format='%(asctime)s %(message)s')


class Message(Base):
	__tablename__ = 'job_messages'
	id = Column(Integer, primary_key=True)
	phone_number = Column(String(255))
	message = Column(String(255))
	sent = Column(Boolean())
	scheduled_time = Column(DateTime())

	def __init__(self, phone_number, message, sent):
		self.phone_number = phone_number
		self.message = message
		self.sent = sent

class Asset(Base):
	__tablename__ = 'assets'
	id = Column(Integer, primary_key=True)
	asset_hash = Column(String(255))
	file_file_name = Column(String(255))
	video_file_name = Column(String(255))
	video_file_size = Column(String(255))
	mms_url = Column(String(255))
	asset_type = Column(String(255))
	file_file_size = Column(Integer)

	def __init__(self, asset_hash, mms_url):
		self.asset_hash = asset_hash
		self.mms_url = mms_url

class Job(Base):
	__tablename__ = 'job_logs'
	id = Column(Integer, primary_key=True)

	method = Column(String(255))
	targets = Column(String(255))
	args = Column(String(255))
	sent = Column(Boolean())
	scheduled_time = Column(DateTime())

	def __init__(self, method, targets, sent, args, scheduled_time):
		self.method = method
		self.targets = targets
		self.sent = sent
		self.args = args
		self.scheduled_time = scheduled_time

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
		self.signalsInterface.registerListener("video_received", self.onVideoReceived)
		
		self.signalsInterface.registerListener("auth_success", self.onAuthSuccess)
		self.signalsInterface.registerListener("auth_fail", self.onAuthFailed)
		self.signalsInterface.registerListener("disconnected", self.onDisconnected)

		self.signalsInterface.registerListener("contact_gotProfilePicture", self.onGotProfilePicture)
		self.signalsInterface.registerListener("profile_setStatusSuccess", self.onSetStatusSuccess)
		self.signalsInterface.registerListener("group_createSuccess", self.onGroupCreateSuccess)
		self.signalsInterface.registerListener("group_createFail", self.onGroupCreateFail)
		self.signalsInterface.registerListener("group_gotInfo", self.onGroupGotInfo)
		self.signalsInterface.registerListener("group_addParticipantsSuccess", self.onGroupAddParticipantsSuccess)

		self.signalsInterface.registerListener("media_uploadRequestSuccess", self.onUploadRequestSuccess)
		# self.signalsInterface.registerListener("media_uploadRequestFailed", self.onUploadRequestFailed)
		self.signalsInterface.registerListener("media_uploadRequestDuplicate", self.onUploadRequestDuplicate)
		
		self.cm = connectionManager
		self.url = os.environ['URL']

		self.post_headers = {'Content-type': 'application/json', 'Accept': 'application/json'}		
		self.done = False

	def onUploadFailed(self, hash):
		print "Upload failed"
	

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
				logging.info("Phone Number : %s" %message.phone_number)
				logging.info("Message : %s" %message.message)

				if self._onSchedule(message.scheduled_time):
					self.sendMessage(message.phone_number.encode('utf8'), message.message.encode('utf8'))
					message.sent = True

			self.s.commit()	
			self.seekJobs()
			time.sleep(10)
	
	def seekJobs(self):
		jobs = self.s.query(Job).filter_by(sent=False).all()
		if len(jobs) > 0:
			logging.info("Jobs %s" % len(jobs))

		for job in jobs:
			if self._onSchedule(job.scheduled_time):
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
				elif job.method == "broadcast_Text":
					jids = job.targets.split(",")
					targets = []
					for jid in jids:
						targets.append("%s@s.whatsapp.net" %jid)
					self.methodsInterface.call("message_broadcast", (targets, job.args, ))

					job.sent = True
				elif job.method == "broadcast_Image":
					args = job.args.encode('utf8').split(",")
					asset_id = args[0]
					asset = self.s.query(Asset).get(asset_id)
					jids = job.targets.split(",")
					for jid in jids:
						self.sendImage(jid + "@s.whatsapp.net", asset)
						time.sleep(1)
					job.sent = True
				elif job.method == "uploadMedia":
					args = job.args.encode('utf8').split(",")
					asset_id = args[0]
					url = args[1]
					preview = args[2]
					logging.info("Asset Id: %s" %args[0])
					asset = self.s.query(Asset).get(asset_id)				
					logging.info("File name: %s" %asset.file_file_name)
					logging.info("Video name: %s" %asset.video_file_name)
					logging.info("Url: %s" %asset.mms_url)

					if asset.mms_url == None:
						self.requestMediaUrl(url, asset, preview)
					job.sent = True
				elif job.method == "sendImage":
					asset = self._getAsset(job.args)
					jids = job.targets.split(",")
					for jid in jids:
						self.sendImage(jid + "@s.whatsapp.net", asset)
					job.sent = True
				elif job.method == "broadcast_Video":
					args = job.args.encode('utf8').split(",")
					asset = self._getAsset(job.args)
					jids = job.targets.split(",")
					for jid in jids:
						self.sendVideo(jid + "@s.whatsapp.net", asset)
						time.sleep(1)
					job.sent = True
				elif job.method == "broadcast_Group_Image":
					asset = self._getAsset(job.args)
					self.sendImage(job.targets, asset)
					job.sent = True
				elif job.method == "broadcast_Group_Video":
					asset = self._getAsset(job.args)
					self.sendVideo(job.targets, asset)
					job.sent = True
				elif job.method == "typing_send":
					self.methodsInterface.call("typing_send", ("%s@s.whatsapp.net" %job.targets,))
					job.sent = True
					time.sleep(5)
					self.methodsInterface.call("typing_paused", ("%s@s.whatsapp.net" %job.targets,))


				
		
		self.s.commit()	

	def _onSchedule(self,scheduled_time):
		return (scheduled_time is None or datetime.now() > self.utc_to_local(scheduled_time))

	def _getAsset(self, args):
		args = args.encode('utf8').split(",")
		asset_id = args[0]
		return self.s.query(Asset).get(asset_id)

	def onUploadRequestDuplicate(self,_hash, url):
		logging.info("Upload duplicate")
		logging.info("The url is %s" %url)
		logging.info("The hash is %s" %_hash)	

		asset = self.s.query(Asset).filter_by(asset_hash=_hash).first()
		print "Asset id %s" %asset.mms_url
		asset.mms_url = url
		self.s.commit()

		put_url = self.url + "/assets/%s" %asset.id
		headers = {'Content-type': 'application/json', 'Accept': 'application/json'}
		data = { "asset" : { "mms_url": url } }

		r = requests.patch(put_url, data=json.dumps(data), headers=headers)		

	def utc_to_local(self,utc_dt):
		# get integer timestamp to avoid precision lost
		timestamp = calendar.timegm(utc_dt.timetuple())
		local_dt = datetime.fromtimestamp(timestamp)
		assert utc_dt.resolution >= timedelta(microseconds=1)
		return local_dt.replace(microsecond=utc_dt.microsecond)

	def onUploadRequestSuccess(self, _hash, url, removeFrom):
		logging.info("Upload Request success")
		logging.info("The url is %s" %url)
		logging.info("The hash is %s" %_hash)
		asset = self.s.query(Asset).filter_by(asset_hash=_hash).first()
		asset.mms_url = url
		self.s.commit()

		# path = "tmp/" + asset.file_file_name + "_%s" %asset.id 
		# path = "tmp/_%s"%asset.id + asset.file_file_name
		path = self.getImageFile(asset)

		logging.info("To upload %s" %path)
		logging.info("To %s" %self.username)

		MU = MediaUploader(self.username + "@s.whatsapp.net", self.username + "@s.whatsapp.net", self.onUploadSucccess, self.onUploadError, self.onUploadProgress)
		MU.upload(path, url, asset.id)

	def onUploadSucccess(self, url, _id):
		logging.info("Upload success!")
		logging.info("Url %s" %url)
		if _id is not None:
			asset = self.s.query(Asset).get(_id)
			asset.mms_url = url
			self.s.commit()
		

	def onUploadError(self):
		logging.info("Error with upload")

	# def onUploadRequestFailed()

	def onUploadProgress(self, progress):
		logging.info("Upload Progress")

	def requestMediaUrl(self, url, asset, preview):
		logging.info("Requesting Url: %s" %url)	
		mtype = asset.asset_type.lower()
		sha1 = hashlib.sha256()

		if not url.startswith("http"):
			url = os.environ['URL'] + url

		if not preview.startswith("http"):
			preview = os.environ['URL'] + preview
		
		file_name = self.getImageFile(asset)
		fp = open(file_name,'wb')
		fp.write(requests.get(url).content)
		fp.close()


		tb_path = self.getImageThumbnailFile(asset)
		tb = open(tb_path, 'wb')
		tb.write(requests.get(preview).content)
		tb.close()


		fp = open(file_name, 'rb')
		try:
			sha1.update(fp.read())
			hsh = base64.b64encode(sha1.digest())

			asset.asset_hash = hsh
			self.s.commit()

			self.methodsInterface.call("media_requestUpload", (hsh, mtype, os.path.getsize(file_name)))
		finally:
			fp.close()  

	def getImageFile(self, asset):
		if asset.asset_type == "Image":
			path = "_%s"%asset.id + asset.file_file_name
			file_name = "tmp/%s" %path
			return file_name
		else:
			path = "_%s"%asset.id + asset.video_file_name
			file_name = "tmp/%s" %path
			return file_name

	def getImageThumbnailFile(self, asset):
		if asset.asset_type == "Image":
			path = "_%s"%asset.id + "_thumb_" + asset.file_file_name
			file_name = "tmp/%s" %path
			return file_name		
		else:
			path = "_%s"%asset.id + "_thumb_" + asset.video_file_name
			file_name = "tmp/%s" %path
			return file_name	

	def sendVideo(self, target, asset):
		f = open(self.getImageThumbnailFile(asset), 'r')
		stream = base64.b64encode(f.read())
		f.close()
		self.methodsInterface.call("message_videoSend",(target,asset.mms_url,"Video", str(os.path.getsize(self.getImageThumbnailFile(asset))), stream))


	def sendImage(self, target, asset):
		f = open(self.getImageThumbnailFile(asset), 'r')
		stream = base64.b64encode(f.read())
		f.close()    	
		self.methodsInterface.call("message_imageSend",(target,asset.mms_url,"Image", str(os.path.getsize(self.getImageThumbnailFile(asset))), stream))


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

		# self.methodsInterface.call("profile_setPicture", (logo_url,))
		self.methodsInterface.call("profile_setStatus", (status,))
        

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
		pull_pic = os.environ['PULL_STATUS_PIC']
		if pull_pic == "true":
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
		data = { "message" : { 'url' : url, 'message_type' : 'Image' , 'phone_number' : phone_number, "whatsapp_message_id" : messageId, 'name' : '' } }
		r = requests.post(post_url, data=json.dumps(data), headers=headers)

		if wantsReceipt and self.sendReceipts:
			self.methodsInterface.call("message_ack", (jid, messageId))

		self.checkProfilePic(jid)

	def onVideoReceived(self, messageId, jid, mediaPreview, mediaUrl, mediaSize, wantsReceipt, isBroadcast):
		logging.info("Video Received %s" %messageId)
		logging.info("From %s" %jid)
		logging.info("url: %s" %mediaUrl)

		post_url = self.url + "/upload"
		phone_number = jid.split("@")[0]
		headers = {'Content-type': 'application/json', 'Accept': 'application/json'}
		data = { "message" : { 'url' : mediaUrl, 'message_type' : 'Video', 'phone_number' : phone_number, "whatsapp_message_id" : messageId, 'name' : '' } }

		# Send a receipt regardless of whether it was a successful upload
		if wantsReceipt and self.sendReceipts:
			self.methodsInterface.call("message_ack", (jid, messageId))
		r = requests.post(post_url, data=json.dumps(data), headers=headers)


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
