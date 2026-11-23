"""Freeze setup inputs for the SciWorld fixed-work study; runs no search arms.

Launch with PYTHONHASHSEED=0. The original freeze checks the retained full
planning CSV. Public reproductions verify the reconstructed inputs against that
freeze's published manifest. Private pickles contain original source-program data.
"""

import argparse
import csv
import hashlib
import itertools
import json
import os
from pathlib import Path
import pickle
import platform
import subprocess
import sys


BASELINE = "3c9022030323bd22e05b3f5276531eaa542cb1eb"
DATASET = "9342e2cbee1f8579b5423ed5821f6ad8a81ab773"
MODEL_REVISION = "5079da9203913381f45ed2e1df92c73c30571e2e"
MODEL = "third_party/PatchWorld/examples/generated_world_models/sciworld_benchmark_world_model.py"
RUNTIME = "src/wctr/isolation.py"
FAILURES = ((364, 23, 3), (374, 24, 3), (476, 27, 16), (863, 41, 17),
            (925, 44, 0), (1560, 68, 10), (1963, 82, 18), (1975, 83, 0),
            (2166, 90, 12))
COMPARISONS = ((390, 24, 19), (465, 27, 5))
PUBLIC_HASHES = {
    MODEL: "9d7c24064d030d15d68c833b031e8a24c5b897a177562e1ee0642c464cfcac72",
    "third_party/PatchWorld/patchworld/worldmodel_base.py": "a888d27c3577fb61cf730be2a22c2b77910c2d3a776b73e1ee07fd2cf369c6d2",
    "results/stage2/final_planning.csv": "804541d198f00a8216adbcba397675e4b08988940cddf9c04546649be884f567",
    "experiments/stage2/benchmark.py": "d0e9e95fb5d4ca04fef50cf9008b529e9b11e8993b89b242c2e35d13a3855792",
    "experiments/stage2/discover.py": "f91bfeeabb61e1f306d3f42a6cac21641d8437cfffe573d9065a0fb2818b017d",
    "experiments/frozen/isolation.py": "4528627f1922286e3058a81c2439f682dde33f8deb9a10ebb5170b8a11b7b612",
    "proposals/sciworld-fixed-work.md": "ff65befd214e3a16811192919be45f9708d3852d0571de4e416cc809b51085c5",
}
PREFIX_HASHES = {
    "test": (100, "9795ea9106a6cfa4d909a6767aed7598d9406d22a8a6e4521f47329464b68641"),
    "train": (32, "b7a093870e5905f1e35161fd353ff464cbf1f4dbada4ffecf3646c3648b9ecfa"),
}
ARCHIVE_CSV_HASH = "af5102115817be0cd8085500a671211730c790c09a8c30616507bc739041278c"


def json_bytes(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"),
                      allow_nan=False).encode("utf-8")


def digest(value):
    return hashlib.sha256(json_bytes(value)).hexdigest()


def shared_paths(root):
    """Enumerate simple paths to mutable containers, including cycle-closing edges."""
    paths = {}
    def walk(value, path, active):
        if type(value) in (dict, list, set):
            paths.setdefault(id(value), []).append(path)
        if id(value) in active:
            return
        if type(value) is dict:
            children = ((("key", k), value[k]) for k in sorted(value, key=json_bytes))
        elif type(value) in (list, tuple):
            children = ((("index", i), child) for i, child in enumerate(value))
        else:
            # A SciWorld set contains hashable values; it cannot contain a mutable child.
            return
        active.add(id(value))
        for label, child in children:
            walk(child, (*path, label), active)
        active.remove(id(value))
    walk(root, (), set())
    return [group for group in paths.values() if len(group) > 1]


def alias_groups(root):
    """Stable public alias IDs are groups of sorted SHA-256 path digests."""
    return sorted(sorted(digest(path) for path in group) for group in shared_paths(root))


def require(condition, message):
    if not condition:
        raise ValueError(message)


def sha_bytes(data):
    return hashlib.sha256(data).hexdigest()


