import json
import os
from datetime import UTC, datetime

from elasticsearch import AsyncElasticsearch

from llm_benchmark.protocols import TelemetryResult, TelemetrySinkProtocol


class ElasticsearchTelemetrySink:
    """Ships benchmark results to a distinct Elasticsearch index."""

    def __init__(self, es_url: str, index_name: str):
        self.index_name = index_name
        self.client = AsyncElasticsearch(hosts=[es_url])

    async def flush(self, result: TelemetryResult) -> None:
        try:
            await self.client.index(
                index=self.index_name, id=result.run_id, document=result.to_dict()
            )
        except Exception as exc:
            print(f"[ES Sink Error] Failed to flush telemetry to ES: {exc}")

    async def close(self) -> None:
        await self.client.close()


class LocalFileTelemetrySink:
    """Appends benchmark results to a local JSONL file for durability."""

    def __init__(self, log_dir: str = "./logs/benchmarks"):
        self.log_dir = log_dir
        os.makedirs(self.log_dir, exist_ok=True)

        timestamp = datetime.now(UTC).strftime("%Y%m%d_%H%M%S")
        self.filepath = os.path.join(self.log_dir, f"run_{timestamp}.jsonl")

        # We intentionally keep the handle open for the session to reduce I/O overhead
        self.file = open(self.filepath, "a", encoding="utf-8")  # noqa: SIM115

    async def flush(self, result: TelemetryResult) -> None:
        try:
            doc = result.to_dict()
            self.file.write(json.dumps(doc) + "\n")
            self.file.flush()
        except Exception as exc:
            print(f"[File Sink Error] Failed to write locally: {exc}")

    async def close(self) -> None:
        if not self.file.closed:
            self.file.close()


class CompositeTelemetrySink:
    """Broadcasts a single telemetry payload to multiple underlying sinks."""

    def __init__(self, sinks: list[TelemetrySinkProtocol]):
        self.sinks = sinks

    async def flush(self, result: TelemetryResult) -> None:
        for sink in self.sinks:
            await sink.flush(result)

    async def close(self) -> None:
        for sink in self.sinks:
            await sink.close()
