# Elastic Security Log Replay Engine

A decoupled, time-dilated log ingestion engine designed specifically for validating Elastic Security SIEM detection rules and Machine Learning Anomaly jobs.
It programmatically downloads open-source threat datasets (e.g., APT29 Sysmon executions, Mirai Botnet C2 traffic), maps them dynamically into deeply nested Elastic Common Schema (ECS) documents, and replays them into Elasticsearch while perfectly preserving the relative chronological gaps between events.

## Getting Started

**Step 1.** Install Dependencies

Because this suite streams data directly to Elasticsearch via the async bulk helper and fetches datasets from the web, it requires the async Elastic client and HTTPX.

```bash
uv sync --all-extras
```

**Step 2.** Configure environment

Ensure your `.env` file points to your Elasticsearch instance. To work natively with Elastic Security's default dashboards and rules without manual Kibana configuration, use the standard `logs-endpoint.events-*` data stream naming convention.

```env
ELASTIC_URL=http://localhost:9200
REPLAY_INDEX=logs-endpoint.events-simulated
```

**Step 3.** Run the Replay

The engine will automatically download the required datasets to `./datasets`, extract them, map the raw vendor logs (Sysmon/Zeek) to ECS, shift the timestamps to "now", and push them to your cluster using the defined `speed_multiplier`.

```bash
uv run python -m log_replay.main
```

**Step 4.** View in Elastic Security

Navigate to **Security -> Explore -> Hosts** or **Network** in Kibana. Ensure your time filter is set to **"Last 1 hour"** to view the live-streamed simulated attacks.

---

## Configuration

All settings are controlled via environment variables.

| Variable | Default | Description |
| --- | --- | --- |
| `ELASTIC_URL` | `http://localhost:9200` | Elasticsearch node URL. |
| `REPLAY_INDEX` | `logs-endpoint.events-simulated` | Target index or Data Stream for ingestion. |

---

## Architecture

```text
                      ┌─────────────────────────┐
                      │   Public Datasets       │
                      └───────────┬─────────────┘
                                  │ (Mordor, IoT-23, Brim)
                                  ▼
┌─────────────────┐    ┌─────────────────────────┐    ┌─────────────────┐
│ Dataset Cacher  │◄───┤   Log Replay Engine     ├───►│  Elasticsearch  │
│ (./datasets)    │───►│   (Time Dilation & ECS) │    │  (Data Streams) │
└─────────────────┘    └─────────────────────────┘    └─────────────────┘

```

### Features

* **Chronological Time-Dilation:** Calculates the exact $\Delta$ between historical log events and shifts them to the current execution time (`T0 = datetime.now()`). This prevents Machine Learning jobs from skewing and ensures rate-based SIEM rules (e.g., "5 failed logins in 1 minute") fire accurately.
* **Speed Multipliers:** Replay a 4-hour APT attack in 10 seconds (`speed_multiplier=10.0`), or dump millions of network noise logs instantly (`speed_multiplier=0`).
* **Dynamic ECS Mapping:** Translates varying schemas (JSON, TSV, Hex PIDs, nested hashes) into strict, deeply-nested Elastic Common Schema (ECS) documents required by the Elastic Security UI.
* **Format Sniffing:** Automatically detects and handles Zeek TSV formats, raw JSON formats, and handles inline decompression of `.gz` and `.zip` files to save disk space.
* **Data Stream Compliant:** Automatically uses the `_op_type: "create"` action required to ingest data into Elastic time-series Data Streams.

---

## Datasets Included

1. **Mordor APT29 Simulation (Host):** Windows Sysmon logs detailing a VBScript Empire launcher execution. Maps to `windows.sysmon` (Event IDs 1, 10, 11, 5156).
2. **IoT-23 Mirai Botnet (Network):** Zeek TSV logs capturing malicious Command & Control (C2) horizontal port scanning. Maps to `zeek.conn` and injects `threat.enrichment` flags.
3. **Brimdata Zed Sample (Noise):** Standard Zeek network noise to simulate a noisy corporate environment and test signal-to-noise detection.

---

## Troubleshooting & Maintenance

### Wipe the Simulated Data

If you run the script multiple times without changing the base execution time, your Data Stream will become polluted with duplicate, overlapping logs. Because Data Streams are append-only by design, you cannot easily delete individual documents.

To reset your testing environment, delete the entire Data Stream from the Kibana **Dev Tools** console:

```json
DELETE _data_stream/logs-endpoint.events-simulated
```

*(Note: If you used a standard index instead of a Data Stream, the command is simply `DELETE logs-endpoint.events-simulated`)*

### Missing Logs in Security App UI

If your logs ingest successfully (visible in the Discover tab) but show "0" in the Security App widgets:

1. Ensure `event.kind: "event"` is present in the document.
2. Ensure you used the `logs-*` index pattern, OR that you manually added your custom index to the `securitySolution:defaultIndex` advanced setting.
3. Ensure Network IP addresses are mapped as strings in Python so Elasticsearch can auto-promote them to the `ip` mapping type.
