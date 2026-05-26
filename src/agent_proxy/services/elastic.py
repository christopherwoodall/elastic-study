import asyncio
import json
import os
from datetime import UTC, datetime

from elasticsearch import AsyncElasticsearch

from agent_proxy.config import (
    AGENT_LOG_DIR,
    ELASTIC_API_KEY,
    ELASTIC_INDEX,
    ELASTIC_URL,
    STRICT_MODE,
)
from agent_proxy.logger import logger


class ElasticService:
    """
    An asynchronous service for managing Elasticsearch connections and logging.

    This service handles creating the connection to the Elasticsearch cluster,
    maintains a dual local-file disk buffer, and provides methods for both
    synchronous (fire-and-forget) and asynchronous document indexing.
    """

    def __init__(self):
        """
        Initializes the ElasticService.

        The Elasticsearch client is not instantiated until `connect()` is called
        to allow for safe integration within asynchronous event loops.
        """
        self.client: AsyncElasticsearch | None = None
        self.file_handle = None

    def connect(self) -> None:
        """
        Establishes the connection to the Elasticsearch client.

        Uses the `ELASTIC_URL` and `ELASTIC_API_KEY` loaded from the application
        configuration. This should be called during the application startup phase.
        """
        # 1. Establish Elastic Target Connection
        kwargs = {"hosts": [ELASTIC_URL]}
        if ELASTIC_API_KEY:
            kwargs["api_key"] = ELASTIC_API_KEY
        self.client = AsyncElasticsearch(**kwargs)

        # 2. Setup Persistent Local File Handle
        try:
            os.makedirs(AGENT_LOG_DIR, exist_ok=True)
            timestamp = datetime.now(UTC).strftime("%Y%m%d_%H%M%S")
            filepath = os.path.join(AGENT_LOG_DIR, f"proxy_run_{timestamp}.jsonl")

            # Keep file open cleanly for session to achieve peak I/O performance
            self.file_handle = open(filepath, "a", encoding="utf-8")  # noqa: SIM115
            logger.info("Local proxy storage sink attached at %s", filepath)
        except Exception as exc:
            logger.error("Failed to initialize local file logger sink: %s", exc)

    async def close(self) -> None:
        """
        Gracefully closes the Elasticsearch client connection.

        This should be called during the application shutdown phase to ensure
        all underlying network connections are properly terminated.
        """
        if self.file_handle and not self.file_handle.closed:
            self.file_handle.close()

        if self.client:
            await self.client.close()

    async def index_log(self, doc: dict) -> None:
        """
        Asynchronously indexes a document into Elasticsearch.

        Args:
            doc (dict): The document to be indexed. Must contain a 'request_id'
                key to be used as the Elasticsearch document ID.

        Raises:
            Exception: If indexing fails AND the application is running in `STRICT_MODE`.
                Otherwise, the exception is caught and logged.
        """
        # Sink Step A: Persistent Local Append
        if self.file_handle:
            try:
                self.file_handle.write(json.dumps(doc) + "\n")
                self.file_handle.flush()
            except Exception as exc:
                logger.error("Failed to append entry to local proxy file: %s", exc)

        # Sink Step B: Elasticsearch Push
        try:
            await self.client.index(
                index=ELASTIC_INDEX, id=doc["event.id"], document=doc
            )
        except Exception as exc:
            msg = f"ES indexing failed for event.id={doc.get('event.id')}: {exc}"
            if STRICT_MODE:
                raise
            logger.error(msg)

    def fire_and_forget(self, doc: dict) -> None:
        """
        Schedules a document to be indexed in the background without awaiting it.

        This is useful for non-blocking logging where the primary execution flow
        (e.g., returning an API response) shouldn't wait for the network request
        to Elasticsearch to complete.

        Args:
            doc (dict): The document to be indexed.
        """
        task = asyncio.create_task(self.index_log(doc))
        task.add_done_callback(self._task_error_handler)

    def _task_error_handler(self, task: asyncio.Task) -> None:
        """
        Callback handler to catch and log exceptions from background tasks.

        Prevents unhandled exceptions in fire-and-forget tasks from silently
        failing or crashing the event loop.

        Args:
            task (asyncio.Task): The finished asyncio task to inspect.
        """
        if task.cancelled():
            return
        exc = task.exception()
        if exc:
            logger.error("Background ES task raised: %s", exc)


# Singleton instance to be used across the app
es_service = ElasticService()
