"""Reconstruct the outcome-blind prospective SciWorld frame and seal local inputs."""
import argparse
import copy
import hashlib
import json
import os
import pickle
import platform
import random
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path
from urllib.request import urlopen


DATA = "9342e2cbee1f8579b5423ed5821f6ad8a81ab773"
RELEASE = "4ba67940378b959a07e63426cf4d3d3bdaf93c86"
SEED = 20261123
TARGET = 64
FIRST_HELDOUT = 100
V1 = "studies/sciworld-fixed-work-v1"
V2 = "studies/sciworld-prospective-v1"
PINNED = {"test": "ebe6b9dbd9838bed92433fd3405d5ac8e5185eca74a77519c6b936b15921422b",
          "train": "a6687372d3e305e7065825e52451b8799a6d3b9e5f5ab93c5e39984e75199492"}
OLD_MANIFEST = "c269fc2ceefd9afdf4b11ed98e56750016169ef7c456eee5a3100ca776a5ba8a"


def sha(data):
    return hashlib.sha256(data).hexdigest()


def require(ok, message):
    if not ok:
        raise ValueError(message)


def load_split(data_root, split, fetch):
    name = f"sciworld_traj_{split}.jsonl"
    file = data_root / "trajectories" / "sciworld" / name
    if fetch and not file.exists():
        url = f"https://huggingface.co/datasets/HKBU-KnowComp/patchworld-trajectories/resolve/{DATA}/sciworld/{name}"
        with urlopen(url, timeout=90) as response:
            data = response.read()
        require(sha(data) == PINNED[split], f"Pinned {split} download digest mismatch")
        file.parent.mkdir(parents=True, exist_ok=True)
        with file.open("xb") as handle:
            handle.write(data)
    data = file.read_bytes()
    require(sha(data) == PINNED[split], f"Pinned {split} file digest mismatch")
    lines = [line for line in data.splitlines() if line.strip()]
    return lines, [json.loads(line) for line in lines]


def source_id(row, split):
    meta = row["metadata"]
    name = meta["item_id"]
    require(meta["split"] == split and re.fullmatch(r"sciworld_[0-9]+", name) is not None
            and name == f"sciworld_{int(meta['task_idx'])}", "Unexpected source item identity")
    return sha(name.encode("utf-8"))


def setup_states(trajectory, model):
    """The correction/prediction order is the historical benchmark.cases procedure."""
    state = model.init_belief()
    for transition in trajectory["transitions"]:
        state = model.correct_belief(state, transition["observation"])
        yield copy.deepcopy(state)
        predicted = model.predict_belief(copy.deepcopy(state), transition["action"])
        state = model.correct_belief(predicted, transition["next_observation"])


