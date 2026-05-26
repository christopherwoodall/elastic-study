import json
from collections.abc import AsyncGenerator
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from log_replay.schemas import DatasetReader


class ZeekLogReader(DatasetReader):
    """Dynamically parses Zeek logs (conn, http, files, dns, etc.) into ECS."""

    def __init__(self, file_path: Path):
        super().__init__(file_path)
        # Extract the type (e.g., "http" from "http.log")
        self.log_type = self.file_path.stem

    async def stream_ecs_documents(self) -> AsyncGenerator[dict[str, Any]]:
        with open(self.file_path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#"):
                    continue

                try:
                    raw_doc = json.loads(line)
                    ecs_doc = self.map_to_ecs(raw_doc)
                    if ecs_doc:
                        yield ecs_doc
                except json.JSONDecodeError:
                    continue

    def map_to_ecs(self, raw_doc: dict) -> dict:
        ts_raw = raw_doc.get("ts")
        if not ts_raw:
            return {}

        try:
            ts_iso = datetime.fromtimestamp(float(ts_raw), tz=UTC).isoformat()
        except ValueError:
            ts_iso = ts_raw

        # 1. Base ECS Document (Applies to all Zeek logs)
        doc = {
            "_original_timestamp": ts_iso,
            "@timestamp": None,
            "event": {
                "kind": "event",
                "module": "zeek",
                "dataset": f"zeek.{self.log_type}",
                "action": "unknown",  # Default, overridden below
            },
            # --- NEW: Explicitly define the agent ---
            "agent": {"type": "zeek"},
        }

        # Safe mapping for Network fields
        if "id.orig_h" in raw_doc:
            doc["source"] = {"ip": raw_doc.get("id.orig_h")}
            if "id.orig_p" in raw_doc:
                doc["source"]["port"] = int(raw_doc["id.orig_p"])

            doc["destination"] = {"ip": raw_doc.get("id.resp_h")}
            if "id.resp_p" in raw_doc:
                doc["destination"]["port"] = int(raw_doc["id.resp_p"])

            doc["network"] = {"transport": raw_doc.get("proto", "tcp").lower()}

        # 2. HTTP Specific Mapping
        if self.log_type == "http":
            doc["event"]["category"] = ["network", "web"]
            doc["event"]["action"] = "http_request"  # --- NEW ---
            doc["url"] = {"path": raw_doc.get("uri"), "domain": raw_doc.get("host")}
            doc["http"] = {
                "request": {"method": raw_doc.get("method")},
                "response": {"status_code": raw_doc.get("status_code")},
            }

            # Map the malicious JNDI string
            if user_agent := raw_doc.get("user_agent"):
                doc["user_agent"] = {"original": user_agent}
                doc["message"] = (
                    f"HTTP {raw_doc.get('method')} {raw_doc.get('uri')} | User-Agent: {user_agent}"
                )

        # 3. File Mapping (Malicious Java classes downloaded over network)
        elif self.log_type == "files":
            doc["event"]["category"] = ["file", "network"]
            doc["event"]["action"] = "file_transfer"  # --- NEW ---
            doc["file"] = {
                "mime_type": raw_doc.get("mime_type"),
                "size": raw_doc.get("total_bytes"),
            }
            doc["message"] = f"Network File Transfer: {raw_doc.get('mime_type')}"

        # 4. Conn Mapping
        elif self.log_type == "conn":
            doc["event"]["category"] = ["network"]
            doc["event"]["type"] = ["connection"]
            doc["event"]["action"] = "network_flow"  # --- NEW ---
            doc["message"] = (
                f"Network Flow: {raw_doc.get('id.orig_h')} -> {raw_doc.get('id.resp_h')}"
            )

        # 5. Weird Mapping (Zeek anomaly detections)
        elif self.log_type == "weird":
            doc["event"]["category"] = ["intrusion_detection"]
            doc["event"]["action"] = "anomaly_detected"  # --- NEW ---
            doc["message"] = f"Zeek Anomaly: {raw_doc.get('name')}"

        return doc
