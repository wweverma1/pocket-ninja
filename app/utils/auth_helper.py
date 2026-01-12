import os
import jwt
from datetime import datetime, timedelta, timezone
from functools import wraps
from flask import request, jsonify

SECRET_KEY = os.getenv("JWT_SECRET_KEY")


def encode_auth_token(user_id: str) -> str:
    try:
        payload = {
            'exp': datetime.now(timezone.utc) + timedelta(days=7),
            'iat': datetime.now(timezone.utc),
            'sub': user_id
        }
        return jwt.encode(
            payload,
            SECRET_KEY,
            algorithm='HS256'
        )
    except Exception as e:
        print(f"Error encoding JWT: {e}")
        return e


def decode_auth_token(auth_token: str) -> str | None:
    try:
        payload = jwt.decode(
            auth_token,
            SECRET_KEY,
            algorithms=['HS256']
        )
        if payload['exp'] < datetime.now(timezone.utc).timestamp():
            return None

        return payload['sub']
    except jwt.ExpiredSignatureError:
        return 'Signature expired'
    except jwt.InvalidTokenError:
        return 'Invalid token'
    except Exception as e:
        print(f"Unexpected error decoding JWT: {e}")
        return 'Token error'


def token_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        auth_header = request.headers.get('Authorization')

        if not auth_header or not auth_header.startswith('Bearer '):
            return jsonify({'message': 'Authorization header is missing or invalid'}), 401

        token = auth_header.split(' ')[1]

        user_id_or_error = decode_auth_token(token)

        if (isinstance(user_id_or_error, str) and
                user_id_or_error not in ('Signature expired', 'Invalid token', 'Token error')):
            from app.models.collections.user import User
            current_user = User.get_by_id(user_id_or_error)

            if not current_user:
                return jsonify({'message': 'Token is valid but user no longer exists'}), 401

            return f(current_user, *args, **kwargs)

        return jsonify({'message': f'Token is invalid: {user_id_or_error}'}), 401

    return decorated


def token_optional(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        auth_header = request.headers.get('Authorization')

        if not auth_header or not auth_header.startswith('Bearer '):
            return f(None, *args, **kwargs)

        token = auth_header.split(' ')[1]
        user_id_or_error = decode_auth_token(token)

        if (isinstance(user_id_or_error, str) and
                user_id_or_error not in ('Signature expired', 'Invalid token', 'Token error')):
            from app.models.collections.user import User
            current_user = User.get_by_id(user_id_or_error)

            if not current_user:
                return jsonify({'message': 'Token is valid but user no longer exists'}), 401

            return f(current_user, *args, **kwargs)

        return jsonify({'message': f'Token is invalid: {user_id_or_error}'}), 401

    return decorated
