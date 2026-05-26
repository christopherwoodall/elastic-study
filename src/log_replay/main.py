import asyncio

from elasticsearch import AsyncElasticsearch

from log_replay.downloader import DatasetManager
from log_replay.engine import LogReplayer
from log_replay.host.mordor import MordorSysmonReader
from log_replay.logger import logger
from log_replay.network.zeek import ZeekConnReader


async def run_replay():
    logger.info("Starting Log Replay Engine...")

    es = AsyncElasticsearch(
        "https://localhost:9200", basic_auth=("elastic", "changeme"), verify_certs=False
    )
    manager = DatasetManager()
    replayer = LogReplayer(es_client=es, target_index="logs-endpoint.events-simulated")

    # 1. Host Attack Simulation (Fast-forward 5x)
    host_file = await manager.fetch_dataset(
        url="https://raw.githubusercontent.com/OTRF/Security-Datasets/master/datasets/atomic/windows/execution/host_execution_cmd.zip",
        filename="host_execution_cmd.zip",
    )
    host_reader = MordorSysmonReader(host_file)
    await replayer.replay(host_reader, speed_multiplier=5.0)

    # 2. Network Anomaly Simulation (As fast as possible)
    network_file = await manager.fetch_dataset(
        url="https://raw.githubusercontent.com/brimdata/zed-sample-data/main/zeek-json/conn.log",
        filename="conn.log",
    )
    network_reader = ZeekConnReader(network_file)
    await replayer.replay(network_reader, speed_multiplier=0, chunk_size=500)

    await es.close()


def main():
    asyncio.run(run_replay())


if __name__ == "__main__":
    main()
