from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
from threading import Barrier, Event
from unittest.mock import Mock

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select, update
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.exceptions import TrainingError
from app.db.session import SessionLocal
from app.ml.algorithms import get_algorithm
from app.ml.training import train_algorithm
from app.ml.validation import read_dataframe
from app.models.registry import ModelVersion, RegisteredModel
from app.models.training import TrainingDispatch, TrainingJob
from app.models.user import Project
from app.services.training_runner import execute_training_job, recover_stale_jobs
from app.workers.dispatch import dispatch_due_training_jobs, dispatch_training_job
from app.workers.training_lease import LeaseLost, TrainingLease


@pytest.fixture
def submission(
    client: TestClient, auth_headers: dict[str, str], db_session: Session, training_csv: bytes
) -> dict:
    project = db_session.scalar(select(Project))
    assert project is not None
    dataset = client.post(
        "/api/v1/datasets",
        headers=auth_headers,
        data={"project_id": project.id, "name": "Outbox data"},
        files={"file": ("churn.csv", training_csv, "text/csv")},
    )
    assert dataset.status_code == 201, dataset.text
    return {
        "project_id": project.id,
        "dataset_version_id": dataset.json()["id"],
        "problem_type": "classification",
        "target_column": "churn",
        "algorithms": [{"algorithm": "logistic_regression"}],
    }


def test_recovers_after_submission_commits_but_before_dispatch(
    client, auth_headers, submission, db_session, monkeypatch
):
    headers = {**auth_headers, "Idempotency-Key": "crash-before-dispatch"}
    with monkeypatch.context() as patch:
        patch.setattr(
            "app.services.training.dispatch_training_job",
            Mock(side_effect=RuntimeError("simulated API termination after commit")),
        )
        failed = client.post("/api/v1/training-jobs", headers=headers, json=submission)
        assert failed.status_code == 500

    replay = client.post("/api/v1/training-jobs", headers=headers, json=submission)
    assert replay.status_code == 202, replay.text
    job = replay.json()
    assert job["status"] == "queued"
    job_id = job["id"]
    assert db_session.get(TrainingDispatch, job_id).attempts == 0

    assert dispatch_due_training_jobs() == 1
    execute_training_job(job_id)
    assert dispatch_due_training_jobs() == 0
    db_session.expire_all()
    assert db_session.get(TrainingDispatch, job_id) is None
    completed = client.get(f"/api/v1/training-jobs/{job_id}", headers=auth_headers).json()
    assert completed["status"] == "completed"
    assert len(completed["experiments"]) == 1


@pytest.mark.parametrize("broker_fails", [True, False], ids=["failed-publish", "lost-message"])
def test_unclaimed_job_waits_and_then_retries(
    client, auth_headers, submission, db_session, monkeypatch, broker_fails
):
    executor = Mock()
    if broker_fails:
        executor.enqueue.side_effect = ConnectionError("broker unavailable")
    with monkeypatch.context() as patch:
        patch.setattr("app.workers.dispatch.get_job_executor", lambda: executor)
        accepted = client.post("/api/v1/training-jobs", headers=auth_headers, json=submission)
        assert accepted.status_code == 202, accepted.text
        job_id = accepted.json()["id"]
        assert db_session.get(TrainingDispatch, job_id).attempts == 1
        assert dispatch_due_training_jobs() == 0
        executor.enqueue.assert_called_once_with(job_id)

    row = db_session.get(TrainingDispatch, job_id)
    row.available_at = datetime.now(UTC) - timedelta(seconds=1)
    db_session.commit()
    assert dispatch_due_training_jobs() == 1
    assert (
        client.get(f"/api/v1/training-jobs/{job_id}", headers=auth_headers).json()["status"]
        == "completed"
    )


def test_competing_dispatchers_and_cancellation(
    client, auth_headers, submission, db_session, monkeypatch
):
    monkeypatch.setattr("app.services.training.dispatch_training_job", Mock())
    accepted = client.post("/api/v1/training-jobs", headers=auth_headers, json=submission)
    assert accepted.status_code == 202, accepted.text
    job_id = accepted.json()["id"]
    executor = Mock()
    monkeypatch.setattr("app.workers.dispatch.get_job_executor", lambda: executor)
    barrier = Barrier(2)

    def dispatch():
        barrier.wait(timeout=5)
        return dispatch_training_job(job_id)

    with ThreadPoolExecutor(2) as pool:
        first = pool.submit(dispatch)
        second = pool.submit(dispatch)
        assert sorted((first.result(timeout=10), second.result(timeout=10))) == [False, True]
    executor.enqueue.assert_called_once_with(job_id)
    assert db_session.get(TrainingDispatch, job_id).attempts == 1
    assert dispatch_due_training_jobs() == 0

    cancelled = client.post(f"/api/v1/training-jobs/{job_id}/cancel", headers=auth_headers)
    assert cancelled.status_code == 200, cancelled.text
    assert cancelled.json()["status"] == "cancelled"
    db_session.expire_all()
    assert db_session.get(TrainingDispatch, job_id) is None
    execute_training_job(job_id)  # The already published message may still arrive.
    assert (
        client.get(f"/api/v1/training-jobs/{job_id}", headers=auth_headers).json()["experiments"]
        == []
    )


