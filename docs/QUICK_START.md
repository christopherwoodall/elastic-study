# Quick Start

## Start Proxy

```bash
docker compose up -d --force-recreate && \
  uv run --env-file .env start-proxy
```

## Start MCP Server

```bash
uv run --env-file .env start-mcp
```

## Hydrate

```bash
uv run --env-file .env agent-hydrate && \
uv run --env-file .env benchmark-hydrate && \
uv run --env-file .env rag-hydrate-logs && \
uv run --env-file .env rag-hydrate && \
uv run --env-file .env log-replay
```

---

## Commands

### Agent (Standard Tooling)

```bash
uv run --env-file .env \
  opencode run \
    --dir ./workspace \
    --model openrouter-audit/moonshotai/kimi-k2.5 \
    "Create todo.py with add, list, and delete commands that persist tasks to a JSON file."

```

### Agent (Testing MCP Database Access)

*Requires the MCP Server to be running on port 8001.*

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

### Benchmark

```bash
uv run --env-file .env benchmark-run
```

### RAG

```bash
uv run --env-file .env rag-ask "What information retrieval system first implemented BM25, and at which university was it developed?"
```

Target doc: Okapi BM25 intro
Answer: Okapi system, City University London
Distractor: Inverted index, Elasticsearch — plausible IR topics but won't contain this
Stays within intro content: yes, explicitly stated in your sample text
