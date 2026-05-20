import json


def strip_hop_by_hop(headers: dict) -> dict:
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


async def aiter_bytes(data: bytes):
    """Wrap a bytes blob as an async generator for StreamingResponse."""
    yield data


def try_parse_json(raw: bytes) -> dict | None:
    """Strictly returns a dict or None. Wraps primitives."""
    if not raw:
        return None
    try:
        parsed = json.loads(raw)
        if isinstance(parsed, dict):
            return parsed
        return {"raw_json_value": parsed}
    except (json.JSONDecodeError, UnicodeDecodeError):
        return {"raw_text": raw.decode("utf-8", errors="replace")}


def parse_body(raw: bytes) -> dict | None:
    """
    Safely parses byte payloads into dictionaries.
    Guarantees a dict return type to prevent Elasticsearch mapping conflicts.
    """
    if not raw:
        return None

    text = raw.decode("utf-8", errors="replace")

    # 1. Try standard JSON first (Non-streaming)
    try:
        parsed = json.loads(text)
        # Ensure it is actually an object. If the API returned a list or string, wrap it.
        if isinstance(parsed, dict):
            return parsed
        return {"raw_json_value": parsed}
    except json.JSONDecodeError:
        pass

    # 2. Try parsing and reconstructing Server-Sent Events (Streaming)
    if "data: " in text:
        content = ""
        reasoning = ""
        usage = None
        model = ""
        req_id = ""

        for line in text.splitlines():
            line = line.strip()
            # Ignore empty lines, SSE keep-alives, and the DONE signal
            if not line or line.startswith(":") or line == "data: [DONE]":
                continue

            if line.startswith("data: "):
                try:
                    chunk = json.loads(line[6:])

                    if not req_id:
                        req_id = chunk.get("id", "")
                    if not model:
                        model = chunk.get("model", "")

                    # Extract text and reasoning deltas
                    choices = chunk.get("choices", [])
                    if choices:
                        delta = choices[0].get("delta", {})

                        c = delta.get("content")
                        if isinstance(c, str):
                            content += c

                        r = delta.get("reasoning")  # For Kimi / DeepSeek
                        if isinstance(r, str):
                            reasoning += r

                    # Capture token usage if present (usually in the final chunk)
                    if "usage" in chunk:
                        usage = chunk["usage"]

                except Exception:
                    pass  # Ignore malformed chunks and keep going

        # If we successfully parsed any content, construct a standard LLM payload
        if content or reasoning:
            message = {"role": "assistant", "content": content}
            if reasoning:
                message["reasoning"] = reasoning

            reconstructed = {
                "id": req_id,
                "model": model,
                "choices": [{"index": 0, "message": message, "finish_reason": "stop"}],
                "streamed": True,  # Helpful flag for your logs
            }
            if usage:
                reconstructed["usage"] = usage

            return reconstructed

    # 3. Ultimate Fallback: Wrap raw text in a dictionary
    return {"raw_text": text}