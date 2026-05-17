import uuid
from datetime import UTC, datetime

import httpx
from fastapi import APIRouter, Request, Response
from fastapi.responses import JSONResponse, StreamingResponse

from agent_proxy.config import OPENROUTER_KEY, STRICT_MODE
from agent_proxy.logger import logger
from agent_proxy.services.elastic import es_service
from agent_proxy.services.proxy import http_proxy
from agent_proxy.utils import parse_body, strip_hop_by_hop

router = APIRouter()


# ---------------------------------------------------------------------------
# Private Helper Functions
# ---------------------------------------------------------------------------


def _extract_latest_user_prompt(request_body: any, logging=False) -> str | None:
    """Extracts the most recent user message from the payload."""
    if not isinstance(request_body, dict):
        return None

    messages = request_body.get("messages", [])
    if not isinstance(messages, list):
        return None

    if logging:
        import json
        import os
        from datetime import datetime

        log_file_path = "./logs/payload_logs.txt"

        os.makedirs("./logs", exist_ok=True)

        with open(log_file_path, "a", encoding="utf-8") as f:
            f.write(f"--- LOG ENTRY: {datetime.now().isoformat()} ---\n")
            f.write(json.dumps(messages, indent=2, ensure_ascii=False))
            f.write("\n\n")

    # Iterate backwards to find the last 'user' role
    for msg in reversed(messages):
        if isinstance(msg, dict) and msg.get("role") == "user":
            content = msg.get("content")

            # # TODO: Handle vision models (array of objects)
            # if isinstance(content, list):
            #     return " ".join(
            #         part.get("text", "")
            #         for part in content
            #         if isinstance(part, dict) and part.get("type") == "text"
            #     )

            return str(content) if content is not None else None

    return None


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
    doc_template: dict,
    headers: dict,
    content_type: str,
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
        doc_template["status_code"] = upstream_response.status_code
        doc_template["response_body"] = parse_body(bytes(accumulated_bytes))
        es_service.fire_and_forget(doc_template)

    return StreamingResponse(
        content=stream_and_log(),
        status_code=upstream_response.status_code,
        headers=headers,
        media_type=content_type,
    )


async def _handle_standard(
    upstream_response: httpx.Response,
    doc_template: dict,
    headers: dict,
    content_type: str,
) -> Response | JSONResponse:
    """Handles standard JSON responses and STRICT_MODE logging."""
    await upstream_response.aread()  # Read full body into memory

    # # TODO: Inject DLP
    # restored_text = dlp_service.deanonymize(request_id, response_text)
    # restored_bytes = restored_text.encode("utf-8")

    doc_template["status_code"] = upstream_response.status_code
    doc_template["response_body"] = parse_body(upstream_response.content)

    if STRICT_MODE:
        try:
            await es_service.index_log(doc_template)
        except Exception as exc:
            logger.error("STRICT_MODE: ES logging failed, returning 500. %s", exc)
            return JSONResponse(
                status_code=500,
                content={"error": "logging_failure", "detail": str(exc)},
            )
    else:
        es_service.fire_and_forget(doc_template)

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
    # 1. Parse Context
    request_id = str(uuid.uuid4())
    timestamp = datetime.now(UTC).isoformat()
    body_bytes: bytes = await request.body()
    request_body = parse_body(body_bytes)

    # # TODO: DLP injection
    # if isinstance(request_body, dict):
    #     # Overwrite body_bytes with the redacted version
    #     body_bytes = dlp_service.anonymize(request_id, request_body)
    #     # (Optional) update request_body so Elasticsearch logs the redacted version
    #     request_body = parse_body(body_bytes)

    # 2. Prepare Upstream Request
    forward_url, clean_path = _build_forward_url(path, request.url.query)
    forward_headers = strip_hop_by_hop(dict(request.headers))
    if OPENROUTER_KEY:
        forward_headers["authorization"] = f"Bearer {OPENROUTER_KEY}"

    # 3. Base Document for Elasticsearch
    doc_template = {
        "request_id": request_id,
        "timestamp": timestamp,
        "method": request.method,
        "path": f"/{clean_path}",
        # "latest_user_prompt": _extract_latest_user_prompt(request_body),
        "request_body": request_body,
    }

    # 4. Execute Upstream Request
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

    # 5. Route Response (Stream vs Standard)
    response_headers = strip_hop_by_hop(dict(upstream_response.headers))
    content_type = upstream_response.headers.get("content-type", "")

    if "text/event-stream" in content_type:
        return await _handle_streaming(
            upstream_response, doc_template, response_headers, content_type
        )

    return await _handle_standard(
        upstream_response, doc_template, response_headers, content_type
    )
