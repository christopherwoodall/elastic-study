# Elastic RAG Pipeline

A Retrieval-Augmented Generation (RAG) pipeline built natively on Elasticsearch 9.x.
Leverages local embedding models for privacy and speed, kNN vector search for context retrieval, and OpenRouter for high-quality LLM generation. This module is entirely decoupled from the proxy and benchmark components, and includes a full observability suite to track latency, costs, and retrieval accuracy across both Elasticsearch and local log files.

## Getting Started

**Step 1.** Install Machine Learning dependencies

Because this suite generates dense vector embeddings locally, it requires the `sentence-transformers` library, which provides a lightweight, local model (`all-MiniLM-L6-v2`) to turn text into 384-dimensional vectors.

```bash
uv pip install sentence-transformers httpx
```

**Step 2.** Configure environment

Ensure your `.env` file contains your OpenRouter API key and points to your Elasticsearch instance.

```env
OPENROUTER_API_KEY=your_openrouter_key
ELASTIC_URL=http://localhost:9200
```

**Step 3.** Hydrate the Database

Before you can ask questions, you must hydrate the vector database. This script reaches out to the Wikipedia REST API, fetches articles (e.g., Elasticsearch, Quantum Computing, LLMs), embeds them locally, and stores the vectors in Elasticsearch. It also initializes the mapping for the Knowledge Base.

```bash
uv run --env-file .env rag-hydrate
```

**Step 4.** Query the Pipeline

Once hydrated, you can ask questions via the CLI. The engine will embed your question, search Elasticsearch for the closest conceptual matches, inject that context into a prompt for OpenRouter's `moonshotai/kimi-k2.5` model, and finally ship a detailed telemetry log back to Elasticsearch and your local file system.

```bash
uv run --env-file .env rag-ask "How does Elasticsearch handle search and what is a vector database?"
```

**Step 5.** Hydrate Observability Logs (Optional)

Because the pipeline writes observability logs to both Elasticsearch and `./logs/rag/`, you never lose telemetry data if the database goes offline. You can re-sync these local JSONL files to Elasticsearch at any time:

```bash
uv run --env-file .env rag-hydrate-logs
```

---

## Configuration

All settings are controlled via environment variables.

| Variable | Default | Description |
| --- | --- | --- |
| `OPENROUTER_API_KEY` | *(None)* | Required to authenticate with the generation LLM. |
| `ELASTIC_URL` | `http://localhost:9200` | Elasticsearch node URL. |
| `RAG_KB_INDEX` | `knowledge-base-rag` | The specific Elasticsearch index used to store documents and vectors. |
| `RAG_LOG_INDEX` | `rag-observability-logs` | The index used to store interaction telemetry, tokens, and retrieved context. |

---

## Architecture

```text
                      ┌─────────────────────────┐
                      │      User Question      │
                      └───────────┬─────────────┘
                                  ▼
┌─────────────────┐    ┌─────────────────────────┐    ┌─────────────────┐
│ Local Embedder  │◄───┤       RAG Engine        ├───►│ OpenRouter API  │
│(all-MiniLM-L6)  │───►│     (Orchestrator)      │◄───┤(kimi-k2.5 LLM)  │
└─────────────────┘    └──────────┬──────────────┘    └─────────────────┘
                                  │
                    ┌─────────────┴─────────────┐
                    ▼                           ▼
    ┌──────────────────────────────────┐    ┌────────────────┐
    │ Elasticsearch (Dual-Index Store) │    │  Local .jsonl  │
    │ ├─ knowledge-base-rag (kNN)      │    │  ./logs/rag/   │
    │ └─ rag-observability-logs        │    └────────────────┘
    └──────────────────────────────────┘

```

### Features

* **Local Embeddings:** Uses `sentence-transformers` (`all-MiniLM-L6-v2`) for zero-cost, private text vectorization. No data is sent to OpenAI or OpenRouter during the embedding phase.
* **Native Vector Search:** Utilizes Elasticsearch 9.x's native `dense_vector` mapping and kNN search capabilities to find contextually relevant text chunks.
* **Dynamic Hydration:** Features a lightweight scraper that fetches real-world summaries from the Wikipedia REST API to instantly bootstrap a meaningful knowledge base.
* **Full Observability:** Automatically tracks and logs end-to-end latency breakdowns, token economics, and retrieved context chunks.
* **Resilient Logging:** Employs a dual-sink pattern, writing observability telemetry simultaneously to an Elasticsearch index and a local JSONL file to prevent data loss.
* **Decoupled Architecture:** Separates the concerns of embedding, storage, and text generation, allowing you to easily swap the LLM backend or the vector database without rewriting the core engine.

---

## Elasticsearch Schemas

### 1. Knowledge Base (Vector Storage)

To perform kNN vector searches, the Knowledge Base index (`knowledge-base-rag`) must be created with a strict mapping *before* documents are inserted. The hydration script enforces this schema:

```json
{
  "mappings": {
    "properties": {
      "title": { "type": "keyword" },
      "content": { "type": "text" },
      "vector": {
        "type": "dense_vector",
        "dims": 384,
        "index": true,
        "similarity": "cosine"
      }
    }
  }
}

```

### 2. Observability Logs (Telemetry & Auditing)

Every time a user asks a question, a comprehensive log is shipped to the `rag-observability-logs` index and appended to `./logs/rag/`. This allows you to audit the pipeline and answer the question: *"Did the LLM hallucinate, or did the vector search fail?"*

```json
{
  "log_id": "rag-550e8400-e29b-41d4-a716-446655440000",
  "timestamp": "2026-05-20T15:24:52.123Z",
  "question": "How does Elasticsearch handle search?",
  "answer": "Elasticsearch handles search by distributing...",
  "retrieved_context": [
    {
      "score": 0.85,
      "title": "Elasticsearch",
      "content": "Elasticsearch is a distributed, RESTful search and analytics engine..."
    }
  ],
  "embedding_latency_ms": 45.2,
  "search_latency_ms": 12.5,
  "generation_latency_ms": 1205.8,
  "total_latency_ms": 1263.5,
  "prompt_tokens": 850,
  "completion_tokens": 120,
  "total_tokens": 970
}

```

### Notes on Storage & Retrieval

* **Dimensionality Limits:** The `dims` parameter in the schema (`384`) is tightly coupled to the output size of the `all-MiniLM-L6-v2` embedding model. If you upgrade the local embedder to a larger model (e.g., `text-embedding-3-small` which outputs 1536 dims), you **must** update the schema and re-hydrate the index.
* **Idempotent Hydration:** Running `uv run rag-hydrate` is a destructive operation by design for the knowledge base. It drops the existing `knowledge-base-rag` index and recreates it to ensure the mapping is completely pristine. Do not use this index for manual storage unless you disable the drop-index behavior.
* **Log Hydration is Additive:** Running `uv run rag-hydrate-logs` is idempotent for your file system (it reads but does not delete local logs), but it will push documents to Elasticsearch. Because `log_id` is explicitly set as the Elasticsearch document ID, duplicate pushes will safely overwrite existing records rather than creating duplicates.
* **Similarity Metric:** The pipeline uses `cosine` similarity, which is standard for sentence embeddings, measuring the angle between vectors rather than their magnitude.