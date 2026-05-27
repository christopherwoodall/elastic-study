import json

from mcp.server import Server
from mcp.types import TextContent, Tool

from agent_mcp.operations import (
    get_mappings_core,
    list_indices_core,
    run_analytics_core,
)

mcp_server = Server("elastic-mcp")


@mcp_server.list_tools()
async def handle_list_tools() -> list[Tool]:
    return [
        Tool(
            name="list_indices",
            description="List all available Elasticsearch indices, excluding system indices.",
            inputSchema={"type": "object", "properties": {}},
        ),
        Tool(
            name="get_mappings",
            description="Get field mappings (schema) for an Elasticsearch index.",
            inputSchema={
                "type": "object",
                "properties": {"index_name": {"type": "string"}},
                "required": ["index_name"],
            },
        ),
        Tool(
            name="run_analytics",
            description="Run analytics on an Elasticsearch index using a JSON Query DSL string.",
            inputSchema={
                "type": "object",
                "properties": {
                    "index_name": {"type": "string"},
                    "query_dsl": {"type": "string"},
                },
                "required": ["index_name", "query_dsl"],
            },
        ),
    ]


@mcp_server.call_tool()
async def handle_call_tool(name: str, arguments: dict) -> list[TextContent]:
    try:
        if name == "list_indices":
            res = await list_indices_core()
            return [TextContent(type="text", text=json.dumps(res))]
        elif name == "get_mappings":
            res = await get_mappings_core(arguments["index_name"])
            return [TextContent(type="text", text=res)]
        elif name == "run_analytics":
            res = await run_analytics_core(
                arguments["index_name"], arguments["query_dsl"]
            )
            return [TextContent(type="text", text=res)]
        else:
            raise ValueError(f"Unknown tool: {name}")
    except Exception as e:
        return [TextContent(type="text", text=f"Error: {str(e)}")]
