#!/usr/bin/env python3
"""Generate a latest-only versions.json for wormhole-auto-config releases.

Each run overwrites the manifest with a single entry for the current release.
Historical versions are intentionally not merged.
"""

from __future__ import annotations

import argparse
import json
import os
from datetime import datetime, timezone
from typing import Any, Dict, Optional


DEFAULT_BASE_URL = (
    "http://minio.hcrobots.com:9000/hc-release/wormhole-auto-config"
)
DEFAULT_PROJECT = "wormhole-auto-config"


def _build_entry(
    base_url: str,
    version: str,
    commit: Optional[str],
    artifact: str,
    notes: Optional[str],
    published_at: Optional[str],
    version_path: Optional[str],
) -> Dict[str, Any]:
    """Build one manifest entry pointing at the MinIO wheel URL."""
    path_segment = version_path or version
    download_url = "/".join(
        part.strip("/") for part in [base_url, path_segment, artifact]
    )
    return {
        "version": version,
        "commit": commit or "",
        "download_url": download_url,
        "published_at": published_at or datetime.now(timezone.utc).isoformat(),
        "notes": notes or "",
    }


def main() -> None:
    """Parse CLI args and write a single-entry versions.json."""
    parser = argparse.ArgumentParser(
        description="Generate a latest-only versions.json for MinIO releases"
    )
    parser.add_argument(
        "--version",
        required=True,
        help="Release version without leading v (e.g. 1.0.1)",
    )
    parser.add_argument("--commit", help="Short commit hash")
    parser.add_argument(
        "--base-url",
        default=DEFAULT_BASE_URL,
        help="Artifact base URL under the MinIO bucket",
    )
    parser.add_argument(
        "--artifact",
        required=True,
        help="Wheel file name (e.g. wormhole_auto_config-1.0.1-py3-none-any.whl)",
    )
    parser.add_argument(
        "--version-path",
        help="Object path segment under base-url (default: --version; use tag like v1.0.1)",
    )
    parser.add_argument("--notes", help="Release notes snippet")
    parser.add_argument("--published-at", help="Override publish time ISO string")
    parser.add_argument(
        "--output",
        default="versions.json",
        help="Output file path",
    )
    parser.add_argument(
        "--project",
        default=DEFAULT_PROJECT,
        help="Project name stored in the manifest",
    )

    args = parser.parse_args()

    entry = _build_entry(
        base_url=args.base_url,
        version=args.version,
        commit=args.commit,
        artifact=args.artifact,
        notes=args.notes,
        published_at=args.published_at,
        version_path=args.version_path,
    )

    manifest = {
        "project": args.project,
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "versions": [entry],
    }

    output_path = os.path.abspath(args.output)
    parent = os.path.dirname(output_path)
    if parent:
        os.makedirs(parent, exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as file_handle:
        json.dump(manifest, file_handle, indent=2, ensure_ascii=False)
        file_handle.write("\n")

    print(f"versions manifest written to {output_path}")


if __name__ == "__main__":
    main()
