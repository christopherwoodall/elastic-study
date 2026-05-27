import json

from tenacity import retry, stop_after_attempt, wait_exponential

from agent_mcp.config import es_client

# Exponential backoff policy shared across database calls
retry_policy = retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=2, max=10),
    reraise=True,
)


@retry_policy
async def list_indices_core() -> list[str]:
    res = await es_client.indices.get_alias(index="*")
    return [idx for idx in res if not idx.startswith(".")]


@retry_policy
async def get_mappings_core(index_name: str) -> str:
    mapping = await es_client.indices.get_mapping(index=index_name)
    return json.dumps(mapping.body, indent=2)


@retry_policy
async def run_analytics_core(index_name: str, query_dsl: str) -> str:
    query_dict = json.loads(query_dsl)
    res = await es_client.search(index=index_name, body=query_dict)
    return json.dumps(res.body["hits"], indent=2)
