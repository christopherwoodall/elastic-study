"""
LLM Proxy — transparent middleman for OpenAI-compatible APIs.

Intercepts requests, forwards them to the target LLM, and ships
request/response pairs to Elasticsearch asynchronously.
"""

import asyncio
import json
import logging
import os
import sys
import uuid
from datetime import UTC, datetime

import httpx
import uvicorn
from elasticsearch import AsyncElasticsearch
from fastapi import FastAPI, Request, Response
from fastapi.responses import JSONResponse, StreamingResponse

# ---------------------------------------------------------------------------
# Configuration (all from environment)
# ---------------------------------------------------------------------------

OPENROUTER_KEY: str | None = os.environ.get("OPENROUTER_API_KEY")

TARGET_URL: str = os.environ.get("TARGET_URL", "https://openrouter.ai/api/v1")
# Notable URLs:
# - OpenAI: https://api.openai.com/v1
# - OpenRouter: https://openrouter.ai/api/v1
# - Ollama: http://localhost:11434

ELASTIC_URL: str = os.environ.get("ELASTIC_URL", "http://localhost:9200")
ELASTIC_API_KEY: str | None = os.environ.get("ELASTIC_API_KEY")  # None → no auth
ELASTIC_INDEX: str = os.environ.get("ELASTIC_INDEX", "llm-proxy-logs")

PROXY_HOST: str = os.environ.get("PROXY_HOST", "0.0.0.0")
PROXY_PORT: int = int(os.environ.get("PROXY_PORT", "8000"))

STRICT_MODE: bool = os.environ.get("STRICT_MODE", "false").lower() == "true"
LOG_LEVEL: str = os.environ.get("LOG_LEVEL", "INFO").upper()

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------

