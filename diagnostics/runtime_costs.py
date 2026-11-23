"""Synthetic Runtime diagnostic. Run in a Git checkout with PYTHONHASHSEED=0."""

import argparse
import copy
import gc
import hashlib
import json
import math
import os
import platform
import re
import statistics
import struct
import subprocess
import sys
import time
import types
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
BASE = "3c9022030323bd22e05b3f5276531eaa542cb1eb"
PRIOR = "7e57af85d0e8a6c7ee16a325c51eabdbcb015822"
CORE = "src/wctr/isolation.py"
ROUNDS = 10
# Counts per throughput batch. Large inputs run fewer times.
SIZES = {4: 128, 64: 48, 256: 16}
TAIL_BATCH = 16
ARMS = ("original_wctr", "prior_wctr", "repaired_wctr", "journal_only", "full_copy")
SCENARIOS = ("read", "first_append", "calibrated_append", "set_read")
MODEL = """
class Model:
    def predict_belief(self, state, action):
        if action == "append":
            state["events"].append(1)
            return state
        if action == "members":
            return {"size": len(state["members"])}
        return {"value": state["rows"][0]["index"]}
"""


def git(*args):
    return subprocess.check_output(["git", "-C", str(ROOT), *args])


def digest(data):
    return hashlib.sha256(data).hexdigest()


def load_core(code, name):
    mod = types.ModuleType(name)
    sys.modules[name] = mod
    exec(compile(code, name + ".py", "exec"), mod.__dict__)
    return mod


def make_parent(rows, scenario):
    history = [0]
    state = {
        "rows": [{"index": i, "slots": [i, i + 1]} for i in range(rows)],
        "events": history,
        "history": history,
    }
    if scenario == "set_read":
        state["members"] = {0, 1, 2}
    return state


def get_action(scenario):
    if scenario in ("first_append", "calibrated_append"):
        return "append"
    return "members" if scenario == "set_read" else "read"


class FullCopy:
    """Independent uninstrumented control, with one counted whole-state copy."""

    def __init__(self, raw):
        self.raw = raw
        self.full_clones = 0

    def transition(self, state, action):
        result = self.raw.predict_belief(copy.deepcopy(state), action)
        self.full_clones += 1
        return result


def order(labels, round_index):
    """Each arm occupies every position twice, with reversed traversal the second time."""
    labels = list(labels)
    if round_index >= len(labels):
        labels.reverse()
    offset = round_index % len(labels)
    return labels[offset:] + labels[:offset]


def transition_batch(make_adapter, arm, raw, rows, scenario, count, individual):
    state = make_parent(rows, scenario)
    initial = copy.deepcopy(state)
    history = state["events"]
    action = get_action(scenario)
    expected = raw.predict_belief(copy.deepcopy(state), action)
    if scenario == "first_append":
        unique = [make_adapter() for _ in range(count)]
        adapters = unique
    else:
        adapter = make_adapter()
        if scenario == "calibrated_append" and arm != "full_copy":
            adapter.calibrate([(state, action)])
        unique = [adapter]
        adapters = [adapter] * count
    gc.collect()
    gc.disable()
    samples = []
    try:
        if individual:
            for adapter in adapters:
                start = time.perf_counter_ns()
                output = adapter.transition(state, action)
                samples.append(time.perf_counter_ns() - start)
        else:
            start = time.perf_counter_ns()
            for adapter in adapters:
                output = adapter.transition(state, action)
            samples.append(time.perf_counter_ns() - start)
    finally:
        gc.enable()
    assert output == expected and state == initial
    assert state["events"] is state["history"] is history
    if action == "append":
        assert output["events"] is output["history"] and output["events"] is not history
    clones = sum(adapter.full_clones for adapter in unique)
    return samples, clones


def percentile95(values):
    """Empirical p95 (nearest rank)."""
    return sorted(values)[math.ceil(0.95 * len(values)) - 1]


def summary(values):
    q1, _, q3 = statistics.quantiles(values, n=4, method="inclusive")
    return [round(x, 3) for x in (q1, statistics.median(values), q3)]


def compare(builders, raw):
    results = []
    for rows, count in SIZES.items():
        for scenario in SCENARIOS:
            batches = {arm: [] for arm in ARMS}
            calls = {arm: [] for arm in ARMS}
            clones = dict.fromkeys(ARMS, 0)
            for arm in ARMS:
                transition_batch(builders[arm], arm, raw, rows, scenario, 12, False)
            for individual in (False, True):
                for i in range(ROUNDS):
                    for arm in order(ARMS, i):
                        samples, copied = transition_batch(
                            builders[arm], arm, raw, rows, scenario,
                            TAIL_BATCH if individual else count, individual,
                        )
                        (calls if individual else batches)[arm].extend(samples)
                        clones[arm] += copied
            for arm in ARMS:
                expected_calls = ROUNDS * (TAIL_BATCH + count)
                values = [ns / (1000 * count) for ns in batches[arm]]
                results.append({
                    "rows": rows,
                    "containers": rows * 2 + 3 + int(scenario == "set_read"),
                    "scenario": scenario,
                    "arm": arm,
                    "batch_size": count,
                    "batch_q1_median_q3_us": summary(values),
                    "individual_p95_us": round(percentile95(calls[arm]) / 1000, 3),
                    "timed_transitions": expected_calls,
                    "full_clones": clones[arm],
                    "batch_elapsed_ns": batches[arm],
                    "individual_elapsed_ns": calls[arm],
                })
            print(rows, scenario, "completed", flush=True)
    return results


