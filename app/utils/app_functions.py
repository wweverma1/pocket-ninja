import time

from datetime import datetime
from flask import request
from app import app
from app.utils.timezone import JST_TZ


@app.before_request
def before_request():
    request.start_time = time.time()


@app.after_request
def after_request(response):
    if request.endpoint:
        end_time = time.time()
        latency = int((end_time - request.start_time) * 1000)
        print(f'[ {str(datetime.now(JST_TZ))}] endpoint {request.endpoint} latency {latency} \
               req_id {request.environ.get("FLASK_REQUEST_ID")}')
    return response
