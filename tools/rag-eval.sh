#!/usr/bin/env bash
set -euo pipefail

# Target: Elasticsearch (single doc)
uv run --env-file .env rag-ask "What company originally developed Elasticsearch and what open-source project is it built on?"

# Target: Inverted index (single doc)
uv run --env-file .env rag-ask "What data structure does an inverted index map, and what does it map to?"

# Target: Okapi BM25 (single doc)
# uv run --env-file .env rag-ask "What information retrieval system first implemented BM25, and at which university was it developed?"

# Target: Cosine similarity (single doc)
uv run --env-file .env rag-ask "What geometric property does cosine similarity measure, and what value does it return for two identical vectors?"

# Target: K-nearest neighbors (single doc)
uv run --env-file .env rag-ask "In the k-nearest neighbors algorithm, what determines which neighbors are nearest and what does k represent?"

# Target: Vector database (single doc)
uv run --env-file .env rag-ask "What type of database is specifically optimized for storing and querying embedding vectors?"

# Target: Large language model (single doc)
uv run --env-file .env rag-ask "What distinguishes a large language model from earlier neural language models in terms of scale?"

# Target: Retrieval-augmented generation (single doc)
uv run --env-file .env rag-ask "What retrieval method does RAG combine with generative models to reduce hallucination?"

# Target: James Webb Space Telescope (single doc, isolated — no meaningful distractor)
uv run --env-file .env rag-ask "What space agency operates the James Webb Space Telescope and what is its primary observing wavelength range?"

# Target: Inverted index + Elasticsearch (cross-doc distractor test)
uv run --env-file .env rag-ask "How does an inverted index work in the context of search engines like Elasticsearch?"

# Target: K-nearest neighbors + Vector database (cross-doc distractor test)
uv run --env-file .env rag-ask "How does the k-nearest neighbors algorithm function when searching through a vector database?"

# Target: Okapi BM25 (distractor: Inverted index)
uv run --env-file .env rag-ask "Describe how Okapi BM25 scores document relevance in search."

# Target: RAG + Large language model (cross-doc)
uv run --env-file .env rag-ask "What is Retrieval-augmented generation and how does it improve answers given by large language models?"

# Target: Cosine similarity + K-nearest neighbors (distractor test — related math)
uv run --env-file .env rag-ask "Explain the concept of cosine similarity and how it is used to find matching documents."

# Target: Inverted index + Vector database (cross-doc, contrasts retrieval paradigms)
uv run --env-file .env rag-ask "Compare traditional search using an inverted index to semantic search using vector embeddings."

# Target: Elasticsearch + Vector database (distractor test — both search systems)
uv run --env-file .env rag-ask "How does Elasticsearch handle search and what is a vector database?"

# Target: James Webb Space Telescope (single doc)
uv run --env-file .env rag-ask "What were the primary scientific goals and discoveries of the James Webb Space Telescope?"
