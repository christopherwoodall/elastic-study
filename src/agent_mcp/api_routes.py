import json

from fastapi import APIRouter
from pydantic import BaseModel

from agent_mcp.operations import (
    get_mappings_core,
    list_indices_core,
    run_analytics_core,
)

router = APIRouter(tags=["Manual Testing"])


class AnalyticsPayload(BaseModel):
    query_dsl: dict


@router.get("/api/indices")
async def api_list_indices():
    return await list_indices_core()


@router.get("/api/mappings/{index_name}")
async def api_get_mappings(index_name: str):
    return json.loads(await get_mappings_core(index_name))


@router.post("/api/analytics/{index_name}")
async def api_run_analytics(index_name: str, payload: AnalyticsPayload):
    # Convert Pydantic dict back to string for the core operation
    return json.loads(
        await run_analytics_core(index_name, json.dumps(payload.query_dsl))
    )
