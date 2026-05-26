import json
from abc import ABC, abstractmethod
from collections.abc import AsyncGenerator
from pathlib import Path
from typing import Any


class DatasetReader(ABC):
    """Abstract Base Class for reading raw logs and mapping to ECS."""

    def __init__(self, file_path: Path):
        self.file_path = file_path

    async def stream_ecs_documents(self) -> AsyncGenerator[dict[str, Any]]:
        """Streams normalized ECS documents line by line."""
        with open(self.file_path, encoding="utf-8") as f:
            for line in f:
                if not line.strip():
                    continue
                raw_doc = json.loads(line)
                ecs_doc = self.map_to_ecs(raw_doc)
                if ecs_doc:
                    yield ecs_doc

    @abstractmethod
    def map_to_ecs(self, raw_doc: dict[str, Any]) -> dict[str, Any]:
        """Transforms a raw vendor document into ECS v8.x schema."""
        pass