def _expire_worker(job_id: str) -> None:
    with SessionLocal.begin() as db:
        job = db.get(TrainingJob, job_id)
        assert job is not None
        job.lease_expires_at = datetime.now(UTC) - timedelta(seconds=1)


def test_worker_heartbeat_keeps_idle_attempt_live(client, auth_headers, submission, monkeypatch):
    monkeypatch.setattr("app.services.training.dispatch_training_job", Mock())
    accepted = client.post("/api/v1/training-jobs", headers=auth_headers, json=submission)
    assert accepted.status_code == 202, accepted.text
    job_id = accepted.json()["id"]
    extended = Event()
    original_guard = TrainingLease.guard

    def observe_heartbeat(lease, db):
        original_guard(lease, db)
        extended.set()

    monkeypatch.setattr(TrainingLease, "guard", observe_heartbeat)
    lease = TrainingLease(job_id, duration_seconds=4)
    try:
        with SessionLocal() as db:
            assert lease.claim(db)
            original_expiry = db.get(TrainingJob, job_id).lease_expires_at
        assert extended.wait(timeout=5)
    finally:
        lease.close()
    with SessionLocal() as db:
        job = db.get(TrainingJob, job_id)
        assert job.lease_expires_at > original_expiry
        assert job.execution_attempt == 1
    assert recover_stale_jobs() == 0


def test_expired_worker_cannot_publish_and_retry_reuses_completed_algorithms(
    client, auth_headers, submission, monkeypatch
):
    monkeypatch.setattr("app.services.training.dispatch_training_job", Mock())
    accepted = client.post(
        "/api/v1/training-jobs",
        headers=auth_headers,
        json={
            **submission,
            "algorithms": [
                {"algorithm": "logistic_regression"},
                {"algorithm": "random_forest_classifier", "hyperparameters": {"n_estimators": 10}},
            ],
            "register_model_name": "Recovered model",
        },
    )
    assert accepted.status_code == 202, accepted.text
    job_id = accepted.json()["id"]
    fitting = Event()
    release = Event()
    fitted = []

    def stop_first_forest(path, name, algorithm, hyperparameters, config, *, check_active):
        fitted.append(algorithm)
        if algorithm == "random_forest_classifier" and fitted.count(algorithm) == 1:
            fitting.set()
            assert release.wait(timeout=15)
        check_active()
        return train_algorithm(
            read_dataframe(path, name),
            get_algorithm(algorithm, config.problem_type),
            hyperparameters,
            config,
        )

    monkeypatch.setattr("app.services.training_runner.run_fit", stop_first_forest)
    with ThreadPoolExecutor(1) as pool:
        expired_worker = pool.submit(execute_training_job, job_id)
        try:
            assert fitting.wait(timeout=10)
            _expire_worker(job_id)
            assert recover_stale_jobs() == 1
            assert recover_stale_jobs() == 0
            assert dispatch_due_training_jobs() == 0
            _make_retry_due(job_id)
            assert dispatch_due_training_jobs() == 1
        finally:
            release.set()
        expired_worker.result(timeout=10)

    result = client.get(f"/api/v1/training-jobs/{job_id}", headers=auth_headers).json()
    assert result["status"] == "completed", result
    assert fitted.count("logistic_regression") == 1
    assert fitted.count("random_forest_classifier") == 2
    experiments = result["experiments"]
    assert sorted(experiment["status"] for experiment in experiments) == [
        "completed",
        "completed",
        "failed",
    ]
    failed = next(experiment for experiment in experiments if experiment["status"] == "failed")
    assert not failed["artifact_available"]
    with SessionLocal() as db:
        job = db.get(TrainingJob, job_id)
        assert job.execution_attempt == 2
        assert job.execution_token is None and job.lease_expires_at is None
        assert db.scalar(select(func.count(ModelVersion.id))) == 1


