import asyncio
import json
import os

from dotenv import load_dotenv
from elasticsearch import AsyncElasticsearch

from log_replay.downloader import DatasetManager
from log_replay.engine import LogReplayer
from log_replay.host.azure_linux import AzureHostReader
from log_replay.logging import logger
from log_replay.network.suricata import SuricataEveReader
from log_replay.network.suricata_orchestrator import process_pcap_with_suricata
from log_replay.network.zeek import ZeekLogReader
from log_replay.network.zeek_pcap import process_pcap_with_zeek

load_dotenv()

BASE_URL = os.getenv("REPLAY_LOG_BASE_URL")
HOST_FILES = json.loads(os.getenv("REPLAY_LOG_HOST_FILES", "[]").strip("'"))
NETWORK_FILES = json.loads(os.getenv("REPLAY_LOG_NET_FILES", "[]").strip("'"))


async def run_replay():
    logger.info("Starting Log Replay Engine...")

    # Use standard HTTP and remove auth since xpack.security is disabled locally
    es = AsyncElasticsearch("http://localhost:9200")

    target_index = os.getenv("REPLAY_INDEX", "logs-endpoint.events-simulated")

    manager = DatasetManager()
    replayer = LogReplayer(es_client=es, target_index=target_index)

    url_seperator = "" if BASE_URL.endswith("/") else "/"

    for f in HOST_FILES:
        logger.info(f"Processing host log file: {f}")

        log_file = await manager.fetch_dataset(
            url=f"{BASE_URL}{url_seperator}{f}", filename=f
        )
        reader = AzureHostReader(log_file)
        # Fast-forward host events at 5x speed to quickly simulate an attack scenario
        await replayer.replay(reader, speed_multiplier=5.0)

    for f in NETWORK_FILES:
        logger.info(f"Processing network log file: {f}")

        log_file = await manager.fetch_dataset(
            url=f"{BASE_URL}{url_seperator}{f}", filename=f
        )

        # Intercept and process PCAPs
        if log_file.suffix == ".pcap":
            # 1. Run and Ingest Suricata
            try:
                eve_log = process_pcap_with_suricata(log_file)
                logger.info("Ingesting Suricata alerts and flows...")
                suricata_reader = SuricataEveReader(eve_log)
                await replayer.replay(
                    suricata_reader, speed_multiplier=0, chunk_size=500
                )
            except Exception as e:
                logger.error(f"Suricata pipeline failed: {e}")

            # 2. Run and Ingest Zeek
            try:
                zeek_log_files = process_pcap_with_zeek(log_file)
                for z_log in zeek_log_files:
                    logger.info(f"Ingesting Zeek log: {z_log.name}...")
                    zeek_reader = ZeekLogReader(z_log)
                    # Ingest network events at full speed (0 multiplier) in larger chunks to simulate high-throughput scenarios
                    await replayer.replay(
                        zeek_reader, speed_multiplier=0, chunk_size=500
                    )
            except Exception as e:
                logger.error(f"Zeek pipeline failed: {e}")

    await es.close()


def main():
    asyncio.run(run_replay())


if __name__ == "__main__":
    main()
