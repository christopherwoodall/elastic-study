import json


def try_parse_json(raw: bytes) -> dict | list | None:
    if not raw:
        return None
    try:
        return json.loads(raw)
    except (json.JSONDecodeError, UnicodeDecodeError):
        return raw.decode("utf-8", errors="replace")


def parse_body(raw: bytes) -> dict | list | str | None:
    if not raw:
        return None

    text = raw.decode("utf-8", errors="replace")

    # 1. Try standard JSON first (Non-streaming)
    try:
        return json.loads(text)
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

    # 3. Ultimate Fallback
    return text


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
