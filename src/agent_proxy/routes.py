import uuid
from datetime import UTC, datetime

import httpx
from fastapi import APIRouter, Request, Response
from fastapi.responses import JSONResponse, StreamingResponse

from .config import OPENROUTER_KEY, STRICT_MODE
from .logger import logger
from .services.elastic import es_service
from .services.proxy import http_proxy
from .utils import parse_body, strip_hop_by_hop

router = APIRouter()


@router.api_route(
    "/{path:path}",
    methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS", "HEAD"],
)
async def proxy_route(path: str, request: Request) -> Response:
    request_id = str(uuid.uuid4())
    timestamp = datetime.now(UTC).isoformat()

    body_bytes: bytes = await request.body()
    request_body = parse_body(body_bytes)

    clean_path = path.lstrip("/")
    if clean_path.startswith("v1/"):
        clean_path = clean_path[3:]

    forward_headers = strip_hop_by_hop(dict(request.headers))
    forward_url = f"/{clean_path}"
    if request.url.query:
        forward_url = f"{forward_url}?{request.url.query}"

    if OPENROUTER_KEY:
        forward_headers["authorization"] = f"Bearer {OPENROUTER_KEY}"

    client = http_proxy.get()

    # Base ES Document
    doc_template = {
        "request_id": request_id,
        "timestamp": timestamp,
        "method": request.method,
        "path": f"/{clean_path}",
        "request_body": request_body,
    }

    try:
        # Build the request but DO NOT download the body yet
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

    response_headers = strip_hop_by_hop(dict(upstream_response.headers))
    content_type = upstream_response.headers.get("content-type", "")

    # ---------------------------------------------------------
    # Handle Streaming Responses (SSE)
    # ---------------------------------------------------------
    if "text/event-stream" in content_type:

        async def stream_and_log():
            accumulated_bytes = bytearray()

            # 1. Yield chunks to the client immediately
            async for chunk in upstream_response.aiter_bytes():
                accumulated_bytes.extend(chunk)
                yield chunk

            # 2. When the stream finishes, reconstruct and log
            doc_template["status_code"] = upstream_response.status_code
            doc_template["response_body"] = parse_body(bytes(accumulated_bytes))
            es_service.fire_and_forget(doc_template)

        return StreamingResponse(
            content=stream_and_log(),
            status_code=upstream_response.status_code,
            headers=response_headers,
            media_type=content_type,
        )

    # ---------------------------------------------------------
    # Handle Standard JSON Responses
    # ---------------------------------------------------------
    await upstream_response.aread()  # Read full body into memory

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
        headers=response_headers,
        media_type=content_type or None,
    )
