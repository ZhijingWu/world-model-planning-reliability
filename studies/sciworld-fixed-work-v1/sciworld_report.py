"""Write a descriptive report using three verified public artifacts. Runs no models."""
import argparse
import gzip
import hashlib
import io
import json
import os
from collections import Counter
from itertools import permutations
from pathlib import Path
from urllib.parse import quote


ARMS = {"raw": "Raw", "full_copy": "Full Copy", "wctr": "Repaired WCTR"}
COHORTS = {"historical_failure": "Historical failure", "comparison": "Comparison"}


def read(path):
    content = gzip.decompress(path.read_bytes()) if path.suffix == ".gz" else path.read_bytes()
    return json.loads(content), hashlib.sha256(content).hexdigest()


def summarize(task):
    counts = Counter()
    for pair in task.get("comparisons", []):
        counts["orders"] += 1
        for name, arm in pair["arms"].items():
            counts[name + "_edges"] += len(arm["edges"])
            counts[name + "_errors"] += arm["status"] != "complete"
            for edge in arm["edges"]:
                counts[name + "_writes"] += edge["parent_before"][0] != edge["parent_after"][0]
                counts[name + "_root_writes"] += edge["root_before"][0] != edge["root_after"][0]
                if name == "wctr":
                    for key, value in edge["runtime_delta"].items():
                        counts["wctr_" + key] += value
            if arm["status"] == "complete":
                counts[name + "_completed"] += 1
                counts[name + "_ties"] += len(arm["root_ties"]) >= 2
                counts[name + "_all_tied"] += arm["all_root_scores_equal"]
                counts[name + "_search_exact"] += arm["search_exact_goal"]
                replay = arm["replay"]
                counts[name + "_replays"] += replay["status"] == "complete"
                counts[name + "_replay_errors"] += replay["status"] != "complete"
                counts[name + "_exact_replays"] += bool(replay["exact_goal"])
                counts[name + "_false_goals"] += bool(replay["false_goal"])
        if pair["decision_changed"] is None:
            continue
        counts["valid"] += 1
        counts["selected"] += pair["decision_changed"]
        counts["rescued"] += pair["classification"] == "verified_single_edge_rescue"
        counts["root_scores"] += pair["raw_score_change"]
        counts["ranks"] += pair["ranking_changed"]
        counts["leaf_scores"] += len(pair["leaf_score_changes"])
        counts["orders_with_leaf_change"] += bool(pair["leaf_score_changes"])
        counts["score_only"] += pair["classification"] == "score_only"
        if pair["rescue"]:
            counts["interventions"] += 1
        full = {tuple(e["path"]): e for e in pair["arms"]["full_copy"]["edges"]}
        for edge in pair["arms"]["raw"]["edges"]:
            counts["inputs"] += edge["parent_before"] != full[tuple(edge["path"])]["parent_before"]
    return counts


def ordered_examples(tasks):
    examples = []
    for row in tasks:
        for pair in row.get("comparisons", []):
            if pair["decision_changed"] is None:
                continue
            ref = {tuple(e["path"]): e for e in pair["arms"]["full_copy"]["edges"]}
            divergent = [e["path"] for e in pair["arms"]["raw"]["edges"]
                         if e["parent_before"] != ref[tuple(e["path"])]["parent_before"]]
            priority = (pair["classification"] == "verified_single_edge_rescue", pair["decision_changed"],
                        bool(pair["leaf_score_changes"]), bool(divergent))
            examples.append((priority, row["task_id"], pair, ref, divergent))
    # Prefer demonstrated causal changes, then unresolved decision differences,
    # then score-only observations, then input differences, then tied/null cases.
    # Frozen state and permutation order break equal priorities.
    return max(examples, key=lambda item: item[0]) if examples else None


def reviewed_object_states(private_edges, verification, rows, example):
    """Expose only a confirmation about the named public field, never private path components."""
    if private_edges is None:
        return False
    compressed = private_edges.read_bytes()
    if hashlib.sha256(compressed).hexdigest() != verification["private_edge_archive_sha256"]:
        raise ValueError("Private edge archive differs from the independently verified gzip SHA-256")
    if example is None:
        return False
    _, task_id, _, _, _ = example
    task = next(row for row in rows if row["task_id"] == task_id)
    rescues = {tuple(pair["order"]): pair["rescue"] for pair in task["comparisons"]}
    if set(rescues) != set(permutations(range(3))) or not all(rescues.values()):
        return False

    # The frozen writer emits compact JSONL. Filter serialized record metadata
    # before parsing so private snapshots and other tasks' paths are never loaded.
    task_marker = f'"task_id":{task_id},'.encode("ascii")
    found = set()
    with gzip.GzipFile(fileobj=io.BytesIO(compressed)) as stream:
        for line in stream:
            if b'"type":"carry_candidates"' not in line or task_marker not in line:
                continue
            record = json.loads(line)
            if record["type"] != "carry_candidates" or record["task_id"] != task_id:
                continue
            order = tuple(record["order"])
            if order not in rescues or order in found or not record["candidates"]:
                return False
            first = record["candidates"][0]
            expected = rescues[order]
            if (first["writer"] != expected["writer"] or first["reader"] != expected["reader"]
                    or first["source"] != expected["source"] or not first["paths"]
                    or not all(path and path[0] == "object_states" for path in first["paths"])):
                return False
            found.add(order)
    return found == set(rescues)


