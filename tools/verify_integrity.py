"""Check the retained dataset against its SHA-256 inventory."""

import hashlib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
manifest = ROOT / "provenance/SHA256SUMS"
count = 0
for line in manifest.read_text().splitlines():
    expected, name = line.split("  ", 1)
    path = ROOT / name
    if not path.is_file():
        raise SystemExit(f"Missing file: {name}")
    with path.open("rb") as handle:
        digest = hashlib.sha256()
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    if digest.hexdigest() != expected:
        raise SystemExit(f"Checksum mismatch: {name}")
    count += 1
print(f"Verified {count} retained files.")
