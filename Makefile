PYTHON_VERSION ?= 3.12
UV ?= uv
DOCKER ?= docker
REVISION := $(shell git rev-parse HEAD 2>/dev/null || printf unknown)
VENV := .venv
PYTHON := $(VENV)/bin/python

.PHONY: setup lint typecheck test train-smoke serve docker-build audit

setup:
	cd backend && $(UV) venv --allow-existing --python $(PYTHON_VERSION) $(VENV)
	cd backend && $(UV) pip sync --require-hashes requirements.lock
	cd backend && $(UV) pip install -c requirements.lock -r requirements-dev.txt
	npm --prefix frontend ci

lint:
	cd backend && $(VENV)/bin/ruff check app tests e2e_server.py ../scripts/compose_smoke.py
	cd backend && $(VENV)/bin/ruff format --check app tests e2e_server.py ../scripts/compose_smoke.py
	npm --prefix frontend run lint

typecheck:
	cd backend && $(PYTHON) -m mypy app/core/config.py app/core/exceptions.py app/ml/executor.py app/schemas/prediction.py app/services/storage.py
	npm --prefix frontend exec -- tsc -b frontend/tsconfig.json

test:
	cd backend && $(PYTHON) -m pytest

train-smoke:
	cd backend && OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 $(PYTHON) -m pytest -q tests/test_e2e_workflow.py

serve:
	cd backend && $(PYTHON) -m alembic upgrade head
	cd backend && CODE_REVISION=$(REVISION) $(PYTHON) -m uvicorn app.main:app --host 127.0.0.1 --port 8000 --timeout-graceful-shutdown 25

docker-build:
	$(DOCKER) build --build-arg CODE_REVISION=$(REVISION) -t atlas-backend:local backend
	$(DOCKER) build -t atlas-frontend:local frontend

audit:
	cd backend && $(VENV)/bin/pip-audit --disable-pip --require-hashes -r requirements.lock
	npm --prefix frontend audit --audit-level=high
