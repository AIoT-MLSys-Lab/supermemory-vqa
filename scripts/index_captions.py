#!/usr/bin/env python3
"""
Build searchable caption index from *_caption_narrations.json files.
"""
import argparse
import json
import os
from pathlib import Path

from src.visualization.caption_search import build_caption_index

ROOT = Path(__file__).resolve().parents[1]


def main() -> int:
    parser = argparse.ArgumentParser(description="Index caption narration files.")
    parser.add_argument(
        "--workspace-root",
        default=str(ROOT),
        help="Workspace root directory to scan recursively.",
    )
    parser.add_argument(
        "--db-path",
        default=str(ROOT / "uploads" / "caption_index.db"),
        help="Output SQLite caption index path.",
    )
    args = parser.parse_args()

    result = build_caption_index(args.workspace_root, args.db_path)
    print(json.dumps(result, indent=2))
    return 0 if result.get("success") else 1


if __name__ == "__main__":
    os._exit(main())