def checked_file(path, expected):
    data = path.read_bytes()
    require(sha_bytes(data) == expected, f"Source digest mismatch: {path}")
    return data


def historical_rows(path):
    with path.open(encoding="utf-8", newline="") as stream:
        rows = [row for row in csv.DictReader(stream)
                if row["program"] == "sciworld" and row["method"] == "raw"]
    by_key = {(int(r["task_id"]), int(r["repeat"])): r for r in rows}
    require(len(rows) == len(by_key) == 240, "Expected 80 archived SciWorld raw tasks, three repeats each")
    return by_key


def verify_selection(tasks, published, archived):
    require(len(tasks) == len({t["task_id"] for t in tasks}) == 80, "Incorrect frozen selection size")
    selected_failures = {item[0] for item in FAILURES}
    selected_comparisons = {item[0] for item in COMPARISONS}
    for task in tasks:
        task_id = task["task_id"]
        for repeat in range(3):
            key = task_id, repeat
            row = published[key]
            if archived is not None:
                require(all(v == archived[key][k] for k, v in row.items()), f"Projection mismatch for {key}")
                require(task["walk"] == json.loads(archived[key]["goal_walk"]), f"Goal walk mismatch for {key}")
            require((task["trajectory"], task["step"], int(task["trivial"])) ==
                    tuple(int(row[k]) for k in ("trajectory", "source_step", "trivial")), f"Wrong source for {key}")
            if task_id in selected_failures or task_id in selected_comparisons:
                require(row["trivial"] == "0" and row["found"] == "1", f"Wrong task class for {key}")
                require(int(row["false_plan"]) == int(task_id in selected_failures)
                        and int(row["success"]) == int(task_id in selected_comparisons),
                        f"Historical outcome mismatch for {key}")


def task_record(task, rank, benchmark):
    actions = task["actions"]
    candidates = list(dict.fromkeys(actions))[:3]
    root = task["state"]
    groups = alias_groups(root)
    return {
        "task_id": task["task_id"], "trajectory": task["trajectory"], "source_step": task["step"],
        "cohort": "historical_failure" if (task["task_id"], task["trajectory"], task["step"]) in FAILURES
                  else "comparison", "seeded_selection_index": rank,
        "root_sha256": digest(benchmark.canonical(root)), "root_alias_groups": groups,
        "root_alias_sha256": digest(groups), "goal_sha256": digest(task["goal"]),
        "ordered_candidates_sha256": digest(actions), "ordered_candidate_ids": [digest(a) for a in actions],
        "branch_action_ids": [digest(a) for a in candidates], "eligible": len(candidates) == 3,
        "goal_walk_sha256": digest(task["walk"]), "goal_walk_length": len(task["walk"]),
    }


