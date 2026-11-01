# ruff: noqa: E402
from __future__ import annotations

import os
import shutil
import tempfile
from collections.abc import Generator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

# Setup temporary test directory and database file
TEST_DIR = Path(tempfile.mkdtemp(prefix="atlas_test_"))
TEST_DB_PATH = TEST_DIR / "test.db"

# Ensure test environment before importing app modules
os.environ["ENVIRONMENT"] = "test"
os.environ["JOB_EXECUTION_MODE"] = "sync"
os.environ["MLFLOW_ENABLED"] = "false"
os.environ["SECRET_KEY"] = "test-secret-key-that-is-at-least-32-characters-long"
os.environ["DATABASE_URL"] = f"sqlite:///{TEST_DB_PATH.as_posix()}"

import app.db.session as session_module
import app.models  # noqa: F401
from app.core.config import get_settings
from app.core.security import create_access_token, hash_password
from app.db.base import Base
from app.main import create_app
from app.models.enums import Role
from app.models.user import Project, User, Workspace, WorkspaceMember
from app.workers.executor import reset_job_executor


@pytest.fixture(scope="session", autouse=True)
def test_environment() -> Generator[None, None, None]:
    settings = get_settings()
    settings.artifact_root = TEST_DIR / "artifacts"
    settings.artifact_root.mkdir(parents=True, exist_ok=True)
    Base.metadata.create_all(bind=session_module.engine)
    yield
    session_module.engine.dispose()
    shutil.rmtree(TEST_DIR, ignore_errors=True)


@pytest.fixture(autouse=True)
def clean_database():
    yield
    with session_module.SessionLocal() as session:
        for table in reversed(Base.metadata.sorted_tables):
            session.execute(table.delete())
        session.commit()


@pytest.fixture
def db_session() -> Generator[Session, None, None]:
    session = session_module.SessionLocal()
    try:
        yield session
    finally:
        session.close()


@pytest.fixture
def app():
    application = create_app()
    reset_job_executor()
    return application


@pytest.fixture
def client(app) -> Generator[TestClient, None, None]:
    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture
def seed_user(db_session: Session) -> User:
    user = User(
        email="engineer@atlas.dev",
        password_hash=hash_password("correct-password-123"),
        full_name="Atlas Engineer",
        is_active=True,
    )
    db_session.add(user)
    db_session.commit()

    workspace = Workspace(
        name="Engineering Workspace",
        slug="engineering-workspace",
        owner_id=user.id,
    )
    db_session.add(workspace)
    db_session.commit()

    member = WorkspaceMember(
        workspace_id=workspace.id,
        user_id=user.id,
        role=Role.OWNER,
    )
    db_session.add(member)
    db_session.commit()

    project = Project(
        workspace_id=workspace.id,
        name="Churn Prediction",
        slug="churn-prediction",
        description="Demo project for testing",
    )
    db_session.add(project)
    db_session.commit()

    return user


@pytest.fixture
def auth_headers(seed_user: User) -> dict[str, str]:
    token, _ = create_access_token(seed_user.id)
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def sample_csv() -> bytes:
    content = (
        "age,tenure,monthly_charges,contract,churn\n"
        "25,12,50.5,month-to-month,0\n"
        "34,24,70.0,one-year,0\n"
        "45,3,85.2,month-to-month,1\n"
        "52,60,110.0,two-year,0\n"
        "23,6,65.0,month-to-month,1\n"
        "38,36,92.5,one-year,0\n"
        "61,48,105.4,two-year,0\n"
        "29,8,75.2,month-to-month,1\n"
        "41,18,60.0,month-to-month,0\n"
        "50,40,95.0,two-year,0\n"
    )
    return content.encode("utf-8")


@pytest.fixture
def training_csv() -> bytes:
    rows = [
        "age,tenure,monthly_charges,contract,churn",
        "25,12,50.5,month-to-month,0",
        "34,24,70.0,one-year,0",
        "45,3,85.2,month-to-month,1",
        "52,60,110.0,two-year,0",
        "23,6,65.0,month-to-month,1",
        "38,36,92.5,one-year,0",
        "61,48,105.4,two-year,0",
        "29,8,75.2,month-to-month,1",
        "41,18,60.0,month-to-month,0",
        "50,40,95.0,two-year,0",
        "22,4,45.0,month-to-month,1",
        "31,14,65.2,month-to-month,0",
        "48,30,88.0,one-year,1",
        "55,55,102.5,two-year,0",
        "27,9,72.0,month-to-month,1",
        "36,28,81.0,one-year,0",
        "63,65,115.0,two-year,0",
        "30,11,69.5,month-to-month,0",
        "44,22,80.0,month-to-month,1",
        "51,45,98.5,two-year,0",
        "26,5,55.0,month-to-month,1",
        "35,26,74.5,one-year,0",
        "46,32,87.0,one-year,0",
        "53,58,108.0,two-year,0",
        "24,7,62.0,month-to-month,1",
        "39,38,91.0,one-year,0",
        "62,50,104.0,two-year,0",
        "28,10,71.0,month-to-month,1",
        "42,20,64.0,month-to-month,0",
        "49,42,96.0,two-year,0",
    ]
    return "\n".join(rows).encode("utf-8")
