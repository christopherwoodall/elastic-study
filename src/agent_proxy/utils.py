import json

def strip_hop_by_hop(headers: dict) -> dict:
    """Remove headers that must not be forwarded."""
    hop_by_hop = {
        "connection", "keep-alive", "proxy-authenticate",
        "proxy-authorization", "te", "trailers",
        "transfer-encoding", "upgrade", "content-length", "host"
    }
    return {k: v for k, v in headers.items() if k.lower() not in hop_by_hop}

def try_parse_json(raw: bytes) -> dict | list | None:
    if not raw:
        return None
    try:
        return json.loads(raw)
    except (json.JSONDecodeError, UnicodeDecodeError):
        return None

async def aiter_bytes(data: bytes):
    """Wrap a bytes blob as an async generator for StreamingResponse."""
    yield data
