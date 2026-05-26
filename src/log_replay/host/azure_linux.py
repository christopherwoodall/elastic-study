import json
import shlex
import xmltodict
from typing import Any
from collections.abc import AsyncGenerator

from log_replay.schemas import DatasetReader

class AzureHostReader(DatasetReader):
    """
    Parses Azure-wrapped JSON logs containing nested Sysmon XML
    or nested AUOMS Key-Value pairs.
    """

    async def stream_ecs_documents(self) -> AsyncGenerator[dict[str, Any]]:
        import gzip
        open_func = gzip.open if self.file_path.suffix == ".gz" else open

        with open_func(self.file_path, "rt", encoding="utf-8") as f:
            for line in f:
                if not line.strip():
                    continue

                raw_azure_doc = json.loads(line)
                ecs_doc = self.map_to_ecs(raw_azure_doc)
                if ecs_doc:
                    yield ecs_doc

    def map_to_ecs(self, raw_doc: dict[str, Any]) -> dict[str, Any]:
        """Routes the log to the correct parser based on the process name."""
        process_name = raw_doc.get("ProcessName", "").lower()

        if process_name == "sysmon":
            return self._parse_sysmon_xml(raw_doc)
        elif process_name == "auoms":
            return self._parse_auoms_kv(raw_doc)

        return {}

    def _parse_sysmon_xml(self, raw_doc: dict) -> dict:
        """Extracts and maps Linux-Sysmon XML."""
        xml_string = raw_doc.get("SyslogMessage", "")
        if not xml_string.startswith("<Event>"):
            return {}

        try:
            parsed_xml = xmltodict.parse(xml_string)
        except Exception:
            return {}

        event = parsed_xml.get("Event", {})
        system = event.get("System", {})

        event_data_raw = event.get("EventData", {}).get("Data", [])
        event_data = {item["@Name"]: item.get("#text") for item in event_data_raw if isinstance(item, dict)}

        host_ip = raw_doc.get("HostIP")
        event_id = str(system.get("EventID"))

        sysmon_action_map = {
            "1": "process_creation",
            "3": "network_connection",
            "5": "process_terminated",
            "9": "raw_access_read",
            "10": "process_accessed",
            "11": "file_creation"
        }

        # 1. Base ECS Document
        doc = {
            "_original_timestamp": raw_doc.get("TimeGenerated"),
            "@timestamp": None,
            "message": xml_string,
            "event": {
                "kind": "event",
                "module": "sysmon",
                "dataset": "linux.sysmon",
                "code": event_id,
                "action": sysmon_action_map.get(event_id, "unknown"),
                "provider": "Linux-Sysmon",
                "original": xml_string
            },
            "agent": {
                "type": raw_doc.get("ProcessName", "sysmon").lower()
            },
            "host": {
                "name": raw_doc.get("HostName"),
                "ip": host_ip,
                "os": {"family": "linux"}
            },
            "process": {
                "pid": event_data.get("ProcessId"),
                "executable": event_data.get("Image"),
                "name": str(event_data.get("Image", "")).split("/")[-1]
            },
            "user": {
                "name": event_data.get("User")
            },
            "source": {
                "ip": host_ip
            }
        }

        # 2. Dynamic Network Mapping (For Sysmon Event ID 3)
        if "SourceIp" in event_data:
            doc["source"]["ip"] = event_data["SourceIp"]
            doc["event"]["category"] = ["network"]
            doc["event"]["type"] = ["connection"]
        if "SourcePort" in event_data:
            doc["source"]["port"] = int(event_data["SourcePort"])

        if "DestinationIp" in event_data:
            doc.setdefault("destination", {})["ip"] = event_data["DestinationIp"]
        if "DestinationPort" in event_data:
            doc.setdefault("destination", {})["port"] = int(event_data["DestinationPort"])

        if "Protocol" in event_data:
            doc.setdefault("network", {})["transport"] = str(event_data["Protocol"]).lower()

        return doc

    def _parse_auoms_kv(self, raw_doc: dict) -> dict:
        """Extracts and maps AUOMS/Auditd Key-Value pairs."""
        event_data_str = raw_doc.get("EventData", "")
        if not event_data_str:
            return {}

        kv_pairs = {}
        try:
            tokens = shlex.split(event_data_str)
            for token in tokens:
                if "=" in token:
                    k, v = token.split("=", 1)
                    kv_pairs[k] = v
        except ValueError:
            pass

        syslog_msg = raw_doc.get("SyslogMessage", "")
        host_ip = raw_doc.get("HostIP")

        return {
            "_original_timestamp": raw_doc.get("TimeGenerated"),
            "@timestamp": None,
            "message": syslog_msg,
            "event": {
                "kind": "event",
                "module": "auditd",
                "dataset": "linux.auditd",
                "action": "executed" if kv_pairs.get("syscall") == "execve" else "unknown",
                "original": syslog_msg
            },
            "agent": {
                "type": raw_doc.get("ProcessName", "auditd").lower()
            },
            "host": {
                "name": raw_doc.get("HostName"),
                "ip": host_ip,
                "os": {"family": "linux"}
            },
            "process": {
                "pid": kv_pairs.get("pid"),
                "parent": {"pid": kv_pairs.get("ppid")},
                "executable": kv_pairs.get("exe"),
                "command_line": kv_pairs.get("proctitle")
            },
            "user": {
                "name": kv_pairs.get("user")
            },
            "source": {
                "ip": host_ip
            }
        }