from __future__ import annotations

import asyncio
import contextlib
import logging
import re
import time
from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import JSONResponse, PlainTextResponse
from prometheus_client import CONTENT_TYPE_LATEST, generate_latest
from redis import Redis
from redis.exceptions import RedisError
from sqlalchemy import text
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.api.router import api_router
from app.core.config import get_settings
from app.core.exceptions import AppError, ServiceUnavailableError
from app.core.logging import configure_logging, request_id_ctx
from app.core.metrics import HTTP_LATENCY, HTTP_REQUESTS
from app.core.security import generate_request_id
from app.core.telemetry import configure_tracing, shutdown_tracing
from app.db.base import Base
from app.db.session import SessionLocal, engine
from app.ml.executor import InferenceExecutor
from app.schemas.common import HealthResponse, ReadinessCheck, ReadinessResponse
from app.services.storage import get_storage
from app.services.training_runner import recover_stale_jobs
from app.workers.executor import reset_job_executor

logger = logging.getLogger(__name__)
REQUEST_ID_PATTERN = re.compile(r"[A-Za-z0-9._-]{1,128}")
HTTP_METHODS = frozenset({"GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS", "HEAD"})
STATUS_CODES = {
    400: "bad_request",
    401: "authentication_required",
    403: "forbidden",
    404: "not_found",
    405: "method_not_allowed",
    409: "conflict",
    413: "payload_too_large",
    415: "unsupported_media_type",
    422: "validation_error",
    429: "rate_limited",
    500: "internal_error",
    503: "service_unavailable",
    504: "gateway_timeout",
}


def _error_response(
    status_code: int,
    code: str,
    message: str,
    details: Any = None,
    headers: dict[str, str] | None = None,
) -> JSONResponse:
    return JSONResponse(
        status_code=status_code,
        content={
            "error": {
                "code": code,
                "message": message,
                "details": details,
                "request_id": request_id_ctx.get(),
            }
        },
        headers=headers,
    )


async def _monitoring_loop(interval: int) -> None:
    from app.services.monitoring import scan_active_deployments

    while True:
        try:
            await asyncio.to_thread(scan_active_deployments)
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("In-process monitoring scan failed")
        await asyncio.sleep(max(60, interval))


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    configure_logging(settings.log_level, settings.log_json)
    settings.ensure_directories()
    if settings.is_sqlite and settings.environment != "production":
        Base.metadata.create_all(bind=engine)
    try:
        recovered = recover_stale_jobs() if settings.job_execution_mode != "celery" else 0
        if recovered:
            logger.warning("Recovered stale training jobs", extra={"count": recovered})
    except Exception:
        logger.exception("Startup training-job recovery failed")
    scheduler_task: asyncio.Task | None = None
    if settings.enable_monitoring_scheduler and settings.job_execution_mode != "celery":
        scheduler_task = asyncio.create_task(_monitoring_loop(settings.monitoring_interval_seconds))
    logger.info(
        "Atlas API started",
        extra={
            "version": settings.version,
            "environment": settings.environment,
            "execution_mode": settings.job_execution_mode,
        },
    )
    redis_client = None
    if settings.job_execution_mode == "celery":
        redis_client = Redis.from_url(
            settings.redis_url,
            socket_connect_timeout=settings.redis_connect_timeout_seconds,
            socket_timeout=settings.redis_connect_timeout_seconds,
        )
    app.state.redis = redis_client
    app.state.inference = InferenceExecutor(
        settings.inference_threads, settings.inference_timeout_seconds
    )
    app.state.accepting_requests = True
    try:
        yield
    finally:
        app.state.accepting_requests = False
        app.state.inference.shutdown()
        if redis_client is not None:
            redis_client.close()
        if scheduler_task is not None:
            scheduler_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await scheduler_task
        shutdown_tracing()
        reset_job_executor()
        logger.info("Atlas API stopped")


