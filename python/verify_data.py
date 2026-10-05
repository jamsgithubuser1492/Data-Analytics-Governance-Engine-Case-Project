"""Integrity check for the verified case study data (the original uploaded files).

``data/VERIFIED_DATA.sha256`` records the SHA-256 of each file. The app and the tests use it to confirm the case study
runs on exactly those files. Synthetic data generation is still available, but it writes elsewhere and never replaces them.

Run:  python python/verify_data.py          (exit code 1 if any file differs)
      python python/verify_data.py --write  (re-record hashes after an intentional change)
"""
from __future__ import annotations

import hashlib
import sys
from pathlib import Path
from typing import Dict, List, Tuple

DATA_DIR = Path(__file__).resolve().parents[1] / "data"
MANIFEST = DATA_DIR / "VERIFIED_DATA.sha256"
FILES = ["RAW_PLATFORM_DATA.csv", "RAW_MTA_OUTPUT.csv", "RAW_HOLDOUT_DATA.csv", "BUSINESS_BENCHMARKS.csv"]


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes().replace(b"\r\n", b"\n")).hexdigest()  # line endings must not matter across systems


def read_manifest(path: Path = MANIFEST) -> Dict[str, str]:
    out = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip() and not line.startswith("#"):
            digest, name = line.split(None, 1)
            out[name.strip()] = digest
    return out


def verify(data_dir: Path = DATA_DIR, manifest: Path = MANIFEST) -> List[Tuple[str, bool, str]]:
    """(file, matches, detail) for each verified file."""
    expected = read_manifest(manifest)
    rows = []
    for name in FILES:
        p = data_dir / name
        if not p.exists():
            rows.append((name, False, "missing"))
        elif _sha(p) != expected.get(name):
            rows.append((name, False, "differs from the verified file"))
        else:
            rows.append((name, True, "verified"))
    return rows


def all_verified(data_dir: Path = DATA_DIR) -> bool:
    try:
        return all(ok for _, ok, _ in verify(data_dir))
    except OSError:
        return False


def write_manifest(data_dir: Path = DATA_DIR, manifest: Path = MANIFEST) -> None:
    lines = ["# SHA-256 of the verified case study data (original uploaded files). Regenerate with: python python/verify_data.py --write"]
    lines += [f"{_sha(data_dir / n)}  {n}" for n in FILES]
    manifest.write_text("\n".join(lines) + "\n", encoding="utf-8")


if __name__ == "__main__":
    if "--write" in sys.argv:
        write_manifest()
        print("Recorded hashes in", MANIFEST)
        sys.exit(0)
    results = verify()
    for name, ok, detail in results:
        print(f"{'OK  ' if ok else 'FAIL'} {name}: {detail}")
    ok_all = all(ok for _, ok, _ in results)
    print("Case study data verified." if ok_all else "Case study data does NOT match the verified files. Restore with: git checkout -- data/")
    sys.exit(0 if ok_all else 1)
