import json
from collections.abc import AsyncGenerator
from typing import Any

from log_replay.schemas import DatasetReader


class SuricataEveReader(DatasetReader):
    """Parses Suricata eve.json logs into Elastic Common Schema."""

    async def stream_ecs_documents(self) -> AsyncGenerator[dict[str, Any]]:
        with open(self.file_path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    raw_doc = json.loads(line)
                    ecs_doc = self.map_to_ecs(raw_doc)
                    if ecs_doc:
                        yield ecs_doc
                except json.JSONDecodeError:
                    continue

    def map_to_ecs(self, raw_doc: dict) -> dict:
        event_type = raw_doc.get("event_type", "unknown")
        timestamp = raw_doc.get("timestamp")

        if not timestamp:
            return {}

        # 1. Base ECS Document
        doc = {
            "_original_timestamp": timestamp,
            "@timestamp": None,
            "event": {
                "kind": "alert" if event_type == "alert" else "event",
                "module": "suricata",
                "dataset": "suricata.eve",
                "category": ["network"],
                "action": event_type,
                "original": json.dumps(raw_doc),
            },
            "agent": {"type": "suricata"},
        }

        # 2. Universal Network Mapping
        if "src_ip" in raw_doc:
            doc.setdefault("source", {})["ip"] = raw_doc["src_ip"]
        if "src_port" in raw_doc:
            doc.setdefault("source", {})["port"] = int(raw_doc["src_port"])

        if "dest_ip" in raw_doc:
            doc.setdefault("destination", {})["ip"] = raw_doc["dest_ip"]
        if "dest_port" in raw_doc:
            doc.setdefault("destination", {})["port"] = int(raw_doc["dest_port"])

        if "proto" in raw_doc:
            doc.setdefault("network", {})["transport"] = str(raw_doc["proto"]).lower()

        # 3. HTTP Specific Mapping (Where the Log4Shell payload lives)
        if event_type == "http":
            http = raw_doc.get("http", {})
            doc["url"] = {"path": http.get("url"), "domain": http.get("hostname")}
            doc["http"] = {
                "request": {"method": http.get("http_method")},
                "response": {"status_code": http.get("status")},
            }
            if user_agent := http.get("http_user_agent"):
                doc["user_agent"] = {"original": user_agent}

            doc["message"] = f"HTTP {http.get('http_method')} {http.get('url')}"

        # 4. Alert Specific Mapping (Suricata's Threat Signatures)
        elif event_type == "alert":
            alert = raw_doc.get("alert", {})
            doc["event"]["category"] = ["intrusion_detection"]
            doc["rule"] = {
                "name": alert.get("signature"),
                "category": alert.get("category"),
                "id": str(alert.get("signature_id")),
            }
            doc["message"] = f"🚨 SURICATA ALERT: {alert.get('signature')}"

        # 5. Flow Mapping
        elif event_type == "flow":
            doc["event"]["type"] = ["connection"]
            doc["message"] = (
                f"Network Flow: {raw_doc.get('src_ip')} -> {raw_doc.get('dest_ip')}"
            )

        return doc
