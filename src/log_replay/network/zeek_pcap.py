import subprocess
from pathlib import Path

from log_replay.logging import logger


def process_pcap_with_zeek(pcap_path: Path) -> list[Path]:
    """
    Runs Zeek against a PCAP file and returns ALL generated JSON logs.
    """
    output_dir = pcap_path.parent / "zeek_logs"
    output_dir.mkdir(exist_ok=True)

    logger.info(f"Running Zeek against {pcap_path.name}...")

    try:
        subprocess.run(
            [
                "/opt/zeek/bin/zeek",
                "-r",
                str(pcap_path.absolute()),
                "LogAscii::use_json=T",
            ],
            cwd=output_dir,
            check=True,
            capture_output=True,
            text=True,
        )

        # Grab ALL generated .log files (conn.log, http.log, files.log, etc.)
        zeek_logs = list(output_dir.glob("*.log"))

        if not zeek_logs:
            raise FileNotFoundError("Zeek ran, but did not produce any logs.")

        logger.info(f"Zeek processing complete. Found {len(zeek_logs)} log files.")
        return zeek_logs

    except subprocess.CalledProcessError as e:
        logger.error(f"Zeek execution failed: {e.stderr}")
        raise
