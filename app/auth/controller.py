import os
import requests
import urllib.parse
import jwt
from flask import request, redirect, jsonify
from app.models.response import Response
from app.models.collections.user import User
from app.utils.auth_helper import encode_auth_token
from app.utils.username_generator import get_random_username

CLOUD_BASE_URL = os.getenv("CLOUD_BASE_URL")
FRONTEND_URL = os.getenv("FRONTEND_URL")


def final_redirect(token: str, is_new_user: bool, username: str = None, error_message: str = None):
    """Constructs the redirect URL with all necessary onboarding flags."""
    if error_message:
        return redirect(f"{FRONTEND_URL}/auth/failure?error={urllib.parse.quote(error_message)}")

    return redirect(f"{FRONTEND_URL}/auth/success?token={token}&username={urllib.parse.quote(username)}&is_new_user={str(is_new_user).lower()}")


def handle_social_login_logic(social_id: str, provider: str, email: str = None):
    """Centralized logic to determine if user is new or existing."""
    if not social_id:
        return final_redirect(None, False, None, "Failed to get unique social ID")

    user_id_obj, username = User.get_id_and_username_by_social_account_id(social_id, provider)

    is_new_user = False

    if user_id_obj:
        user_id_str = str(user_id_obj)
    else:
        is_new_user = True
        rand_base_username = get_random_username()
        username = f"{rand_base_username}_{social_id[:4]}"

        kwargs = {
            "username": username,
            "email": email,
            f"{provider}_account_id": social_id
        }

        new_user_id_obj = User.create_user(**kwargs)

        if not new_user_id_obj:
            return final_redirect(None, False, None, "Registration failed on DB level")
        user_id_str = str(new_user_id_obj)

    token = encode_auth_token(user_id_str)
    return final_redirect(token, is_new_user, username)

# --- Initiation Redirects ---


def google_redirect():
    client_id = os.getenv("GOOGLE_CLIENT_ID")
    redirect_uri = f"{CLOUD_BASE_URL}/auth/callback/google"
    AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
    params = {
        'response_type': 'code',
        'client_id': client_id,
        'redirect_uri': redirect_uri,
        'scope': 'openid email profile',
        'state': 'pocket-ninja-state'
    }
    return redirect(f"{AUTH_URL}?{urllib.parse.urlencode(params)}")


def line_redirect():
    client_id = os.getenv("LINE_CHANNEL_ID")
    redirect_uri = f"{CLOUD_BASE_URL}/auth/callback/line"
    AUTH_URL = "https://access.line.me/oauth2/v2.1/authorize"
    params = {
        'response_type': 'code',
        'client_id': client_id,
        'redirect_uri': redirect_uri,
        'scope': 'profile openid email',
        'state': 'pocket-ninja-line-state'
    }
    return redirect(f"{AUTH_URL}?{urllib.parse.urlencode(params)}")

# --- Callback Exchanges ---


def google_callback():
    code = request.args.get('code')
    if not code:
        return final_redirect(None, False, None, "Auth code missing")
    try:
        resp = requests.post("https://oauth2.googleapis.com/token", data={
            'code': code, 'client_id': os.getenv("GOOGLE_CLIENT_ID"),
            'client_secret': os.getenv("GOOGLE_CLIENT_SECRET"),
            'redirect_uri': f"{CLOUD_BASE_URL}/auth/callback/google", 'grant_type': 'authorization_code'
        })
        resp.raise_for_status()
        token_data = resp.json()
        user_info = requests.get("https://openidconnect.googleapis.com/v1/userinfo",
                                 headers={'Authorization': f"Bearer {token_data['access_token']}"}).json()
        return handle_social_login_logic(user_info.get('sub'), 'google', user_info.get('email'))
    except Exception as e:
        return final_redirect(None, False, None, str(e))


def line_callback():
    code = request.args.get('code')
    if not code:
        return final_redirect(None, False, None, "Auth code missing")
    try:
        resp = requests.post("https://api.line.me/oauth2/v2.1/token", data={
            'code': code, 'client_id': os.getenv("LINE_CHANNEL_ID"),
            'client_secret': os.getenv("LINE_CHANNEL_SECRET"),
            'redirect_uri': f"{CLOUD_BASE_URL}/auth/callback/line", 'grant_type': 'authorization_code'
        }, headers={'Content-Type': 'application/x-www-form-urlencoded'})
        resp.raise_for_status()
        token_data = resp.json()

        # Extract email from ID Token
        email = None
        id_token = token_data.get('id_token')
        if id_token:
            # Decode without verification since we received it directly from the token endpoint
            decoded = jwt.decode(id_token, options={"verify_signature": False})
            email = decoded.get('email')

        profile = requests.get("https://api.line.me/v2/profile",
                               headers={'Authorization': f"Bearer {token_data['access_token']}"}).json()
        return handle_social_login_logic(profile.get('userId'), 'line', email)
    except Exception as e:
        return final_redirect(None, False, None, str(e))
