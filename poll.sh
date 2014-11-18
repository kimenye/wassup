#!/bin/bash
export URL="http://localhost:3000"
export SQLALCHEMY_DATABASE_URI="mysql+mysqldb://root:root@127.0.0.1:8889/ongair_prod"
export ROLLBAR_KEY="8193ca0abd604fdebc0b5099970b9be1"
export ENV="development"


account="$1"
timeout="$2"


source venv/bin/activate
python poll.py "$account" "$timeout"
