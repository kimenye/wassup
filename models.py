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