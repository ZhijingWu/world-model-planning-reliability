"""Run from a Git checkout with the publication and proposal commits in its history.

    python tools/release_gate.py

Uses the selected Python interpreter, its standard library and Git. In a shallow
clone, fetch the full history before running this check.
"""

import hashlib
import os
from pathlib import Path
import subprocess
import sys


ROOT = Path(__file__).resolve().parents[1]
PUBLICATION = "3c9022030323bd22e05b3f5276531eaa542cb1eb"
PROPOSAL_REVISION = "9e28df1463f9a878a0df853926243ef9bcbc1642"
FROZEN_CORE = "experiments/frozen/isolation.py"
PUBLICATION_PATHS = (
    "results", "note", "third_party", "CV_PROJECT_ENTRY.md", "PUBLICATION_AUDIT.md",
    "docs/PROVENANCE.json", "docs/ASSET_HASHES.json", "docs/native_runtime_inventory.txt",
    "experiments/stage2/EXPERIMENT_CONFIG.json", "experiments/stage2/FROZEN_PROTOCOL.json",
    "experiments/stage3/FROZEN_LIVE_PROTOCOL.json", "src/wctr/isolation.py",
)


def git(*args):
    return subprocess.check_output(["git", *args], cwd=ROOT)


def check_baseline(revision, paths):
    entries = git("ls-tree", "-r", "--name-only", "-z", revision, "--", *paths)
    tracked = git("ls-files", "-z", "--", *paths)
    historical = set(entries.decode().split("\0")[:-1])
    current = set(tracked.decode().split("\0")[:-1])
    if current != historical:
        raise SystemExit(f"Protected paths differ from {revision}: {sorted(current ^ historical)}")
    for path in sorted(historical):
        # The active package moved on. The original publication bytes live here.
        actual_path = FROZEN_CORE if path == "src/wctr/isolation.py" else path
        expected = hashlib.sha256(git("show", f"{revision}:{path}")).hexdigest()
        actual = hashlib.sha256((ROOT / actual_path).read_bytes()).hexdigest()
        if actual != expected:
            raise SystemExit(f"{actual_path}: expected {expected} from {revision}, found {actual}")
    print(f"PASS: protected files match {revision} (count={len(historical)})", flush=True)


def main():
    check_baseline(PUBLICATION, PUBLICATION_PATHS)
    check_baseline(PROPOSAL_REVISION, ("proposals/sciworld-fixed-work.md",))
    env = {**os.environ, "PYTHONPATH": str(ROOT / "src"), "PYTHONOPTIMIZE": "0"}
    commands = (
        ("-m", "unittest", "discover", "-s", "tests", "-v"),
        ("examples/branch_isolation.py",),
        ("experiments/verify_evidence.py",),
        ("tools/check_frozen_import.py", "stage2"),
        ("tools/check_frozen_import.py", "stage3"),
    )
    failed = []
    for args in commands:
        command = [sys.executable, "-B", "-S", "-W", "error", *args]
        print(f"Running {' '.join(command)}", flush=True)
        if subprocess.run(command, cwd=ROOT, env=env).returncode:
            failed.append(" ".join(args))
    if failed:
        raise SystemExit("Release gate failed: " + ", ".join(failed))
    print(f"Release gate passed on Python {sys.version.split()[0]}.")


if __name__ == "__main__":
    main()
