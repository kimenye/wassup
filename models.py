from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy import Column, Integer, String, Boolean, DateTime, desc, Float, Text

Base = declarative_base()

class Account(Base):
	__tablename__ = 'accounts'
	id = Column(Integer, primary_key=True)
	whatsapp_password = Column(String(255))
	auth_token = Column(String(255))
	phone_number = Column(String(255))
	setup = Column(Boolean())
	off_line = Column(Boolean())
	beta_user = Column(Boolean())
	name = Column(String(255))

class Message(Base):
	__tablename__ = 'messages'
	id = Column(Integer, primary_key=True)
	received = Column(Boolean())
	whatsapp_message_id = Column(String(255))
	receipt_timestamp = Column(DateTime())
	account_id = Column(Integer())

	def __init__(self, received):
		self.received = received

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