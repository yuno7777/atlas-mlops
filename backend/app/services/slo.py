from __future__ import annotations

from collections import defaultdict

from prometheus_client import REGISTRY

from app.core.config import get_settings
from app.schemas.modelops import SLOSnapshot

AVAILABILITY_TARGET = 0.995
LATENCY_TARGET_MS = 500.0
LATENCY_TARGET = 0.95


def system_slo_snapshot() -> SLOSnapshot:
    requests = 0
    server_errors = 0
    buckets: dict[float, int] = defaultdict(int)
    histogram_count = 0
    for family in REGISTRY.collect():
        for sample in family.samples:
            if sample.name == "atlas_http_requests_total":
                count = int(sample.value)
                requests += count
                if str(sample.labels.get("status", "")).startswith("5"):
                    server_errors += count
            elif sample.name == "atlas_http_request_duration_seconds_bucket":
                try:
                    bound = float(sample.labels["le"])
                except (KeyError, ValueError):
                    continue
                buckets[bound] += int(sample.value)
            elif sample.name == "atlas_http_request_duration_seconds_count":
                histogram_count += int(sample.value)

    availability = (requests - server_errors) / requests if requests else None
    budget = (
        server_errors / (requests * (1 - AVAILABILITY_TARGET)) * 100
        if requests and AVAILABILITY_TARGET < 1
        else None
    )
    latency_compliant = buckets.get(LATENCY_TARGET_MS / 1000, 0)
    latency_sli = min(latency_compliant / histogram_count, 1.0) if histogram_count else None
    p95 = None
    if histogram_count:
        threshold = histogram_count * 0.95
        cumulative = 0
        for bound in sorted(buckets):
            cumulative = buckets[bound]
            if cumulative >= threshold:
                p95 = bound * 1000 if bound != float("inf") else None
                break
    if not requests:
        status = "no_data"
    elif (availability or 0) < AVAILABILITY_TARGET or (latency_sli or 0) < LATENCY_TARGET:
        status = "breached"
    elif budget is not None and budget >= 75:
        status = "at_risk"
    else:
        status = "met"
    endpoint = get_settings().otel_exporter_otlp_endpoint
    return SLOSnapshot(
        window="process lifetime (Prometheus in-process registry)",
        requests=requests,
        server_errors=server_errors,
        availability=availability,
        availability_target=AVAILABILITY_TARGET,
        availability_error_budget_percent_used=budget,
        latency_sli=latency_sli,
        latency_target_ms=LATENCY_TARGET_MS,
        latency_target=LATENCY_TARGET,
        p95_latency_ms=p95,
        status=status,
        trace_export_enabled=bool(endpoint),
        trace_export_endpoint=endpoint,
    )
