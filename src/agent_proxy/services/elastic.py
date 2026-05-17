import asyncio

from elasticsearch import AsyncElasticsearch

from agent_proxy.config import ELASTIC_API_KEY, ELASTIC_INDEX, ELASTIC_URL, STRICT_MODE
from agent_proxy.logger import logger


class ElasticService:
    def __init__(self):
        self.client: AsyncElasticsearch | None = None

    def connect(self):
        kwargs = {"hosts": [ELASTIC_URL]}
        if ELASTIC_API_KEY:
            kwargs["api_key"] = ELASTIC_API_KEY
        self.client = AsyncElasticsearch(**kwargs)

    async def close(self):
        if self.client:
            await self.client.close()

    async def index_log(self, doc: dict) -> None:
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
        task = asyncio.create_task(self.index_log(doc))
        task.add_done_callback(self._task_error_handler)

    def _task_error_handler(self, task: asyncio.Task) -> None:
        if task.cancelled():
            return
        exc = task.exception()
        if exc:
            logger.error("Background ES task raised: %s", exc)


# Singleton instance to be used across the app
es_service = ElasticService()
