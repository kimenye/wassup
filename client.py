from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

import os, base64, requests, json

from Yowsup.connectionmanager import YowsupConnectionManager

from models import Account, Message
from util import get_phone_number


class Client:
	def __init__(self, phone_number, logger):
		self.phone_number = phone_number
		self.logger = logger
		self.url = os.environ['URL']

		self.init_db()

		self.connected = False
		self.connectionManager = YowsupConnectionManager()
		self.connectionManager.setAutoPong(True)		

		self.signalsInterface = self.connectionManager.getSignalsInterface()
		self.methodsInterface = self.connectionManager.getMethodsInterface()

		self._registerListeners()

	def init_db(self):
		url = os.environ['SQLALCHEMY_DATABASE_URI']
		self.db = create_engine(url, echo=False, pool_size=5, pool_timeout=600,pool_recycle=600)
		self.s = sessionmaker(bind=self.db)
		self.session = self.s()

		self.account = self.session.query(Account).filter_by(phone_number = self.phone_number).scalar()
		self.password = self.account.whatsapp_password

	def connect(self):
		self.logger.info("Connecting")		
		self.methodsInterface.call("auth_login", (self.phone_number, base64.b64decode(bytes(self.account.whatsapp_password.encode('utf-8')))))

	def disconnect(self):
		self._setStatus(1, "Disconected!")

	def _registerListeners(self):
		self.signalsInterface.registerListener("auth_success", self._onAuthSuccess)
		self.signalsInterface.registerListener("auth_fail", self._onAuthFailed)
		self.signalsInterface.registerListener("disconnected", self._onDisconnected)
		self.signalsInterface.registerListener("message_received", self._onMessageReceived)
		self.signalsInterface.registerListener("group_messageReceived", self._onGroupMessageReceived)

	# util methods

	def _post(self, url, data):
		data.update(account = self.phone_number)
		headers = {'Content-type': 'application/json', 'Accept': 'application/json'}
		r = requests.post(self.url + url, data=json.dumps(data), headers=headers)

	def _patch(self,url,data):
		data.update(account = self.phone_number)
		headers = {'Content-type': 'application/json', 'Accept': 'application/json'}
		r = requests.patch(self.url + url, data=json.dumps(data), headers=headers)

	def _setStatus(self, status, message="Connected!"):
		self.logger.info("Setting status %s" %status)
		data = { "status" : status, "message" : message }
		self._post("/status", data)

	def _messageExists(self, whatsapp_message_id):
		message = self.session.query(Message).filter_by(whatsapp_message_id=whatsapp_message_id, account_id=self.account.id).scalar()
		return message is not None

	def _d(self, message):
		self.logger.debug(message)

	def _i(self, message):
		self.logger.info(message)

	def _e(self, message):
		self.logger.error(message)

	def _w(self, message):
		self.logger.warning(message)

	# signals

	def _onGroupMessageReceived(self, messageId, jid, author, content, timestamp, wantsReceipt, pushName):
		self._i('Received a message on the group %s' %content)
		self._i('JID %s - %s - %s' %(jid, pushName, author))
		
		if self._messageExists(messageId) == False:

			# Always send receipts
			self.methodsInterface.call("message_ack", (jid, messageId))
			
			# Post to server
			data = { "message" : { "text" : content, "group_jid" : jid, "message_type" : "Text", "whatsapp_message_id" : messageId, "name" : pushName, "jid" : author }}
			self._post("/receive_broadcast", data)

		else:
			self._w("Duplicate group message (%s) %s - %s" %(messageId, self.phone_number, self.account.name))
			rollbar.report_message('Duplicate group message (%s) %s - %s' %(messageId, self.phone_number, self.account.name), 'warning')

	def _onMessageReceived(self, messageId, jid, messageContent, timestamp, wantsReceipt, pushName, isBroadcast):
		self.logger.debug("Received message %s from %s - %s" %(messageContent, get_phone_number(jid), pushName))
		if self._messageExists(messageId) == False:
			
			# Always send receipts
			self.methodsInterface.call("message_ack", (jid, messageId))

			# Post to server
			data = { "message" : { "text" : messageContent, "phone_number" : get_phone_number(jid), "message_type" : "Text", "whatsapp_message_id" : messageId, "name" : pushName  }}
			self._post("/messages", data)
		else:
			self._w("Duplicate message %s" %messageId)			

				

	def _onAuthSuccess(self, username):
		self.logger.info("Auth Success! - %s" %username)
		self.methodsInterface.call("ready")
		self.methodsInterface.call("clientconfig_send")
		self.methodsInterface.call("presence_sendAvailable", ())
		self._setStatus(1)

	def _onAuthFailed(self, username, err):
		self.logger.error("Auth error! - %s. Using %s with %s " %(err, username, self.password))
		self._post("/wa_auth_error", {})

	def _onDisconnected(self, reason):
		self.logger.error("Disconected! - %s, %s" %(self.username, reason))
