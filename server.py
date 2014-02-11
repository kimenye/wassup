from sqlalchemy import create_engine
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy import Column, Integer, String, Boolean
from sqlalchemy.orm import sessionmaker
from Yowsup.connectionmanager import YowsupConnectionManager
from Yowsup.Common.utilities import Utilities

Base = declarative_base()

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

class Server:
	def __init__(self, url, keepAlive = False, sendReceipts = False):
		self.sendReceipts = sendReceipts
		self.keepAlive = keepAlive
		self.db = create_engine(url, echo=True)
		# self.metadata = BoundMetaData(self.db)

		self.Session = sessionmaker(bind=self.db)
		self.s = self.Session()

		# messages = self.Session.query(Message).filter_by(sent=True).all()			
		for instance in self.s.query(Message): 
			print instance.message


# server = Server('sqlite:///db/dev.db',True, True)
server = Server('sqlite:///../chatcrm/db/development.sqlite3',True, True)
