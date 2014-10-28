from sqlalchemy import create_engine
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy import Column, Integer, String, Boolean, DateTime, desc, Float, Text
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
import rollbar
import stathat

Base = declarative_base()
logging.basicConfig(filename='logs/production.log',level=logging.INFO, format='%(asctime)s %(message)s')
rollbar.init(os.environ['ROLLBAR_KEY'], os.environ['ENV'])
# logging.getLogger('sqlalchemy.engine').setLevel(logging.INFO)

class Contact(Base):
	__tablename__ = 'contacts'
	id = Column(Integer, primary_key=True)
	phone_number = Column(String(255))
	account_id = Column(Integer)

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
	url = Column(String(255))
	preview_url = Column(String(255))

	def __init__(self, asset_hash, mms_url):
		self.asset_hash = asset_hash
		self.mms_url = mms_url

class Job(Base):
	__tablename__ = 'job_logs'
	id = Column(Integer, primary_key=True)

	method = Column(String(255))
	targets = Column(String())
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
	pending = Column(Boolean())

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

class Location(Base):
	__tablename__ = 'locations'
	id = Column(Integer, primary_key=True)
	name = Column(String(255))
	latitude = Column(Float())
	longitude = Column(Float())
	preview = Column(Text)

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
		self.signalsInterface.registerListener("group_imageReceived", self.onGroupImageReceived)


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

	def _formatContacts(self, raw):
		contacts = raw.split(",")
		for i, _ in enumerate(contacts):		
			contacts[i] = contacts[i] + "@s.whatsapp.net"
		return contacts

	def _formatContact(self, phone_number):
		return phone_number + "@s.whatsapp.net"
	
	def seekJobs(self):
		jobs = self.s.query(Job).filter_by(sent=False, account_id=self.account_id, pending=False).all()
		if len(jobs) > 0:
			self._d("Pending Jobs %s" % len(jobs))

		acc = self._getAccount()
		self._d("Offline : %s" %acc.off_line, True)
		
		for job in jobs:									
			if self._onSchedule(job.scheduled_time) and acc.off_line == False:
				self._d("Calling %s" %job.method)
				job.runs += 1

				if job.off_line == True:
					account = self._getAccount()
					account.off_line = True										

					job.sent = True					
					self.job = job
					
					self.s.commit()
					self.cm.disconnect("Disconnecting for offline jobs")						
				else:
					if job.method == "group_create":
						res = self.methodsInterface.call(job.method, (job.args,))
						job.sent = True
					elif job.method == "group_end":
						res = self.methodsInterface.call(job.method, (job.args,))
						job.sent = True
					elif job.method == "group_addParticipants":
						self.methodsInterface.call(job.method, (job.targets, self._formatContacts(job.args),))
						job.sent = True
					elif job.method == "group_removeParticipants":
						# params = job.args.split(",")
						self.methodsInterface.call(job.method, (job.targets, self._formatContacts(job.args),))
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
						asset = self.s.query(Asset).get(job.asset_id)

						if asset.mms_url == None:
							self.requestMediaUrl(asset)
						else:
							# find the jobs after this
							next_job = self.s.query(Job).filter_by(id=job.next_job_id, pending=True).first()
							next_job.pending = False
						job.sent = True					
					elif job.method == "sendImage":
						asset = self._getAsset(job.args)		
						targets = job.targets
						if "@" not in targets:
							targets = targets + "@s.whatsapp.net"
						job.whatsapp_message_id = self.sendImage(targets, asset)
						job.sent = True
					elif job.method == "sendVideo":
						asset = self.s.query(Asset).get(job.asset_id)
						job.whatsapp_message_id = self.sendVideo(job.targets, asset)
						job.sent = True
					elif job.method == "sendContact":
						jids = job.targets.split(",")
						for jid in jids:
							self.sendVCard(jid, job.args)
						job.sent = True
					elif job.method == "sendAudio":
						asset = self.s.query(Asset).get(job.asset_id)
						self.sendAudio(job.targets + "@s.whatsapp.net", asset)
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
					elif job.method == "sendLocation":
						location = self.s.query(Location).get(job.args)
						self.sendLocation(job.targets, location)
						job.sent = True					
					elif job.method == "syncGroup":
						self._d("Calling group_getInfo %s" %job.args)
						self.methodsInterface.call("group_getInfo", (job.args,))
						job.sent = True
		if acc.off_line == True and self.job == None:
			self._d("Reconnecting")
			
			acc = self._getAccount()						
			acc.off_line = False
			self.s.commit()

			self.methodsInterface.call("auth_login", (self.username, self.password))
			self.methodsInterface.call("presence_sendAvailable", ())
			

		self.s.commit()		

	def _d(self, message, debug=False):
		if debug == False:
			logging.info("%s - %s" %(self.username, message))
		else:
			logging.debug("%s - %s" %(self.username, message))

	def _onSchedule(self,scheduled_time):
		return (scheduled_time is None or datetime.now() > self.utc_to_local(scheduled_time))

	def _getContact(self,phone_number):
		return self.s.query(Contact).filter_by(account_id = self.account_id, phone_number = phone_number).scalar()

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
		self._d("Delivered %s" %messageId)
		self._d("From %s" %jid)
		# self.s.query(Job).filter_by(sent=False).all()

		session = self.Session()
		job = session.query(Job).filter_by(sent=True, whatsapp_message_id=messageId).scalar()
		if job is not None:
			job.received = True
			session.commit()

			if job.method == "sendMessage" or job.method == "sendImage":
				m = session.query(Message).get(job.message_id)
				self._d("Looking for message with id to send a receipt %s" %job.message_id)
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
		self._d("Sent %s" %messageId)
		self._d("To %s" %jid)

	def onPresenceAvailable(self, jid):
		self._d("JID available %s" %jid)
		phone_number = jid.split("@")[0]
		contact = self._getContact(phone_number)

		if contact is not None:
			url = "/contacts/%s" %contact.id
			self._patch(url, { "contact" : { "last_seen" : str(datetime.now()) } })

	def onPresenceUnavailable(self, jid, last):
		self._d("JID unavilable %s" %jid)
		self._d("Last seen is %s" %last)

		if last == "deny":
			self._d("this number %s has blocked you" %jid)


	def onUploadRequestDuplicate(self,_hash, url):
		self._d("Upload duplicate")
		self._d("The url is %s" %url)
		self._d("The hash is %s" %_hash)	

		asset = self.s.query(Asset).filter_by(asset_hash=_hash).order_by(desc(Asset.id)).first()
		self._d("Asset id %s" %asset.mms_url)
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
		self._d("Upload Request success")
		self._d("The url is %s" %url)
		self._d("The hash is %s" %_hash)
		asset = self.s.query(Asset).filter_by(asset_hash=_hash).order_by(desc(Asset.id)).first()
		asset.mms_url = url
		self.s.commit()

		path = self.getImageFile(asset)

		self._d("To upload %s" %path)
		self._d("To %s" %self.username)

		MU = MediaUploader(self.username + "@s.whatsapp.net", self.username + "@s.whatsapp.net", self.onUploadSucccess, self.onUploadError, self.onUploadProgress)
		
		self._d("Path %s" %path)
		self._d("Url %s" %url)
		
		MU.upload(path, url, asset.id)

	def _sendAsset(self, asset_id):
		self._d("Sending an uploaded asset %s" %asset_id)
		upload_jobs = self.s.query(Job).filter_by(asset_id = asset_id, method="uploadMedia", sent=True).all()
		self._d("Found %s jobs tied to this asset" %len(upload_jobs))
		for job in upload_jobs:
			self._d("Found job with sent %s" %job.sent)			
			self._d("Found job %s - %s " %(job.id, job.next_job_id))
			if job.next_job_id is not None:
				next_job = self.s.query(Job).get(job.next_job_id)
				if next_job.pending == True and next_job.sent == False:
					next_job.pending = False

		self.s.commit()

	def onUploadSucccess(self, url, _id):
		self._d("Upload success!")
		self._d("Url %s" %url)
		if _id is not None:
			asset = self.s.query(Asset).get(_id)
			asset.mms_url = url

			self.s.commit()
			self._sendAsset(asset.id)
		
	def onUploadError(self):
		self._d("Error with upload")

	def onUploadProgress(self, progress):
		self._d("Upload Progress")

	def _link(self, url):
		if url is not None and not url.startswith("http"):
			return os.environ['URL'] + url
		else:
			return url

	def requestMediaUrl(self, asset):
		self._d("About to request for Asset %s" %asset.id)
		self._d("Requesting Url: %s" %asset.url)	
		mtype = asset.asset_type.lower()
		sha1 = hashlib.sha256()

		url = self._link(asset.url)
		preview = self._link(asset.preview_url)
		self._d("Full url : %s" %url)
		self._d("Preview url: %s" %preview)

		
		file_name = self.getImageFile(asset)

		self._d("File name: %s" %file_name)

		fp = open(file_name,'wb')
		fp.write(requests.get(url).content)
		fp.close()

		self._d("Written file to %s" %file_name)

		if asset.asset_type != "Audio":
			tb_path = self.getImageThumbnailFile(asset)			
			tb = open(tb_path, 'wb')
			self._d("Preview URL %s" %preview)
			tb.write(requests.get(preview).content)
			tb.close()
			self._d("Written thumbnail path : %s" %tb_path)


		fp = open(file_name, 'rb')
		try:
			sha1.update(fp.read())
			hsh = base64.b64encode(sha1.digest())

			asset.asset_hash = hsh
			self.s.commit()

			rst = self.methodsInterface.call("media_requestUpload", (hsh, mtype, os.path.getsize(file_name)))
			self._d("Requested media upload for %s" %asset.id)
		finally:
			fp.close()  

	def getImageFile(self, asset):
		if asset.asset_type == "Image":
			path = "_%s"%asset.id + asset.name
			file_name = "tmp/%s" %path
			return file_name
		elif asset.asset_type == "Video":
			path = "_%s"%asset.id + asset.name
			file_name = "tmp/%s.mp4" %path
			self._d("Image filename %s" %file_name)
			return file_name
		elif asset.asset_type == "Audio":
			path = "_%s"%asset.id + asset.name
			file_name = "tmp/%s" %path
			return file_name

	def getImageThumbnailFile(self, asset):
		if asset.asset_type == "Image":
			path = "_%s"%asset.id + "_thumb_" + asset.name
			file_name = "tmp/%s" %path
			return file_name		
		else:
			path = "_%s"%asset.id + "_thumb_" + asset.name
			file_name = "tmp/%s.jpg" %path
			return file_name	

	def sendVideo(self, target, asset):
		self._d("In sendVideo %s" %asset.id)
		thumbnail = self.getImageThumbnailFile(asset)
		self._d("The thumbnail %s" %thumbnail)
		
		f = open(thumbnail, 'r')
		stream = base64.b64encode(f.read())
		f.close()		
		rst = self.methodsInterface.call("message_videoSend",(target,asset.mms_url,"Video", str(os.path.getsize(self.getImageThumbnailFile(asset))), stream))
		self._d("Called video send %s" %rst)
		return rst

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

		self._d("First name %s" %family_name)
		self._d("Last name %s" %given_name)

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

		self._d("Response is %s" %response)
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


		self._d("Data %s" %card.serialize())
		self.methodsInterface.call("message_vcardSend", (target, card.serialize(), name))

	def sendAudio(self, target, asset):
		self._d("Sending %s" %asset.mms_url)
		self._d("To %s" %target)
		self._d("Name %s" %asset.name)
		self._d("Size %s" %asset.audio_file_size)
		rst = self.methodsInterface.call("message_audioSend", (target, asset.mms_url, asset.name, str(asset.audio_file_size)))
		return rst

	def sendImage(self, target, asset):
		f = open(self.getImageThumbnailFile(asset), 'r')
		stream = base64.b64encode(f.read())
		f.close()    	
		self._d("Target %s" %target)
		self._d("URL %s" %asset.mms_url)
		self._d("URL %s" %asset.asset_hash)
		rst = self.methodsInterface.call("message_imageSend",(target,asset.mms_url,"Image", str(os.path.getsize(self.getImageThumbnailFile(asset))), stream))
		self._d("Result of send image %s" %rst)
		return rst

	def sendMessage(self, target, text):
		self._d("Message %s" %text)
		jid = target
		self._d("To %s" %jid)
		rst = self.methodsInterface.call("message_send", (jid, text))	
		return rst

	def sendLocation(self, target, location):
		self._d("Sending location %s,%s to %s" %(str(location.latitude), str(location.longitude), target))
		jid = self._formatContact(target)
		# message_locationSend(str jid,float latitude,float longitude,str preview)

		rst = self.methodsInterface.call("message_locationSend", (jid, str(location.latitude), str(location.longitude), location.preview))
		return rst


	def onGroupSubjectReceived(self,messageId,jid,author,subject,timestamp,receiptRequested):
		self._d("Group subject received")
		if receiptRequested and self.sendReceipts:
			self.methodsInterface.call("message_ack", (jid, messageId))

		data = { "name" : subject, "group_type" : "External", "jid" : jid }
		self._post("/groups", data)
		self._d("Updated the group")

	def onGroupAddParticipantsSuccess(self, groupJid, jid):
		self._d("Added participant %s" %jid)
		# check the profile pic
		self.checkProfilePic(jid[0])
		self._post("/update_membership", { "groupJid" : groupJid, "type": "add", "contact" : jid.split("@")[0]})

	def onGroupRemoveParticipantsSuccess(self, groupJid, jid):
		self._d("Removed participant %s" %jid)

	def onNotificationGroupParticipantAdded(self, groupJid, jid):
		self._d("Group participant added %s" %jid)		
		data = { "groupJid" : groupJid, "phone_number": jid.split("@")[0] }
				
		self._post("/groups/add_member", data)

	def onNotificationRemovedFromGroup(self, groupJid,jid):
		self._d("You were removed from the group %s" %groupJid)

		put_url = self.url  + "/groups/remove_member"
		data = { "groupJid" : groupJid, 'phone_number': jid.split("@")[0] }		
		self._post("/groups/remove_member", data)
		self._d("Updated the group")

	def onGotGroupParticipants(self, groupJid, jids):
		self._d("Got group participants")

		data = { "groupJid" : groupJid, "jids" : jids }
		self._post("/groups/update_membership", data)

	def onGroupCreateSuccess(self, groupJid):
		self._d("Created with id %s" %groupJid)
		self.methodsInterface.call("group_getInfo", (groupJid,))

	def onGroupGotInfo(self,jid,owner,subject,subjectOwner,subjectTimestamp,creationTimestamp):
		self._d("Group info %s - %s" %(jid, subject))
		self._d("Group owner %s" %owner)
		self._d("Subject owner %s" %subjectOwner)
		
		data = { "name" : subject, "jid" : jid, "owner": owner, "subjectOwner" : subjectOwner }
		self._post("/update_group", data)
		self._d("Updated the group %s" %subject)

		create_job = self.s.query(Job).filter_by(method="group_create", args=subject).first()
		if create_job.next_job_id is not None:
			next_job = self.s.query(Job).get(create_job.next_job_id)

			self._d("Next job %s" %next_job.id)
			self._d("Next job %s" %next_job.method)
			self._d("Next job sent? %s" %next_job.sent)
			self._d("Next job runs? %s" %next_job.runs)
			
			will_run = (next_job.method == "group_addParticipants" and next_job.sent == True and next_job.runs == 0)
			self._d("Will run? %s" %will_run)
			if next_job.method == "group_addParticipants" and next_job.sent == True and next_job.runs == 0:
				next_job.sent = False
				next_job.targets = jid
				self.s.commit()
			else:
				self.methodsInterface.call('group_getParticipants', (jid,))
		else:
			self.methodsInterface.call('group_getParticipants', (jid,))

	def onGroupCreateFail(self, errorCode):
		self._d("Error creating a group %s" %errorCode)

	def onSetStatusSuccess(self,jid,messageId):
		self._d("Set the profile message for %s - %s" %(jid, messageId))

	def onAuthSuccess(self, username):
		self._d("We are authenticated")
		self.methodsInterface.call("ready")
		self.setStatus(1, "Authenticated")
        
	def setStatus(self, status, message="Status message"):
		self._d("Setting status %s" %status)
		data = { "status" : status, "message" : message }
		self._post("/status", data)

	def onAuthFailed(self, username, err):
		self._d("Authentication failed for %s" %username)
		self._post("/wa_auth_error", {})

	def _postOffline(self, args):
		url = os.environ['API_URL']
		headers = {'Content-type': 'application/json', 'Accept': 'application/json'}
		params = { "nickname" : account.name, "password" : account.whatsapp_password, "jid" : account.phone_number }
		r = requests.post(url, data=dict(params.items() + args.items()))
		return r
		
	def onDisconnected(self, reason):
		self._d("Disconnected! Reason: %s" %reason)
		self.setStatus(0, "Got disconnected")
		
		account = self.s.query(Account).get(self.account_id)
		if account.off_line == False:
			self._d('About to log in again with %s and %s' %(self.username, self.password))
			self._d('Unscheduled outtage for this number')

			rollbar.report_message('Unscheduled outage for %s - %s' %(self.username, account.name), 'warning')
			self._d('Going to wait for a few minutes before trying to log in again')
			time.sleep(15)
			self.login(self.username, self.password, self.account_id)
		elif account.off_line == True and self.job is not None:			
			# call the current job
			job = self.job
			url = os.environ['API_URL']
			headers = {'Content-type': 'application/json', 'Accept': 'application/json'}
			if job.method == "profile_setStatus":				
				args = { "nickname" : account.name, "method" : job.method, "password" : account.whatsapp_password, "status" : job.args, "jid" : account.phone_number }
				r = requests.post(url, data=args)
				self._d(r.text)
			elif job.method == "setProfilePicture":				
				ret = self._postOffline({"method" : job.method, "image_url" : job.args })
				self._d(ret.text)
			elif job.method == "broadcast_Image":
				image_url = job.args.split(",")[1]
				full_url = os.environ['URL'] + image_url
				self._d(full_url)				
				args = { "nickname" : account.name, "targets" : job.targets, "method" : job.method , "password" : account.whatsapp_password , "image" : full_url, "jid" : account.phone_number, "externalId" : job.id }

				r = requests.post(url, data=args)
				self._d(r.text)

			self.job = None
			# account.off_line = False
			self.s.commit()


	def onGotProfilePicture(self, jid, imageId, filePath):
		self._d('Got profile picture')
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
		self._d('Received a message on the group %s' %content)
		self._d('JID %s - %s - %s' %(jid, pushName, author))

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
		self._d('Message Received %s' %messageContent)
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
		self._d('Location Received')	
		phone_number = jid.split("@")[0]

		if wantsReceipt and self.sendReceipts:
			self.methodsInterface.call("message_ack", (jid, messageId))

		data = { "location" : { 'latitude' : latitude, 'longitude': longitude, 'preview' : preview, 'phone_number' : phone_number, "whatsapp_message_id" : messageId, 'name' : name } }
		self._post("/locations", data)
		

	def onImageReceived(self, messageId, jid, preview, url, size, wantsReceipt, isBroadCast):	
		self._d('Image Received')	
		phone_number = jid.split("@")[0]

		data = { "message" : { 'url' : url, 'message_type' : 'Image' , 'phone_number' : phone_number, "whatsapp_message_id" : messageId, 'name' : '' } }
		self._post("/upload", data)

		if wantsReceipt and self.sendReceipts:
			self.methodsInterface.call("message_ack", (jid, messageId))

		self._sendRealtime({
			'type' : 'image',
			'phone_number' : phone_number,
			'url' : url,
			'name' : ''
		})

		self.checkProfilePic(jid)

	def onGroupImageReceived(self, messageId, jid, author, preview, url, size, wantsReceipt):
		phone_number = author.split("@")[0]
		self._d("Group image received %s - %s - %s - %s " %(messageId, jid, phone_number, url))

		if wantsReceipt and self.sendReceipts:
			self.methodsInterface.call("message_ack", (jid, messageId))

		data = { "message" : { 'url' : url, 'message_type' : 'Image', 'phone_number': phone_number , 'group_jid' : jid, "whatsapp_message_id" : messageId, 'name' : '' } }
		self._post("/upload", data)

		self._sendRealtime({
			'type' : 'image',
			'group_jid' : jid,
			'url' : url,
			'from' : phone_number
		})
	
	def onVCardReceived(self, messageId, jid, name, data, wantsReceipt, isBroadcast):				
		vcard = vobject.readOne( data )
		vcard.prettyPrint()

		data = { "vcard" : { 'phone_number' : jid.split("@")[0], 'whatsapp_message_id' : messageId, 'data' : vcard.serialize() }}		
		self._post("/vcards", data)

		if wantsReceipt and self.sendReceipts:
			self.methodsInterface.call("message_ack", (jid, messageId))

	def onAudioReceived(self, messageId, jid, url, size, wantsReceipt, isBroadcast):
		self._d("Audio received %s" %messageId)
		self._d("url: %s" %url)
		phone_number = jid.split("@")[0]

		data = { "message" : { 'url' : url,  'message_type': 'Audio', 'phone_number' : phone_number, "whatsapp_message_id" : messageId, 'name' : '' } }
		self._post("/upload", data)
		
		if wantsReceipt and self.sendReceipts:
			self.methodsInterface.call("message_ack", (jid, messageId))

	def onVideoReceived(self, messageId, jid, mediaPreview, mediaUrl, mediaSize, wantsReceipt, isBroadcast):
		self._d("Video Received %s" %messageId)
		self._d("From %s" %jid)
		self._d("url: %s" %mediaUrl)

		phone_number = jid.split("@")[0]
		data = { "message" : { 'url' : mediaUrl, 'message_type' : 'Video', 'phone_number' : phone_number, "whatsapp_message_id" : messageId, 'name' : '' } }
		self._post("/upload", data)

		# Send a receipt regardless of whether it was a successful upload
		if wantsReceipt and self.sendReceipts:
			self.methodsInterface.call("message_ack", (jid, messageId))
		# r = requests.post(post_url, data=json.dumps(data), headers=headers)

	def onGotProfilePicture(self, jid, imageId, filePath):
		self._d('Profile picture received')
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

	# if os.environ['ENV'] == "development":
	# stathat.ez_value(os.environ['STAT_HAT'], 'online accounts', len(accounts))

	for account in accounts:
		server = Server(database_url, True, True)		
		server.login(account.phone_number, base64.b64decode(bytes(account.whatsapp_password.encode('utf-8'))), account.id)
		server.start()

# server = Server(database_url,True, True)
# login = os.environ['TEL_NUMBER']
# password = os.environ['PASS']
# password = base64.b64decode(bytes(password.encode('utf-8')))
# server.login(login, password)


