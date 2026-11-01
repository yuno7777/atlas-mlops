from __future__ import annotations

import tempfile
from pathlib import Path

import pytest

from app.core.exceptions import AuthenticationError
from app.core.security import (
    api_key_matches,
    api_key_prefix,
    create_access_token,
    decode_access_token,
    generate_api_key,
    hash_api_key,
    hash_password,
    verify_password,
)
from app.services.predictions import ModelCache
from app.services.storage import LocalStorage


def test_password_hashing_and_verification():
    password = "SuperSecretPassword123!"
    hashed = hash_password(password)

    assert hashed != password
    assert verify_password(password, hashed) is True
    assert verify_password("WrongPassword!", hashed) is False

    with pytest.raises(ValueError, match="Password must not be empty"):
        hash_password("")

    with pytest.raises(ValueError, match="Password must not exceed 72 bytes"):
        hash_password("a" * 73)


def test_jwt_access_token_lifecycle():
    subject = "user-uuid-12345"
    token, expires_in = create_access_token(subject, expires_minutes=15)

    assert isinstance(token, str)
    assert expires_in == 15 * 60

    decoded = decode_access_token(token)
    assert decoded == subject

    # Tampered token
    tampered = token[:-4] + "abcd"
    with pytest.raises(AuthenticationError, match="Invalid authentication token"):
        decode_access_token(tampered)

    # Expired token
    expired_token, _ = create_access_token(subject, expires_minutes=-1)
    with pytest.raises(AuthenticationError, match="Token has expired"):
        decode_access_token(expired_token)


def test_api_key_generation_and_matching():
    key = generate_api_key()
    assert key.startswith("atlas_")
    assert len(key) > 30

    prefix = api_key_prefix(key)
    assert prefix == key[:12]

    key_hash = hash_api_key(key)
    assert api_key_matches(key, key_hash) is True
    assert api_key_matches("atlas_invalid_key", key_hash) is False


def test_local_storage_operations():
    with tempfile.TemporaryDirectory() as temp_dir:
        storage = LocalStorage(Path(temp_dir))

        # Health
        healthy, msg = storage.health()
        assert healthy is True
        assert msg == str(Path(temp_dir).resolve())

        # Put bytes & read bytes
        data = b"sample content for storage test"
        storage.put_bytes("datasets/churn/v1.csv", data)
        assert storage.exists("datasets/churn/v1.csv") is True
        assert storage.read_bytes("datasets/churn/v1.csv") == data

        # Checksum
        checksum = storage.sha256("datasets/churn/v1.csv")
        import hashlib

        expected_hash = hashlib.sha256(data).hexdigest()
        assert checksum == expected_hash

        # Iter chunks
        chunks = list(storage.iter_chunks("datasets/churn/v1.csv"))
        assert b"".join(chunks) == data

        # Open path
        with storage.open_path("datasets/churn/v1.csv") as path:
            assert path.exists()
            assert path.read_bytes() == data

        # Delete prefix
        storage.put_bytes("datasets/churn/v2.csv", b"version 2")
        storage.put_bytes("models/v1.joblib", b"model data")
        storage.delete_prefix("datasets/churn")
        assert storage.exists("datasets/churn/v1.csv") is False
        assert storage.exists("datasets/churn/v2.csv") is False
        assert storage.exists("models/v1.joblib") is True

        # Path traversal guard
        with pytest.raises(ValueError):
            storage.read_bytes("../secret.txt")
        with pytest.raises(ValueError):
            storage.read_bytes("/absolute/path")


def test_model_cache_lru_and_clear():
    cache = ModelCache(max_entries=2, ttl_seconds=60)
    assert cache.size == 0
    assert cache.has_entry("nonexistent", "dummy") is False

    cache.clear()
    assert cache.size == 0
