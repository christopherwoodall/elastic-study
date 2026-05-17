# Elastic Study

Transparent HTTP proxy for OpenAI-compatible LLM APIs.
Intercepts every request/response pair and ships a structured log to Elasticsearch — without adding latency to the critical path.

[Demo Video](https://github.com/user-attachments/assets/ba44e17f-3407-4a49-bca0-9138b8de235f)

## Getting Started

**Step 1.** Install dependencies

Requires [`uv`](https://github.com/astral-sh/uv). Install with `pip install uv` if needed.

```bash
uv sync --all-extras
source .venv/bin/activate
```

**Step 2.** Configure environment

Copy or create a `.env` file with your credentials:

```env
OPENROUTER_API_KEY=your_key_here
TARGET_URL=https://openrouter.ai/api/v1   # default; change to http://localhost:11434 for Ollama
ELASTIC_URL=http://localhost:9200          # default
```

**Step 3.** Start Elasticsearch + Kibana

```bash
docker compose up -d --force-recreate
```

**Step 4.** Start the proxy

```bash
uv run --env-file .env start-proxy
```

Proxy listens on `http://localhost:8000`. Verify with:

```bash
curl -o /dev/null -s -w "%{http_code}\n" -X POST http://localhost:8000/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{"model": "moonshotai/kimi-k2.5", "messages": [{"role": "user", "content": "Hello"}]}'
```

Expected: `200`

**Step 5.** Run an OpenCode agent through the proxy

The `openrouter-audit` provider (defined in `opencode.jsonc`) routes through the proxy at `localhost:8000` instead of calling OpenRouter directly — this is what triggers logging to Elasticsearch.

```bash
uv run opencode \
  run \
  --env-file .env \
  --dir ./workspace \
  --model openrouter-audit/moonshotai/kimi-k2.5 \
  "Create a simple game called game.py where the player has to guess a number between 1 and 10. The game should provide feedback on whether the guess is too high, too low, or correct."
```

**Step 6.** View logs

- **Kibana:** http://localhost:5601 → Create a data view for index `llm-proxy-logs`
- **Elasticsearch direct:** `curl http://localhost:9200/llm-proxy-logs/_search?pretty`

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

## Notes

- **Streaming / SSE**: responses with `Content-Type: text/event-stream` are passed through as `StreamingResponse`. The response body logged to ES will be the raw SSE bytes interpreted as JSON (likely `null` for chunked streams). For full token-level streaming logs you'd need to accumulate chunks — not implemented here to keep the hot path clean.
- **Auth passthrough**: the proxy does not inspect or strip `Authorization` headers; they are forwarded as-is to the upstream LLM.
- **No TLS termination**: run behind nginx/Caddy if you need HTTPS on the proxy side.
