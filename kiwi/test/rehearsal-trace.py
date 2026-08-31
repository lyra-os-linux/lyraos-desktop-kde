#!/usr/bin/env python3
"""Append a fail-closed QEMU launch record for an upgrade rehearsal."""

from __future__ import annotations

import argparse
import datetime as dt
import json
import os
from pathlib import Path
import stat
import uuid

MAX_TRACE_SIZE = 1024 * 1024


def file_identity(path: Path) -> dict[str, int]:
    metadata = path.lstat()
    if stat.S_ISLNK(metadata.st_mode) or not stat.S_ISREG(metadata.st_mode):
        raise ValueError(f"unsafe VM artifact: {path}")
    return {"device": metadata.st_dev, "inode": metadata.st_ino}


def load_trace(path: Path, installation_uuid: str, disk: dict, nvram: dict) -> dict:
    if not path.exists():
        return {"schema": 1, "status": "in-progress", "installation_uuid": installation_uuid, "disk_identity": disk, "nvram_identity": nvram, "qemu_launch_count": 0, "launches": []}
    metadata = path.lstat()
    if stat.S_ISLNK(metadata.st_mode) or not stat.S_ISREG(metadata.st_mode):
        raise ValueError("trace must be a regular file")
    if metadata.st_uid != os.getuid() or metadata.st_size > MAX_TRACE_SIZE:
        raise ValueError("trace ownership or size is unsafe")
    document = json.loads(path.read_text(encoding="utf-8"))
    expected = (1, "in-progress", installation_uuid, disk, nvram)
    actual = (document.get("schema"), document.get("status"), document.get("installation_uuid"), document.get("disk_identity"), document.get("nvram_identity"))
    if actual != expected or not isinstance(document.get("launches"), list):
        raise ValueError("trace identity or schema changed")
    return document


def save_trace(path: Path, document: dict) -> None:
    temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    descriptor = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
            json.dump(document, stream, sort_keys=True, indent=2); stream.write("\n"); stream.flush(); os.fsync(stream.fileno())
        os.replace(temporary, path)
        directory = os.open(path.parent, os.O_RDONLY | os.O_DIRECTORY)
        try: os.fsync(directory)
        finally: os.close(directory)
    finally: temporary.unlink(missing_ok=True)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--trace", required=True, type=Path); parser.add_argument("--uuid", required=True); parser.add_argument("--mode", required=True, choices=("live", "installed")); parser.add_argument("--disk", required=True, type=Path); parser.add_argument("--nvram", required=True, type=Path)
    args = parser.parse_args(); installation_uuid = str(uuid.UUID(args.uuid))
    if args.trace.parent.is_symlink() or args.trace.parent.stat().st_uid != os.getuid(): raise ValueError("trace directory is unsafe")
    disk = file_identity(args.disk); nvram = file_identity(args.nvram); document = load_trace(args.trace, installation_uuid, disk, nvram)
    sequence = len(document["launches"]) + 1; document["qemu_launch_count"] = sequence
    document["launches"].append({"sequence": sequence, "mode": args.mode, "recorded_at": dt.datetime.now(dt.timezone.utc).isoformat()})
    save_trace(args.trace, document); return 0


if __name__ == "__main__": raise SystemExit(main())
