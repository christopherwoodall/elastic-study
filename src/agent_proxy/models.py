from dataclasses import asdict, dataclass
from typing import Any


@dataclass
class ProxyLogDocument:
    """Represents the exact schema of our Elasticsearch log."""

    # Metadata
    request_id: str
    timestamp: str
    method: str
    path: str

    # Core request/response data
    request_body: Any = None
    response_body: Any = None
    status_code: int | None = None

    # Enrichment
    hostname: str | None = None
    environment: str | None = None
    client_ip: str | None = None
    user_agent: str | None = None
    duration_ms: float | None = None

    # Custom fields for LLM interactions (optional)
    latest_user_prompt: str | None = None
    last_message: str | None = None

    # Token Usage Data
    usage: dict[str, Any] | None = None

    def to_dict(self) -> dict:
        return asdict(self)
