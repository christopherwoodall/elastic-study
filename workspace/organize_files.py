#!/usr/bin/env python3
"""
Organize files into subdirectories by extension.

Examples:
    .py -> python/
    .txt -> text/
    .jpg -> images/
"""

import argparse
import os
import shutil
import sys
from pathlib import Path


# Map of extensions to folder names
EXTENSION_MAP = {
    # Python
    ".py": "python",
    ".pyw": "python",
    ".pyc": "python",
    ".pyd": "python",
    # Text
    ".txt": "text",
    ".md": "text",
    ".rst": "text",
    ".log": "text",
    # Images
    ".jpg": "images",
    ".jpeg": "images",
    ".png": "images",
    ".gif": "images",
    ".bmp": "images",
    ".svg": "images",
    ".webp": "images",
    ".ico": "images",
    # Documents
    ".pdf": "documents",
    ".doc": "documents",
    ".docx": "documents",
    ".xls": "documents",
    ".xlsx": "documents",
    ".ppt": "documents",
    ".pptx": "documents",
    ".odt": "documents",
    # Audio
    ".mp3": "audio",
    ".wav": "audio",
    ".flac": "audio",
    ".aac": "audio",
    ".ogg": "audio",
    ".wma": "audio",
    # Video
    ".mp4": "video",
    ".avi": "video",
    ".mkv": "video",
    ".mov": "video",
    ".wmv": "video",
    ".flv": "video",
    ".webm": "video",
    # Archives
    ".zip": "archives",
    ".tar": "archives",
    ".gz": "archives",
    ".bz2": "archives",
    ".xz": "archives",
    ".7z": "archives",
    ".rar": "archives",
    # Code
    ".js": "code",
    ".ts": "code",
    ".jsx": "code",
    ".tsx": "code",
    ".html": "code",
    ".htm": "code",
    ".css": "code",
    ".scss": "code",
    ".sass": "code",
    ".less": "code",
    ".json": "code",
    ".xml": "code",
    ".yaml": "code",
    ".yml": "code",
    ".sql": "code",
    ".sh": "code",
    ".bash": "code",
    ".zsh": "code",
    ".fish": "code",
    ".ps1": "code",
    ".bat": "code",
    ".cmd": "code",
    ".c": "code",
    ".cpp": "code",
    ".h": "code",
    ".hpp": "code",
    ".java": "code",
    ".cs": "code",
    ".go": "code",
    ".rs": "code",
    ".rb": "code",
    ".php": "code",
    ".swift": "code",
    ".kt": "code",
    ".scala": "code",
    ".r": "code",
    ".pl": "code",
    ".lua": "code",
    ".vim": "code",
}


def get_folder_for_extension(ext: str) -> str:
    """Get the target folder for a file extension."""
    ext_lower = ext.lower()
    return EXTENSION_MAP.get(ext_lower, "other")


def organize_files(source_dir: Path, execute: bool = False) -> None:
    """
    Organize files in source_dir by extension.

    Args:
        source_dir: Directory to organize
        execute: If True, actually move files. If False, just print what would happen.
    """
    if not source_dir.exists():
        print(f"Error: Directory '{source_dir}' does not exist.", file=sys.stderr)
        sys.exit(1)

    if not source_dir.is_dir():
        print(f"Error: '{source_dir}' is not a directory.", file=sys.stderr)
        sys.exit(1)

    # Track statistics
    files_moved = 0
    directories_created = set()

    # Get all files in the directory (not recursive)
    files = [f for f in source_dir.iterdir() if f.is_file()]

    if not files:
        print(f"No files found in '{source_dir}'.")
        return

    mode_str = "EXECUTING" if execute else "DRY-RUN"
    print(f"\n[{mode_str}] Organizing files in: {source_dir}\n")

    for file_path in files:
        # Skip the script itself if it's in the same directory
        if file_path.name == "organize_files.py":
            continue

        ext = file_path.suffix
        folder_name = get_folder_for_extension(ext)
        target_dir = source_dir / folder_name
        target_path = target_dir / file_path.name

        # Check if file already exists in target
        if target_path.exists():
            print(f"  SKIP: {file_path.name} (already exists in {folder_name}/)")
            continue

        if execute:
            # Create directory if it doesn't exist
            if folder_name not in directories_created:
                target_dir.mkdir(exist_ok=True)
                directories_created.add(folder_name)

            # Move the file
            shutil.move(str(file_path), str(target_path))
            print(f"  MOVED: {file_path.name} -> {folder_name}/")
        else:
            if folder_name not in directories_created:
                directories_created.add(folder_name)
            print(f"  WOULD MOVE: {file_path.name} -> {folder_name}/")

        files_moved += 1

    print(f"\n{'=' * 50}")
    print(f"Files processed: {files_moved}")
    print(f"Directories that would be created: {len(directories_created)}")
    if directories_created:
        print(f"  - {', '.join(sorted(directories_created))}")

    if not execute:
        print("\nThis was a dry-run. Use --execute to actually move files.")
    else:
        print("\nFiles have been moved.")


def main():
    parser = argparse.ArgumentParser(
        description="Organize files into subdirectories by extension.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s /path/to/directory          # Dry-run (shows what would happen)
  %(prog)s /path/to/directory --execute  # Actually move files
  %(prog)s . --execute                 # Organize current directory
        """,
    )

    parser.add_argument("source_dir", help="Source directory to organize")

    parser.add_argument(
        "--execute",
        action="store_true",
        help="Actually move files (default is dry-run)",
    )

    args = parser.parse_args()

    source_path = Path(args.source_dir).resolve()
    organize_files(source_path, execute=args.execute)


if __name__ == "__main__":
    main()
