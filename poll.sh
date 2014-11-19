#!/bin/bash
export URL="http://localhost:3000"
export SQLALCHEMY_DATABASE_URI="mysql+mysqldb://root:root@127.0.0.1:8889/ongair_prod"
export ROLLBAR_KEY="8193ca0abd604fdebc0b5099970b9be1"
export ENV="development"
export PUB_KEY="pub-c-862576a0-c515-4814-9f78-3dc017d031fc"
export SUB_KEY="sub-c-57552884-6fd3-11e4-bcf0-02ee2ddab7fe"
export PUB_CHANNEL="ongair_im_dev"

account="$1"
timeout="$2"
debug="$3"


source venv/bin/activate
python poll.py "$account" "$timeout" "$debug"
