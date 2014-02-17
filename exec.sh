#!/bin/bash
export URL="http://localhost:8080"
export SQLALCHEMY_DATABASE_URI="mysql+mysqldb://rails:wxFKW6Fz4B@localhost/rails"
source /home/wassup/venv/bin/activate & cd /home/wassup & python /home/wassup/server.py
