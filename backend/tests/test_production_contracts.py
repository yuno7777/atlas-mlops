from __future__ import annotations

import hashlib
import threading
from pathlib import Path
from unittest.mock import Mock

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError
from redis.exceptions import ConnectionError as RedisConnectionError

from app.core.config import Settings, get_settings
from app.core.exceptions import ServiceUnavailableError
from app.ml.executor import InferenceExecutor
from app.services.predictions import ModelArtifact, ModelCache
from app.services.storage import LocalStorage


def test_production_settings_reject_defaults() -> None:
    with pytest.raises(ValidationError, match="strong value"):
        Settings(
            _env_file=None,
            environment="production",
            secret_key=Settings.model_fields["secret_key"].default,
        )
    with pytest.raises(ValidationError, match="inference_threads"):
        Settings(_env_file=None, inference_threads=0)


def test_request_ids_on_errors_and_unmatched_metrics(app) -> None:
    @app.get("/unexpected")
    def unexpected():
        raise RuntimeError("internal details")

    with TestClient(app) as client:
        failure = client.get("/unexpected", headers={"X-Request-ID": "trace.unit-1"})
        assert failure.status_code == 500
        assert failure.headers["X-Request-ID"] == "trace.unit-1"
        assert failure.json()["error"]["request_id"] == "trace.unit-1"
        assert "internal details" not in failure.text

        missing = client.get("/custom-missing-path", headers={"X-Request-ID": "contains spaces"})
        assert missing.status_code == 404
        assert missing.headers["X-Request-ID"] != "contains spaces"
        assert missing.json()["error"]["request_id"] == missing.headers["X-Request-ID"]
        metrics = client.get("/metrics").text
        assert 'route="unmatched",status="404"' in metrics
        assert "custom-missing-path" not in metrics


def test_readiness_reports_broker_failure_without_credentials(client: TestClient) -> None:
    client.app.state.redis = Mock()
    client.app.state.redis.ping.side_effect = RedisConnectionError("internal broker credentials")
    assert client.get("/health").status_code == 200
    readiness = client.get("/ready")
    assert readiness.status_code == 503
    assert any(
        check["name"] == "redis" and check["status"] == "failed"
        for check in readiness.json()["checks"]
    )
    assert "internal broker credentials" not in readiness.text


def test_model_integrity_check_precedes_deserialization(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    storage = LocalStorage(tmp_path)
    storage.put_bytes("registry/model.joblib", b"unexpected model bytes")
    monkeypatch.setattr("app.services.predictions.get_storage", lambda: storage)
    load = Mock()
    monkeypatch.setattr("app.services.predictions.joblib.load", load)
    artifact = ModelArtifact(
        "version",
        "registry/model.joblib",
        hashlib.sha256(b"trusted bytes").hexdigest(),
        {},
        "classification",
    )
    with pytest.raises(ServiceUnavailableError, match="integrity check"):
        ModelCache().load_artifact(artifact)
    load.assert_not_called()


def test_timed_out_inference_keeps_slot_until_scoring_exits() -> None:
    pool = InferenceExecutor(1, 0.05)
    started = threading.Event()
    unblock = threading.Event()

    def score() -> None:
        started.set()
        unblock.wait(timeout=2)

    try:
        with pytest.raises(ServiceUnavailableError) as timeout:
            pool.run(score)
        assert started.is_set()
        assert timeout.value.status_code == 504
        with pytest.raises(ServiceUnavailableError) as busy:
            pool.run(lambda: 1)
        assert busy.value.code == "inference_busy"
    finally:
        unblock.set()
        pool.shutdown()


def test_prediction_body_limit_applies_before_validation(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(get_settings(), "max_prediction_body_bytes", 1024)
    result = client.post(
        "/api/v1/predictions/deployment",
        content=iter((b'{"records":[{"value":"', b"x" * 1024, b'"}]}')),
        headers={"Content-Type": "application/json", "X-Request-ID": "oversize"},
    )
    assert result.status_code == 413
    assert result.json()["error"]["request_id"] == "oversize"
