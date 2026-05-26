import zipfile
from pathlib import Path

import httpx

from log_replay.logger import logger

# logger = logging.getLogger(__name__)


class DatasetManager:
    """Manages downloading, caching, and extracting historical datasets."""

    def __init__(self):
        self.dataset_dir = Path.cwd() / "datasets"
        self.dataset_dir.mkdir(parents=True, exist_ok=True)

    async def fetch_dataset(self, url: str, filename: str) -> Path:
        """Downloads a dataset if not cached. Extracts if it's a zip file."""
        target_path = self.dataset_dir / filename

        # Check cache
        if target_path.exists():
            logger.info(f"Dataset already cached: {target_path}")
            return self._handle_extraction(target_path)

        logger.info(f"Downloading dataset from {url} to {target_path}...")

        # Combined async with statements to resolve SIM117
        async with (
            httpx.AsyncClient(follow_redirects=True) as client,
            client.stream("GET", url) as response,
        ):
            response.raise_for_status()
            with open(target_path, "wb") as f:
                async for chunk in response.aiter_bytes(chunk_size=8192):
                    f.write(chunk)

        logger.info(f"Download complete: {target_path}")
        return self._handle_extraction(target_path)

    def _handle_extraction(self, file_path: Path) -> Path:
        """Extracts zipped datasets and returns the path to the JSON file."""
        if file_path.suffix == ".zip":
            extract_dir = file_path.parent / file_path.stem
            if not extract_dir.exists():
                logger.info(f"Extracting {file_path} to {extract_dir}...")
                with zipfile.ZipFile(file_path, "r") as zip_ref:
                    zip_ref.extractall(extract_dir)

            # Assume one main JSON file inside the zip for simplicity
            json_files = list(extract_dir.glob("*.json"))
            if not json_files:
                raise FileNotFoundError(f"No JSON files found in {extract_dir}")
            return json_files[0]

        return file_path