@pytest.mark.parametrize("cancelled", [False, True])
def test_expired_execution_honors_budget_and_cancellation(
    client, auth_headers, submission, monkeypatch, cancelled
):
    monkeypatch.setattr("app.services.training.dispatch_training_job", Mock())
    monkeypatch.setattr(get_settings(), "training_max_attempts", 1 if not cancelled else 2)
    accepted = client.post("/api/v1/training-jobs", headers=auth_headers, json=submission)
    assert accepted.status_code == 202, accepted.text
    job_id = accepted.json()["id"]
    lease = TrainingLease(job_id, duration_seconds=120)
    try:
        with SessionLocal() as db:
            assert lease.claim(db)
        if cancelled:
            assert (
                client.post(
                    f"/api/v1/training-jobs/{job_id}/cancel", headers=auth_headers
                ).status_code
                == 200
            )
        _expire_worker(job_id)
        with SessionLocal.begin() as db, pytest.raises(LeaseLost):
            lease.guard(db)
        assert recover_stale_jobs() == 1
    finally:
        lease.close()
    with SessionLocal() as db:
        assert db.get(TrainingJob, job_id).status == ("cancelled" if cancelled else "failed")
        assert db.get(TrainingDispatch, job_id) is None


def test_lease_expiring_during_registration_rolls_back_model_version(
    client, auth_headers, submission, monkeypatch
):
    from app.services.registry import register_experiment_as_model

    def expire_during_registration(db, **kwargs):
        version = register_experiment_as_model(db, **kwargs)
        db.execute(
            update(TrainingJob).values(lease_expires_at=datetime.now(UTC) - timedelta(seconds=1))
        )
        return version

    monkeypatch.setattr(
        "app.services.registry.register_experiment_as_model", expire_during_registration
    )
    accepted = client.post(
        "/api/v1/training-jobs",
        headers=auth_headers,
        json={**submission, "register_model_name": "Uncommitted model"},
    )
    assert accepted.status_code == 202, accepted.text
    assert accepted.json()["status"] == "running"
    with SessionLocal() as db:
        assert db.scalar(select(func.count(ModelVersion.id))) == 0
        assert db.scalar(select(func.count(RegisteredModel.id))) == 0


def _make_retry_due(job_id: str) -> None:
    with SessionLocal.begin() as db:
        record = db.get(TrainingDispatch, job_id)
        assert record is not None
        record.available_at = datetime.now(UTC) - timedelta(seconds=1)


@pytest.mark.parametrize("cancelled", [False, True], ids=["execution-deadline", "cancel-grace"])
def test_deadlines_fence_a_live_worker(client, auth_headers, submission, monkeypatch, cancelled):
    monkeypatch.setattr("app.services.training.dispatch_training_job", Mock())
    accepted = client.post(
        "/api/v1/training-jobs",
        headers=auth_headers,
        json={
            **submission,
            "execution_policy": {
                "timeout_seconds": 900,
                "cancel_grace_seconds": 10,
                "max_attempts": 3,
            },
        },
    )
    assert accepted.status_code == 202, accepted.text
    job_id = accepted.json()["id"]
    lease = TrainingLease(job_id, duration_seconds=120)
    try:
        with SessionLocal() as db:
            assert lease.claim(db)
            job = db.get(TrainingJob, job_id)
            assert job.execution_deadline_at - job.started_at == timedelta(seconds=900)
        if cancelled:
            endpoint = f"/api/v1/training-jobs/{job_id}/cancel"
            first = client.post(endpoint, headers=auth_headers)
            repeated = client.post(endpoint, headers=auth_headers)
            assert first.status_code == repeated.status_code == 200
            assert first.json()["cancel_deadline_at"] == repeated.json()["cancel_deadline_at"]
            assert first.json()["cancel_deadline_at"] is not None
        with SessionLocal.begin() as db:
            job = db.get(TrainingJob, job_id)
            deadline = datetime.now(UTC) - timedelta(seconds=1)
            if cancelled:
                job.cancel_deadline_at = deadline
            else:
                job.execution_deadline_at = deadline
        with SessionLocal.begin() as db, pytest.raises(LeaseLost):
            lease.guard(db)
        assert recover_stale_jobs(job_id) == 1
    finally:
        lease.close()
    with SessionLocal() as db:
        job = db.get(TrainingJob, job_id)
        assert job.status == ("cancelled" if cancelled else "failed")
        assert job.execution_attempt == 1
        assert db.get(TrainingDispatch, job_id) is None
        if not cancelled:
            assert job.error_message == "Training exceeded its execution deadline."


