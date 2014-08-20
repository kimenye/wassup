from sqlalchemy import create_engine
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy import Column, Integer, String, Boolean, DateTime, desc
from sqlalchemy.orm import sessionmaker
from Yowsup.connectionmanager import YowsupConnectionManager
from Yowsup.Common.utilities import Utilities
from Yowsup.Media.uploader import MediaUploader
import os, json, base64, time, requests, hashlib, datetime
import logging
import vobject
import thread
from threading import Thread

import calendar
from datetime import datetime, timedelta
from pubnub import Pubnub

Base = declarative_base()
logging.basicConfig(filename='logs/production.log',level=logging.DEBUG, format='%(asctime)s %(message)s')
# logging.getLogger('sqlalchemy.engine').setLevel(logging.INFO)

class Message(Base):
	__tablename__ = 'messages'
	id = Column(Integer, primary_key=True)
	received = Column(Boolean())
	receipt_timestamp = Column(DateTime())

	def __init__(self, received):
		self.received = received

class Account(Base):
	__tablename__ = 'accounts'
	id = Column(Integer, primary_key=True)
	whatsapp_password = Column(String(255))
	auth_token = Column(String(255))
	phone_number = Column(String(255))
	setup = Column(Boolean())
	off_line = Column(Boolean())
	name = Column(String(255))


class Asset(Base):
	__tablename__ = 'assets'
	id = Column(Integer, primary_key=True)
	name = Column(String(255))
	asset_hash = Column(String())
	file_file_name = Column(String(255))
	video_file_name = Column(String(255))
	video_file_size = Column(String(255))
	mms_url = Column(String(255))
	asset_type = Column(String(255))
	file_file_size = Column(Integer)
	audio_file_name = Column(String(255))
	audio_file_size = Column(Integer)

	def __init__(self, asset_hash, mms_url):
		self.asset_hash = asset_hash
		self.mms_url = mms_url

class Job(Base):
	__tablename__ = 'job_logs'
	id = Column(Integer, primary_key=True)

	method = Column(String(255))
	targets = Column(String(255))
	args = Column(String())
	sent = Column(Boolean())
	scheduled_time = Column(DateTime())
	simulate = Column(Boolean())
	whatsapp_message_id = Column(String(255))
	received = Column(String(255))
	receipt_timestamp = Column(DateTime())
	message_id = Column(Integer)
	broadcast_part_id = Column(Integer)
	account_id = Column(Integer)
	runs = Column(Integer)
	next_job_id = Column(Integer)
	asset_id = Column(Integer)
	off_line = Column(Boolean())

	def __init__(self, method, targets, sent, args, scheduled_time):
		self.method = method
		self.targets = targets
		self.sent = sent
		self.args = args
		self.scheduled_time = scheduled_time

class BroadcastPart(Base):
	__tablename__ = 'broadcast_parts'
	id = Column(Integer, primary_key=True)
	whatsapp_id = Column(String(255))

