# Elastic MCP Server

A remote Server-Sent Events (SSE) Model Context Protocol (MCP) engine designed to give LLM agents dynamic introspection and querying capabilities over your Elasticsearch data layer.
Built as a hybrid architecture, it simultaneously exposes a human-friendly FastAPI Swagger UI for manual testing and a persistent SSE transport stream for seamless OpenCode AI integration, complete with robust retry mechanics for database resiliency.

---

## Getting Started

**Step 1.** Install dependencies

Ensure your virtual environment is updated with the new web and MCP dependencies (`mcp`, `fastapi`, `tenacity`).

```bash
uv sync --all-extras
source .venv/bin/activate
```

**Step 2.** Configure environment

Ensure your `.env` file points to your Elasticsearch instance.

```env
ELASTIC_URL=http://localhost:9200
```

**Step 3.** Start Elasticsearch

Ensure your data layer is online and ready to accept connections.

```bash
docker compose up -d elasticsearch
```

**Step 4.** Start the Hybrid MCP Server

Launch the standalone FastAPI + MCP server. It defaults to port `8001` to avoid conflicting with the main LLM proxy.

```bash
uv run --env-file .env start-mcp
```

**Step 5.** Manual Testing (Swagger UI)

Before attaching an agent, you can manually verify the tools and Elasticsearch connectivity. Open your browser and navigate to the built-in Swagger UI:

* **URL:** [http://localhost:8001/docs](https://www.google.com/search?q=http://localhost:8001/docs)
* Try executing the `/api/indices` route to view available target indices.
* Try passing a JSON Query DSL to the `/api/analytics/{index_name}` route to test search logic.

**Step 6.** Connect your OpenCode Agent

Update your `opencode.jsonc` configuration file to attach the remote SSE endpoint to your agent workspace.

```json
  "mcp": {
    "elastic-analytics": {
      "type": "sse",
      "url": "http://localhost:8001/sse",
      "enabled": true
    }
  }
```

Now, when you prompt your agent, it can automatically discover the index mappings and run complex analytics against your cluster:

**Ensure you have ran the `log-replay` command before querying the logs so that the `logs-endpoint.events-simulated` index is available.**


**Attack Chain Hunt**
```bash
uv run --env-file .env \
  opencode run \
    --dir ./workspace \
    --model openrouter-audit/moonshotai/kimi-k2.5 \
    "Hunt through the 'logs-endpoint.events-simulated' index for a Log4Shell (CVE-2021-44228) compromise. First, check the mappings to understand the ECS schema. Then, look for 'jndi:ldap' strings in network events, and correlate that with any suspicious child processes spawned by a Java process in the Sysmon events. Summarize the attack chain you find. Write a report and include kibana queries to validate your findings."
```

**Initial Access Investigation**
```bash
uv run --env-file .env \
  opencode run \
    --dir ./workspace \
    --model openrouter-audit/moonshotai/kimi-k2.5 \
    "Analyze the network logs in the 'logs-endpoint.events-simulated' index. Identify the source IP addresses that attempted a Log4Shell exploit by sending 'jndi' strings in their payloads. What destination ports were targeted the most? Write a report and include kibana queries to validate your findings."
```

**Post Exploitation Analysis**
```bash
uv run --env-file .env \
  opencode run \
    --dir ./workspace \
    --model openrouter-audit/moonshotai/kimi-k2.5 \
    "Investigate the Sysmon process creation logs in the 'logs-endpoint.events-simulated' index. Are there any instances where 'java.exe' or 'java' spawned unexpected binaries like 'cmd.exe', 'sh', 'wget', or 'curl'? List the suspicious command lines executed. Write a report and include kibana queries to validate your findings."
```

**Step 7. Validation**

You should be able to validate the agent's responses in the Kibana dashboard with queries like:

```kql
source.ip : "192.168.2.6" and destination.port : 8080 and "*jndi:ldap*"

process.name : ("java" or "java.exe") and destination.port : 1389

process.parent.name : ("java" or "java.exe") and process.name : ("cmd.exe" or "sh" or "bash")
```

You can also use the Kibana Dev Tools console to directly query the indices and verify the data:

```json
GET logs-endpoint.events-simulated/_search
{
  "size": 2,
  "query": {
    "bool": {
      "must": [
        { "match": { "source.ip": "192.168.2.6" } },
        { "match": { "destination.port": 8080 } },
        { "wildcard": { "user_agent.original": "*jndi:ldap*" } }
      ]
    }
  },
  "_source": [
    "source.ip",
    "destination.ip",
    "destination.port",
    "network.transport",
    "url.path",
    "user_agent.original"
  ]
}
```

---

## Configuration

All settings are controlled via environment variables.

| Variable | Default | Description |
| --- | --- | --- |
| `ELASTIC_URL` | `http://localhost:9200` | Elasticsearch node URL. |
| `MCP_HOST` | `0.0.0.0` | Bind address for the hybrid server. |
| `MCP_PORT` | `8001` | Listen port for the UI and SSE stream. |

---

## Architecture

```text
                      ┌─────────────────────────┐
                      │  OpenCode Agent (LLM)   │
                      └───────────┬─────────────┘
                                  │ (SSE Protocol via /sse)
                                  ▼
┌─────────────────┐    ┌─────────────────────────┐    ┌─────────────────┐
│ Human Developer │◄───┤  Hybrid FastAPI Server  ├───►│  Elasticsearch  │
│ (Swagger UI)    │───►│  (MCP Tools & Retries)  │    │  :9200          │
└─────────────────┘    └─────────────────────────┘    └─────────────────┘

```

### Features

* **Hybrid Execution:** Exposes standard REST endpoints (`/api/*`) for human debugging via Swagger UI, while simultaneously serving an `/sse` stream for the MCP protocol.
* **Agent Introspection:** Enables an LLM to dynamically call `list_indices` and `get_mappings` to understand your database schema without requiring hardcoded prompts.
* **Resilient Operations:** All core Elasticsearch queries are wrapped in `tenacity` retry blocks with exponential backoff, shielding the agent from transient cluster unavailability.
* **Decoupled Scaling:** Runs as a completely independent process from the LLM proxy, allowing you to host the MCP server adjacent to your database while the agent runs locally.

---

## Available MCP Tools

The server exposes the following tools to the connected agent:

1. **`list_indices`**: Returns a list of all available non-system indices in the cluster.
2. **`get_mappings`**: Requires an `index_name`. Returns the raw JSON schema (field names and data types) so the LLM can construct valid queries.
3. **`run_analytics`**: Requires an `index_name` and a `query_dsl` (a JSON string). Executes the search and returns the top hits directly to the LLM's context window.


---

## Resources
- [Elasticsearch/OpenSearch MCP Server](https://github.com/cr7258/elasticsearch-mcp-server)
