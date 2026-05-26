import time
import uuid
from datetime import UTC, datetime

import httpx
from fastapi import APIRouter, Request, Response
from fastapi.responses import JSONResponse, StreamingResponse

from agent_proxy.config import OPENROUTER_KEY, STRICT_MODE
from agent_proxy.logger import logger

# from agent_proxy.models import ProxyLogDocument
from agent_proxy.models import build_otel_ecs_document
from agent_proxy.parsers import (
    _extract_last_message,
    _extract_latest_user_prompt,
    _extract_usage,
)
from agent_proxy.services.elastic import es_service
from agent_proxy.services.proxy import http_proxy
from agent_proxy.utils import parse_body, strip_hop_by_hop

router = APIRouter()


# ---------------------------------------------------------------------------
# Private Helper Functions
# ---------------------------------------------------------------------------
def _build_forward_url(path: str, query_params: str) -> tuple[str, str]:
    """Sanitizes the path and reconstructs the target URL."""
    clean_path = path.lstrip("/")
    if clean_path.startswith("v1/"):
        clean_path = clean_path[3:]

    forward_url = f"/{clean_path}"
    if query_params:
        forward_url = f"{forward_url}?{query_params}"

    return forward_url, clean_path


async def _handle_streaming(
    upstream_response: httpx.Response,
    request_state: dict,
    headers: dict,
    content_type: str,
    start_time: float,
) -> StreamingResponse:
    """Handles Server-Sent Events (SSE) streaming and background logging."""

    async def stream_and_log():
        accumulated_bytes = bytearray()

        # TODO: Inject DLP is option is enabled

        # Yield chunks to the client immediately
        async for chunk in upstream_response.aiter_bytes():
            accumulated_bytes.extend(chunk)
            yield chunk

        # When the stream finishes, reconstruct and log
        parsed_response = parse_body(bytes(accumulated_bytes))

        otel_doc = build_otel_ecs_document(
            **request_state,
            response_body=parsed_response,
            status_code=upstream_response.status_code,
            usage=_extract_usage(parsed_response),
            last_message=_extract_last_message(parsed_response),
        )
        # doc_template.usage = _extract_usage(parsed_response)
        # doc_template.duration_ms = round((time.perf_counter() - start_time) * 1000, 2)
        # doc_template.status_code = upstream_response.status_code
        # doc_template.response_body = parsed_response

        es_service.fire_and_forget(otel_doc)
        # es_service.fire_and_forget(doc_template.to_dict())

    return StreamingResponse(
        content=stream_and_log(),
        status_code=upstream_response.status_code,
        headers=headers,
        media_type=content_type,
    )


async def _handle_standard(
    upstream_response: httpx.Response,
    request_state: dict,
    headers: dict,
    content_type: str,
    start_time: float,
) -> Response | JSONResponse:
    """Handles standard JSON responses and STRICT_MODE logging."""
    await upstream_response.aread()  # Read full body into memory

    parsed_response = parse_body(upstream_response.content)

    # # TODO: Inject DLP
    # restored_text = dlp_service.deanonymize(request_id, response_text)
    # restored_bytes = restored_text.encode("utf-8")

    otel_doc = build_otel_ecs_document(
        **request_state,
        response_body=parsed_response,
        status_code=upstream_response.status_code,
        usage=_extract_usage(parsed_response),
        last_message=_extract_last_message(parsed_response),
    )

    if STRICT_MODE:
        try:
            await es_service.index_log(otel_doc)
        except Exception as exc:
            logger.error("STRICT_MODE: ES logging failed, returning 500. %s", exc)
            return JSONResponse(
                status_code=500,
                content={"error": "logging_failure", "detail": str(exc)},
            )
    else:
        es_service.fire_and_forget(otel_doc)

    return Response(
        content=upstream_response.content,
        status_code=upstream_response.status_code,
        headers=headers,
        media_type=content_type or None,
    )


# ---------------------------------------------------------------------------
# Main Orchestrator Route
# ---------------------------------------------------------------------------
@router.api_route(
    "/{path:path}",
    methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS", "HEAD"],
)
async def proxy_route(path: str, request: Request) -> Response:
    start_time = time.perf_counter()

    # 1. Parse Context
    request_id = str(uuid.uuid4())
    _timestamp = datetime.now(UTC).isoformat()
    body_bytes: bytes = await request.body()
    request_body = parse_body(body_bytes)

    # 2. Extract Network / Enrichment Data
    # Safely get the real IP if behind a proxy/load balancer
    forwarded_for = request.headers.get("x-forwarded-for")
    if forwarded_for:
        client_ip = forwarded_for.split(",")[0].strip()
    else:
        client_ip = request.client.host if request.client else None

    # # TODO: DLP injection
    # if isinstance(request_body, dict):
    #     # Overwrite body_bytes with the redacted version
    #     body_bytes = dlp_service.anonymize(request_id, request_body)
    #     # (Optional) update request_body so Elasticsearch logs the redacted version
    #     request_body = parse_body(body_bytes)

    # 3. Prepare Upstream Request
    forward_url, clean_path = _build_forward_url(path, request.url.query)
    forward_headers = strip_hop_by_hop(dict(request.headers))
    if OPENROUTER_KEY:
        forward_headers["authorization"] = f"Bearer {OPENROUTER_KEY}"

    # 4. Base Document for Elasticsearch
    request_state = {
        "request_id": request_id,
        "method": request.method,
        "path": f"/{clean_path}",
        "start_time": start_time,
        "request_body": request_body,
        "client_ip": client_ip,
        "user_agent": request.headers.get("user-agent"),
        "latest_user_prompt": _extract_latest_user_prompt(request_body),
    }
    # doc_template = ProxyLogDocument(
    #     request_id=request_id,
    #     timestamp=timestamp,
    #     method=request.method,
    #     path=f"/{clean_path}",
    #     request_body=request_body,
    #     # Enrichment Fields populated here:
    #     hostname=socket.gethostname(),
    #     environment=os.environ.get("ENVIRONMENT", "development"),
    #     client_ip=client_ip,
    #     user_agent=request.headers.get("user-agent"),
    #     # Custom Extractors
    #     latest_user_prompt=_extract_latest_user_prompt(request_body),
    #     last_message=_extract_last_message(request_body),
    #     usage=_extract_usage(request_body),
    # )

    # 5. Execute Upstream Request
    client = http_proxy.get()
    try:
        req = client.build_request(
            method=request.method,
            url=forward_url,
            headers=forward_headers,
            content=body_bytes,
        )
        upstream_response = await client.send(req, stream=True)

    except httpx.RequestError as exc:
        logger.error("Upstream request failed: %s", exc)
        return JSONResponse(
            status_code=502,
            content={"error": "upstream_unreachable", "detail": str(exc)},
        )

    # 6. Route Response (Stream vs Standard)
    response_headers = strip_hop_by_hop(dict(upstream_response.headers))
    content_type = upstream_response.headers.get("content-type", "")

    if "text/event-stream" in content_type:
        return await _handle_streaming(
            upstream_response, request_state, response_headers, content_type, start_time
        )

    return await _handle_standard(
        upstream_response, request_state, response_headers, content_type, start_time
    )
