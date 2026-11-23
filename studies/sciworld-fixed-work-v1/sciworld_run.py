"""Execute the three fixed-work arms from a locally generated, sealed input bundle."""
import argparse
import gzip
import json
import os
from pathlib import Path
import pickle
import sys

from sciworld_prepare import MODEL, RUNTIME, checked_file, json_bytes, require, sha_bytes
from sciworld_study_engine import evaluate_task


def run(repo, bundle, manifest_sha):
    manifest = json.loads(checked_file(bundle / "public/manifest.json", manifest_sha))
    require(manifest["phase"] in ("pre-intervention", "public-reproduction-inputs"), "Unexpected manifest")
    require(os.getenv("PYTHONHASHSEED") == "0" and sys.flags.hash_randomization == 0, "Use PYTHONHASHSEED=0")
    require(sys.version == manifest["environment"]["python"], "Use the interpreter that sealed these inputs")
    for name, expected in manifest["study_code_sha256"].items():
        checked_file(Path(__file__).resolve().with_name(name), expected)
    for name, expected in manifest["repository_sha256"].items():
        checked_file(repo / name, expected)
    checked_file(repo / RUNTIME, manifest["runtime_sha256"])
    sys.path[:0] = [str(repo / "src"), str(repo / "experiments/stage2")]
    import benchmark
    from wctr import isolation

    require(Path(isolation.__file__).resolve() == repo / RUNTIME, "Incorrect active runtime import")
    require(Path(benchmark.__file__).resolve() == repo / "experiments/stage2/benchmark.py", "Incorrect Stage 2 harness")
    # Inputs are generated locally by sciworld_prepare.py. Never load a downloaded pickle.
    def load_private(name):
        return pickle.loads(checked_file(bundle / name, manifest["private_file_sha256"][name]))

    tasks = load_private("private/tasks.pkl")
    calibration = load_private("private/calibration.pkl")
    source = (repo / MODEL).read_text(encoding="utf-8")

    def raw_model():
        return benchmark.load_model("sciworld")

    def protected_model():
        ordinary = raw_model()  # also initializes the vendored base-class import
        cls = isolation.compile_source(source, str(repo / MODEL))[type(ordinary).__name__]
        model = cls()
        model._wctr_raw_model = ordinary
        return isolation.Adapter(model, "wctr")

    expected_ids = [task["task_id"] for task in manifest["tasks"]]
    require([task["task_id"] for task in tasks] == expected_ids, "Wrong frozen state order")
    output = bundle / "public/results.json"
    traces = bundle / "private/edges.jsonl.gz"
    require(not output.exists() and not traces.exists(), "Use a fresh bundle for each execution")
    records = []
    # A partial private archive is retained if the process fails; publish results only on completion.
    with traces.open("xb") as stream, gzip.GzipFile(filename="", fileobj=stream, mode="wb", mtime=0) as trace:
        def private_sink(record):
            trace.write(json_bytes(record) + b"\n")

        for task in tasks:
            item = evaluate_task(task, canonical=benchmark.canonical, raw_factory=raw_model,
                                 wctr_factory=protected_model, calibration=calibration, private_sink=private_sink)
            records.append(item)
            print(f"Recorded task {task['task_id']} with {len(item.get('comparisons', []))} paired orders.", flush=True)
    document = {"schema_version": 1, "manifest_sha256": manifest_sha,
                "runtime_commit": manifest["runtime_commit"], "tasks": records}
    data = json_bytes(document) + b"\n"
    with output.open("xb") as stream:
        stream.write(data)
    print(f"Results SHA-256 {sha_bytes(data)}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", required=True, type=Path)
    parser.add_argument("--bundle", required=True, type=Path)
    parser.add_argument("--manifest-sha256", required=True)
    args = parser.parse_args()
    run(args.repo.resolve(), args.bundle.resolve(), args.manifest_sha256)