def component_probes(mod, model, repaired):
    """Measure prior core primitives and the repaired traversal on matching inputs."""
    state = make_parent(64, "read")
    inputs = mod.graph(state)
    nodes, parents, _ = inputs
    target = {id(state["events"])}
    adapter = mod.Adapter(model())
    adapter.calibrate([(state, "append")])
    set_last = make_parent(64, "set_read")
    set_first = {"members": set_last["members"], **state}

    def closure():
        affected = set(target) & nodes.keys()
        todo = list(affected)
        while todo:
            for parent in parents[todo.pop()]:
                if parent not in affected:
                    affected.add(parent)
                    todo.append(parent)
        return affected

    temporary = []
    def direct_dispatch():
        temporary.append(1)
        temporary.pop()

    def guarded_dispatch():
        mod.bind_mutator(temporary.append)(1)
        temporary.pop()

    probes = {
        "entry_graph": lambda: mod.graph(state),
        "type_scan_prebuilt_nodes": lambda: any(isinstance(obj, (set, defaultdict)) for obj in nodes.values()),
        "reverse_alias_closure_only": closure,
        "alias_fork_prebuilt_graph": lambda: mod.alias_fork(state, target, inputs),
        "alias_fork_including_graph": lambda: mod.alias_fork(state, target),
        "frontier_match": lambda: mod.match_targets(state, adapter.frontiers["append"], "append"),
        "full_copy": lambda: copy.deepcopy(state),
        "direct_append_and_raw_pop": direct_dispatch,
        "guarded_append_and_raw_pop": guarded_dispatch,
        "repaired_discovery_clean": lambda: repaired._needs_full_copy(state),
        "repaired_discovery_set_last_key": lambda: repaired._needs_full_copy(set_last),
        "repaired_discovery_set_first_key": lambda: repaired._needs_full_copy(set_first),
        "repaired_graph_with_type_check": lambda: repaired.graph(state, stop_on_fallback=True),
    }
    records = []
    samples = {key: [] for key in probes}
    batch_size = 128
    journal = mod.Journal(state, inputs, {id(temporary)})
    token = mod.CURRENT.set(journal)
    try:
        for func in probes.values():
            for _ in range(12):
                func()
        for i in range(2 * len(probes)):
            for key in order(probes, i):
                func = probes[key]
                gc.collect()
                gc.disable()
                try:
                    start = time.perf_counter_ns()
                    for _ in range(batch_size):
                        func()
                    samples[key].append(time.perf_counter_ns() - start)
                finally:
                    gc.enable()
    finally:
        mod.CURRENT.reset(token)
    assert not temporary and not journal.saved and closure() == {id(state), *target}
    for key, elapsed in samples.items():
        records.append({"probe": key, "batch_size": batch_size, "batch_elapsed_ns": elapsed,
                        "batch_q1_median_q3_us": summary([ns / (1000 * batch_size) for ns in elapsed])})
    return records


def processor():
    if sys.platform == "win32":
        import winreg
        with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, r"HARDWARE\DESCRIPTION\System\CentralProcessor\0") as key:
            return winreg.QueryValueEx(key, "ProcessorNameString")[0].strip()
    return platform.processor()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    if os.environ.get("PYTHONHASHSEED") != "0" or not __debug__:
        parser.error("run with PYTHONHASHSEED=0 and assertions enabled")
    repaired_commit = git("log", "-1", "--format=%H", "HEAD", "--", CORE).decode().strip()
    sources = {"original_wctr": git("show", BASE + ":" + CORE),
               "prior_wctr": git("show", PRIOR + ":" + CORE),
               "repaired_wctr": (ROOT / CORE).read_bytes()}
    assert sources["original_wctr"] == git("show", "HEAD:experiments/frozen/isolation.py")
    assert sources["repaired_wctr"] == git("show", repaired_commit + ":" + CORE)
    mods = {arm: load_core(source, arm) for arm, source in sources.items()}
    models = {arm: mod.compile_source(MODEL, "diagnostic_fixture.py")["Model"]
              for arm, mod in mods.items()}
    raw_ns = {}
    exec(compile(MODEL, "raw_fixture.py", "exec"), raw_ns)
    raw = raw_ns["Model"]()

    def adapter(arm, method):
        instrumented = models[arm]()
        instrumented._wctr_raw_model = raw
        return mods[arm].Adapter(instrumented, method)

    builders = {arm: (lambda arm=arm: adapter(arm, "wctr")) for arm in mods}
    builders["journal_only"] = lambda: adapter("repaired_wctr", "journal")
    builders["full_copy"] = lambda: FullCopy(raw)
    report = {
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "python": sys.version,
        "platform": platform.platform(),
        "pointer_bits": struct.calcsize("P") * 8,
        "processor": processor(),
        "hash_seed": os.environ["PYTHONHASHSEED"],
        "clock": vars(time.get_clock_info("perf_counter")),
        "throughput_rounds": ROUNDS, "individual_rounds": ROUNDS,
        "individual_batch_size": TAIL_BATCH, "warmup_transitions_per_cell": 12,
        "original_version": BASE,
        "prior_version": PRIOR,
        "repaired_version": repaired_commit,
        "source_sha256": {arm: digest(code) for arm, code in sources.items()},
        "fixture_sha256": digest(MODEL.encode()),
        "components": component_probes(mods["prior_wctr"], models["prior_wctr"], mods["repaired_wctr"]),
        "comparisons": compare(builders, raw),
    }
    # Keep numeric vectors on one line while retaining every observation.
    output = json.dumps(report, indent=2)
    output = re.sub(r"\[\s*([-+\d.eE]+(?:,\s*[-+\d.eE]+)*)\s*\]",
                    lambda match: "[" + ", ".join(value.strip() for value in match[1].split(",")) + "]",
                    output)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("w", encoding="utf-8", newline="\n") as handle:
        handle.write(output + "\n")


if __name__ == "__main__":
    main()