def example_lines(example, confirmed_object_states):
    if example is None:
        return ["No order qualified for a decision comparison."]
    _, tid, pair, ref, divergent = example
    raw, full = (pair["arms"][name] for name in ("raw", "full_copy"))
    lines = [f"Task **{tid}**, root visit order `{pair['order']}`. Raw scored the three root actions "
             f"`{raw['root_scores']}` and selected the path `{raw['selected']}`. Full Copy scored them "
             f"`{full['root_scores']}` and selected `{full['selected']}`. Indices follow the frozen "
             "candidate list. The first index is the root decision."]
    if divergent:
        lines.append(f"The earliest edge whose input differed from Full Copy was `{divergent[0]}`.")
    else:
        lines.append("Every raw branch input matched the corresponding Full Copy input.")
    if pair["leaf_score_changes"]:
        path = pair["leaf_score_changes"][0]
        raw_edge = next(e for e in raw["edges"] if e["path"] == path)
        lines.append(f"At leaf `{path}`, Raw matched {raw_edge['goal_fields_equal']} goal fields and "
                     f"Full Copy matched {ref[tuple(path)]['goal_fields_equal']}.")
    outcome = pair["rescue"]
    if outcome:
        restored = "restored" if outcome["sibling_restored"] else "did not restore"
        decision = "restored" if outcome["reference_decision_restored"] else "did not restore"
        lines.append(f"Copying only the input to edge `{outcome['writer']}` {restored} the input "
                     f"to later sibling `{outcome['reader']}` and {decision} the reference decision.")
        if (outcome["reference_decision_restored"] and outcome["run"]["selected"] != full["selected"]):
            lines.append(f"The rescue selected `{outcome['run']['selected']}`, so its second action "
                         f"still differed from Full Copy's `{full['selected'][1]}`.")
        if confirmed_object_states:
            lines.append("Review of the retained traces identified the model's `object_states` field "
                         "at the first carried write in each of this task's six orders. "
                         "The released transition starts with `belief.copy()`, which leaves that nested "
                         "dictionary shared. [Model source](https://github.com/ZhijingWu/world-model-planning-reliability/blob/"
                         "3c9022030323bd22e05b3f5276531eaa542cb1eb/third_party/PatchWorld/examples/generated_world_models/"
                         "sciworld_benchmark_world_model.py#L154-L166)")
    elif pair["decision_changed"]:
        lines.append("The trace yielded no single carried write eligible for the prescribed rescue.")
    return [" ".join(lines)]


