import asyncio
import os

from dotenv import load_dotenv
from elasticsearch import AsyncElasticsearch

from log_replay.downloader import DatasetManager
from log_replay.engine import LogReplayer
from log_replay.host.mordor import MordorSysmonReader
from log_replay.logger import logger
from log_replay.network.zeek import ZeekConnReader

load_dotenv()


async def run_replay():
    logger.info("Starting Log Replay Engine...")

    # Use standard HTTP and remove auth since xpack.security is disabled locally
    es = AsyncElasticsearch("http://localhost:9200")

    manager = DatasetManager()
    target_index = os.getenv("REPLAY_INDEX", "logs-endpoint.events-simulated")
    replayer = LogReplayer(es_client=es, target_index=target_index)

    # 1. Host Attack Simulation (Fast-forward 5x)
    host_file = await manager.fetch_dataset(
        url="https://raw.githubusercontent.com/OTRF/Security-Datasets/master/datasets/atomic/windows/execution/host/empire_launcher_vbs.zip",
        filename="empire_launcher_vbs.zip",
    )
    host_reader = MordorSysmonReader(host_file)
    await replayer.replay(host_reader, speed_multiplier=5.0)

    # 2. Network Anomaly Simulation (Brimdata Generic Network Noise)
    network_file_1 = await manager.fetch_dataset(
        url="https://raw.githubusercontent.com/brimdata/zed-sample-data/main/zeek-json/conn.json.gz",
        filename="conn_brim.json.gz",
    )
    network_reader_1 = ZeekConnReader(network_file_1)
    await replayer.replay(network_reader_1, speed_multiplier=0, chunk_size=500)

    # 3. Network Anomaly Simulation (IoT-23 Mirai Botnet C2 Traffic)
    network_file_2 = await manager.fetch_dataset(
        url="https://mcfp.felk.cvut.cz/publicDatasets/IoT-23-Dataset/IndividualScenarios/CTU-IoT-Malware-Capture-1-1/bro/conn.log.labeled",
        filename="conn_iot23.log.labeled",
    )
    network_reader_2 = ZeekConnReader(network_file_2)
    await replayer.replay(network_reader_2, speed_multiplier=0, chunk_size=500)

    await es.close()


def main():
    asyncio.run(run_replay())


if __name__ == "__main__":
    main()
