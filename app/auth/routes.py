from flask import Blueprint

from app.auth.controller import (
    google_redirect,
    line_redirect,
    google_callback,
    line_callback
)

auth_endpoints = Blueprint('auth', __name__, url_prefix="/auth")

auth_endpoints.add_url_rule(rule='/redirect/google',
                            view_func=google_redirect, methods=['GET'])
auth_endpoints.add_url_rule(rule='/redirect/line',
                            view_func=line_redirect, methods=['GET'])

auth_endpoints.add_url_rule(rule='/callback/google',
                            view_func=google_callback, methods=['GET'])
auth_endpoints.add_url_rule(rule='/callback/line',
                            view_func=line_callback, methods=['GET'])
