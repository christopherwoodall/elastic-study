from contextlib import asynccontextmanager

import uvicorn
from fastapi import FastAPI, Request
from mcp.server.sse import SseServerTransport
from starlette.routing import Mount

from agent_mcp.api_routes import router as human_router
from agent_mcp.config import es_client
from agent_mcp.mcp_tools import mcp_server


@asynccontextmanager
async def lifespan(app: FastAPI):
    yield
    # Cleanly close the database connection on shutdown
    await es_client.close()


app = FastAPI(
    title="Elasticsearch Operations API & MCP Server",
    description="Provides a Swagger UI for humans and an SSE endpoint for AI Agents.",
    lifespan=lifespan,
)

# Attach human-facing routes
app.include_router(human_router)

# Setup Agent Transport
sse_transport = SseServerTransport("/messages/")

# Handle POST messages via raw ASGI mount (Fixes the RuntimeError)
# Use Route instead of Mount to avoid 307 -> 202 ping pong
app.router.routes.append(Mount("/messages", app=sse_transport.handle_post_message))
# app.router.routes.append(Route("/messages", app=sse_transport.handle_post_message, methods=["POST"]))
# @app.post("/messages", include_in_schema=False)
# async def mcp_messages(request: Request):
#     """Receives JSON-RPC messages from the AI agent."""
#     await sse_transport.handle_post_message(
#         request.scope, request.receive, request._send
#     )


@app.get("/sse", include_in_schema=False)
async def mcp_sse(request: Request):
    """Establishes the Server-Sent Events stream for the AI agent."""
    async with sse_transport.connect_sse(
        request.scope, request.receive, request._send
    ) as streams:
        await mcp_server.run(
            streams[0], streams[1], mcp_server.create_initialization_options()
        )


def start():
    """Entry point mapped to pyproject.toml."""
    uvicorn.run("agent_mcp.main:app", host="0.0.0.0", port=8001, reload=True)
