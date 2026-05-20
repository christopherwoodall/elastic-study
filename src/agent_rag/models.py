from dataclasses import asdict, dataclass
from typing import Any


@dataclass
class RAGInteractionLog:
    """Strict schema for RAG observability logging in Elasticsearch."""

    log_id: str
    timestamp: str

    # Text Data
    question: str
    answer: str
    retrieved_context: list[dict[str, Any]]  # Stores title, score, and content

    # Latency Telemetry
    embedding_latency_ms: float
    search_latency_ms: float
    generation_latency_ms: float
    total_latency_ms: float

    # Token Economics
    prompt_tokens: int
    completion_tokens: int
    total_tokens: int

    def to_dict(self) -> dict:
        return asdict(self)
