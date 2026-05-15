# LLM Proxy

Transparent HTTP proxy for OpenAI-compatible LLM APIs.
Intercepts every request/response pair and ships a structured log to Elasticsearch — without adding latency to the critical path.

---

## Architecture

```
Your Agent
    │  base_url = http://localhost:8000/v1
    ▼
┌─────────────┐    httpx (async)    ┌─────────────────────┐
│  LLM Proxy  │ ──────────────────► │  Target LLM API     │
│  :8000      │ ◄────────────────── │  (Ollama / OpenAI / │
└─────────────┘                     │   LiteLLM / vLLM)   │
    │                               └─────────────────────┘
    │  asyncio.create_task (fire-and-forget)
    ▼
┌─────────────┐
│Elasticsearch│
│  :9200      │
└─────────────┘
```

The proxy adds **zero latency** on the hot path — ES indexing runs in a background task after the response is already on its way back to the caller.

---

## Configuration

All settings are environment variables. No config files needed.

| Variable | Default | Description |
|---|---|---|
| `TARGET_URL` | `http://localhost:11434` | Upstream LLM base URL (no trailing slash) |
| `ELASTIC_URL` | `http://localhost:9200` | Elasticsearch node URL |
| `ELASTIC_API_KEY` | *(unset)* | `id:api_key` string for ES auth. Omit for unauthenticated. |
| `ELASTIC_INDEX` | `llm-proxy-logs` | Index to write documents into |
| `STRICT_MODE` | `false` | `true` → return HTTP 500 if ES indexing fails. `false` → log error to stderr and return the LLM response anyway. |
| `PROXY_HOST` | `0.0.0.0` | Bind address |
| `PROXY_PORT` | `8000` | Listen port |
| `LOG_LEVEL` | `INFO` | Python logging level |

---

## Running

```bash
# Minimal (Ollama local, ES local, no auth, fail-open)
TARGET_URL=http://localhost:11434 \
ELASTIC_URL=http://localhost:9200 \
start-proxy

# OpenAI as upstream, ES Cloud, strict mode
TARGET_URL=https://api.openai.com \
ELASTIC_URL=https://my-cluster.es.io:443 \
ELASTIC_API_KEY=myid:mysecret \
STRICT_MODE=true \
start-proxy
```

---

## Redirecting Agents

Change **only** `base_url` (or equivalent) in your agent/SDK config.
Everything else — API keys for the LLM, model names, parameters — stays the same.

### OpenAI Python SDK

```python
from openai import OpenAI

client = OpenAI(
    api_key="sk-...",          # forwarded verbatim to the upstream
    base_url="http://localhost:8000/v1",  # ← only change
)
```

### LangChain / LangGraph

```python
from langchain_openai import ChatOpenAI

llm = ChatOpenAI(
    model="gpt-4o",
    openai_api_base="http://localhost:8000/v1",  # ← only change
    openai_api_key="sk-...",
)
```

### LlamaIndex

```python
from llama_index.llms.openai import OpenAI

llm = OpenAI(
    model="gpt-4o",
    api_base="http://localhost:8000/v1",  # ← only change
    api_key="sk-...",
)
```

### Ollama (via OpenAI-compat endpoint)

```python
from openai import OpenAI

client = OpenAI(
    api_key="ollama",   # arbitrary, Ollama ignores it
    base_url="http://localhost:8000/v1",
)
```

### Environment variable (works for any OpenAI-SDK-based tool)

```bash
export OPENAI_BASE_URL=http://localhost:8000/v1
```

---

## Elasticsearch Schema

Each document written to the index has the following shape:

```json
{
  "request_id":    "550e8400-e29b-41d4-a716-446655440000",
  "timestamp":     "2025-01-15T12:34:56.789Z",
  "method":        "POST",
  "path":          "/v1/chat/completions",
  "status_code":   200,
  "request_body":  { "model": "gpt-4o", "messages": [...] },
  "response_body": { "id": "chatcmpl-...", "choices": [...] }
}
```

`request_body` and `response_body` are parsed JSON objects when the payload is JSON, otherwise `null`.

### Recommended Index Mapping

```json
PUT /llm-proxy-logs
{
  "mappings": {
    "properties": {
      "request_id":    { "type": "keyword" },
      "timestamp":     { "type": "date" },
      "method":        { "type": "keyword" },
      "path":          { "type": "keyword" },
      "status_code":   { "type": "short" },
      "request_body":  { "type": "object", "dynamic": true },
      "response_body": { "type": "object", "dynamic": true }
    }
  }
}
```

---

## STRICT_MODE Semantics

| Mode | ES succeeds | ES fails |
|---|---|---|
| `STRICT_MODE=false` (default) | Response returned normally | Error logged to stderr; LLM response still returned |
| `STRICT_MODE=true` | Response returned normally | HTTP 500 returned to caller; LLM response discarded |

Use `STRICT_MODE=true` in compliance-critical environments where every interaction **must** be logged.

---

## Notes

- **Streaming / SSE**: responses with `Content-Type: text/event-stream` are passed through as `StreamingResponse`. The response body logged to ES will be the raw SSE bytes interpreted as JSON (likely `null` for chunked streams). For full token-level streaming logs you'd need to accumulate chunks — not implemented here to keep the hot path clean.
- **Auth passthrough**: the proxy does not inspect or strip `Authorization` headers; they are forwarded as-is to the upstream LLM.
- **No TLS termination**: run behind nginx/Caddy if you need HTTPS on the proxy side.