def make_report(manifest, results, verification, source_links, private_edges=None):
    rows = results["tasks"]
    meta = {t["task_id"]: t for t in manifest["tasks"]}
    if set(meta) != {r["task_id"] for r in rows} or len(rows) != len(meta):
        raise ValueError("Result IDs differ from frozen state bank")
    counts = {r["task_id"]: summarize(r) for r in rows}
    all_counts, work = Counter(), Counter()
    for row in rows:
        tid = row["task_id"]
        c = counts[tid]
        checked = verification["task_counts"].get(str(tid), {})
        if row["eligible"] != meta[tid]["eligible"]:
            raise ValueError(f"Eligibility differs for task {tid}")
        for key, name in (("orders", "paired_orders"), ("selected", "decision_changes"),
                          ("rescued", "verified_single_edge_rescue"), ("inputs", "raw_parent_inputs_different_from_reference"),
                          ("leaf_scores", "leaf_scores_changed"), ("root_scores", "root_score_changes"),
                          ("raw_writes", "raw_parent_value_changes"), ("wctr_full_clones", "wctr_full_clones")):
            if c[key] != checked.get(name, 0):
                raise ValueError(f"Public rows and independently verified count disagree for task {tid}, {name}")
        all_counts.update(c)
        work.update(row.get("calls", {}))
    example = ordered_examples(rows)
    confirmed_object_states = reviewed_object_states(private_edges, verification, rows, example)
    c = all_counts
    eligible = sum(t["eligible"] for t in rows)
    tested = sum(bool(s["valid"]) for s in counts.values())
    changed = sum(bool(s["selected"]) for s in counts.values())
    rescued = sum(bool(s["rescued"]) for s in counts.values())
    failed = verification["independently_recomputed_controls_pass"] is not True
    status = ("At least one control or execution check failed. The task table identifies state-level "
              "coverage; causal conclusions require successful controls on the affected comparisons. " if failed else "")
    if c["selected"]:
        changed_ids = [str(tid) for tid, values in counts.items() if values["selected"]]
        primary = (f"Raw and Full Copy selected different root actions on **{changed}/{tested} evaluable states** "
                   f"(task {', '.join(changed_ids)}) and {c['selected']}/{c['valid']} paired visit orders. "
                   f"Copying only the input at the earliest traced writing edge restored both the affected "
                   f"sibling input and the reference action in **{c['rescued']}/{c['interventions']} interventions**.")
        partial = sum(bool(p["rescue"]) and p["rescue"]["sibling_restored"]
                      and not p["rescue"]["reference_decision_restored"]
                      for row in rows for p in row.get("comparisons", []))
        if partial:
            primary += (f" In {partial} further orders the same intervention restored the sibling input "
                        "while the decision difference persisted. Those orders remain causally unresolved.")
    elif tested:
        primary = (f"Raw and Full Copy selected the **same root action on all {tested} evaluable states** "
                   f"and all {c['valid']} paired visit orders. The frozen rule therefore triggered no "
                   "single-edge rescue.")
    else:
        primary = "No state passed the controls needed to evaluate the primary endpoint."
    body = ["# Does state contamination change the first action in SciWorld?", "",
            status + primary, "",
            f"Raw execution changed its caller's edge-parent value on **{c['raw_writes']}/{c['raw_edges']}** "
            f"search transitions. Across evaluable orders, {c['inputs']}/{12*c['valid']} branch inputs "
            f"differed from the corresponding Full Copy input in value or internal sharing. "
            f"{c['leaf_scores']}/{9*c['valid']} leaf scores differed, and the root score vector differed "
            f"in {c['root_scores']}/{c['valid']} orders. {c['score_only']} orders had a score difference with "
            f"the same selected root action.", "",
            "## State bank and decisions", "",
            "The frozen bank contains nine states where a historical Raw plan failed replay and two nearby "
            "states from the same trajectories where historical replay succeeded. Each state contributes "
            "six repeated orders. The task-level denominator counts each eligible state once.", "",
            "| Historical cohort | Frozen | Eligible | Evaluable states | States with different action | States with verified rescue |",
            "| --- | ---: | ---: | ---: | ---: | ---: |"]
    for group, label in COHORTS.items():
        g = [r for r in rows if meta[r["task_id"]]["cohort"] == group]
        values = [counts[r["task_id"]] for r in g]
        body.append(f"| {label} | {len(g)} | {sum(r['eligible'] for r in g)} | {sum(bool(s['valid']) for s in values)} | "
                    f"{sum(bool(s['selected']) for s in values)} | {sum(bool(s['rescued']) for s in values)} |")
    body += ["", "Raw writes count search edges. Changed inputs compare corresponding path inputs. "
             "Leaf scores count the nine leaves per order. Root scores and decisions count paired orders. "
             "Rows with fewer than three distinct actions remain in the frozen bank.", "",
             "| Task ID | Cohort | Raw writes / edges | Changed inputs / edges | Changed leaf scores / leaves | Changed root scores / orders | Changed actions / orders | Rescues / interventions |",
             "| ---: | --- | ---: | ---: | ---: | ---: | ---: | ---: |"]
    for r in rows:
        tid = r["task_id"]
        s = counts[tid]
        label = COHORTS[meta[tid]["cohort"]]
        if not r["eligible"]:
            body.append(f"| {tid} | {label} | Ineligible | — | — | — | — | — |")
        else:
            rescues_display = f"{s['rescued']}/{s['interventions']}" if s["interventions"] else "—"
            body.append(f"| {tid} | {label} | {s['raw_writes']}/{s['raw_edges']} | {s['inputs']}/{12*s['valid']} | "
                        f"{s['leaf_scores']}/{9*s['valid']} | {s['root_scores']}/{s['valid']} | "
                        f"{s['selected']}/{s['valid']} | {rescues_display} |")
    body += ["", "## How the search chose an action", "",
             "The fixed tree uses the first three distinct actions from each task. Each root action is followed "
             "immediately by its three children in frozen order. A leaf earns one point per matching top-level goal "
             "field. Each root action receives its best leaf score. Frozen candidate index breaks ties. "
             "Independent replay executes the selected two actions on fresh copies from the pristine root.", "",
             "| Arm | Completed searches | Tied best roots | All three tied | Selected leaf exact in search | Exact after replay | False goals | Replay errors |",
             "| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |"]
    for arm, label in ARMS.items():
        body.append(f"| {label} | {c[arm+'_completed']} | {c[arm+'_ties']} | {c[arm+'_all_tied']} | "
                    f"{c[arm+'_search_exact']} | {c[arm+'_exact_replays']} | {c[arm+'_false_goals']} | {c[arm+'_replay_errors']} |")
    body += ["", "A false goal requires exact whole-goal equality during search followed by a replay that "
             "misses the goal. A partial-score winner can replay consistently and still miss the goal. "
             f"Raw and Full Copy ranked the three root actions differently in {c['ranks']}/{c['valid']} orders.", "",
             "### One paired order", "", *example_lines(example, confirmed_object_states), "",
             "## Isolation and interpretation", "",
             f"Full Copy passed the state-level controls on {sum(r.get('reference_controls_pass') is True for r in rows)}/{eligible} "
             f"eligible states. WCTR passed its state-level controls on {sum(r.get('wctr_controls_pass') is True for r in rows)}/{eligible}. "
             f"Full Copy had {c['full_copy_writes']} edge-parent value changes and WCTR had {c['wctr_writes']}. "
             f"WCTR recorded {c['wctr_full_clones']} whole-state copies over {c['wctr_edges']} search calls, "
             f"{c['wctr_deoptimizations']} deoptimizations and {c['wctr_witness_paths']} net added witness paths. "
             f"The three arms recorded {sum(c[a+'_errors'] for a in ARMS)} incomplete search or calibration runs.", ""]
    if c["wctr_edges"] and c["wctr_full_clones"] == c["wctr_edges"]:
        body += ["Every WCTR search transition took Full Copy. The released model source selects the native "
                 "fallback, and its belief includes sets. These trials provide evidence for isolation on this "
                 "workload. The WCTR search arm did not exercise selective copying.", ""]
    body += [f"The run used {work['search']:,} search transitions, {work['initial_calibration']:,} initial "
             f"WCTR calibration calls, {work['replay']:,} independent replay calls and {work['rescue']:,} rescue "
             f"search calls. Trace inspection added {work['trace_inspection']} model calls. The frozen runtime "
             f"commit was `{manifest['runtime_commit']}`.", "",
             "The bank was selected using historical replay outcomes. It does not estimate prevalence among all "
             "SciWorld tasks. This experiment measures choices within a released executable model at depth two. "
             "Native environment outcomes and the causes of the earlier deadline-limited failures remain open.", ""]
    if failed:
        next_step = "Resolve the reported reference or replay failures and repeat the preregistered controls before interpreting the affected states."
    elif rescued:
        next_step = "Test whether the verified single-edge rescues recur on a prospectively sampled bank with a fixed scoring rule and separately measured environment outcomes."
    elif changed:
        next_step = "Predefine a multiple-edge intervention for the unresolved decision differences and test it on fresh states."
    elif c["leaf_scores"]:
        next_step = "Predefine a scoring sensitivity check on a fresh, unselected state bank to test when a change in a leaf score can move a root decision."
    else:
        next_step = "Test a prospectively sampled bank with a prespecified score and depth that can distinguish the consequences of altered branch inputs."
    body += ["**Next research question.** " + next_step, "", " ".join(source_links)]
    return "\n".join(body) + "\n"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for flag in ("manifest", "results", "verification", "output"):
        parser.add_argument("--" + flag, type=Path, required=True)
    parser.add_argument("--private-edges", type=Path,
                        help="Check the verified private gzip for the worked example's top-level field.")
    parser.add_argument("--replace", action="store_true", help="Refresh an existing report generated here.")
    args = parser.parse_args()
    manifest, manifest_hash = read(args.manifest)
    results, results_hash = read(args.results)
    verification, _ = read(args.verification)
    if not (manifest_hash == results["manifest_sha256"] == verification["manifest_sha256"]
            and results_hash == verification["public_results_sha256"]
            and manifest["runtime_commit"] == results["runtime_commit"]):
        raise ValueError("Report inputs do not match their verified SHA-256 or runtime commitment")
    links = []
    for name, path in (("Frozen inputs and protocol", args.manifest), ("Public per-edge records", args.results),
                       ("Independent verification", args.verification)):
        relative = os.path.relpath(path.resolve(), args.output.resolve().parent).replace(os.sep, "/")
        links.append(f"[{name}]({quote(relative, safe='/.-_')})")
    report = make_report(manifest, results, verification, links, args.private_edges)
    replace = args.replace and args.output.is_file()
    if replace and not args.output.read_text(encoding="utf-8").startswith(report.splitlines()[0] + "\n"):
        raise ValueError("Existing destination is not the generated research report")
    with args.output.open("w" if replace else "x", encoding="utf-8", newline="\n") as handle:
        handle.write(report)


if __name__ == "__main__":
    main()
