import socket
from typing import Any

# Using the official OTel Semantic Conventions (v0.63b0)
from opentelemetry.semconv.resource import ResourceAttributes

# Note: Many network/security attributes are still incubating in 0.63b0,
# so we define the standardized OTel string paths for them.
OTEL_NETWORK_TRANSPORT = "network.transport"
OTEL_NETWORK_BYTES = "network.bytes"
OTEL_SOURCE_IP = "source.address"
OTEL_SOURCE_PORT = "source.port"
OTEL_DEST_IP = "destination.address"
OTEL_DEST_PORT = "destination.port"
OTEL_PROCESS_NAME = "process.name"
OTEL_PROCESS_EXECUTABLE = "process.executable"
OTEL_PROCESS_COMMAND_LINE = "process.command_line"


def build_otel_base_document(
    original_timestamp: str,
    event_dataset: str,
    event_category: list[str],
    event_type: list[str],
) -> dict[str, Any]:
    """
    Constructs the base OpenTelemetry/ECS document required for all replay logs.
    Includes a placeholder for the engine to inject the time-dilated @timestamp.
    """
    return {
        "_original_timestamp": original_timestamp,  # Used by the engine for math, popped before ingestion
        "@timestamp": None,  # Will be overwritten by the time-dilation engine
        "event.dataset": event_dataset,  # Critical for Elastic SIEM rule targeting
        "event.category": event_category,
        "event.type": event_type,
        # Static Resource Attributes via official SemConv
        ResourceAttributes.HOST_NAME: socket.gethostname(),
        ResourceAttributes.SERVICE_NAME: "siem-replay-engine",
    }


def build_host_execution_log(
    original_timestamp: str,
    computer_name: str,
    process_name: str,
    executable: str,
    command_line: str,
    event_code: int,
) -> dict[str, Any]:
    """Constructs an OTel-compliant host process execution log (e.g., Sysmon)."""
    doc = build_otel_base_document(
        original_timestamp=original_timestamp,
        event_dataset="windows.sysmon",
        event_category=["process"],
        event_type=["start"],
    )

    # Enrichment
    doc["event.code"] = event_code
    doc[ResourceAttributes.HOST_NAME] = computer_name
    doc[OTEL_PROCESS_NAME] = process_name
    doc[OTEL_PROCESS_EXECUTABLE] = executable
    doc[OTEL_PROCESS_COMMAND_LINE] = command_line

    return doc


def build_network_connection_log(
    original_timestamp: str,
    transport: str,
    src_ip: str,
    src_port: int,
    dest_ip: str,
    dest_port: int,
    total_bytes: int,
) -> dict[str, Any]:
    """Constructs an OTel-compliant network flow log (e.g., Zeek)."""
    doc = build_otel_base_document(
        original_timestamp=original_timestamp,
        event_dataset="zeek.conn",
        event_category=["network"],
        event_type=["connection"],
    )

    # Enrichment
    doc[OTEL_NETWORK_TRANSPORT] = transport
    doc[OTEL_NETWORK_BYTES] = total_bytes
    doc[OTEL_SOURCE_IP] = src_ip
    doc[OTEL_SOURCE_PORT] = src_port
    doc[OTEL_DEST_IP] = dest_ip
    doc[OTEL_DEST_PORT] = dest_port

    return doc
