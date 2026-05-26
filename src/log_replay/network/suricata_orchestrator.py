import subprocess
from pathlib import Path

from log_replay.logging import logger


def process_pcap_with_suricata(pcap_path: Path) -> Path:
    """
    Runs Suricata against a PCAP file to generate an eve.json log.
    """
    output_dir = pcap_path.parent / "suricata_logs"
    output_dir.mkdir(exist_ok=True)

    logger.info(f"Running Suricata against {pcap_path.name}...")

    try:
        # -r reads the pcap, -l sets the log output directory
        subprocess.run(
            [
                "suricata",
                "-r",
                str(pcap_path.absolute()),
                "-l",
                str(output_dir.absolute()),
            ],
            check=True,
            capture_output=True,
            text=True,
        )

        eve_log = output_dir / "eve.json"
        if not eve_log.exists():
            raise FileNotFoundError("Suricata ran, but did not produce eve.json.")

        logger.info(f"Suricata processing complete. Logs saved to {eve_log}")
        return eve_log

    except subprocess.CalledProcessError as e:
        logger.error(f"Suricata execution failed: {e.stderr}")
        raise
