from log_replay.models import build_host_execution_log
from log_replay.schemas import DatasetReader


class MordorSysmonReader(DatasetReader):
    """Parses Mordor APT29 Sysmon JSON logs into OTel format."""

    def map_to_ecs(self, raw_doc: dict) -> dict:
        ts_raw = raw_doc.get("@timestamp") or raw_doc.get("EventTime")
        event_code_raw = raw_doc.get("event_id") or raw_doc.get("EventID")

        # 1. Safely cast event code to int to prevent "1" != 1 string comparison drops
        try:
            event_code = int(event_code_raw)
        except (TypeError, ValueError):
            return {}

        # We only care about Process Creation (Event ID 1) for this ML validation
        if not ts_raw or event_code != 1:
            return {}

        # 2. Extract fields safely (handles both missing keys AND explicit JSON nulls)
        # using Python's `or` operator to guarantee a string type.
        image = raw_doc.get("image") or raw_doc.get("Image") or ""
        command_line = raw_doc.get("command_line") or raw_doc.get("CommandLine") or ""
        computer_name = (
            raw_doc.get("computer_name") or raw_doc.get("Computer") or "unknown"
        )

        # 3. Safely split the process name
        process_name = image.split("\\")[-1] if image else "unknown"

        return build_host_execution_log(
            original_timestamp=ts_raw,
            computer_name=computer_name,
            process_name=process_name,
            executable=image,
            command_line=command_line,
            event_code=event_code,
        )
