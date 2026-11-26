from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
from threading import Barrier
from unittest.mock import Mock

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.training import TrainingDispatch
from app.models.user import Project
from app.services.training_runner import execute_training_job
from app.workers.dispatch import dispatch_due_training_jobs, dispatch_training_job


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
