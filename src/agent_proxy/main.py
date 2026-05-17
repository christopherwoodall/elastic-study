from contextlib import asynccontextmanager

import uvicorn
from fastapi import FastAPI

import agent_proxy
from agent_proxy.config import (
    ELASTIC_URL,
    LOG_LEVEL,
    PROXY_HOST,
    PROXY_PORT,
    STRICT_MODE,
    TARGET_URL,
)
from agent_proxy.logger import logger
from agent_proxy.routes import router
from agent_proxy.services.elastic import es_service
from agent_proxy.services.proxy import http_proxy


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info(
        "Agent Proxy starting — target=%s  elastic=%s  strict=%s  port=%d",
        TARGET_URL,
        ELASTIC_URL,
        STRICT_MODE,
        PROXY_PORT,
    )
    es_service.connect()
    http_proxy.start()

    yield

    logger.info("Shutting down — closing ES and HTTP clients")
    await es_service.close()
    await http_proxy.close()


app = FastAPI(
    title=agent_proxy.__title__,
    version=agent_proxy.__version__,
    docs_url=None,
    redoc_url=None,
    lifespan=lifespan,
)

app.include_router(router)


def start() -> None:
    uvicorn.run(
        "agent_proxy.main:app",
        host=PROXY_HOST,
        port=PROXY_PORT,
        log_level=LOG_LEVEL.lower(),
        reload=False,
    )


if __name__ == "__main__":
    start()
