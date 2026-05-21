#!/usr/bin/env bash
set -euo pipefail

uv run --env-file .env rag-ask "How does Elasticsearch handle search and what is a vector database?"
uv run --env-file .env rag-ask "How does an inverted index work in the context of search engines like Elasticsearch?"
uv run --env-file .env rag-ask "Explain the concept of cosine similarity and how it is used to find matching documents."
uv run --env-file .env rag-ask "What is Retrieval-augmented generation (RAG) and how does it improve the answers given by large language models?"
uv run --env-file .env rag-ask "How does the k-nearest neighbors algorithm function when searching through a vector database?"
uv run --env-file .env rag-ask "Describe how Okapi BM25 scores document relevance in search."
uv run --env-file .env rag-ask "What were the primary scientific goals and discoveries of the James Webb Space Telescope?"
uv run --env-file .env rag-ask "Compare traditional search using an inverted index to semantic search using vector embeddings."
