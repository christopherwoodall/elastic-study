import asyncio
import time
from datetime import UTC, datetime

from dateutil import parser as date_parser
from elasticsearch import AsyncElasticsearch
from elasticsearch.helpers import async_bulk

from log_replay.logger import logger
from log_replay.schemas import DatasetReader

# logger = logging.getLogger(__name__)


class LogReplayer:
    """Core Engine for chronological, rate-limited log ingestion."""

    def __init__(self, es_client: AsyncElasticsearch, target_index: str):
        self.es_client = es_client
        self.target_index = target_index

    async def _chronological_generator(
        self, reader: DatasetReader, speed_multiplier: float, base_timestamp: datetime
    ):
        """Generates ECS documents with shifted timestamps and manages rate-limiting."""
        first_event_time: datetime | None = None
        replay_start_time = time.time()

        async for ecs_doc in reader.stream_ecs_documents():
            original_time_str = ecs_doc.pop("_original_timestamp")

            # Parse robustly (handles 'Z', offsets, etc.)
            original_time = date_parser.isoparse(original_time_str)

            if first_event_time is None:
                first_event_time = original_time

            # Calculate exact timeline delta
            delta_seconds = (original_time - first_event_time).total_seconds()

            # Shift the SIEM/ECS @timestamp chronologically
            shifted_time = (
                base_timestamp + asyncio.get_running_loop().time()
            )  # Use reliable monotonic clock for delta if needed, but timedelta is better:
            from datetime import timedelta

            shifted_time = base_timestamp + timedelta(seconds=delta_seconds)
            ecs_doc["@timestamp"] = shifted_time.isoformat()

            # Time-Dilation / Rate Limiting (Throttle ingestion to match speed_multiplier)
            if speed_multiplier > 0:
                target_fire_time = replay_start_time + (
                    delta_seconds / speed_multiplier
                )
                sleep_duration = target_fire_time - time.time()

                if sleep_duration > 0.05:  # Prevent micro-sleep CPU thrashing
                    await asyncio.sleep(sleep_duration)

            yield {"_index": self.target_index, "_source": ecs_doc}

    async def replay(
        self,
        reader: DatasetReader,
        speed_multiplier: float = 1.0,
        chunk_size: int = 100,
    ):
        """
        Executes the replay to Elasticsearch.
        :param speed_multiplier: 1.0 = real-time. 10.0 = 10x faster. 0 = as fast as possible.
        """
        base_timestamp = datetime.now(UTC)
        logger.info(
            f"Starting replay. Simulating logs starting at {base_timestamp} (Speed: {speed_multiplier}x)"
        )

        doc_generator = self._chronological_generator(
            reader, speed_multiplier, base_timestamp
        )

        # Ingest into Elasticsearch
        successes, errors = await async_bulk(
            client=self.es_client,
            actions=doc_generator,
            chunk_size=chunk_size,
            raise_on_error=False,
            stats_only=True,
        )
        logger.info(
            f"Replay complete. Successfully ingested {successes} logs. Errors: {errors}"
        )
