from __future__ import annotations

import logging
from typing import Any
from urllib.parse import urlparse

from fastapi import FastAPI, Request

logger = logging.getLogger(__name__)
_provider: Any | None = None


def configure_tracing(app: FastAPI, *, service_name: str, endpoint: str | None) -> bool:
    """Enable W3C trace propagation and OTLP span export only when configured."""
    global _provider
    if not endpoint:
        return False
    try:
        from opentelemetry import trace
        from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
        from opentelemetry.sdk.resources import Resource
        from opentelemetry.sdk.trace import TracerProvider
        from opentelemetry.sdk.trace.export import BatchSpanProcessor
        from opentelemetry.trace.propagation.tracecontext import TraceContextTextMapPropagator
    except ImportError:
        logger.warning("OTLP endpoint is configured but OpenTelemetry packages are not installed")
        return False

    parsed = urlparse(endpoint.rstrip("/"))
    if not parsed.scheme or not parsed.netloc:
        logger.warning("OTLP tracing is disabled because the endpoint URL is invalid")
        return False
    trace_endpoint = endpoint.rstrip("/")
    if not trace_endpoint.endswith("/v1/traces"):
        trace_endpoint += "/v1/traces"
    if _provider is None:
        _provider = TracerProvider(resource=Resource.create({"service.name": service_name}))
        _provider.add_span_processor(
            BatchSpanProcessor(OTLPSpanExporter(endpoint=trace_endpoint, timeout=5))
        )
        trace.set_tracer_provider(_provider)
    tracer = trace.get_tracer(service_name)
    propagator = TraceContextTextMapPropagator()

    @app.middleware("http")
    async def otel_request_span(request: Request, call_next):
        parent = propagator.extract(dict(request.headers))
        with tracer.start_as_current_span(f"{request.method} request", context=parent) as span:
            span.set_attribute("http.request.method", request.method)
            span.set_attribute("url.scheme", request.url.scheme)
            try:
                response = await call_next(request)
                route = request.scope.get("route")
                route_name = getattr(route, "path", None) or "unmatched"
                span.update_name(f"{request.method} {route_name}")
                span.set_attribute("http.route", route_name)
                span.set_attribute("http.response.status_code", response.status_code)
                if response.status_code >= 500:
                    span.set_status(trace.Status(trace.StatusCode.ERROR))
                trace_id = format(span.get_span_context().trace_id, "032x")
                response.headers.setdefault("X-Trace-ID", trace_id)
                return response
            except Exception:
                span.set_status(trace.Status(trace.StatusCode.ERROR))
                raise

    return True


def shutdown_tracing() -> None:
    if _provider is not None:
        try:
            _provider.force_flush(timeout_millis=1500)
            _provider.shutdown()
        except Exception:
            logger.exception("OpenTelemetry provider shutdown failed")
