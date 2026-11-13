"""Download the DataCo Smart Supply Chain dataset (Mendeley Data v5) into data/raw/.

Source: Constante, F., Silva, F., Pereira, A. (2019). DataCo SMART SUPPLY CHAIN FOR
BIG DATA ANALYSIS. Mendeley Data, V5. https://doi.org/10.17632/8gx2fvg2k6.5 (CC BY 4.0)

The file list (names, download URLs, SHA-256 hashes) comes from Mendeley's public API,
so every download is checked against the hash the publisher reports.

Usage:
    python scripts/download_data.py            # main CSV + data dictionary
    python scripts/download_data.py --all      # also the 95 MB web access log (optional Q5)
"""
from __future__ import annotations

import argparse
import hashlib
import sys
from pathlib import Path

import requests

DATASET_ID = "8gx2fvg2k6"
VERSION = 5
API = f"https://data.mendeley.com/public-api/datasets/{DATASET_ID}/files?folder_id=root&version={VERSION}"
REQUIRED = {"DataCoSupplyChainDataset.csv", "DescriptionDataCoSupplyChain.csv"}
OPTIONAL = {"tokenized_access_logs.csv"}

RAW_DIR = Path(__file__).resolve().parents[1] / "data" / "raw"


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def download(url: str, dest: Path, expected_size: int) -> None:
    tmp = dest.with_suffix(dest.suffix + ".part")
    with requests.get(url, stream=True, timeout=60) as r:
        r.raise_for_status()
        done = 0
        with tmp.open("wb") as f:
            for chunk in r.iter_content(chunk_size=1 << 20):
                f.write(chunk)
                done += len(chunk)
                pct = 100 * done / expected_size if expected_size else 0
                print(f"\r  {dest.name}: {done / 1e6:6.1f} MB ({pct:5.1f}%)", end="", flush=True)
    print()
    tmp.replace(dest)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--all", action="store_true", help="also download the optional access-log file")
    args = parser.parse_args()

    wanted = REQUIRED | (OPTIONAL if args.all else set())
    RAW_DIR.mkdir(parents=True, exist_ok=True)

    files = requests.get(API, headers={"Accept": "application/json"}, timeout=30).json()
    by_name = {f["filename"]: f for f in files}
    missing = wanted - by_name.keys()
    if missing:
        print(f"Mendeley API did not list: {sorted(missing)}", file=sys.stderr)
        return 1

    for name in sorted(wanted):
        meta = by_name[name]["content_details"]
        dest = RAW_DIR / name
        if dest.exists() and sha256(dest) == meta["sha256_hash"]:
            print(f"  {name}: already present, hash OK")
            continue
        download(meta["download_url"], dest, meta["size"])
        got = sha256(dest)
        if got != meta["sha256_hash"]:
            print(f"  {name}: SHA-256 mismatch ({got} != {meta['sha256_hash']})", file=sys.stderr)
            return 1
        print(f"  {name}: hash OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
