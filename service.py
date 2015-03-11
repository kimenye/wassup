import os, sys, logging
import rollbar
from util import error_message, setup_logging

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from models import Account
from client import Client

if len(sys.argv) >= 2:
	
	timeout = int(sys.argv[1])
	debug = sys.argv[2] == "True"

	env = os.environ['ENV']
	
	logger = setup_logging("SERVICE", env)
	rollbar.init(os.environ['ROLLBAR_KEY'], env)

	try:	
		logger.info("Starting service Timeout: %s - Debug %s" %(timeout, debug))

		url = os.environ['SQLALCHEMY_DATABASE_URI']
		_db = create_engine(url, echo=False, pool_size=15, pool_timeout=600,pool_recycle=600)
		_session = sessionmaker(bind=_db)

		accounts = _session().query(Account).filter_by(setup=True, beta_user=False).all()
		logger.info("Going to load %s accounts" %len(accounts))

		for account in accounts:
			# create a logger for the client
			client_logger = setup_logging(account.phone_number, env)
			
			# create the client
			client = Client(account.phone_number, client_logger, timeout)
			client.start()

	except Exception, e:
		raise
	else:
		pass
	finally:
		logger.info("Finished execution")
