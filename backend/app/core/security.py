from __future__ import annotations

import hashlib
import hmac
import secrets
from datetime import UTC, datetime, timedelta

import bcrypt
import jwt

from app.core.config import get_settings
from app.core.exceptions import AuthenticationError

JWT_ISSUER = "atlas-mlops"
JWT_AUDIENCE = "atlas-api"
API_KEY_PREFIX = "atlas_"


def _password_bytes(password: str) -> bytes:
    encoded = password.encode("utf-8")
    if len(encoded) > 72:
        raise ValueError("Password must not exceed 72 bytes when UTF-8 encoded")
    if not encoded:
        raise ValueError("Password must not be empty")
    return encoded


def hash_password(password: str) -> str:
    return bcrypt.hashpw(_password_bytes(password), bcrypt.gensalt(rounds=12)).decode("utf-8")


def verify_password(password: str, password_hash: str) -> bool:
    try:
        return bcrypt.checkpw(_password_bytes(password), password_hash.encode("utf-8"))
    except (ValueError, TypeError):
        return False


def create_access_token(subject: str, expires_minutes: int | None = None) -> tuple[str, int]:
    settings = get_settings()
    minutes = expires_minutes or settings.access_token_expire_minutes
    now = datetime.now(UTC)
    expires_delta = timedelta(minutes=minutes)
    payload = {
        "sub": subject,
        "iat": int(now.timestamp()),
        "exp": int((now + expires_delta).timestamp()),
        "iss": JWT_ISSUER,
        "aud": JWT_AUDIENCE,
    }
    token = jwt.encode(payload, settings.secret_key, algorithm=settings.jwt_algorithm)
    return token, int(expires_delta.total_seconds())


def decode_access_token(token: str) -> str:
    settings = get_settings()
    try:
        payload = jwt.decode(
            token,
            settings.secret_key,
            algorithms=[settings.jwt_algorithm],
            audience=JWT_AUDIENCE,
            issuer=JWT_ISSUER,
        )
    except jwt.ExpiredSignatureError as exc:
        raise AuthenticationError("Token has expired") from exc
    except jwt.InvalidTokenError as exc:
        raise AuthenticationError("Invalid authentication token") from exc
    subject = payload.get("sub")
    if not subject or not isinstance(subject, str):
        raise AuthenticationError("Invalid authentication token")
    return subject


def generate_api_key() -> str:
    return f"{API_KEY_PREFIX}{secrets.token_urlsafe(32)}"


def hash_api_key(api_key: str) -> str:
    return hashlib.sha256(api_key.encode("utf-8")).hexdigest()


def api_key_matches(api_key: str, expected_hash: str) -> bool:
    return hmac.compare_digest(hash_api_key(api_key), expected_hash)


def api_key_prefix(api_key: str) -> str:
    return api_key[:12]


def generate_request_id() -> str:
    return secrets.token_hex(16)
