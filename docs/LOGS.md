# Elastic Security Log Replay Engine

A decoupled, time-dilated log ingestion engine designed specifically for validating Elastic Security SIEM detection rules and Machine Learning Anomaly jobs.
It programmatically downloads open-source threat datasets (e.g., Log4Shell exploitation logs), maps them dynamically into deeply nested Elastic Common Schema (ECS) documents, and replays them into Elasticsearch while perfectly preserving the relative chronological gaps between events.

## Prerequisites

Ensure you have a local Elasticsearch instance running on port `9200` with authentication disabled (e.g., `xpack.security.enabled: false`), or configure your credentials accordingly in the Python client.

---

## Getting Started

**Step 1. Install Dependencies**

Because this suite streams data directly to Elasticsearch via the async bulk helper and fetches datasets from the web, it requires the async Elastic client and HTTPX.

```bash
uv sync --all-extras
```

**Step 2. Configure Environment**

Ensure your `.env` file is set up. To work natively with Elastic Security's default dashboards and rules without manual Kibana configuration, use the standard `logs-endpoint.events-*` data stream naming convention.

```env
ELASTIC_URL="http://localhost:9200"
REPLAY_INDEX="logs-endpoint.events-simulated"
LOG_LEVEL="INFO"

# Log4Shell Dataset Configuration
REPLAY_LOG_BASE_URL="[https://raw.githubusercontent.com/OTRF/Security-Datasets/master/datasets/compound/Log4Shell/](https://raw.githubusercontent.com/OTRF/Security-Datasets/master/datasets/compound/Log4Shell/)"
REPLAY_LOG_HOST_FILES='["syslog_auoms_auditd_log4shell_cve2021_44228_jndi_reference.zip", "syslog_sysmon_log4shell_cve2021_44228_jndi_reference.zip"]'
REPLAY_LOG_NET_FILES='["pcap_log4shell_cve2021_44228_jndi_reference.zip"]'
```

**Step 3. Prepare the Engine**

> **⚠️ Important Debug Note:** The current `main.py` file contains a debug exit line (`__import__("sys").exit()`) at the top, and hardcodes older dataset URLs further down. You will need to update `main.py` to utilize the new `REPLAY_LOG_*` environment variables and remove the exit line before the script will successfully ingest the Log4Shell data.

**Step 4. Run the Replay**

The engine will automatically download the required datasets to `./datasets`, extract them, map the raw vendor logs to ECS, shift the timestamps to "now", and push them to your cluster.

```bash
uv run python -m log_replay.main
```

**Step 5. View in Elastic Security**

Navigate to **Security -> Explore -> Hosts** or **Network** in Kibana. Ensure your time filter is set to **"Last 1 hour"** to view the live-streamed simulated attacks.

---

## Configuration

All settings are controlled via environment variables.

| Variable | Default | Description |
| --- | --- | --- |
| `ELASTIC_URL` | `http://localhost:9200` | Elasticsearch node URL. |
| `REPLAY_INDEX` | `logs-endpoint.events-simulated` | Target index or Data Stream for ingestion. |
| `LOG_LEVEL` | `INFO` | Controls the verbosity of terminal output (`DEBUG`, `INFO`, `ERROR`). |
| `REPLAY_LOG_BASE_URL` | `None` | Base URL string for fetching dynamic dataset repositories. |
| `REPLAY_LOG_HOST_FILES` | `[]` | JSON-formatted array of Host log dataset filenames. |
| `REPLAY_LOG_NET_FILES` | `[]` | JSON-formatted array of Network log dataset filenames. |

---

## Architecture

```text
                      ┌─────────────────────────┐
                      │   Public Datasets       │
                      └───────────┬─────────────┘
                                  │ (Log4Shell Compound)
                                  ▼
┌─────────────────┐    ┌─────────────────────────┐    ┌─────────────────┐
│ Dataset Cacher  │◄───┤   Log Replay Engine     ├───►│  Elasticsearch  │
│ (./datasets)    │───►│   (Time Dilation & ECS) │    │  (Data Streams) │
└─────────────────┘    └─────────────────────────┘    └─────────────────┘
```

### Features

* **Chronological Time-Dilation:** Calculates the exact relative time between historical log events and shifts them to the current execution time (`T0 = datetime.now()`). This prevents Machine Learning jobs from skewing and ensures rate-based SIEM rules (e.g., "5 failed logins in 1 minute") fire accurately.
* **Speed Multipliers:** Replay a multi-hour attack dataset in seconds, or dump millions of network noise logs instantly (`speed_multiplier=0`).
* **OpenTelemetry Native:** Leverages official OTel Semantic Conventions alongside ECS mapping to ensure deep forensic data (like hostnames and OS families) is accurately captured and future-proofed.
* **Dynamic ECS Mapping:** Translates varying schemas (JSON, TSV, Hex PIDs, nested hashes) into strict, deeply-nested Elastic Common Schema (ECS) documents required by the Elastic Security UI.
* **Format Sniffing:** Automatically detects and handles Zeek TSV formats, raw JSON formats, and inline decompression of `.gz` and `.zip` files to save disk space.
* **Data Stream Compliant:** Automatically uses the `_op_type: "create"` action required to ingest data into Elastic time-series Data Streams.

---

## Datasets Included

1. **Log4Shell Compound Simulation (Host & Network):** A comprehensive dataset from the Open Threat Research Forge (OTRF) detailing the exploitation of CVE-2021-44228 (Log4Shell). This includes:
* **Linux Auditd / AUOMS logs:** Tracking process creation and system calls.
* **Windows Sysmon logs:** Tracking malicious child processes spawned by the vulnerable Java application.
* **PCAP / Zeek Network logs:** Capturing the initial JNDI lookup payload and subsequent LDAP/RMI traffic.



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
