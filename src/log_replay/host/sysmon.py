from log_replay.models import build_windows_otel_document
from log_replay.schemas import DatasetReader


class MordorSysmonReader(DatasetReader):
    """Parses Mordor Windows JSON logs via OTel/ECS conventions."""

    def map_to_ecs(self, raw_doc: dict) -> dict:
        # Pass the raw log directly to our robust OTel/ECS builder
        return build_windows_otel_document(raw_doc)
