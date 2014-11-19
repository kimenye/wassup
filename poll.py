from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from Yowsup.Common.utilities import Utilities
from Yowsup.Media.uploader import MediaUploader
import os, json, base64, time, requests, hashlib, datetime, logging, vobject, thread, calendar

from datetime import datetime, timedelta
from pubnub import Pubnub
import rollbar
import stathat
import sys
from util import error_message, setup_logging
from client import Client


# print sys.argv
if len(sys.argv) >= 2:
	phone_number = sys.argv[1]
	timeout = int(sys.argv[2])
	debug = False
	if len(sys.argv) > 3:
		debug = sys.argv[3] == "True"



	env = os.environ['ENV']		
	
	logger = setup_logging(phone_number, env)
	logger.info("Ready to go with %s - Debug %s" %(phone_number, debug))

	rollbar.init(os.environ['ROLLBAR_KEY'], env)

	client = Client(phone_number, logger)

	if client.account.setup == True:
		if debug == False:
			client.connect()

		poll = True
		start = time.time()
		while (poll):
			now = time.time()
			runtime = int(now - start)			
			time.sleep(5)
			logger.info("Disconnecting in %s seconds" %(timeout - runtime))
			poll = runtime < timeout

		logger.info("Complete!")
		client.disconnect()

	else:
		error_message("Called poll script un setup account %s" %phone_number)
else:
	error_message("Called poll script without a phone number", "error")
	sys.exit(1)