def test_transient_errors_back_off_and_exhaust_the_job_budget(
    client, auth_headers, submission, monkeypatch
):
    def fail_fit(*_args, **_kwargs):
        raise TrainingError("Training dependency failed") from ConnectionError("connection reset")

    fit = Mock(side_effect=fail_fit)
    monkeypatch.setattr("app.services.training_runner.run_fit", fit)
    response = client.post(
        "/api/v1/training-jobs",
        headers=auth_headers,
        json={**submission, "execution_policy": {"max_attempts": 3, "retry_backoff_seconds": 10}},
    )
    assert response.status_code == 202, response.text
    job_id = response.json()["id"]
    for attempt, delay in [(1, 10), (2, 20)]:
        with SessionLocal() as db:
            job = db.get(TrainingJob, job_id)
            assert job.status == "queued"
            assert job.execution_attempt == attempt
            record = db.get(TrainingDispatch, job_id)
            available = record.available_at.replace(tzinfo=UTC)
            remaining = (available - datetime.now(UTC)).total_seconds()
            assert delay - 5 < remaining <= delay
        assert dispatch_due_training_jobs() == 0
        _make_retry_due(job_id)
        assert dispatch_due_training_jobs() == 1
    with SessionLocal() as db:
        job = db.get(TrainingJob, job_id)
        assert job.status == "failed"
        assert job.execution_attempt == fit.call_count == 3
        assert db.get(TrainingDispatch, job_id) is None


def test_permanent_training_errors_are_not_retried(client, auth_headers, submission, monkeypatch):
    fit = Mock(side_effect=TrainingError("Invalid data for fitting"))
    monkeypatch.setattr("app.services.training_runner.run_fit", fit)
    response = client.post(
        "/api/v1/training-jobs",
        headers=auth_headers,
        json={**submission, "execution_policy": {"max_attempts": 3}},
    )
    assert response.status_code == 202, response.text
    assert response.json()["status"] == "failed"
    assert response.json()["execution_attempt"] == fit.call_count == 1
    assert dispatch_due_training_jobs() == 0


@pytest.fixture
def blocked_fit_process(tmp_path, monkeypatch):
    import sys

    started = tmp_path / "fit-started"
    command = """
import sys
import time
from pathlib import Path
from app.ml import training
from app.workers.fit_worker import main

def slow_fit(*args, **kwargs):
    Path(sys.argv.pop()).touch()
    time.sleep(60)
    raise AssertionError("A stopped fit must never return")

training.train_algorithm = slow_fit
main()
"""

    def fit_command(directory):
        return [sys.executable, "-c", command, str(directory), str(started)]

    monkeypatch.setattr("app.workers.fit_process._fit_command", fit_command)
    return started, fit_command


def _wait_for_fit_marker(marker):
    import time

    until = time.monotonic() + 20
    while not marker.is_file() and time.monotonic() < until:
        time.sleep(0.05)
    assert marker.is_file(), "Fit process did not reach the estimator"


@pytest.mark.parametrize("cancelled", [True, False], ids=["cancel", "deadline"])
def test_supervisor_stops_a_live_fit(
    client, auth_headers, submission, blocked_fit_process, monkeypatch, cancelled
):
    monkeypatch.setattr("app.services.training.dispatch_training_job", Mock())
    received = client.post("/api/v1/training-jobs", headers=auth_headers, json=submission)
    assert received.status_code == 202, received.text
    job_id = received.json()["id"]
    with ThreadPoolExecutor(1) as pool:
        worker = pool.submit(execute_training_job, job_id)
        try:
            _wait_for_fit_marker(blocked_fit_process[0])
            if cancelled:
                response = client.post(
                    f"/api/v1/training-jobs/{job_id}/cancel", headers=auth_headers
                )
                assert response.status_code == 200
            else:
                with SessionLocal.begin() as db:
                    job = db.get(TrainingJob, job_id)
                    job.execution_deadline_at = datetime.now(UTC) - timedelta(seconds=1)
            worker.result(timeout=8)
        finally:
            if not worker.done():
                _expire_worker(job_id)
    response = client.get(f"/api/v1/training-jobs/{job_id}", headers=auth_headers).json()
    assert response["status"] == ("cancelled" if cancelled else "failed")
    assert response["execution_attempt"] == 1
    assert not any(experiment["artifact_available"] for experiment in response["experiments"])


def test_fit_worker_exits_when_parent_pipe_closes(tmp_path, blocked_fit_process):
    import json
    import subprocess

    from app.workers.fit_process import BACKEND_ROOT

    snapshot = tmp_path / "dataset.csv"
    snapshot.write_text("x,y,target\n" + "1,1,0\n" * 24, encoding="utf-8")
    (tmp_path / "input.json").write_text(
        json.dumps(
            {
                "dataset_path": str(snapshot),
                "original_filename": "dataset.csv",
                "config": {
                    "problem_type": "classification",
                    "target_column": "target",
                    "feature_columns": None,
                },
                "algorithm": "logistic_regression",
                "hyperparameters": {},
            }
        ),
        encoding="utf-8",
    )
    marker, command = blocked_fit_process
    with subprocess.Popen(command(tmp_path), cwd=BACKEND_ROOT, stdin=subprocess.PIPE) as worker:
        try:
            _wait_for_fit_marker(marker)
            worker.stdin.close()
            assert worker.wait(timeout=8) == 2
        finally:
            if worker.poll() is None:
                worker.kill()
    assert not (tmp_path / "result.joblib").exists()
