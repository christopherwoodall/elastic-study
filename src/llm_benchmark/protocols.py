from dataclasses import asdict, dataclass
from typing import Protocol


@dataclass
class TelemetryResult:
    """Standardized benchmark payload for a single model generation."""

    run_id: str
    model_name: str

    # Text Data
    prompt: str
    response_text: str
    expected_output: str | None
    is_correct: bool | None

    # Hardware Telemetry
    time_to_first_token_ms: float
    tokens_per_second: float
    total_latency_ms: float
    output_tokens: int

    def to_dict(self) -> dict:
        return asdict(self)


class ModelClientProtocol(Protocol):
    async def load_model(self) -> None: ...
    async def generate(self, run_id: str, prompt: str) -> TelemetryResult: ...
    async def close(self) -> None: ...


class TelemetrySinkProtocol(Protocol):
    async def flush(self, result: TelemetryResult) -> None: ...
    async def close(self) -> None: ...
