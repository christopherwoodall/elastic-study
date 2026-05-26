import os
import socket
import time
from datetime import UTC, datetime
from typing import Any

# Evaluate static Resource Attributes once at startup
_RESOURCE_ATTRIBUTES = {
    "host.name": socket.gethostname(),
    "service.environment": os.environ.get("ENVIRONMENT", "development"),
    "service.name": "agent-proxy",
}


def build_otel_ecs_document(
    request_id: str,
    method: str,
    path: str,
    start_time: float,
    request_body: Any = None,
    response_body: Any = None,
    status_code: int | None = None,
    client_ip: str | None = None,
    user_agent: str | None = None,
    latest_user_prompt: str | None = None,
    last_message: str | None = None,
    usage: dict[str, Any] | None = None,
) -> dict:
    """Builds a flat, OpenTelemetry/ECS compliant dictionary for Elasticsearch."""

    # OTel records duration in nanoseconds
    duration_ns = int((time.perf_counter() - start_time) * 1_000_000_000)

    # Base OTel & ECS mappings
    doc = {
        "@timestamp": datetime.now(UTC).isoformat(),
        "event.id": request_id,
        "event.duration": duration_ns,
        "http.request.method": method,
        "url.path": path,
        "http.request.body.content": request_body,
        "http.response.body.content": response_body,
        "http.response.status_code": status_code,
        "client.address": client_ip,
        "user_agent.original": user_agent,
    }

    # Merge GenAI Conventions if data is present
    if latest_user_prompt:
        doc["gen_ai.prompt"] = latest_user_prompt
    if last_message:
        doc["gen_ai.completion"] = last_message
    if usage:
        doc["gen_ai.usage.input_tokens"] = usage.get("prompt_tokens")
        doc["gen_ai.usage.output_tokens"] = usage.get("completion_tokens")

    # Merge static Resource Attributes
    doc.update(_RESOURCE_ATTRIBUTES)

    # Filter out None values to keep the Elastic document clean
    return {k: v for k, v in doc.items() if v is not None}