logging.basicConfig(
    stream=sys.stderr,
    level=getattr(logging, LOG_LEVEL, logging.INFO),
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("llm-proxy")

# ---------------------------------------------------------------------------
# Elasticsearch client (module-level singleton, lazy-connected)
# ---------------------------------------------------------------------------


def _build_es_client() -> AsyncElasticsearch:
    kwargs: dict = {"hosts": [ELASTIC_URL]}
    if ELASTIC_API_KEY:
        kwargs["api_key"] = ELASTIC_API_KEY
    return AsyncElasticsearch(**kwargs)


es: AsyncElasticsearch = _build_es_client()

# ---------------------------------------------------------------------------
# FastAPI app
# ---------------------------------------------------------------------------

app = FastAPI(title="LLM Proxy", version="0.1.0", docs_url=None, redoc_url=None)


# ---------------------------------------------------------------------------
# Elasticsearch logging — fire-and-forget
# ---------------------------------------------------------------------------


async def _index_log(doc: dict) -> None:
    """
    Index a single document into Elasticsearch.
    Called via asyncio.create_task() so it never blocks the response path.
    """
    try:
        await es.index(index=ELASTIC_INDEX, id=doc["request_id"], document=doc)
    except Exception as exc:  # noqa: BLE001  (intentionally broad)
        msg = f"ES indexing failed for request_id={doc.get('request_id')}: {exc}"
        if STRICT_MODE:
            # Propagate so the route handler can return 500
            raise
        logger.error(msg)


def _fire_and_forget(doc: dict) -> None:
    """
    Schedule ES indexing without awaiting — caller gets the LLM response
    immediately regardless of how long ES takes (or whether it fails).

    In STRICT_MODE this still returns immediately; the task's exception
    will be logged by the event loop's exception handler since nobody
    awaits it. For strict failure semantics, use _await_log() instead.
    """
    task = asyncio.create_task(_index_log(doc))
    # Attach a callback so unhandled exceptions surface in stderr
    task.add_done_callback(_task_error_handler)


def _task_error_handler(task: asyncio.Task) -> None:
    if task.cancelled():
        return
    exc = task.exception()
    if exc:
        logger.error("Background ES task raised: %s", exc)


# ---------------------------------------------------------------------------
# Request forwarding
# ---------------------------------------------------------------------------

# Single shared async client — reuses connections (keep-alive)
_http_client: httpx.AsyncClient | None = None


def get_http_client() -> httpx.AsyncClient:
    global _http_client
    if _http_client is None or _http_client.is_closed:
        _http_client = httpx.AsyncClient(
            base_url=TARGET_URL,
            timeout=httpx.Timeout(300.0),  # LLMs can be slow
            follow_redirects=True,
            limits=httpx.Limits(max_keepalive_connections=20, max_connections=50),
        )
    return _http_client


def _strip_hop_by_hop(headers: dict) -> dict:
    """Remove headers that must not be forwarded."""
    hop_by_hop = {
        "connection",
        "keep-alive",
        "proxy-authenticate",
        "proxy-authorization",
        "te",
        "trailers",
        "transfer-encoding",
        "upgrade",
        "content-length",
        "host",
    }
    return {k: v for k, v in headers.items() if k.lower() not in hop_by_hop}


def _try_parse_json(raw: bytes) -> dict | list | None:
    if not raw:
        return None
    try:
        return json.loads(raw)
    except (json.JSONDecodeError, UnicodeDecodeError):
        return None


# ---------------------------------------------------------------------------
# Core proxy route — catches everything
# ---------------------------------------------------------------------------


@app.api_route(
    "/{path:path}",
    methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS", "HEAD"],
)
async def proxy(path: str, request: Request) -> Response:
    request_id = str(uuid.uuid4())
    timestamp = datetime.now(UTC).isoformat()

    # --- Read request body ---
    body_bytes: bytes = await request.body()
    request_body = _try_parse_json(body_bytes)

    # --- Clean the path to prevent double /v1/v1/ ---
    clean_path = path.lstrip("/")
    if clean_path.startswith("v1/"):
        clean_path = clean_path[3:]  # Remove the leading 'v1/'

    # --- Build forwarded request ---
    forward_headers = _strip_hop_by_hop(dict(request.headers))
    forward_url = f"/{clean_path}"
    if request.url.query:
        forward_url = f"{forward_url}?{request.url.query}"
    # Inject the API key from the environment (if set) — this allows the proxy to work with OpenRouter without clients needing to set their own keys
    if OPENROUTER_KEY:
        forward_headers["authorization"] = f"Bearer {OPENROUTER_KEY}"

    client = get_http_client()

    # --- Forward ---
    try:
        upstream: httpx.Response = await client.request(
            method=request.method,
            url=forward_url,
            headers=forward_headers,
            content=body_bytes,
        )
    except httpx.RequestError as exc:
        logger.error("Upstream request failed: %s", exc)
        return JSONResponse(
            status_code=502,
            content={"error": "upstream_unreachable", "detail": str(exc)},
        )

    response_body = _try_parse_json(upstream.content)

    # --- Build ES document ---
    doc = {
        "request_id": request_id,
        "timestamp": timestamp,
        "method": request.method,
        "path": f"/{clean_path}",
        "status_code": upstream.status_code,
        "request_body": request_body,
        "response_body": response_body,
    }

    # --- Log to ES ---
    if STRICT_MODE:
        # Await so failures can influence the HTTP response
        try:
            await _index_log(doc)
        except Exception as exc:  # noqa: BLE001
            logger.error("STRICT_MODE: ES logging failed, returning 500. %s", exc)
            return JSONResponse(
                status_code=500,
                content={"error": "logging_failure", "detail": str(exc)},
            )
    else:
        _fire_and_forget(doc)

    # --- Return upstream response verbatim ---
    response_headers = _strip_hop_by_hop(dict(upstream.headers))

    # Stream-through for chunked / SSE responses
    content_type = upstream.headers.get("content-type", "")
    if "text/event-stream" in content_type:
        return StreamingResponse(
            content=_aiter_bytes(upstream.content),
            status_code=upstream.status_code,
            headers=response_headers,
            media_type=content_type,
        )

    return Response(
        content=upstream.content,
        status_code=upstream.status_code,
        headers=response_headers,
        media_type=content_type or None,
    )


async def _aiter_bytes(data: bytes):
    """Wrap a bytes blob as an async generator for StreamingResponse."""
    yield data


# ---------------------------------------------------------------------------
# Lifespan: graceful shutdown
# ---------------------------------------------------------------------------


@app.on_event("startup")
async def startup() -> None:
    logger.info(
        "LLM Proxy starting — target=%s  elastic=%s  strict=%s  port=%d",
        TARGET_URL,
        ELASTIC_URL,
        STRICT_MODE,
        PROXY_PORT,
    )


@app.on_event("shutdown")
async def shutdown() -> None:
    logger.info("Shutting down — closing ES and HTTP clients")
    await es.close()
    if _http_client and not _http_client.is_closed:
        await _http_client.aclose()


# ---------------------------------------------------------------------------
# CLI entry point (referenced in pyproject.toml)
# ---------------------------------------------------------------------------


def start() -> None:
    uvicorn.run(
        "proxy.proxy:app",
        host=PROXY_HOST,
        port=PROXY_PORT,
        log_level=LOG_LEVEL.lower(),
        reload=False,
    )


if __name__ == "__main__":
    start()