def create_app() -> FastAPI:
    settings = get_settings()
    docs_enabled = settings.docs_enabled
    app = FastAPI(
        title=settings.app_name,
        version=settings.version,
        description=(
            "Self-hostable MLOps platform: datasets, training, experiment tracking, "
            "registry, deployments, predictions, monitoring, and retraining."
        ),
        lifespan=lifespan,
        docs_url=f"{settings.api_v1_prefix}/docs" if docs_enabled else None,
        redoc_url=f"{settings.api_v1_prefix}/redoc" if docs_enabled else None,
        openapi_url=f"{settings.api_v1_prefix}/openapi.json" if docs_enabled else None,
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins_list,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
        expose_headers=["X-Request-ID", "X-Trace-ID"],
    )
    app.add_middleware(GZipMiddleware, minimum_size=1024)

    @app.middleware("http")
    async def request_context(request: Request, call_next):
        incoming = request.headers.get("x-request-id")
        request_id = (
            incoming
            if incoming and REQUEST_ID_PATTERN.fullmatch(incoming)
            else generate_request_id()
        )
        token = request_id_ctx.set(request_id)
        started = time.perf_counter()
        status_code = 500
        try:
            try:
                response = await call_next(request)
            except Exception:
                logger.exception("Unhandled request error")
                response = _error_response(500, "internal_error", "An unexpected error occurred.")
            status_code = response.status_code
            response.headers["X-Request-ID"] = request_id
            response.headers["X-Content-Type-Options"] = "nosniff"
            response.headers["X-Frame-Options"] = "DENY"
            response.headers["Referrer-Policy"] = "same-origin"
            return response
        finally:
            duration = time.perf_counter() - started
            route = request.scope.get("route")
            route_label = getattr(route, "path", None) or "unmatched"
            method_label = request.method if request.method in HTTP_METHODS else "OTHER"
            HTTP_REQUESTS.labels(
                method=method_label, route=route_label, status=str(status_code)
            ).inc()
            HTTP_LATENCY.labels(method=method_label, route=route_label).observe(duration)
            logger.info(
                "request",
                extra={
                    "method": request.method,
                    "path": request.url.path,
                    "status": status_code,
                    "duration_ms": round(duration * 1000, 2),
                    "client_ip": request.client.host if request.client else None,
                },
            )
            request_id_ctx.reset(token)

    configure_tracing(
        app,
        service_name=settings.otel_service_name,
        endpoint=settings.otel_exporter_otlp_endpoint,
    )

    @app.exception_handler(AppError)
    async def app_error_handler(request: Request, exc: AppError) -> JSONResponse:
        headers = None
        if exc.status_code == 429 and isinstance(exc.details, dict):
            retry_after = exc.details.get("retry_after")
            if retry_after:
                headers = {"Retry-After": str(retry_after)}
        return _error_response(exc.status_code, exc.code, exc.message, exc.details, headers)

    @app.exception_handler(RequestValidationError)
    async def validation_error_handler(
        request: Request, exc: RequestValidationError
    ) -> JSONResponse:
        details = []
        for error in exc.errors():
            location = ".".join(
                str(part) for part in error.get("loc", ()) if part not in {"body", "query"}
            )
            details.append(
                {
                    "field": location or "request",
                    "message": str(error.get("msg", "Invalid value")),
                }
            )
        return _error_response(422, "validation_error", "Request validation failed.", details)

    @app.exception_handler(StarletteHTTPException)
    async def http_error_handler(request: Request, exc: StarletteHTTPException) -> JSONResponse:
        code = STATUS_CODES.get(exc.status_code, "http_error")
        message = exc.detail if isinstance(exc.detail, str) else "Request failed."
        return _error_response(
            exc.status_code,
            code,
            message,
            None if isinstance(exc.detail, str) else exc.detail,
            headers=dict(exc.headers or {}),
        )

    app.include_router(api_router, prefix=settings.api_v1_prefix)

    @app.get("/health", response_model=HealthResponse, tags=["Meta"])
    def health() -> HealthResponse:
        return HealthResponse(
            status="ok", version=settings.version, environment=settings.environment
        )

    @app.get("/ready", response_model=ReadinessResponse, tags=["Meta"])
    def readiness() -> JSONResponse:
        checks = [
            ReadinessCheck(
                name="lifecycle",
                status="ok" if app.state.accepting_requests else "failed",
            )
        ]
        try:
            with SessionLocal() as db:
                db.execute(text("SELECT 1"))
            checks.append(ReadinessCheck(name="database", status="ok"))
        except Exception:
            checks.append(ReadinessCheck(name="database", status="failed"))
        try:
            healthy, _detail = get_storage().health()
            checks.append(ReadinessCheck(name="storage", status="ok" if healthy else "failed"))
        except ServiceUnavailableError:
            checks.append(ReadinessCheck(name="storage", status="failed"))
        if app.state.redis is not None:
            try:
                healthy = bool(app.state.redis.ping())
                checks.append(ReadinessCheck(name="redis", status="ok" if healthy else "failed"))
            except RedisError:
                checks.append(ReadinessCheck(name="redis", status="failed"))
        overall = "ready" if all(check.status == "ok" for check in checks) else "degraded"
        response = ReadinessResponse(status=overall, checks=checks)
        return JSONResponse(
            status_code=200 if overall == "ready" else 503,
            content=response.model_dump(mode="json"),
        )

    @app.get("/metrics", tags=["Meta"])
    def metrics() -> PlainTextResponse:
        return PlainTextResponse(generate_latest().decode("utf-8"), media_type=CONTENT_TYPE_LATEST)

    return app


app = create_app()
