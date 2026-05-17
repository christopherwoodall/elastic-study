import asyncio

from elasticsearch import AsyncElasticsearch

from agent_proxy.config import ELASTIC_API_KEY, ELASTIC_INDEX, ELASTIC_URL, STRICT_MODE
from agent_proxy.logger import logger


class ElasticService:
    """
    An asynchronous service for managing Elasticsearch connections and logging.

    This service handles creating the connection to the Elasticsearch cluster
    and provides methods for both synchronous (fire-and-forget) and asynchronous
    document indexing.
    """

    def __init__(self):
        """
        Initializes the ElasticService.

        The Elasticsearch client is not instantiated until `connect()` is called
        to allow for safe integration within asynchronous event loops.
        """
        self.client: AsyncElasticsearch | None = None

    def connect(self) -> None:
        """
        Establishes the connection to the Elasticsearch client.

        Uses the `ELASTIC_URL` and `ELASTIC_API_KEY` loaded from the application
        configuration. This should be called during the application startup phase.
        """
        kwargs = {"hosts": [ELASTIC_URL]}
        if ELASTIC_API_KEY:
            kwargs["api_key"] = ELASTIC_API_KEY
        self.client = AsyncElasticsearch(**kwargs)

    async def close(self) -> None:
        """
        Gracefully closes the Elasticsearch client connection.

        This should be called during the application shutdown phase to ensure
        all underlying network connections are properly terminated.
        """
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
        try:
            await self.client.index(
                index=ELASTIC_INDEX, id=doc["request_id"], document=doc
            )
        except Exception as exc:
            msg = f"ES indexing failed for request_id={doc.get('request_id')}: {exc}"
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
