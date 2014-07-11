#!/bin/bash
export URL="http://localhost:8080"
export SQLALCHEMY_DATABASE_URI="mysql+mysqldb://rails:wxFKW6Fz4B@localhost/rails"
export TEL_NUMBER=""
export PASS=""
export NUMBER=""
export LOGO="logo.png"
export USE_REALTIME="false"
export API_URL=""

cd /home/wassup
source venv/bin/activate
python /home/wassup/server.py
