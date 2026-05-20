import json
import os
from datetime import UTC, datetime

from elasticsearch import AsyncElasticsearch


class ElasticVectorStore:
    """Manages the KB vector index, ES observability logs, and local JSONL backups."""

    def __init__(
        self, es_url: str, kb_index: str, log_index: str, log_dir: str = "./logs/rag"
    ):
        self.client = AsyncElasticsearch(hosts=[es_url])
        self.kb_index = kb_index
        self.log_index = log_index
        self.log_dir = log_dir

        # Setup local file sink for observability logs
        os.makedirs(self.log_dir, exist_ok=True)
        timestamp = datetime.now(UTC).strftime("%Y%m%d_%H%M%S")
        self.filepath = os.path.join(
            self.log_dir, f"rag_interactions_{timestamp}.jsonl"
        )

        # Keep handle open for the session
        self.file = open(self.filepath, "a", encoding="utf-8")  # noqa: SIM115

    async def setup_kb_index(self) -> None:
        mapping = {
            "mappings": {
                "properties": {
                    "title": {"type": "keyword"},
                    "content": {"type": "text"},
                    "vector": {
                        "type": "dense_vector",
                        "dims": 384,
                        "index": True,
                        "similarity": "cosine",
                    },
                }
            }
        }
        if await self.client.indices.exists(index=self.kb_index):
            print(f"Dropping existing KB index '{self.kb_index}'...")
            await self.client.indices.delete(index=self.kb_index)

        print(f"Creating KB index '{self.kb_index}' with vector mapping...")
        await self.client.indices.create(index=self.kb_index, body=mapping)

    async def insert_document(
        self, doc_id: str, title: str, content: str, vector: list[float]
    ) -> None:
        doc = {"title": title, "content": content, "vector": vector}
        await self.client.index(index=self.kb_index, id=doc_id, document=doc)

    async def search(self, query_vector: list[float], top_k: int = 3) -> list[dict]:
        query = {
            "knn": {
                "field": "vector",
                "query_vector": query_vector,
                "k": top_k,
                "num_candidates": 50,
            },
            "_source": ["title", "content"],
        }
        response = await self.client.search(index=self.kb_index, body=query)
        hits = response.get("hits", {}).get("hits", [])
        return [
            {
                "score": hit["_score"],
                "title": hit["_source"]["title"],
                "content": hit["_source"]["content"],
            }
            for hit in hits
        ]

    async def log_interaction(self, log_doc: dict) -> None:
        """Dual-sink logging: Pushes to Elasticsearch and appends to local JSONL."""
        # 1. Log to Elasticsearch
        try:
            await self.client.index(
                index=self.log_index, id=log_doc["log_id"], document=log_doc
            )
        except Exception as exc:
            print(f"[RAG Logger Error] Failed to write to ES: {exc}")

        # 2. Log to Local File
        try:
            self.file.write(json.dumps(log_doc) + "\n")
            self.file.flush()
        except Exception as exc:
            print(f"[RAG Logger Error] Failed to write locally: {exc}")

    async def close(self) -> None:
        if not self.file.closed:
            self.file.close()
        await self.client.close()
