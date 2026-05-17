import os

from dotenv import load_dotenv

load_dotenv()

OPENROUTER_KEY: str | None = os.environ.get("OPENROUTER_API_KEY")

TARGET_URL: str = os.environ.get("TARGET_URL", "https://openrouter.ai/api/v1")
ELASTIC_URL: str = os.environ.get("ELASTIC_URL", "http://localhost:9200")
ELASTIC_API_KEY: str | None = os.environ.get("ELASTIC_API_KEY")
ELASTIC_INDEX: str = os.environ.get("ELASTIC_INDEX", "llm-proxy-logs")

PROXY_HOST: str = os.environ.get("PROXY_HOST", "0.0.0.0")
PROXY_PORT: int = int(os.environ.get("PROXY_PORT", "8000"))

STRICT_MODE: bool = os.environ.get("STRICT_MODE", "false").lower() == "true"
LOG_LEVEL: str = os.environ.get("LOG_LEVEL", "INFO").upper()
