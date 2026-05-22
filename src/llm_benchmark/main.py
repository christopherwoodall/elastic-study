import asyncio
import json
import os

import httpx
from dotenv import load_dotenv

from llm_benchmark.clients import NemotronDiffusionClient
from llm_benchmark.engine import BenchmarkEngine
from llm_benchmark.protocols import TelemetryResult
from llm_benchmark.sinks import (
    CompositeTelemetrySink,
    ElasticsearchTelemetrySink,
    LocalFileTelemetrySink,
)

load_dotenv()

ES_URL = os.environ.get("ELASTIC_URL", "http://localhost:9200")
BENCHMARK_INDEX = os.environ.get("BENCHMARK_INDEX", "llm-benchmarks")
TARGET_MODEL = os.environ.get("TARGET_MODEL", "nvidia/Nemotron-Labs-Diffusion-8B")
LOCAL_LOG_DIR = "./logs/benchmarks"


async def fetch_benchmarks(limit: int = 5) -> list[dict[str, str]]:
    """
    Fetches instructions AND ground-truth outputs from the Alpaca dataset.
    """
    url = f"https://datasets-server.huggingface.co/rows?dataset=tatsu-lab/alpaca&config=default&split=train&offset=0&length={limit}"

    print(f"Downloading dataset: Fetching {limit} instructions from Alpaca...")
    async with httpx.AsyncClient() as client:
        response = await client.get(url, timeout=10.0)
        response.raise_for_status()
        data = response.json()

    # We now return a dictionary containing both the prompt and the expected answer
    return [
        {"prompt": row["row"]["instruction"], "expected": row["row"]["output"]}
        for row in data.get("rows", [])
    ]


# =============================================================
# COMMAND: RUN BENCHMARK
# =============================================================
async def async_start() -> None:
    print("=== Initiating LLM Benchmark Pipeline ===")

    client = NemotronDiffusionClient(repo_name=TARGET_MODEL)

    es_sink = ElasticsearchTelemetrySink(es_url=ES_URL, index_name=BENCHMARK_INDEX)
    file_sink = LocalFileTelemetrySink(log_dir=LOCAL_LOG_DIR)
    composite_sink = CompositeTelemetrySink([es_sink, file_sink])

    try:
        await client.load_model()

        # 1. Fetch the data (now a list of dicts with prompt + expected)
        benchmark_data = await fetch_benchmarks(limit=3)
        if not benchmark_data:
            print("Failed to load benchmarks. Exiting.")
            return

        engine = BenchmarkEngine(client=client, sink=composite_sink)
        print("Starting Benchmark Engine...")

        # 2. Update the parameter name here!
        await engine.run_suite(benchmark_data=benchmark_data)

    finally:
        print("Cleaning up resources...")
        await client.close()
        await composite_sink.close()


def start() -> None:
    try:
        asyncio.run(async_start())
    except KeyboardInterrupt:
        print("\nBenchmark aborted by user.")


# =============================================================
# COMMAND: HYDRATE ELASTICSEARCH
# =============================================================
async def async_hydrate() -> None:
    """Reads all local JSONL logs and pushes them to Elasticsearch."""
    print("=== Initiating Elasticsearch Hydration Pipeline ===")

    if not os.path.exists(LOCAL_LOG_DIR):
        print(f"Log directory '{LOCAL_LOG_DIR}' does not exist. Nothing to hydrate.")
        return

    files = [f for f in os.listdir(LOCAL_LOG_DIR) if f.endswith(".jsonl")]
    if not files:
        print("No .jsonl files found in log directory. Exiting.")
        return

    es_sink = ElasticsearchTelemetrySink(es_url=ES_URL, index_name=BENCHMARK_INDEX)
    total_synced = 0

    try:
        for filename in files:
            filepath = os.path.join(LOCAL_LOG_DIR, filename)
            print(f"Hydrating file: {filename}...")

            with open(filepath, encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue

                    # Rehydrate dictionary into Dataclass instance
                    payload = json.loads(line)
                    result = TelemetryResult(**payload)

                    await es_sink.flush(result)
                    total_synced += 1

        print(f"Hydration complete. {total_synced} records synced to Elasticsearch.")
    except Exception as exc:
        print(f"Hydration failed: {exc}")
    finally:
        await es_sink.close()


def hydrate() -> None:
    try:
        asyncio.run(async_hydrate())
    except KeyboardInterrupt:
        print("\nHydration aborted by user.")
