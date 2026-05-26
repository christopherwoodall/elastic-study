from log_replay.models import build_host_execution_log
from log_replay.schemas import DatasetReader


class MordorSysmonReader(DatasetReader):
    """Parses Mordor APT29 Sysmon JSON logs into OTel format."""

    def map_to_ecs(self, raw_doc: dict) -> dict:
        ts_raw = raw_doc.get("@timestamp") or raw_doc.get("EventTime")
        event_code = raw_doc.get("event_id") or raw_doc.get("EventID")

        # We only care about Process Creation (Event ID 1) for this ML validation
        if not ts_raw or event_code != 1:
            return {}

        return build_host_execution_log(
            original_timestamp=ts_raw,
            computer_name=raw_doc.get("computer_name")
            or raw_doc.get("Computer", "unknown"),
            process_name=raw_doc.get("image", "").split("\\")[-1],
            executable=raw_doc.get("image", ""),
            command_line=raw_doc.get("command_line", ""),
            event_code=event_code,
        )
