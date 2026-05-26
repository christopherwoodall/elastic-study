import socket
from typing import Any

# Leveraging official OpenTelemetry Semantic Conventions
from opentelemetry.semconv.resource import ResourceAttributes


def build_windows_otel_document(raw_doc: dict) -> dict[str, Any]:
    """
    Dynamically maps raw Windows Security & Sysmon logs into a deeply nested
    ECS document, capturing rich forensic data while honoring OTel concepts.
    """
    # 1. Base Time & Metadata
    timestamp = raw_doc.get("@timestamp") or raw_doc.get("EventTime")
    if not timestamp:
        return {}

    event_id = str(raw_doc.get("EventID", "unknown"))
    provider = raw_doc.get("SourceName", "unknown")

    # Determine the specific Elastic module based on the provider
    event_module = "sysmon" if "Sysmon" in provider else "security"
    event_dataset = f"windows.{event_module}"

    # 2. Base OTel / ECS Structure
    doc = {
        "_original_timestamp": timestamp,
        "@timestamp": None,
        "message": raw_doc.get("Message", ""),
        "event": {
            "kind": "event",
            "module": event_module,
            "dataset": event_dataset,
            "provider": provider,
            "code": event_id,
            "action": raw_doc.get("Category"),
        },
        "host": {
            # Map to OTel Resource Attribute internally, output as ECS
            "name": raw_doc.get("Hostname") or socket.gethostname(),
            "os": {"family": "windows"},
        },
        "service": {ResourceAttributes.SERVICE_NAME: "siem-replay-engine"},
        "process": {},
        "file": {},
        "network": {},
        "source": {},
        "destination": {},
        "windows": {},  # Used for custom Windows forensics (CallTrace, etc.)
    }

    # 3. Dynamic Process & Thread Mapping
    def parse_int(val: Any) -> int | None:
        """Helper to safely parse decimal strings or hex strings like '0x0'."""
        if val is None:
            return None
        try:
            # If it's a hex string (starts with 0x), convert using base 16
            if isinstance(val, str) and val.lower().startswith("0x"):
                return int(val, 16)
            # Otherwise assume base 10
            return int(val)
        except (ValueError, TypeError):
            return None

    if pid := parse_int(raw_doc.get("ProcessId") or raw_doc.get("ExecutionProcessID")):
        doc["process"]["pid"] = pid

    if tid := parse_int(raw_doc.get("ThreadID")):
        doc["process"]["thread"] = {"id": tid}

    # Map executable from various Windows formats
    if executable := (
        raw_doc.get("Image") or raw_doc.get("Application") or raw_doc.get("SourceImage")
    ):
        doc["process"]["executable"] = executable
        doc["process"]["name"] = str(executable).split("\\")[-1]

    # 4. Dynamic File Mapping (Sysmon Event 11)
    if target_file := raw_doc.get("TargetFilename"):
        doc["file"]["path"] = target_file
        doc["event"]["category"] = ["file"]
        doc["event"]["type"] = ["creation"]

    # 5. Dynamic Host-Network Mapping (Security Events 5156, 5158)
    if src_ip := raw_doc.get("SourceAddress"):
        doc["source"]["ip"] = src_ip
        doc["event"]["category"] = ["network"]
        doc["event"]["type"] = ["connection"]
    if src_port := raw_doc.get("SourcePort"):
        doc["source"]["port"] = int(src_port)
    if dest_ip := raw_doc.get("DestAddress"):
        doc["destination"]["ip"] = dest_ip
    if dest_port := raw_doc.get("DestPort"):
        doc["destination"]["port"] = int(dest_port)

    if protocol := raw_doc.get("Protocol"):
        doc["network"]["iana_number"] = str(protocol)  # 6 = TCP, 17 = UDP
    if direction := raw_doc.get("Direction"):
        doc["network"]["direction"] = (
            "outbound" if "outbound" in str(direction).lower() else "inbound"
        )

    # 6. Deep Forensics (Sysmon Event 10 - Process Access)
    if call_trace := raw_doc.get("CallTrace"):
        doc["windows"]["call_trace"] = call_trace
    if granted_access := raw_doc.get("GrantedAccess"):
        doc["windows"]["granted_access"] = granted_access
    if target_process := raw_doc.get("TargetImage"):
        doc["windows"]["target_executable"] = target_process

    # 7. Dictionary Cleanup (Remove empty dicts so Elasticsearch mapping doesn't break)
    return {
        k: v for k, v in doc.items() if v and (not isinstance(v, dict) or len(v) > 0)
    }


def build_network_connection_log(
    original_timestamp: str,  # <--- Ensure this is first
    transport: str,
    src_ip: str,
    src_port: int,
    dest_ip: str,
    dest_port: int,
    total_bytes: int,
    label: str = "Benign",
    detailed_label: str = None,
) -> dict[str, Any]:
    """Constructs a nested ECS network flow log with threat intelligence labels."""
    doc = {
        "_original_timestamp": original_timestamp,
        "@timestamp": None,  # Engine fills this
        "event": {
            "kind": "event",
            "module": "zeek",
            "dataset": "zeek.conn",
            "category": ["network"],
            "type": ["connection"],
            "outcome": "success" if label == "Benign" else "failure",
        },
        "observer": {"name": socket.gethostname()},
        "network": {"transport": transport, "bytes": total_bytes},
        "source": {"ip": src_ip, "port": src_port},
        "destination": {"ip": dest_ip, "port": dest_port},
    }

    if label != "Benign":
        doc["threat"] = {
            "enrichment": {
                "indicator": {
                    "matched": True,
                    "type": label,
                    "description": detailed_label,
                }
            }
        }
    return doc


def build_suricata_alert_log(raw_doc: dict) -> dict[str, Any]:
    """Constructs a nested ECS document from Suricata eve.json alerts."""
    doc = {
        "_original_timestamp": raw_doc.get("timestamp"),
        "@timestamp": None,
        "event": {
            "kind": "alert",
            "module": "suricata",
            "dataset": "suricata.eve",
            "category": ["intrusion_detection"],
            "type": ["info"],
        },
        "observer": {"name": socket.gethostname(), "type": "ids"},
        "network": {
            "transport": raw_doc.get("proto"),
            "protocol": raw_doc.get("app_proto"),
        },
        "source": {"ip": raw_doc.get("src_ip"), "port": raw_doc.get("src_port")},
        "destination": {"ip": raw_doc.get("dest_ip"), "port": raw_doc.get("dest_port")},
    }

    # Map the deep Suricata Alert forensics
    if alert := raw_doc.get("alert"):
        doc["threat"] = {
            "enrichment": {
                "indicator": {
                    "matched": True,
                    "type": alert.get("category"),
                    "description": alert.get("signature"),
                    "reference": f"sid:{alert.get('signature_id')}",
                }
            }
        }
        # Include severity (Suricata uses 1 for high, 3 for low)
        doc["event"]["severity"] = alert.get("severity")

    return {k: v for k, v in doc.items() if v}