def freeze(args):
    require(os.getenv("PYTHONHASHSEED") == "0" and sys.flags.hash_randomization == 0,
            "Launch a new Python process with PYTHONHASHSEED=0")
    repo, data_root, bundle = args.repo.resolve(), args.data_root.resolve(), args.bundle.resolve()
    files = ["private/tasks.pkl", "private/calibration.pkl", "private/manifest.json", "public/manifest.json"]
    for name in files:
        require(not (bundle / name).exists(), f"Output already exists: {name}")
    release = subprocess.check_output(["git", "rev-parse", "--verify", args.release_ref + "^{commit}"],
                                      cwd=repo, text=True).strip()
    require(release == args.runtime_sha, "Release reference does not identify specified commit")
    release_runtime = subprocess.check_output(["git", "show", f"{release}:{RUNTIME}"], cwd=repo)
    runtime_hash = sha_bytes(release_runtime)
    checked_file(repo / RUNTIME, runtime_hash)
    for path, expected in PUBLIC_HASHES.items():
        checked_file(repo / path, expected)
    archived, reference = None, None
    if args.historical_rows is not None:
        checked_file(args.historical_rows, ARCHIVE_CSV_HASH)
        archived = historical_rows(args.historical_rows)
    else:
        reference = json.loads(args.reference_manifest.read_text(encoding="utf-8"))
        require(reference["phase"] == "pre-intervention" and reference["selection"]["archive_raw_rows_crosschecked"] == 240,
                "Provide the published original pre-intervention manifest")
    for split, (count, expected) in PREFIX_HASHES.items():
        path = data_root / "trajectories" / "sciworld" / f"sciworld_traj_{split}.jsonl"
        require(len(checked_file(path, expected).splitlines()) == count, f"Unexpected {split} count")

    os.environ["WCTR_DATA_ROOT"] = str(data_root)
    sys.path.insert(0, str(repo / "experiments" / "stage2"))
    import benchmark
    require(Path(benchmark.__file__).resolve() == repo / "experiments/stage2/benchmark.py",
            "Wrong historical generator loaded")
    tasks = benchmark.make_tasks("sciworld", "test", 80, 20261028)
    verify_selection(tasks, historical_rows(repo / "results/stage2/final_planning.csv"), archived)
    by_id = {t["task_id"]: (rank, t) for rank, t in enumerate(tasks)}
    selected, records, private_rows = [], [], []
    for task_id, trajectory, step in FAILURES + COMPARISONS:
        rank, task = by_id[task_id]
        require((task["trajectory"], task["step"]) == (trajectory, step), f"Wrong frozen triple for {task_id}")
        selected.append(task)
        records.append(task_record(task, rank, benchmark))
        private_rows.append({"task_id": task_id, "ordered_candidates": task["actions"],
                             "goal_walk": task["walk"], "goal": task["goal"],
                             "root_alias_path_groups": shared_paths(task["state"])})
    cases = benchmark.cases("sciworld", "train", 32)
    require(len(cases) == 32, "Expected 32 initial calibration transitions")
    calibration = [(c[0], c[1]) for c in cases]
    calibration_rows = [{"trajectory": ti, "source_step": step, "action_id": digest(action),
                         "state_sha256": digest(benchmark.canonical(state)),
                         "alias_sha256": digest(alias_groups(state))} for state, action, ti, step, _ in cases]
    assets = {"private/tasks.pkl": pickle.dumps(selected, protocol=4),
              "private/calibration.pkl": pickle.dumps(calibration, protocol=4),
              "private/manifest.json": json_bytes({"tasks": private_rows, "pickle_protocol": 4})}
    code_paths = [Path(__file__).resolve(), *[p.resolve() for p in args.study_code]]
    code = {p.name: sha_bytes(p.read_bytes()) for p in code_paths}
    require(len(code) == len(code_paths), "Duplicate study code basenames")
    manifest = {
        "schema_version": 1, "study": "wctr-sciworld-fixed-work-v1",
        "phase": "pre-intervention" if reference is None else "public-reproduction-inputs",
        "historical_public_revision": BASELINE, "model_revision": MODEL_REVISION, "dataset_revision": DATASET,
        "runtime_release_ref": args.release_ref, "runtime_commit": release, "runtime_sha256": runtime_hash,
        "environment": {"python": sys.version, "implementation": platform.python_implementation(),
                        "platform": platform.platform(), "machine": platform.machine(),
                        "hash_seed": 0, "dependencies": "Python standard library and vendored sources"},
        "repository_sha256": PUBLIC_HASHES, "archived_full_planning_csv_sha256": ARCHIVE_CSV_HASH,
        "jsonl_prefixes": {split: {"trajectories": count, "sha256": sha}
                           for split, (count, sha) in PREFIX_HASHES.items()},
        "study_code_sha256": code, "private_file_sha256": {p: sha_bytes(b) for p, b in assets.items()},
        "expected_outputs": {"manifest": "public/manifest.json", "results": "public/results.json",
                             "report": "public/report.md", "edge_snapshots": "private/edges.jsonl.gz"},
        "serializer": {"version": 1, "encoding": "UTF-8 JSON, ensure_ascii=False, sort_keys=True, "
                       "compact separators, allow_nan=False; SHA-256",
                       "values": "historical benchmark.canonical hierarchy; goal is already canonical",
                       "alias_paths": "typed key/index tokens; root path []; sort path digests within each "
                       "shared mutable group, then sort groups; retain closing edge of cycles"},
        "selection": {"seed": 20261028, "generated_tasks": 80, "public_raw_rows_crosschecked": 240,
                      "archive_raw_rows_crosschecked": 240 if archived is not None else 0,
                      "ordered_80_task_ids_sha256": digest([t["task_id"] for t in tasks]),
                      "ordered_80_goal_walks_sha256": digest([t["walk"] for t in tasks]),
                      "ordered_80_candidate_lists_sha256": digest([t["actions"] for t in tasks]),
                      "frozen_triples": len(records), "eligible": sum(r["eligible"] for r in records)},
        "initial_calibration": calibration_rows, "tasks": records,
        "protocol": {"arms": ["raw", "full_copy", "wctr"],
                     "root_orders": [list(order) for order in itertools.permutations(range(3))],
                     "child_order": [0, 1, 2], "expansion": "depth-first; first three distinct frozen actions",
                     "depth": 2, "search_transitions_per_arm_order": 12,
                     "resets": "pristine root and fresh model/adapter per arm and order; WCTR calibrates 32 transitions",
                     "stopping": "complete fixed tree without goal stop, deadline or deduplication",
                     "score": "count of top-level goal keys present with equal canonical value; max leaf per root",
                     "ties": "lowest frozen child index, then lowest frozen root index; report all ties",
                     "controls": "check Full Copy parent invariance and path values across root orders; compare WCTR",
                     "replay": "selected two-action sequence from pristine root with raw-on-per-edge deep copies",
                     "rescue": "single-edge raw-on-deep-copy in fresh raw order; require both restored sibling input "
                     "and reference action for causal attribution",
                     "denominators": "no replacement of ineligible states; report comparisons separately; "
                     "orders are repeated measures; calibration, replay and rescue calls counted separately"},
    }
    if reference is not None:
        for key in ("schema_version", "study", "runtime_commit", "runtime_sha256", "dataset_revision",
                    "model_revision", "repository_sha256", "study_code_sha256", "jsonl_prefixes",
                    "serializer", "protocol", "tasks", "initial_calibration"):
            require(reference[key] == manifest[key], f"Published pre-intervention manifest mismatch for {key}")
        for key, value in manifest["selection"].items():
            if key != "archive_raw_rows_crosschecked":
                require(reference["selection"][key] == value, f"Published seeded selection mismatch for {key}")
        manifest["reference_manifest_sha256"] = sha_bytes(args.reference_manifest.read_bytes())
    assets["public/manifest.json"] = (json.dumps(manifest, ensure_ascii=False, sort_keys=True,
                                                indent=2, allow_nan=False) + "\n").encode("utf-8")
    # Publish the manifest last. Only files created by this invocation are rolled back on failure.
    created = []
    try:
        for name, content in assets.items():
            path = bundle / name
            path.parent.mkdir(parents=True, exist_ok=True)
            with path.open("xb") as handle:
                created.append(path)
                handle.write(content)
    except BaseException:
        for path in reversed(created):
            path.unlink()
        raise
    print(f"{manifest['phase']} manifest SHA-256 {sha_bytes(assets['public/manifest.json'])}")
    print(f"Frozen {len(records)} tasks, {manifest['selection']['eligible']} eligible; 32 calibration transitions.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    for option in ("repo", "data-root", "bundle"):
        parser.add_argument("--" + option, required=True, type=Path)
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--historical-rows", type=Path, help="Retained full CSV for original freeze")
    source.add_argument("--reference-manifest", type=Path, help="Published original manifest for reproduction")
    parser.add_argument("--runtime-sha", required=True)
    parser.add_argument("--release-ref", required=True)
    parser.add_argument("--study-code", type=Path, action="append", default=[],
                        help="Additional finalized study source to hash; may be repeated")
    freeze(parser.parse_args())