class Server(Thread):
	def __init__(self, url, keepAlive = False, sendReceipts = False):
		super(Server, self).__init__()
		self.sendReceipts = sendReceipts
		self.keepAlive = keepAlive
		self.db = create_engine(url, echo=False, pool_size=10, pool_timeout=600,pool_recycle=300)

		self.Session = sessionmaker(bind=self.db)
		self.s = self.Session()
		self.job = None

		self.pubnub = Pubnub(os.environ['PUB_KEY'], os.environ['SUB_KEY'], None, False)

		self.timeout = int(os.getenv('TIMEOUT', 3600))
		connectionManager = YowsupConnectionManager(self.timeout)

		connectionManager.setAutoPong(keepAlive)		

		self.signalsInterface = connectionManager.getSignalsInterface()
		self.methodsInterface = connectionManager.getMethodsInterface()
		
		self.signalsInterface.registerListener("message_received", self.onMessageReceived)
		self.signalsInterface.registerListener("group_messageReceived", self.onGroupMessageReceived)
		self.signalsInterface.registerListener("image_received", self.onImageReceived)
		self.signalsInterface.registerListener("video_received", self.onVideoReceived)
		self.signalsInterface.registerListener("audio_received", self.onAudioReceived)
		self.signalsInterface.registerListener("vcard_received", self.onVCardReceived)
		self.signalsInterface.registerListener("location_received", self.onLocationReceived)
		self.signalsInterface.registerListener("receipt_messageSent", self.onReceiptMessageSent)
		self.signalsInterface.registerListener("receipt_messageDelivered", self.onReceiptMessageDelivered)		
		
		self.signalsInterface.registerListener("auth_success", self.onAuthSuccess)
		self.signalsInterface.registerListener("auth_fail", self.onAuthFailed)
		self.signalsInterface.registerListener("disconnected", self.onDisconnected)

		self.signalsInterface.registerListener("contact_gotProfilePicture", self.onGotProfilePicture)
		self.signalsInterface.registerListener("profile_setStatusSuccess", self.onSetStatusSuccess)
		self.signalsInterface.registerListener("group_createSuccess", self.onGroupCreateSuccess)
		self.signalsInterface.registerListener("group_createFail", self.onGroupCreateFail)
		self.signalsInterface.registerListener("group_gotInfo", self.onGroupGotInfo)
		self.signalsInterface.registerListener("group_addParticipantsSuccess", self.onGroupAddParticipantsSuccess)
		self.signalsInterface.registerListener("group_removeParticipantsSuccess", self.onGroupRemoveParticipantsSuccess)

		self.signalsInterface.registerListener("group_subjectReceived", self.onGroupSubjectReceived)
		self.signalsInterface.registerListener("notification_removedFromGroup", self.onNotificationRemovedFromGroup)
		self.signalsInterface.registerListener("notification_groupParticipantAdded", self.onNotificationGroupParticipantAdded)
		self.signalsInterface.registerListener("group_gotParticipants", self.onGotGroupParticipants)

		self.signalsInterface.registerListener("media_uploadRequestSuccess", self.onUploadRequestSuccess)
		# self.signalsInterface.registerListener("media_uploadRequestFailed", self.onUploadRequestFailed)
		self.signalsInterface.registerListener("media_uploadRequestDuplicate", self.onUploadRequestDuplicate)
		self.signalsInterface.registerListener("presence_available", self.onPresenceAvailable)
		self.signalsInterface.registerListener("presence_unavailable", self.onPresenceUnavailable)
		
		self.cm = connectionManager
		self.url = os.environ['URL']

		self.post_headers = {'Content-type': 'application/json', 'Accept': 'application/json'}		
		self.done = False

	def onUploadFailed(self, hash):
		print "Upload failed"
	
	def login(self, username, password, id):
		# logging.info("In Login : %s" %username)

		self.username = username
		self.password = password
		self.account_id = id
		self.use_realtime = os.environ['USE_REALTIME'] == "true"
		self.pubnub_channel = os.environ['PUB_CHANNEL'] + "_%s" %self.username
		
		self._d("Logging in")
		self.methodsInterface.call("auth_login", (self.username, self.password))
		self.methodsInterface.call("presence_sendAvailable", ())
		
	def run(self):
		while not self.done:
			self.seekJobs()
			time.sleep(2)
	
	def seekJobs(self):
		jobs = self.s.query(Job).filter_by(sent=False, account_id=self.account_id).all()
		if len(jobs) > 0:
			logging.info("Pending Jobs %s" % len(jobs))

		acc = self._getAccount()
		logging.info("Found the account. Offline status is %s" %acc.off_line)
		
		for job in jobs:									
			if self._onSchedule(job.scheduled_time) and acc.off_line == False:
				logging.info("Calling %s" %job.method)
				job.runs += 1

				if job.off_line == True:
					account = self._getAccount()
					account.off_line = True										

					job.sent = True					
					self.job = job
					
					self.s.commit()
					self.cm.disconnect("Disconnecting for broadcast image job")						
				else:
					if job.method == "group_create":
						res = self.methodsInterface.call(job.method, (job.args,))
						job.sent = True
					elif job.method == "group_end":
						res = self.methodsInterface.call(job.method, (job.args,))
						job.sent = True
					elif job.method == "group_addParticipants":
						params = job.args.split(",")
						self.methodsInterface.call(job.method, (params[0], [params[1] + "@s.whatsapp.net"],))
						job.sent = True
					elif job.method == "group_removeParticipants":
						params = job.args.split(",")
						self.methodsInterface.call(job.method, (params[0], [params[1] + "@s.whatsapp.net"],))
						job.sent = True
					elif job.method == "group_getParticipants":				
						self.methodsInterface.call('group_getParticipants', (job.targets,))
						job.sent = True
					elif job.method == "contact_getProfilePicture":
						self.methodsInterface.call("contact_getProfilePicture", (job.args,))
						job.sent = True
					elif job.method == "sendMessage":
						
						if job.simulate == True:
							self.methodsInterface.call("typing_send", (job.targets,))
							self.methodsInterface.call("typing_paused", (job.targets,))

						job.whatsapp_message_id = self.sendMessage(job.targets, job.args)
						job.sent = True
					elif job.method == "broadcast_Text":
						jids = job.targets.split(",")
						targets = []
						for jid in jids:
							targets.append("%s@s.whatsapp.net" %jid)
						job.whatsapp_message_id = self.methodsInterface.call("message_broadcast", (targets, job.args, ))

						job.sent = True
					elif job.method == "uploadMedia":
						args = job.args.split(",")
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
					elif job.method == "uploadAudio":
						args = job.args.split(",")
						asset_id = args[0]
						url = args[1]
						logging.info("Asset Id: %s" %args[0])
						asset = self.s.query(Asset).get(asset_id)
						logging.info("File name: %s" %asset.audio_file_name)

						if asset.mms_url == None:
							self.requestMediaUrl(url, asset, None)
						job.sent = True
					elif job.method == "sendImage":
						asset = self._getAsset(job.args)					
						job.whatsapp_message_id = self.sendImage(job.targets + "@s.whatsapp.net", asset)
						job.sent = True
					elif job.method == "sendContact":
						jids = job.targets.split(",")
						for jid in jids:
							self.sendVCard(jid, job.args)
						job.sent = True
					elif job.method == "sendAudio":
						asset = self._getAsset(job.args)
						jids = job.targets.split(",")
						for jid in jids:
							self.sendAudio(jid + "@s.whatsapp.net", asset)
						job.sent = True
					elif job.method == "broadcast_Video":
						args = job.args.split(",")
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
						job.sent = True
					elif job.method == "setProfilePicture":
						job.sent = True
						self.setProfilePicture(job)
					elif job.method == "disconnect":
						account = self.s.query(Account).get(self.account_id)
						account.off_line = True

						self.cm.disconnect("Disconnecting for other jobs")

						job.sent = True
		if acc.off_line == True and self.job == None:
			logging.info("Time to reconnect")
			
			acc = self._getAccount()						
			acc.off_line = False
			self.s.commit()

			self.methodsInterface.call("auth_login", (self.username, self.password))
			self.methodsInterface.call("presence_sendAvailable", ())
			

		self.s.commit()	

	def setProfilePicture(self, job):
		logging.info("About to set the profile picture")
		
		# first disconnect the server
		account = self.s.query(Account).get(self.account_id)
		account.setup = False
		self.s.commit()

		logging.info("About to sleep for 5 seconds")
		time.sleep(5)

		logging.info("Finished setting of the profile")

	def _d(self, message):
		logging.info("%s - %s" %(self.username, message))

	def _onSchedule(self,scheduled_time):
		return (scheduled_time is None or datetime.now() > self.utc_to_local(scheduled_time))

	def _getAccount(self):
		return self.s.query(Account).get(self.account_id)

	def _getAsset(self, args):
		args = args.split(",")
		asset_id = args[0]
		return self.s.query(Asset).get(asset_id)

	def _sendRealtime(self, message):
		if self.use_realtime:
			self.pubnub.publish({
				'channel' : self.pubnub_channel,
				'account' : self.username,
				'message' : message
			})

	def onReceiptMessageDelivered(self, jid, messageId):
		logging.info("Delivered %s" %messageId)
		logging.info("From %s" %jid)
		# self.s.query(Job).filter_by(sent=False).all()

		session = self.Session()
		job = session.query(Job).filter_by(sent=True, whatsapp_message_id=messageId).scalar()
		if job is not None:
			job.received = True
			session.commit()

			if job.method == "sendMessage":
				m = session.query(Message).get(job.message_id)
				logging.info("Looking for message with id to send a receipt %s" %job.message_id)
				if m is not None:
					m.received = True
					m.receipt_timestamp = datetime.now()
					session.commit()
					
					data = { "receipt" : { "message_id" : m.id } }
					self._post("/receipt", data)

					self._sendRealtime({
						'type' : 'receipt',
						'message_id': m.id
					})
			else:
				data = { "receipt" : { "message_id" : messageId, "phone_number" : jid.split("@")[0] } }
				self._post("/broadcast_receipt", data)				

				

	def onReceiptMessageSent(self, jid, messageId):
		logging.info("Sent %s" %messageId)
		logging.info("To %s" %jid)

	def onPresenceAvailable(self, jid):
		logging.info("JID available %s" %jid)

	def onPresenceUnavailable(self, jid, last):
		logging.info("JID unavilable %s" %jid)
		logging.info("Last seen is %s" %last)

		if last == "deny":
			logging.info("this number %s has blocked you" %jid)


	def onUploadRequestDuplicate(self,_hash, url):
		logging.info("Upload duplicate")
		logging.info("The url is %s" %url)
		logging.info("The hash is %s" %_hash)	

		asset = self.s.query(Asset).filter_by(asset_hash=_hash).order_by(desc(Asset.id)).first()
		logging.info("Asset id %s" %asset.mms_url)
		asset.mms_url = url
		self.s.commit()

		self._sendAsset(asset.id)

		put_url = "/assets/%s" %asset.id		
		data = { "asset" : { "mms_url": url } }
		self._patch(put_url, data)		

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

		path = self.getImageFile(asset)

		logging.info("To upload %s" %path)
		logging.info("To %s" %self.username)

		MU = MediaUploader(self.username + "@s.whatsapp.net", self.username + "@s.whatsapp.net", self.onUploadSucccess, self.onUploadError, self.onUploadProgress)
		
		logging.info("Path %s" %path)
		logging.info("Url %s" %url)
		
		MU.upload(path, url, asset.id)

	def _sendAsset(self, asset_id):
		logging.info("Sending an uploaded asset %s" %asset_id)
		upload_jobs = self.s.query(Job).filter_by(asset_id = asset_id).all()
		logging.info("Found %s jobs tied to this asset" %len(upload_jobs))
		for job in upload_jobs:
			logging.info("Found job with sent %s" %job.sent)
			if job.next_job_id is not None:
				next_job = self.s.query(Job).get(job.next_job_id)

				logging.info("Next job %s" %next_job.id)
				logging.info("Next job sent? %s" %next_job.sent)
				logging.info("Next job runs? %s" %next_job.runs)
				if next_job.method == "sendImage" and next_job.sent == True and next_job.runs == 0:
					next_job.sent = False
		self.s.commit()

	def onUploadSucccess(self, url, _id):
		logging.info("Upload success!")
		logging.info("Url %s" %url)
		if _id is not None:
			asset = self.s.query(Asset).get(_id)
			asset.mms_url = url

			self.s.commit()
			self._sendAsset(asset.id)
		
	def onUploadError(self):
		logging.info("Error with upload")

	def onUploadProgress(self, progress):
		logging.info("Upload Progress")

	def requestMediaUrl(self, url, asset, preview):
		logging.info("Requesting Url: %s" %url)	
		mtype = asset.asset_type.lower()
		sha1 = hashlib.sha256()

		if not url.startswith("http"):
			url = os.environ['URL'] + url

		if preview is not None and not preview.startswith("http"):
			preview = os.environ['URL'] + preview
		
		file_name = self.getImageFile(asset)
		fp = open(file_name,'wb')
		fp.write(requests.get(url).content)
		fp.close()

		if asset.asset_type != "Audio":
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
			path = "_%s"%asset.id + asset.name
			file_name = "tmp/%s" %path
			return file_name
		elif asset.asset_type == "Video":
			path = "_%s"%asset.id + asset.video_file_name
			file_name = "tmp/%s" %path
			return file_name
		elif asset.asset_type == "Audio":
			path = "_%s"%asset.id + asset.audio_file_name
			file_name = "tmp/%s" %path
			return file_name

	def getImageThumbnailFile(self, asset):
		if asset.asset_type == "Image":
			path = "_%s"%asset.id + "_thumb_" + asset.name
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

	def sendVCard(self, target, args):
		account = self.s.query(Account).get(self.account_id)

		card = vobject.vCard()
		params = args.split(",")
		family_name = params[0]
		given_name = params[1]
		name = family_name + " " + given_name

		card.add('fn')
		card.fn.value = name

		card.add('n')
		card.n.value = vobject.vcard.Name(family=family_name, given=given_name)

		logging.info("First name %s" %family_name)
		logging.info("Last name %s" %given_name)

		api_url = self.url  + "/api/v1/base/status?token=%s" %account.auth_token
		headers = {'Content-type': 'application/json', 'Accept': 'application/json'}
		r = requests.get(api_url, headers=headers)
		response = r.json()

		
		del params[0]
		del params[0]		

		for number in params:
			tel = number.split(":")
			num = card.add('tel')
			num.value = tel[1]
			num.type_param = tel[0]

		logging.info("Response is %s" %response)
		if response['profile_pic'] != self.url + '/blank-profile.png':			
			tb = open('tmp/profile_thumb.jpg', 'wb')
			tb.write(requests.get(response['profile_pic']).content)
			tb.close()

			f = open('tmp/profile_thumb.jpg', 'r')
			stream = base64.b64encode(f.read())
			f.close()

			card.add('photo')
			card.photo.value = stream
			card.photo.type_param = "JPEG"
			# card.photo.encoding_param = "b"


		logging.info("Data %s" %card.serialize())
		self.methodsInterface.call("message_vcardSend", (target, card.serialize(), name))

	def sendAudio(self, target, asset):
		logging.info("Sending %s" %asset.mms_url)
		logging.info("To %s" %target)
		logging.info("Name %s" %asset.name)
		logging.info("Size %s" %asset.audio_file_size)
		self.methodsInterface.call("message_audioSend", (target, asset.mms_url, asset.name, str(asset.audio_file_size)))

	def sendImage(self, target, asset):
		f = open(self.getImageThumbnailFile(asset), 'r')
		stream = base64.b64encode(f.read())
		f.close()    	
		logging.info("Target %s" %target)
		logging.info("URL %s" %asset.mms_url)
		logging.info("URL %s" %asset.asset_hash)
		rst = self.methodsInterface.call("message_imageSend",(target,asset.mms_url,"Image", str(os.path.getsize(self.getImageThumbnailFile(asset))), stream))
		logging.info("Result of send image %s" %rst)
		return rst

	def sendMessage(self, target, text):
		logging.info("Message %s" %text)
		jid = target
		logging.info("To %s" %jid)
		rst = self.methodsInterface.call("message_send", (jid, text))	
		return rst

	def onGroupSubjectReceived(self,messageId,jid,author,subject,timestamp,receiptRequested):
		logging.info("Group subject received")
		if receiptRequested and self.sendReceipts:
			self.methodsInterface.call("message_ack", (jid, messageId))

		data = { "name" : subject, "group_type" : "External", "jid" : jid }
		self._post("/groups", data)
		logging.info("Updated the group")

	def onGroupAddParticipantsSuccess(self, groupJid, jid):
		logging.info("Added participant %s" %jid)
		# check the profile pic
		self.checkProfilePic(jid[0])

	def onGroupRemoveParticipantsSuccess(self, groupJid, jid):
		logging.info("Removed participant %s" %jid)

	def onNotificationGroupParticipantAdded(self, groupJid, jid):
		logging.info("Group participant added %s" %jid)		
		data = { "groupJid" : groupJid, "phone_number": jid.split("@")[0] }
				
		self._post("/groups/add_member", data)

	def onNotificationRemovedFromGroup(self, groupJid,jid):
		logging.info("You were removed from the group %s" %groupJid)

		put_url = self.url  + "/groups/remove_member"
		data = { "groupJid" : groupJid, 'phone_number': jid.split("@")[0] }		
		self._post("/groups/remove_member", data)
		logging.info("Updated the group")

	def onGotGroupParticipants(self, groupJid, jids):
		logging.info("Got group participants")

		data = { "groupJid" : groupJid, "jids" : jids }
		self._post("/groups/update_membership", data)

	def onGroupCreateSuccess(self, groupJid):
		logging.info("Created with id %s" %groupJid)
		self.methodsInterface.call("group_getInfo", (groupJid,))

	def onGroupGotInfo(self,jid,owner,subject,subjectOwner,subjectTimestamp,creationTimestamp):
		logging.info("Group info %s - %s" %(jid, subject))
		
		data = { "name" : subject, "jid" : jid }
		self._post("/update_group", data)
		logging.info("Updated the group")

	def onGroupCreateFail(self, errorCode):
		logging.info("Error creating a group %s" %errorCode)

	def onSetStatusSuccess(self,jid,messageId):
		logging.info("Set the profile message for %s - %s" %(jid, messageId))

	def onAuthSuccess(self, username):
		logging.info("We are authenticated")
		self.methodsInterface.call("ready")
		self.setStatus(1, "Authenticated")
        
	def setStatus(self, status, message="Status message"):
		logging.info("Setting status %s" %status)
		data = { "status" : status, "message" : message }
		self._post("/status", data)

	def onAuthFailed(self, username, err):
		logging.info("Authentication failed for %s" %username)
		
	def onDisconnected(self, reason):
		logging.info("Disconnected! Reason: %s" %reason)
		self.setStatus(0, "Got disconnected")
		# self.done = True
		account = self.s.query(Account).get(self.account_id)
		if account.off_line == False:
			logging.info('About to log in again with %s and %s' %(self.username, self.password))
			self.login(self.username, self.password, self.account_id)
		elif account.off_line == True and self.job is not None:			
			# call the current job
			job = self.job
			url = os.environ['API_URL']
			headers = {'Content-type': 'application/json', 'Accept': 'application/json'}
			if job.method == "profile_setStatus":				
				args = { "nickname" : account.name, "method" : "profile_setStatus", "password" : account.whatsapp_password, "status" : job.args, "jid" : account.phone_number }
				r = requests.post(url, data=args)
				print r.text
			elif job.method == "broadcast_Image":
				image_url = job.args.split(",")[1]
				full_url = os.environ['URL'] + image_url
				print full_url				
				args = { "nickname" : account.name, "targets" : job.targets, "method" : job.method , "password" : account.whatsapp_password , "image" : full_url, "jid" : account.phone_number, "externalId" : job.id }

				r = requests.post(url, data=args)
				print r.text

			self.job = None
			# account.off_line = False
			self.s.commit()


	def onGotProfilePicture(self, jid, imageId, filePath):
		logging.info('Got profile picture')
		url = self.url + "/contacts/" + jid.split("@")[0] + "/upload?account=" + self.username
		files = {'file': open(filePath, 'rb')}
		r = requests.post(url, files=files)

	def checkProfilePic(self, jid):
		pull_pic = os.environ['PULL_STATUS_PIC']
		if pull_pic == "true":
			phone_number = jid.split("@")[0]
			get_url = self.url + "/profile?phone_number=" + phone_number + "&account=" + self.username
			headers = {'Content-type': 'application/json', 'Accept': 'application/json'}
			r = requests.get(get_url, headers=headers)
			response = r.json()
			
			if response['profile_url'] == '/missing.jpg':		
				self.methodsInterface.call("contact_getProfilePicture", (jid,))	

	def onGroupMessageReceived(self, messageId, jid, author, content, timestamp, wantsReceipt, pushName):
		logging.info('Received a message on the group %s' %content)
		logging.info('JID %s - %s - %s' %(jid, pushName, author))

		if wantsReceipt and self.sendReceipts:
			self.methodsInterface.call("message_ack", (jid, messageId))
		
		data = { "message" : { "text" : content, "group_jid" : jid, "message_type" : "Text", "whatsapp_message_id" : messageId, "name" : pushName, "jid" : author }}
		self._post("/receive_broadcast", data)

		self.checkProfilePic(author)
		self._sendRealtime({
			'type' : 'text',
			'phone_number' : jid,
			'text' : content,
			'name' : pushName
		})

	def _patch(self,url,data):
		data.update(account = self.username)
		headers = {'Content-type': 'application/json', 'Accept': 'application/json'}
		r = requests.patch(self.url + url, data=json.dumps(data), headers=headers)

	def _post(self, url, data):
		data.update(account = self.username)
		headers = {'Content-type': 'application/json', 'Accept': 'application/json'}
		r = requests.post(self.url + url, data=json.dumps(data), headers=headers)

	def onMessageReceived(self, messageId, jid, messageContent, timestamp, wantsReceipt, pushName, isBroadCast):
		logging.info('Message Received %s' %messageContent)
		phone_number = jid.split("@")[0]

		if wantsReceipt and self.sendReceipts:
			self.methodsInterface.call("message_ack", (jid, messageId))
		
		data = { "message" : { "text" : messageContent, "phone_number" : phone_number, "message_type" : "Text", "whatsapp_message_id" : messageId, "name" : pushName  }}
		self._post("/messages", data)

		self._sendRealtime({
			'type' : 'text',
			'phone_number' : phone_number,
			'text' : messageContent,
			'name' : pushName
		})
		
		self.checkProfilePic(jid)

	def onLocationReceived(self, messageId, jid, name, preview, latitude, longitude, wantsReceipt, isBroadcast):
		logging.info('Location Received')	
		phone_number = jid.split("@")[0]

		if wantsReceipt and self.sendReceipts:
			self.methodsInterface.call("message_ack", (jid, messageId))

		data = { "location" : { 'latitude' : latitude, 'longitude': longitude, 'preview' : preview, 'phone_number' : phone_number, "whatsapp_message_id" : messageId, 'name' : name } }
		self._post("/locations", data)
		

	def onImageReceived(self, messageId, jid, preview, url, size, wantsReceipt, isBroadCast):	
		logging.info('Image Received')	
		phone_number = jid.split("@")[0]

		data = { "message" : { 'url' : url, 'message_type' : 'Image' , 'phone_number' : phone_number, "whatsapp_message_id" : messageId, 'name' : '' } }
		self._post("/upload", data)

		if wantsReceipt and self.sendReceipts:
			self.methodsInterface.call("message_ack", (jid, messageId))

		# channel = os.environ['PUB_CHANNEL'] + "_%s" %self.username
		# self.pubnub.publish({
		# 	'channel' : channel,
		# 	'message' : {
		# 		'type' : 'image',
		# 		'phone_number' : phone_number,
		# 		'url' : url,
		# 		'name' : ''
		# 	}
		# })
		self._sendRealtime({
			'type' : 'image',
			'phone_number' : phone_number,
			'url' : url,
			'name' : ''
		})

		self.checkProfilePic(jid)
	
	def onVCardReceived(self, messageId, jid, name, data, wantsReceipt, isBroadcast):				
		vcard = vobject.readOne( data )
		vcard.prettyPrint()

		data = { "vcard" : { 'phone_number' : jid.split("@")[0], 'whatsapp_message_id' : messageId, 'data' : vcard.serialize() }}		
		self._post("/vcards", data)

		if wantsReceipt and self.sendReceipts:
			self.methodsInterface.call("message_ack", (jid, messageId))

	def onAudioReceived(self, messageId, jid, url, size, wantsReceipt, isBroadcast):
		logging.info("Audio received %s" %messageId)
		logging.info("url: %s" %url)
		phone_number = jid.split("@")[0]

		data = { "message" : { 'url' : url,  'message_type': 'Audio', 'phone_number' : phone_number, "whatsapp_message_id" : messageId, 'name' : '' } }
		self._post("/upload", data)
		
		if wantsReceipt and self.sendReceipts:
			self.methodsInterface.call("message_ack", (jid, messageId))

	def onVideoReceived(self, messageId, jid, mediaPreview, mediaUrl, mediaSize, wantsReceipt, isBroadcast):
		logging.info("Video Received %s" %messageId)
		logging.info("From %s" %jid)
		logging.info("url: %s" %mediaUrl)

		phone_number = jid.split("@")[0]
		data = { "message" : { 'url' : mediaUrl, 'message_type' : 'Video', 'phone_number' : phone_number, "whatsapp_message_id" : messageId, 'name' : '' } }
		self._post("/upload", data)

		# Send a receipt regardless of whether it was a successful upload
		if wantsReceipt and self.sendReceipts:
			self.methodsInterface.call("message_ack", (jid, messageId))
		r = requests.post(post_url, data=json.dumps(data), headers=headers)

	def onGotProfilePicture(self, jid, imageId, filePath):
		logging.info('Profile picture received')
		url = self.url + "/contacts/" + jid.split("@")[0] + "/upload?account=" + self.username
		files = {'file': open(filePath, 'rb')}
		r = requests.post(url, files=files)


database_url = os.environ['SQLALCHEMY_DATABASE_URI']

man_db = create_engine(database_url, echo=False)
man_Session = sessionmaker(bind=man_db)
man_s = man_Session()

accounts = man_s.query(Account).filter_by(setup=True, off_line=False).all()
if len(accounts) > 0:
	print("Accounts : %s" % len(accounts))

	for account in accounts:
		server = Server(database_url, True, True)		
		server.login(account.phone_number, base64.b64decode(bytes(account.whatsapp_password.encode('utf-8'))), account.id)
		server.start()

# server = Server(database_url,True, True)
# login = os.environ['TEL_NUMBER']
# password = os.environ['PASS']
# password = base64.b64decode(bytes(password.encode('utf-8')))
# server.login(login, password)


