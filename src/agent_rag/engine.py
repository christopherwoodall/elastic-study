import time
import uuid
from datetime import UTC, datetime

from agent_rag.embedder import LocalEmbedder
from agent_rag.llm_client import OpenRouterClient
from agent_rag.models import RAGInteractionLog
from agent_rag.vector_store import ElasticVectorStore


class RAGEngine:
    def __init__(
        self, embedder: LocalEmbedder, store: ElasticVectorStore, llm: OpenRouterClient
    ):
        self.embedder = embedder
        self.store = store
        self.llm = llm

    async def query(self, question: str) -> str:
        total_start = time.perf_counter()

        # Phase 1: Embedding
        print(f"\n[1] Embedding question: '{question}'...")
        t0 = time.perf_counter()
        query_vector = self.embedder.embed(question)
        embed_time_ms = (time.perf_counter() - t0) * 1000

        # Phase 2: Vector Search
        print("[2] Searching Elasticsearch for context...")
        t1 = time.perf_counter()
        results = await self.store.search(query_vector=query_vector, top_k=2)
        search_time_ms = (time.perf_counter() - t1) * 1000

        if not results:
            return "I could not find any relevant information in the database."

        context_blocks = []
        for _, res in enumerate(results):
            print(f"    -> Found match: {res['title']} (Score: {res['score']:.2f})")
            context_blocks.append(f"Source: {res['title']}\n{res['content']}")

        context_str = "\n\n---\n\n".join(context_blocks)

        # Phase 3: LLM Generation
        print(f"[3] Generating response via OpenRouter ({self.llm.model})...")
        system_prompt = (
            "You are a highly accurate technical assistant. Answer the user's question "
            "based strictly on the provided context. If the context does not contain the answer, "
            "state that you do not know. Do not use outside knowledge."
        )
        user_prompt = f"Context:\n{context_str}\n\nQuestion: {question}"

        t2 = time.perf_counter()
        answer, usage = await self.llm.generate(system_prompt, user_prompt)
        gen_time_ms = (time.perf_counter() - t2) * 1000

        total_time_ms = (time.perf_counter() - total_start) * 1000

        # Phase 4: Construct and Ship Observability Log
        log_entry = RAGInteractionLog(
            log_id=f"rag-{uuid.uuid4()}",
            timestamp=datetime.now(UTC).isoformat(),
            question=question,
            answer=answer,
            retrieved_context=results,
            embedding_latency_ms=round(embed_time_ms, 2),
            search_latency_ms=round(search_time_ms, 2),
            generation_latency_ms=round(gen_time_ms, 2),
            total_latency_ms=round(total_time_ms, 2),
            prompt_tokens=usage.get("prompt_tokens", 0),
            completion_tokens=usage.get("completion_tokens", 0),
            total_tokens=usage.get("total_tokens", 0),
        )

        # Fire and forget the log to Elasticsearch
        await self.store.log_interaction(log_entry.to_dict())

        return answer
