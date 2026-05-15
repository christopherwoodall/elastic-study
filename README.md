# Elastic Study

Learning experiment: Elasticsearch as a logging backend for an LLM proxy.

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
uv run start-proxy
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
  --dir ./workspace \
  --model openrouter-audit/moonshotai/kimi-k2.5 \
  "Create a simple game called game.py where the player has to guess a number between 1 and 10. The game should provide feedback on whether the guess is too high, too low, or correct."
```

**Step 6.** View logs

- **Kibana:** http://localhost:5601 → Create a data view for index `llm-proxy-logs`
- **Elasticsearch direct:** `curl http://localhost:9200/llm-proxy-logs/_search?pretty`

---

For full proxy configuration options (strict mode, auth, ports), see [proxy/README.md](src/proxy/README.md).
