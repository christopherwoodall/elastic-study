import asyncio
import json
import os
import sys
import time
import uuid

import httpx
from dotenv import load_dotenv

from agent_rag.embedder import LocalEmbedder
from agent_rag.engine import RAGEngine
from agent_rag.llm_client import OpenRouterClient
from agent_rag.vector_store import ElasticVectorStore

load_dotenv()

ES_URL = os.environ.get("ELASTIC_URL", "http://localhost:9200")
RAG_KB_INDEX = os.environ.get("RAG_KB_INDEX", "rag-knowledge-base")
RAG_LOG_INDEX = os.environ.get("RAG_LOG_INDEX", "rag-observability-logs")
OPENROUTER_KEY = os.environ.get("OPENROUTER_API_KEY")

# Expanded documents to provide deeper context for Elasticsearch and Vector DB queries
WIKI_TOPICS = [
    "Elasticsearch",
    "Large language model",
    "Retrieval-augmented generation",
    "Vector database",
    "James Webb Space Telescope",
    "Inverted index",
    "Okapi BM25",
    "Cosine similarity",
    "K-nearest neighbors algorithm",
]


async def fetch_wikipedia_summary(topic: str) -> str:
    """Fetches real-world text from Wikipedia with a descriptive User-Agent header."""
    url = f"https://en.wikipedia.org/w/api.php?action=query&prop=extracts&exintro&explaintext&titles={topic}&format=json"

    # Wikipedia requires an identifiable User-Agent header to allow programmatic access
    headers = {
        "User-Agent": "ElasticStudyRAGEngine/1.0 (contact: github_or_email_placeholder) httpx/client"
    }

    async with httpx.AsyncClient() as client:
        response = await client.get(url, headers=headers)

        # Guard block to check for failures before running json parsing
        if response.status_code != 200:
            print(
                f"  [HTTP Error] Wikipedia returned status code {response.status_code}"
            )
            return ""

        try:
            data = response.json()
        except json.JSONDecodeError:
            print(
                "  [Format Error] Failed to parse API response as JSON. Content preview:"
            )
            print(response.text[:200])
            return ""

        pages = data.get("query", {}).get("pages", {})
        for _page_id, page_info in pages.items():
            return page_info.get("extract", "")

    return ""


# =============================================================
# KNOWLEDGE BASE HYDRATION (WIKIPEDIA)
# =============================================================
async def async_hydrate() -> None:
    print("=== Initiating RAG Database Hydration ===")

    # 1. Warm up the embedding model with upfront verbosity
    print("\n[Step 1/3] Initializing Local Transformer Embedder...")
    print(
        "           (If this is the first run, model weights will download automatically)..."
    )
    t_model_start = time.perf_counter()
    embedder = LocalEmbedder()
    embedder.load()
    print(
        f"           Model ready! Initialized in {time.perf_counter() - t_model_start:.2f} seconds.\n"
    )

    # 2. Connect to vector store and wipe index mappings
    print("[Step 2/3] Configuring Elasticsearch index maps...")
    store = ElasticVectorStore(
        es_url=ES_URL, kb_index=RAG_KB_INDEX, log_index=RAG_LOG_INDEX
    )
    await store.setup_kb_index()

    # 3. Pull summaries, embed, and sink
    print("\n[Step 3/3] Commencing data ingestion pipeline loop...")
    try:
        for idx, topic in enumerate(WIKI_TOPICS, 1):
            print(f"\n({idx}/{len(WIKI_TOPICS)}) Processing topic: '{topic}'")

            t0 = time.perf_counter()
            content = await fetch_wikipedia_summary(topic)
            if not content:
                print(f"  -> Failed to fetch text data for '{topic}', skipping.")
                continue
            print(
                f"  -> Downloaded {len(content)} characters in {time.perf_counter() - t0:.2f}s"
            )

            t1 = time.perf_counter()
            vector = embedder.embed(content)
            print(
                f"  -> Generated dense embedding vector in {time.perf_counter() - t1:.2f}s"
            )

            t2 = time.perf_counter()
            doc_id = str(uuid.uuid4())
            await store.insert_document(
                doc_id=doc_id, title=topic, content=content, vector=vector
            )
            print(
                f"  -> Stored to Elasticsearch index '{RAG_KB_INDEX}' in {time.perf_counter() - t2:.2f}s"
            )

        print("\nHydration complete! You can now query the RAG pipeline.")
    finally:
        await store.close()


def hydrate() -> None:
    try:
        asyncio.run(async_hydrate())
    except KeyboardInterrupt:
        print("\nHydration aborted by user.")


# =============================================================
# OBSERVABILITY LOGS HYDRATION (JSONL -> ES)
# =============================================================
async def async_hydrate_logs() -> None:
    """Reads all local JSONL logs in ./logs/rag and pushes them to Elasticsearch."""
    print("=== Initiating RAG Logs Hydration Pipeline ===")

    log_dir = "./logs/rag"
    if not os.path.exists(log_dir):
        print(f"Log directory '{log_dir}' does not exist. Nothing to hydrate.")
        return

    files = [
        f
        for f in os.listdir(log_dir)
        if f.startswith("rag_interactions_") and f.endswith(".jsonl")
    ]
    if not files:
        print("No RAG .jsonl logs found in directory. Exiting.")
        return

    store = ElasticVectorStore(
        es_url=ES_URL, kb_index=RAG_KB_INDEX, log_index=RAG_LOG_INDEX, log_dir=log_dir
    )
    total_synced = 0

    try:
        for filename in files:
            filepath = os.path.join(log_dir, filename)
            print(f"Hydrating file: {filename}...")

            with open(filepath, encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue

                    doc = json.loads(line)
                    await store.client.index(
                        index=store.log_index, id=doc["log_id"], document=doc
                    )
                    total_synced += 1

        print(f"Hydration complete. {total_synced} RAG logs synced to Elasticsearch.")
    except Exception as exc:
        print(f"Hydration failed: {exc}")
    finally:
        await store.close()


def hydrate_logs() -> None:
    try:
        asyncio.run(async_hydrate_logs())
    except KeyboardInterrupt:
        print("\nLog hydration aborted by user.")


# =============================================================
# RAG ENGINE EXECUTION
# =============================================================
async def async_ask(question: str) -> None:
    if not OPENROUTER_KEY:
        print("ERROR: OPENROUTER_API_KEY is not set in .env")
        return

    embedder = LocalEmbedder()
    store = ElasticVectorStore(
        es_url=ES_URL, kb_index=RAG_KB_INDEX, log_index=RAG_LOG_INDEX
    )
    llm = OpenRouterClient(api_key=OPENROUTER_KEY)

    engine = RAGEngine(embedder=embedder, store=store, llm=llm)

    try:
        answer = await engine.query(question)
        print("\n=== ANSWER ===")
        print(answer)
        print("==============")
    finally:
        await store.close()


def ask() -> None:
    if len(sys.argv) < 2:
        print('Usage: uv run rag-ask "Your question here"')
        sys.exit(1)

    question = " ".join(sys.argv[1:])
    asyncio.run(async_ask(question))