def construct(args):
    require(os.environ.get("PYTHONHASHSEED") == "0" and sys.flags.hash_randomization == 0,
            "Start the interpreter with PYTHONHASHSEED=0")
    repo = args.repo.resolve()
    sys.path[:0] = [str(repo / V1), str(repo / "experiments/stage2")]
    os.environ["WCTR_DATA_ROOT"] = str(args.data_root.resolve())
    import benchmark
    import sciworld_prepare as v1

    old = json.loads(v1.checked_file(repo / V1 / "public/manifest.json", OLD_MANIFEST))
    require(old["runtime_commit"] == RELEASE, "Unexpected original release")
    paths = {**old["repository_sha256"], f"{V1}/public/manifest.json": OLD_MANIFEST}
    for name, expected in old["study_code_sha256"].items():
        paths[f"{V1}/{name}"] = expected
    for path, expected in paths.items():
        v1.checked_file(repo / path, expected)
    v1.checked_file(repo / v1.RUNTIME, old["runtime_sha256"])
    for name in ("prepare.py", "protocol.md"):
        paths[f"{V2}/{name}"] = sha(Path(__file__).with_name(name).read_bytes())

    sets = {}
    for split in PINNED:
        lines, sets[split] = load_split(args.data_root, split, args.fetch)
        count, expected = v1.PREFIX_HASHES[split]
        require(sha(b"\n".join(lines[:count]) + b"\n") == expected, f"Wrong {split} prefix")
    train, test = sets["train"], sets["test"]
    train_ids = {source_id(row, "train") for row in train}
    test_ids = [source_id(row, "test") for row in test]
    prefix_ids = set(test_ids[:FIRST_HELDOUT])
    prohibited_sources = train_ids | prefix_ids
    model = benchmark.load_model("sciworld")
    root_hash = lambda state: v1.digest(benchmark.canonical(state))
    prohibited_roots = {root_hash(s) for t in test[:FIRST_HELDOUT] + train[:32]
                        for s in setup_states(t, model)}
    require({t["root_sha256"] for t in old["tasks"]} <= prohibited_roots,
            "Original fixed-work roots are absent from historical exclusion frame")

    groups = defaultdict(list)
    offsets, total = [], 0
    counts = Counter()
    for i, (row, item) in enumerate(zip(test, test_ids)):
        offsets.append(total)
        total += len(row["transitions"])
        if i < FIRST_HELDOUT:
            counts["historical_prefix_trajectories"] += 1
        elif item in prohibited_sources:
            counts["additional_trajectories_sharing_prohibited_item"] += 1
        elif len({t["action"] for t in row["transitions"]}) < 3:
            counts["trajectories_with_fewer_than_three_actions"] += 1
        else:
            groups[item].append(i)
            counts["eligible_trajectories_before_representative_selection"] += 1

    frame, held, seen_roots, excluded = [], {}, set(), []
    for item, indices in sorted(groups.items()):
        # Independent hash priorities preassign one trajectory and one step per source.
        i = min(indices, key=lambda n: (v1.digest(["trajectory", item, n]), n))
        trace = test[i]
        j = min(range(len(trace["transitions"])), key=lambda n: (v1.digest(["step", item, i, n]), n))
        state = next(s for pos, s in enumerate(setup_states(trace, model)) if pos == j)
        key = root_hash(state)
        public = {"source_item_sha256": item, "task_id": offsets[i] + j,
                  "trajectory": i, "source_step": j, "root_sha256": key}
        reason = "historical_root" if key in prohibited_roots else "duplicate_root" if key in seen_roots else None
        if reason:
            excluded.append({**public, "reason": reason})
            counts["items_excluded_" + reason] += 1
            continue
        seen_roots.add(key)
        rng = random.Random(int(v1.digest(["tree", item, i, j]), 16))
        candidates = list(dict.fromkeys(t["action"] for t in trace["transitions"]))
        rng.shuffle(candidates)
        candidates = candidates[:4]
        rng.shuffle(candidates)
        walk = [rng.choice(candidates) for _ in range(rng.choice([2, 3, 4]))]
        public.update(ordered_candidates_sha256=v1.digest(candidates), goal_walk_sha256=v1.digest(walk))
        frame.append(public)
        held[item] = (state, candidates, walk)

    sampling = {
        "seed": SEED, "target_n": TARGET, "first_heldout_trajectory": FIRST_HELDOUT,
        "test_trajectories": len(test), "test_source_items": len(set(test_ids)),
        "train_trajectories": len(train), "train_source_items": len(train_ids),
        "test_train_shared_items": len(set(test_ids) & train_ids), "historical_test_source_items": len(prefix_ids),
        "representative_items_before_root_exclusions": len(groups), "excluded_counts": dict(counts),
        "frame_size": len(frame), "sample_size": min(TARGET, len(frame)), "frame_sha256": v1.digest(frame),
        "excluded_source_item_sha256": sorted(prohibited_sources), "excluded_root_sha256": sorted(prohibited_roots),
    }
    if args.inventory:
        print(json.dumps({k: v for k, v in sampling.items() if not k.startswith("excluded_")
                          or k == "excluded_counts"}, indent=2))
        return
    selected = random.Random(SEED).sample(frame, min(TARGET, len(frame)))
    tasks, records, private_rows = [], [], []
    for rank, row in enumerate(selected):
        state, actions, walk = held[row["source_item_sha256"]]
        ref = benchmark.load_model("sciworld")
        goal = copy.deepcopy(state)
        for action in walk:
            goal = ref.predict_belief(copy.deepcopy(goal), action)
        task = {"task_id": row["task_id"], "trajectory": row["trajectory"], "step": row["source_step"],
                "state": state, "actions": actions, "walk": walk, "goal": benchmark.canonical(goal)}
        record = v1.task_record(task, rank, benchmark)
        record.update(cohort="prospective", source_item_sha256=row["source_item_sha256"])
        require(record["eligible"] and all(record[k] == v for k, v in row.items()), "Frame mismatch")
        tasks.append(task)
        records.append(record)
        private_rows.append({"task_id": task["task_id"], "ordered_candidates": actions, "goal_walk": walk,
                             "goal": task["goal"], "root_alias_path_groups": v1.shared_paths(state)})
    cases = benchmark.cases("sciworld", "train", 32)
    calibration = [(c[0], c[1]) for c in cases]
    calibration_rows = [{"trajectory": ti, "source_step": j, "action_id": v1.digest(action),
                         "state_sha256": root_hash(state), "alias_sha256": v1.digest(v1.alias_groups(state))}
                        for state, action, ti, j, _ in cases]
    require(calibration_rows == old["initial_calibration"], "Historical calibration mismatch")
    assets = {"private/tasks.pkl": pickle.dumps(tasks, protocol=4),
              "private/calibration.pkl": pickle.dumps(calibration, protocol=4),
              "private/manifest.json": v1.json_bytes({"tasks": private_rows, "pickle_protocol": 4})}
    manifest = {"schema_version": 2, "phase": "pre-intervention", "study": "sciworld-prospective-v1",
                "dataset_revision": DATA, "model_revision": old["model_revision"], "split_sha256": PINNED,
                "runtime_release_ref": old["runtime_release_ref"], "runtime_commit": RELEASE,
                "runtime_sha256": old["runtime_sha256"], "environment": {
                    "python": sys.version, "platform": platform.platform(), "machine": platform.machine(),
                    "implementation": platform.python_implementation(), "hash_seed": 0},
                "repository_sha256": paths, "study_code_sha256": old["study_code_sha256"],
                "sampling": sampling, "frame": frame, "excluded_representatives": excluded,
                "selection": {"eligible": len(records)}, "tasks": records, "initial_calibration": calibration_rows,
                "serializer": old["serializer"], "fixed_work": old["protocol"],
                "private_file_sha256": {p: sha(b) for p, b in assets.items()}}
    if args.check_manifest:
        prior = json.loads(args.check_manifest.read_bytes())
        for key in manifest.keys() - {"environment", "private_file_sha256"}:
            require(manifest[key] == prior[key], f"Reconstruction differs in {key}")
        require(manifest["private_file_sha256"] == prior["private_file_sha256"], "Private input bytes differ")
        print(f"Reconstructed {len(frame)} eligible representatives and all {len(records)} selected roots.")
    if args.bundle is None:
        return
    assets["public/manifest.json"] = (json.dumps(manifest, ensure_ascii=False, sort_keys=True, indent=2)
                                     + "\n").encode("utf-8")
    bundle = args.bundle.resolve()
    require(all(not (bundle / name).exists() for name in assets), "Use fresh setup artifact paths")
    for name, data in assets.items():
        path = bundle / name
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("xb") as handle:
            handle.write(data)
    print(f"Sealed {len(records)} states from {len(frame)} eligible representatives.")
    print("Manifest SHA-256", sha(assets["public/manifest.json"]))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", type=Path, required=True)
    parser.add_argument("--data-root", type=Path, required=True)
    parser.add_argument("--fetch", action="store_true", help="Acquire missing pinned full test/train files")
    parser.add_argument("--bundle", type=Path, help="Destination for new study inputs and public seal")
    parser.add_argument("--check-manifest", type=Path, help="Verify a published seal against reconstructed inputs")
    parser.add_argument("--inventory", action="store_true", help="Count the outcome-blind frame without selecting states")
    args = parser.parse_args()
    if args.bundle is None and not args.check_manifest and not args.inventory:
        parser.error("specify --bundle, --check-manifest or --inventory")
    construct(args)
