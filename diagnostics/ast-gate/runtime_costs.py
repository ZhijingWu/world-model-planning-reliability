"""Time the two pinned AST release candidates and two controls on small synthetic states."""
import argparse
import copy
import gc
import hashlib
import importlib.util
import json
import os
import platform
import re
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PRIOR = "9e28df1463f9a878a0df853926243ef9bcbc1642"
CANDIDATE = "dd3aa05f9fc064a5293650e75a55f00308495fbb"
CORE = "src/wctr/isolation.py"

# Explicit file import because both diagnostics have the same script name.
spec = importlib.util.spec_from_file_location("earlier_diagnostic", ROOT / "diagnostics/runtime_costs.py")
controls = importlib.util.module_from_spec(spec)
spec.loader.exec_module(controls)

SHAPES = {
    "mixed_model": controls.MODEL,
    "name_iadd": """class Model:
    def predict_belief(self, state, action):
        alias = state['events']
        alias += [1]
        return state
""",
    "annotated_subscript": """class Model:
    def predict_belief(self, state, action):
        state['events'][0]: int = state['events'][0] + 1
        return state
""",
}


def core_bytes(revision):
    return subprocess.check_output(["git", "-C", str(ROOT), "show", revision + ":" + CORE])


def preflight(builder, raw, size, scenario, arm):
    parent = controls.make_parent(size, scenario)
    history = parent["events"]
    original = copy.deepcopy(parent)
    action = controls.get_action(scenario)
    expected = raw.predict_belief(copy.deepcopy(parent), action)
    adapter = builder()
    if scenario == "calibrated_append" and arm != "full_copy":
        adapter.calibrate([(parent, action)])
    result = adapter.transition(parent, action)
    if parent != original:
        return "parent value changed"
    assert parent["events"] is parent["history"] is history
    assert result == expected
    if action == "append":
        assert result["events"] is result["history"] and result["events"] is not history
    return "PASS"


def setup_costs(prior, candidate):
    def factories(mod):
        cls = mod.compile_source(controls.MODEL, "setup_fixture.py")["Model"]
        return (lambda: mod.compile_source(controls.MODEL, "setup_fixture.py"),
                lambda: mod.Adapter(cls()))

    functions = {"prior_wctr": factories(prior), "candidate_wctr": factories(candidate)}
    results = {}
    for index, label, count in ((0, "compile_source", 32), (1, "create_model_and_adapter", 128)):
        elapsed = {arm: [] for arm in functions}
        for rnd in range(8):
            arms = list(functions)
            if rnd % 2:
                arms.reverse()
            for arm in arms:
                func = functions[arm][index]
                gc.collect()
                gc.disable()
                try:
                    start = time.perf_counter_ns()
                    for _ in range(count):
                        func()
                    elapsed[arm].append(time.perf_counter_ns() - start)
                finally:
                    gc.enable()
        results[label] = {
            arm: {"batch_size": count, "elapsed_ns": durations,
                  "q1_median_q3_us": controls.summary([ns / (1000 * count) for ns in durations])}
            for arm, durations in elapsed.items()
        }
    return results


def measure(builders, raw, size, scenario, shape):
    count = 48 if size == 64 else 128
    checks = {arm: preflight(build, raw, size, scenario, arm) for arm, build in builders.items()}
    for arm, outcome in checks.items():
        expected_failure = arm == "prior_wctr" and shape != "mixed_model"
        assert outcome == ("parent value changed" if expected_failure else "PASS"), (arm, shape, outcome)
    active = [arm for arm in builders if checks[arm] == "PASS"]
    rounds = 2 * len(active)
    batches = {arm: [] for arm in active}
    individual = {arm: [] for arm in active}
    clones = dict.fromkeys(active, 0)
    for arm in active:
        controls.transition_batch(builders[arm], arm, raw, size, scenario, 12, False)
    for sampled in (False, True):
        for rnd in range(rounds):
            for arm in controls.order(active, rnd):
                times, copied = controls.transition_batch(
                    builders[arm], arm, raw, size, scenario, 12 if sampled else count, sampled)
                (individual if sampled else batches)[arm].extend(times)
                clones[arm] += copied
    for arm, outcome in checks.items():
        item = {"shape": shape, "rows": size, "scenario": scenario, "arm": arm, "preflight": outcome}
        if arm in active:
            values = [ns / (1000 * count) for ns in batches[arm]]
            item.update(q1_median_q3_us=controls.summary(values),
                        p95_us=controls.percentile95(individual[arm]) / 1000,
                        timed=rounds * (count + 12), full_clones=clones[arm], batch_size=count,
                        elapsed_ns=batches[arm], individual_ns=individual[arm])
        yield item


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if not __debug__ or os.environ.get("PYTHONHASHSEED") != "0":
        parser.error("enable assertions and set PYTHONHASHSEED=0 before interpreter startup")
    prior_bytes = core_bytes(PRIOR)
    candidate_bytes = core_bytes(CANDIDATE)
    prior = controls.load_core(prior_bytes, "ast_gate_prior")
    candidate = controls.load_core(candidate_bytes, "ast_gate_candidate")
    report = {
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "head": CANDIDATE, "prior": PRIOR, "py": sys.version, "platform": platform.platform(),
        "processor": controls.processor(), "hash_seed": os.environ["PYTHONHASHSEED"],
        "fixture_sha256": {shape: hashlib.sha256(source.encode()).hexdigest()
                           for shape, source in SHAPES.items()},
        "prior_core_sha256": hashlib.sha256(prior_bytes).hexdigest(),
        "candidate_core_sha256": hashlib.sha256(candidate_bytes).hexdigest(),
        "setup": setup_costs(prior, candidate), "comparisons": [],
    }
    for shape, source in SHAPES.items():
        namespace = {}
        exec(compile(source, "raw_gate_fixture.py", "exec", dont_inherit=True), namespace)
        raw = namespace["Model"]()
        old_model = prior.compile_source(source, "prior_gate_fixture.py")["Model"]
        new_model = candidate.compile_source(source, "candidate_gate_fixture.py")["Model"]
        builders = {
            "prior_wctr": lambda: prior.Adapter(old_model()),
            "candidate_wctr": lambda: candidate.Adapter(new_model()),
            "candidate_journal": lambda: candidate.Adapter(new_model(), "journal"),
            "full_copy": lambda: controls.FullCopy(raw),
        }
        scenarios = controls.SCENARIOS if shape == "mixed_model" else ("first_append",)
        for size in (4, 64):
            for scenario in scenarios:
                report["comparisons"].extend(measure(builders, raw, size, scenario, shape))
                print(shape, size, scenario, flush=True)
    output = json.dumps(report, indent=2)
    output = re.sub(r"\[\s*([-+\d.eE]+(?:,\s*[-+\d.eE]+)*)\s*\]",
                    lambda match: "[" + ", ".join(v.strip() for v in match[1].split(",")) + "]", output)
    with args.output.open("w", encoding="utf-8", newline="\n") as handle:
        handle.write(output + "\n")


if __name__ == "__main__":
    main()
