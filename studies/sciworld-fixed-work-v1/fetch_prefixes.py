"""Fetch and verify the two pinned SciWorld trajectory prefixes for local reproduction."""
import argparse
from pathlib import Path
from urllib.request import urlopen

from sciworld_prepare import DATASET, PREFIX_HASHES, checked_file, require, sha_bytes


def fetch(data_root):
    folder = data_root / "trajectories/sciworld"
    folder.mkdir(parents=True, exist_ok=True)
    for split, (count, expected) in PREFIX_HASHES.items():
        name = f"sciworld_traj_{split}.jsonl"
        path = folder / name
        if path.exists():
            checked_file(path, expected)
            continue
        url = f"https://huggingface.co/datasets/HKBU-KnowComp/patchworld-trajectories/resolve/{DATASET}/sciworld/{name}"
        rows = []
        with urlopen(url, timeout=30) as response:
            for line in response:
                if line.strip():
                    rows.append(line.rstrip(b"\r\n"))
                if len(rows) == count:
                    break
        payload = b"\n".join(rows) + b"\n"
        require(len(rows) == count and sha_bytes(payload) == expected, f"Wrong {split} prefix")
        with path.open("xb") as stream:
            stream.write(payload)
        print(name, expected)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-root", type=Path, required=True)
    fetch(parser.parse_args().data_root)
