FROM python:3.12.14-slim@sha256:f77ac9e44ae96ef2c90b8053ea08c31f8be030f824196b0ae4db6d462c84e51f AS dependencies
COPY requirements.lock /tmp/requirements.lock
RUN python -m venv /opt/venv \
    && /opt/venv/bin/pip install --no-cache-dir --only-binary=:all: --require-hashes -r /tmp/requirements.lock

FROM python:3.12.14-slim@sha256:f77ac9e44ae96ef2c90b8053ea08c31f8be030f824196b0ae4db6d462c84e51f
ARG CODE_REVISION=unknown
ENV PATH="/opt/venv/bin:$PATH" \
    CODE_REVISION=$CODE_REVISION \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONPATH=/app \
    HOME=/tmp \
    ARTIFACT_ROOT=/data/artifacts \
    DATABASE_URL=sqlite:////data/artifacts/atlas.db \
    MLFLOW_TRACKING_URI=sqlite:////data/artifacts/mlflow.db \
    MLFLOW_ARTIFACT_ROOT=/data/artifacts/mlflow \
    OPENBLAS_NUM_THREADS=1 \
    OMP_NUM_THREADS=1 \
    MKL_NUM_THREADS=1 \
    MLFLOW_DISABLE_AGENT_HINT=1 \
    MLFLOW_DISABLE_TELEMETRY=true

RUN groupadd --gid 10001 atlas \
    && useradd --uid 10001 --gid atlas --no-create-home atlas \
    && mkdir -p /data/artifacts \
    && chown atlas:atlas /data/artifacts

WORKDIR /app
COPY --from=dependencies /opt/venv /opt/venv
COPY alembic.ini .
COPY alembic alembic
COPY app app

USER 10001:10001
EXPOSE 8000
STOPSIGNAL SIGTERM
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--timeout-keep-alive", "5", "--timeout-graceful-shutdown", "25"]
