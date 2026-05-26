from datetime import UTC, datetime

from log_replay.models import build_network_connection_log
from log_replay.schemas import DatasetReader


class ZeekConnReader(DatasetReader):
    """Parses Zeek conn.log JSON into OTel format."""

    def map_to_ecs(self, raw_doc: dict) -> dict:
        ts_epoch = raw_doc.get("ts")
        if not ts_epoch:
            return {}

        # Zeek JSON uses epoch floats; convert to ISO for our engine
        ts_iso = datetime.fromtimestamp(ts_epoch, tz=UTC).isoformat()

        return build_network_connection_log(
            original_timestamp=ts_iso,
            transport=raw_doc.get("proto", "tcp"),
            src_ip=raw_doc.get("id.orig_h", ""),
            src_port=raw_doc.get("id.orig_p", 0),
            dest_ip=raw_doc.get("id.resp_h", ""),
            dest_port=raw_doc.get("id.resp_p", 0),
            total_bytes=raw_doc.get("orig_bytes", 0) + raw_doc.get("resp_bytes", 0),
        )
