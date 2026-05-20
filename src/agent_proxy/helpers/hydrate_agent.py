import asyncio
import json
import os

from agent_proxy.config import AGENT_LOG_DIR
from agent_proxy.services.elastic import es_service


async def async_hydrate() -> None:
    print("=== Initiating Agent Proxy Log Recovery Pipeline ===")

    if not os.path.exists(AGENT_LOG_DIR):
        print(
            f"Target log path '{AGENT_LOG_DIR}' could not be resolved. Skipping execution."
        )
        return

    # Filter for proxy log signatures, avoiding collision files
    target_files = [
        f
        for f in os.listdir(AGENT_LOG_DIR)
        if f.startswith("proxy_run_") and f.endswith(".jsonl")
    ]

    if not target_files:
        print("No recoverable local transaction signatures encountered. Exiting.")
        return

    # Reuse service initialization boundaries safely
    es_service.connect()
    total_recovered = 0

    try:
        for filename in target_files:
            filepath = os.path.join(AGENT_LOG_DIR, filename)
            print(f"Rehydrating records from file target: {filename}...")

            with open(filepath, encoding="utf-8") as file:
                for line in file:
                    line = line.strip()
                    if not line:
                        continue

                    raw_document = json.loads(line)

                    # Direct client indexing bypasses local append loop mirroring
                    await es_service.client.index(
                        index=os.environ.get("ELASTIC_INDEX", "llm-proxy-logs"),
                        id=raw_document["request_id"],
                        document=raw_document,
                    )
                    total_recovered += 1

        print(
            f"Success! Rehydration sync finalized. Recovered {total_recovered} entries."
        )
    except Exception as exc:
        print(
            f"Operational execution failure occurred during recovery processing: {exc}"
        )
    finally:
        await es_service.close()


def main() -> None:
    try:
        asyncio.run(async_hydrate())
    except KeyboardInterrupt:
        print("\nProcess execution aborted by administrative command.")


if __name__ == "__main__":
    main()
