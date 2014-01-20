import os, json
from flask import Flask, jsonify, request
from rq import Queue
from messenger import conn
import requests
from WhatsappEchoClient import WhatsappEchoClient

import logging, base64
from logging import StreamHandler


app = Flask(__name__)
app.debug = True
file_handler = StreamHandler()
app.logger.setLevel(logging.DEBUG)  # set the desired logging level here
app.logger.addHandler(file_handler)


@app.route('/')
def hello():
	print("The request is in")
	app.logger.info('Received message')
	return 'Yo Wassup!'

def send_message(to,msg):
	wa = WhatsappEchoClient(to.encode('utf8'), msg.encode('utf8'), False)
	login = "254733171036"
	password = "+rYGoEyk7y9QBGLCSHuPS2VVZNw="
	password = base64.b64decode(bytes(password.encode('utf-8')))
	wa.login(login, password)
	app.logger.info('Sending to %s' %msg)


def initialize_profile(jid, jobId):
	server_url = os.getenv('SERVER_URL', 'http://localhost:3000')
	post_url = server_url + "/jobs/%s" %jobId
	headers = {'Content-type': 'application/json', 'Accept': 'application/json'}
	data = { "job" : { 'success': True, 'result' : "%s was retrieved" %jid } }
	r = requests.patch(post_url, data=json.dumps(data), headers=headers)

@app.route('/initialize', methods=['POST'])
def initialize():
	phone_number = request.json['phone_number']
	job_id = request.json['job_id']
	q = Queue(connection=conn)
	job = q.enqueue(initialize_profile, phone_number, job_id)
	return jsonify(status="ok")

@app.route('/send', methods=['POST', 'GET'])
def send():
	phone_number = request.json['phone_number']
	msg = request.json['message']
	app.logger.info('TO: %s' %phone_number)
	app.logger.info('MSG: %s' %msg)
	

	q = Queue(connection=conn)
	job = q.enqueue(send_message, phone_number, msg)

	app.logger.info('MSG %s' %job.result)
	
	return jsonify(status="ok", to=request.json['phone_number'], result=job.result)
