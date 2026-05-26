import gzip
import json
from collections.abc import AsyncGenerator
from datetime import UTC, datetime
from typing import Any

from log_replay.models import build_network_connection_log
from log_replay.schemas import DatasetReader


class ZeekConnReader(DatasetReader):
    """Parses Zeek conn.log files (both JSON and standard TSV formats) into ECS."""

    async def stream_ecs_documents(self) -> AsyncGenerator[dict[str, Any]]:
        open_func = gzip.open if self.file_path.suffix == ".gz" else open
        headers = []
        is_json = False
        sniffed = False

        with open_func(self.file_path, "rt", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue

                # 1. Format Sniffing (Determine JSON vs TSV on the first line)
                if not sniffed:
                    if line.startswith("{"):
                        is_json = True
                    sniffed = True

                raw_doc = {}

                # 2. Parse based on detected format
                if is_json:
                    raw_doc = json.loads(line)
                else:
                    if line.startswith("#"):
                        if line.startswith("#fields"):
                            headers = line.split("\t")[1:]
                        continue
                    if not headers:
                        continue

                    values = line.split("\t")
                    raw_doc = dict(zip(headers, values, strict=False))

                # 3. Map to ECS and yield
                ecs_doc = self.map_to_ecs(raw_doc)
                if ecs_doc:
                    yield ecs_doc

    def map_to_ecs(self, raw_doc: dict) -> dict:
        ts_raw = raw_doc.get("ts")
        if not ts_raw or ts_raw == "-":
            return {}

        # Handle ISO or Epoch
        try:
            ts_iso = datetime.fromtimestamp(float(ts_raw), tz=UTC).isoformat()
        except ValueError:
            ts_iso = ts_raw

        def safe_int(val: Any) -> int:
            try:
                return int(val) if val and val != "-" else 0
            except (ValueError, TypeError):
                return 0

        # Extract the IoT-23 specific labels if they exist
        label = raw_doc.get("label", "Benign")
        detailed_label = raw_doc.get("detailed-label")

        return build_network_connection_log(
            original_timestamp=ts_iso,
            transport=raw_doc.get("proto", "tcp"),
            src_ip=raw_doc.get("id.orig_h", ""),
            src_port=safe_int(raw_doc.get("id.orig_p")),
            dest_ip=raw_doc.get("id.resp_h", ""),
            dest_port=safe_int(raw_doc.get("id.resp_p")),
            total_bytes=safe_int(raw_doc.get("orig_bytes"))
            + safe_int(raw_doc.get("resp_bytes")),
            label=label,
            detailed_label=detailed_label,
        )
