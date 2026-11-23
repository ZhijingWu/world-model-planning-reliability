"""Independently recompute the fixed-work study from its frozen bank and saved evidence.

Usage: python sciworld_verify.py --bundle STUDY_DIR [--summary NEW_JSON_FILE]
Reads JSON and gzipped JSONL only. No experiment model or runner is imported.
"""
import argparse
from collections import Counter
from dataclasses import dataclass
import gzip
from hashlib import sha256
from itertools import groupby, permutations
import json
from pathlib import Path


ORDERS = tuple(permutations(range(3)))
ARMS = ("full_copy", "wctr", "raw")
FAILURES = {364: (23, 3), 374: (24, 3), 476: (27, 16), 863: (41, 17),
            925: (44, 0), 1560: (68, 10), 1963: (82, 18), 1975: (83, 0), 2166: (90, 12)}
COMPARISONS = {390: (24, 19), 465: (27, 5)}
FIELDS = ("root_before", "root_after", "parent_before", "parent_after", "successor")
ABSENT = object()


def check(condition, message):
    if not condition:
        raise ValueError(message)


def digest(value):
    payload = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)
    return sha256(payload.encode("utf-8")).hexdigest()


def file_digest(path):
    result = sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1048576), b""):
            result.update(chunk)
    return result.hexdigest()


def read_json(path):
    return json.loads(path.read_text(encoding="utf-8"))


def indexed(rows, key):
    result = {row[key]: row for row in rows}
    check(len(result) == len(rows), f"duplicate {key}")
    return result


def children(node):
    if isinstance(node, list) and len(node) == 2:
        if node[0] == "dict":
            return dict(node[1])
        if node[0] in ("tuple", "list"):
            return dict(enumerate(node[1]))
    return None


def at(node, path):
    for key in path:
        mapping = children(node)
        if mapping is None or key not in mapping:
            return ABSENT
        node = mapping[key]
    return node


def differences(a, b):
    """Compare materialized snapshots. Sets are atomic fields in the frozen diff convention."""
    changes = set()
    stack = [((), a, b)]
    while stack:
        path, left, right = stack.pop()
        if left == right:
            continue
        lmap, rmap = children(left), children(right)
        if lmap is None or rmap is None or left[0] != right[0]:
            changes.add(path)
            continue
        for k in lmap.keys() | rmap.keys():
            stack.append((path + (k,), lmap.get(k, ABSENT), rmap.get(k, ABSENT)))
    return changes


def score(leaf, goal):
    check(leaf[0] == goal[0] == "dict", "expected a dictionary leaf and goal")
    readings = dict(leaf[1])
    return sum(k in readings and readings[k] == target for k, target in goal[1])


def steps(order):
    return [path for first in order for path in [(first,), *((first, k) for k in range(3))]]


class PrivateEvidence:
    def __init__(self, rows):
        self.values, self.shapes, self.edges, self.carries = {}, {}, {}, {}
        for row in rows:
            kind = row["type"]
            if kind in ("canonical_snapshot", "shared_paths"):
                mapping, key = ((self.values, "canonical") if kind == "canonical_snapshot"
                                else (self.shapes, "groups"))
                h = row["sha256"]
                check(h == digest(row[key]) and h not in mapping, "private snapshot hash or duplicate")
                if kind == "shared_paths":
                    check(sorted(sorted(digest(p) for p in group) for group in row["paths"]) == row[key],
                          "shared paths do not reproduce alias grouping")
                mapping[h] = row[key]
            elif kind == "edge_paths":
                key = (row["arm"], tuple(row["order"]), tuple(row["path"]))
                check(key not in self.edges, "duplicate private edge")
                self.edges[key] = row
            elif kind == "carry_candidates":
                key = tuple(row["order"])
                check(key not in self.carries, "duplicate private carry records")
                self.carries[key] = row["candidates"]
            else:
                raise ValueError(f"unknown private record type {kind}")

    def lookup(self, ref):
        check(isinstance(ref, list) and len(ref) == 2 and ref[1] in self.shapes, "missing alias snapshot")
        return self.values[ref[0]]


@dataclass
class Reading:
    by_path: dict
    complete: bool
    preserves: bool
    scores: list
    selected: list
    replay_exact: object
    exact: object
    replay_refs: list


def audit_run(arm, run, order, frozen_root, goal, evidence, summary):
    check(run["arm"] == arm and tuple(run["order"]) == order, "arm or permutation mismatch")
    if run["status"] == "calibration_error":
        check(arm == "wctr" and not run["edges"] and 0 < run["calibration_calls"] <= 32,
              "incorrect calibration failure")
        summary["calibration_errors"] += 1
        summary["calibration_calls"] += run["calibration_calls"]
        return Reading({}, False, True, [], [], None, None, [])
    complete = run["status"] == "complete"
    check(complete or run["status"] == "transition_error", "unexpected search status")
    paths = [tuple(e["path"]) for e in run["edges"]]
    schedule = steps(order)
    check(paths == schedule[:len(paths)] and (len(paths) == 12 if complete else 0 < len(paths) <= 12),
          "wrong fixed-work schedule")
    if not complete:
        check(tuple(run["failed_path"]) == paths[-1] and bool(run["exception_type"]), "missing failed edge")
    check(run["calibration_calls"] == (32 if arm == "wctr" else 0), "incorrect calibration count")
    summary["search_calls_" + arm] += len(paths)
    summary["calibration_calls"] += run["calibration_calls"]
    preserve = True
    edges = {}
    last_root = frozen_root
    leaf_scores, leaf_exacts = {}, {}
    for position, (path, edge) in enumerate(zip(paths, run["edges"])):
        check(edge["step"] == position and edge["root_before"] == last_root, "broken root continuity")
        check(edge["parent_before"] == (edge["root_before"] if len(path) == 1 else
              edges[(path[0],)]["successor"] if path[1] == 0 else
              edges[(path[0], path[1] - 1)]["parent_after"]), "broken sibling input continuity")
        if len(path) == 1:
            check(edge["parent_after"] == edge["root_after"], "root/parent post-state mismatch")
        last_root = edge["root_after"]
        private = evidence.edges.pop((arm, order, path))
        check(private["rescue_writer"] == run.get("isolated_path"), "intervention marker mismatch")
        check(private["snapshot_ids"] == {k: edge[k] for k in FIELDS}, "private/public snapshot mismatch")
        for name in FIELDS:
            if edge[name] is not None:
                evidence.lookup(edge[name])
        for role in ("parent", "root"):
            pre, post = edge[role + "_before"], edge[role + "_after"]
            changed = differences(evidence.lookup(pre), evidence.lookup(post))
            check(changed == {tuple(p) for p in private[role + "_changed"]}, "incorrect private field differences")
            check(sorted(map(digest, changed)) == sorted(edge[role + "_changed_paths"]), "incorrect public field differences")
            preserve &= pre == post
            summary[arm + "_" + role + "_value_changes"] += bool(changed)
            summary[arm + "_" + role + "_alias_changes"] += pre[1] != post[1]
        for ids in edge["shared_ids"].values():
            check(ids == sorted(set(ids)) and all(type(i) is int and i >= 0 for i in ids), "invalid object IDs")
        if arm == "full_copy" and edge["successor"] is not None:
            summary["full_copy_edges_sharing_mutable_input"] += bool(edge["shared_ids"]["parent_successor"])
        if arm == "wctr":
            delta = edge["runtime_delta"]
            check(delta["calls"] == 1, "incorrect WCTR call delta")
            for k, count in delta.items():
                check(type(count) is int and count >= 0, "invalid runtime counter")
                summary["wctr_" + k] += count
        if edge["successor"] is None:
            check(not complete and position == len(paths) - 1, "missing successful successor")
        elif len(path) == 2:
            leaf = evidence.lookup(edge["successor"])
            leaf_scores[path], leaf_exacts[path] = score(leaf, goal), leaf == goal
            check(edge["goal_fields_equal"] == leaf_scores[path] and edge["exact_goal"] is leaf_exacts[path],
                  "incorrect leaf score or exact-goal flag")
        edges[path] = edge
    if not complete:
        summary["errors_" + arm] += 1
        return Reading(edges, False, preserve, [], [], None, None, [])
    scores = [max(leaf_scores[i, j] for j in range(3)) for i in range(3)]
    children_tied = [[j for j in range(3) if leaf_scores[i, j] == scores[i]] for i in range(3)]
    tied = [i for i in range(3) if scores[i] == max(scores)]
    selected = [tied[0], children_tied[tied[0]][0]]
    exact = leaf_exacts[tuple(selected)]
    check((scores, children_tied, tied, selected) == (run["root_scores"], run["child_ties"],
          run["root_ties"], run["selected"]), "incorrect scores, ties or selected plan")
    check(run["all_root_scores_equal"] is (len(tied) == 3) and run["search_exact_goal"] is exact,
          "incorrect search exact-goal or all-tied flag")
    summary[arm + "_root_ties"] += len(tied) > 1
    summary[arm + "_all_tied"] += len(tied) == 3
    replay_exact, refs = None, []
    if arm != "rescue":
        replay = run["replay"]
        refs = replay["snapshots"]
        for ref in refs:
            evidence.lookup(ref)
        if replay["status"] == "complete":
            check(replay["calls"] == len(refs) == 2, "incorrect independent replay length")
            replay_exact = evidence.lookup(refs[-1]) == goal
            check(replay["exact_goal"] is replay_exact and replay["false_goal"] is (exact and not replay_exact),
                  "incorrect replay exact-goal or false-goal flag")
            summary[arm + "_false_goals"] += exact and not replay_exact
            summary[arm + "_exact_replays"] += replay_exact
        else:
            check(replay["status"] == "replay_error" and replay["calls"] == len(refs) + 1 <= 2,
                  "invalid replay error accounting")
            summary["replay_errors_" + arm] += 1
        summary["replay_calls_" + arm] += replay["calls"]
        expected_path = [edges[(selected[0],)]["successor"], edges[tuple(selected)]["successor"]]
        check(replay["matches_search_path"] is (replay["status"] == "complete" and refs == expected_path),
              "incorrect replay path match flag")
    return Reading(edges, True, preserve, scores, selected, replay_exact, exact, refs)


def same_search(r, ref):
    if not (r.complete and ref.complete):
        return False
    return (r.scores == ref.scores and r.selected == ref.selected and all(
        r.by_path[p][k] == ref.by_path[p][k] for p in ref.by_path for k in ("parent_before", "successor")))


def replay_matches(r, ref):
    if not (r.complete and ref.complete and len(r.replay_refs) == 2):
        return False
    a, b = r.selected
    return r.replay_refs == [ref.by_path[(a,)]["successor"], ref.by_path[(a, b)]["successor"]]


def carried_values(raw, full, evidence):
    edges = list(raw.by_path.items())
    for index, (wp, writer) in enumerate(edges):
        for later_index in range(index + 1, len(edges)):
            rp, reader = edges[later_index]
            if len(rp) == 1 and rp[0] != wp[0]:
                role = "root"
            elif len(wp) == len(rp) == 2 and rp[0] == wp[0]:
                role = "parent"
            else:
                continue
            before = evidence.lookup(writer[role + "_before"])
            after = evidence.lookup(writer[role + "_after"])
            target = evidence.lookup(reader["parent_before"])
            pristine = evidence.lookup(full.by_path[rp]["parent_before"])
            intervening = [evidence.lookup(mid[role + suffix]) for _, mid in edges[index + 1:later_index]
                           for suffix in ("_before", "_after")]
            paths = {p for p in differences(before, after)
                     if at(before, p) == at(pristine, p) and at(after, p) == at(target, p)
                     and all(at(s, p) == at(after, p) for s in intervening)}
            if paths:
                yield wp, rp, role, paths


def audit_rescue(pair, raw, full, order, root, goal, evidence, summary):
    candidates = list(carried_values(raw, full, evidence))
    if not candidates:
        check(pair["rescue"] is None, "rescue has no evidenced carry")
        return "unresolved_no_carried_write"
    reported = evidence.carries.pop(order)
    converted = [(tuple(c["writer"]), tuple(c["reader"]), c["source"], {tuple(p) for p in c["paths"]})
                 for c in reported]
    check(converted == candidates, "incorrect earliest carried write or downstream path")
    writer, reader, source, changed = candidates[0]
    s = pair["rescue"]
    check(s is not None, "missing required intervention")
    check((tuple(s["writer"]), tuple(s["reader"]), s["source"]) == (writer, reader, source) and
          sorted(s["changed_paths"]) == sorted(map(digest, changed)), "wrong intervention target")
    check(tuple(s["run"]["isolated_path"]) == writer, "wrong edge isolated")
    n = len({c[0] for c in candidates})
    check(s["candidate_writer_count"] == n, "incorrect candidate writer count")
    result = audit_run("rescue", s["run"], order, root, goal, evidence, summary)
    for p, e in result.by_path.items():
        if p == writer:
            check(all(e[k] == raw.by_path[p][k] for k in ("root_before", "parent_before")), "different writer inputs")
            check(all(e[r + "_before"] == e[r + "_after"] for r in ("root", "parent")), "rescue edge changed its caller")
            break
        check(all(e[k] == raw.by_path[p][k] for k in FIELDS), "changed search prefix before intervention")
    restored = result.complete and result.by_path[reader]["parent_before"] == full.by_path[reader]["parent_before"]
    decision = result.complete and result.selected[0] == full.selected[0]
    check(s["sibling_restored"] is restored and s["reference_decision_restored"] is decision,
          "incorrect rescue attribution")
    if restored and decision:
        return "verified_single_edge_rescue"
    return "unresolved_multiple_writes" if n > 1 else "unresolved_rescue"


def rank_scores(scores):
    return tuple(sum(other > score for other in scores) for score in scores)


def audit_task(result, meta, source, evidence):
    goal = source["goal"]
    root = [meta["root_sha256"], meta["root_alias_sha256"]]
    check(result["root"] == root and result["goal_sha256"] == digest(goal) == meta["goal_sha256"],
          "task does not use frozen root or goal")
    check(result["candidate_ids"] == meta["branch_action_ids"], "wrong action index order")
    evidence.lookup(root)
    pairs = {tuple(pair["order"]): pair for pair in result["comparisons"]}
    check(len(result["comparisons"]) == len(pairs) == 6 and set(pairs) == set(ORDERS), "missing permutation")
    summary, runs = Counter(), {}
    for order, pair in pairs.items():
        check(set(pair["arms"]) == set(ARMS), "wrong treatment arms")
        runs[order] = {arm: audit_run(arm, pair["arms"][arm], order, root, goal, evidence, summary)
                       for arm in ARMS}
    reference = runs[ORDERS[0]]["full_copy"]
    reference_ok = all(r["full_copy"].preserves and same_search(r["full_copy"], reference)
                       and replay_matches(r["full_copy"], reference) for r in runs.values())
    protected_ok = all(r["wctr"].preserves and same_search(r["wctr"], r["full_copy"])
                       and replay_matches(r["wctr"], r["wctr"]) for r in runs.values())
    check(result["reference_controls_pass"] is reference_ok and result["wctr_controls_pass"] is protected_ok,
          "reported controls disagree with recorded evidence")
    summary["reference_control_failures"] = int(not reference_ok)
    summary["wctr_control_failures"] = int(not protected_ok)
    for order, pair in pairs.items():
        raw, full, wctr = (runs[order][arm] for arm in ("raw", "full_copy", "wctr"))
        check(pair["wctr_preserves"] is wctr.preserves and pair["wctr_agrees"] is same_search(wctr, full),
              "wrong paired WCTR controls")
        if not reference_ok or not raw.complete:
            label = "uninterpretable_reference" if not reference_ok else "raw_transition_error"
            check(all(pair[k] is None for k in ("decision_changed", "raw_score_change", "rescue")),
                  "causal outcome reported for a failed reference or raw trial")
        else:
            # An independent replay of the raw-chosen sequence must reproduce the corresponding
            # Full Copy path even when the two searches chose different plans.
            summary["raw_replay_vs_reference_failures"] += not replay_matches(raw, full)
            chosen = raw.selected[0] != full.selected[0]
            score_changed = raw.scores != full.scores
            changed_leaves = {p for p in raw.by_path if len(p) == 2 and
                              raw.by_path[p]["goal_fields_equal"] != full.by_path[p]["goal_fields_equal"]}
            ranking = rank_scores(raw.scores) != rank_scores(full.scores)
            check(pair["decision_changed"] is chosen and pair["raw_score_change"] is score_changed
                  and pair["ranking_changed"] is ranking and set(map(tuple, pair["leaf_score_changes"])) == changed_leaves,
                  "incorrect paired decision, rank, or score label")
            summary["decision_changes"] += chosen
            summary["root_score_changes"] += score_changed
            summary["any_leaf_score_changes"] += bool(changed_leaves)
            summary["leaf_scores_changed"] += len(changed_leaves)
            summary["rank_changes"] += ranking
            summary["raw_parent_inputs_different_from_reference"] += sum(
                e["parent_before"] != full.by_path[p]["parent_before"] for p, e in raw.by_path.items())
            if chosen:
                label = audit_rescue(pair, raw, full, order, root, goal, evidence, summary)
            else:
                check(pair["rescue"] is None, "unplanned intervention")
                label = "score_only" if score_changed or changed_leaves else "same_decision_and_scores"
        check(pair["classification"] == label, "incorrect causal classification")
        summary[label] += 1
    check(not evidence.edges and not evidence.carries, "unmatched private edge or intervention observations")
    calls = {"search": sum(summary["search_calls_" + arm] for arm in ARMS),
             "initial_calibration": summary["calibration_calls"], "trace_inspection": 0,
             "replay": sum(summary["replay_calls_" + arm] for arm in ARMS), "rescue": summary["search_calls_rescue"]}
    check(calls == result["calls"], "published search/calibration/replay/rescue denominators disagree")
    summary["paired_orders"] = len(pairs)
    return dict(summary)


def verify(bundle, expected_manifest=None):
    manifest_path = bundle / "public/manifest.json"
    manifest_hash = file_digest(manifest_path)
    if expected_manifest is not None:
        check(manifest_hash == expected_manifest, "manifest differs from the prior freeze")
    manifest = read_json(manifest_path)
    check(manifest["phase"] in ("pre-intervention", "public-reproduction-inputs"), "missing frozen protocol")
    hashes = manifest["private_file_sha256"]
    for name in ("private/tasks.pkl", "private/calibration.pkl", "private/manifest.json"):
        check(file_digest(bundle / name) == hashes[name], "frozen private input digest mismatch")
    bank = indexed(manifest["tasks"], "task_id")
    private = indexed(read_json(bundle / "private/manifest.json")["tasks"], "task_id")
    preselected = FAILURES | COMPARISONS
    check(bank.keys() == private.keys() == preselected.keys(), "state bank was changed")
    results_path = bundle / "public/results.json"
    public = read_json(results_path)
    check(public["manifest_sha256"] == manifest_hash and public["runtime_commit"] == manifest["runtime_commit"],
          "results identify a different input manifest or runtime")
    tasks = indexed(public["tasks"], "task_id")
    check(tasks.keys() == bank.keys(), "result task set differs from frozen bank")
    eligible = set()
    for tid, meta in bank.items():
        task, source = tasks[tid], private[tid]
        cohort = "historical_failure" if tid in FAILURES else "comparison"
        check(meta["cohort"] == cohort and (meta["trajectory"], meta["source_step"]) == preselected[tid]
              and (task["trajectory"], task["transition"]) == preselected[tid], "wrong cohort or source triple")
        actions, walk = source["ordered_candidates"], source["goal_walk"]
        chosen = list(dict.fromkeys(actions))[:3]
        check(meta["goal_sha256"] == digest(source["goal"]) and meta["goal_walk_sha256"] == digest(walk)
              and meta["goal_walk_length"] == len(walk) and meta["ordered_candidate_ids"] == list(map(digest, actions))
              and meta["ordered_candidates_sha256"] == digest(actions) and meta["branch_action_ids"] == list(map(digest, chosen)),
              "private frozen goal, walk or action projection mismatch")
        shapes = sorted(sorted(digest(p) for p in group) for group in source["root_alias_path_groups"])
        check(shapes == meta["root_alias_groups"] and digest(shapes) == meta["root_alias_sha256"], "frozen root aliases")
        check(task["candidate_count"] == len(chosen) and meta["eligible"] is (len(chosen) == 3)
              and task["eligible"] is meta["eligible"], "eligibility mismatch")
        if meta["eligible"]:
            eligible.add(tid)
        else:
            check(not task.get("comparisons"), "ineligible task entered intervention")
    check(manifest["selection"]["eligible"] == len(eligible), "frozen eligibility count mismatch")
    per_task, aggregate = {}, Counter()
    edge_file = bundle / "private/edges.jsonl.gz"
    with gzip.open(edge_file, "rt", encoding="utf-8") as stream:
        for tid, private_rows in groupby(map(json.loads, stream), lambda row: row["task_id"]):
            check(tid in eligible and tid not in per_task, "unexpected or repeated private task segment")
            try:
                per_task[tid] = audit_task(tasks[tid], bank[tid], private[tid], PrivateEvidence(private_rows))
            except (ValueError, KeyError, TypeError, IndexError) as error:
                raise ValueError(f"task {tid}: {error}") from error
            aggregate.update(per_task[tid])
    check(set(per_task) == eligible, "missing archived edge observations")
    controls_ok = bool(eligible) and not any(aggregate[k] for k in ("reference_control_failures", "wctr_control_failures",
                          "raw_replay_vs_reference_failures", "errors_raw", "replay_errors_raw", "full_copy_edges_sharing_mutable_input"))
    rescues = [tid for tid, row in per_task.items() if row.get("verified_single_edge_rescue")]
    decision_ids = [tid for tid, row in per_task.items() if row.get("decision_changes")]
    cohorts = {}
    for name, members in (("historical_failure", FAILURES), ("comparison", COMPARISONS)):
        counters = Counter()
        for tid in members.keys() & eligible:
            counters.update(per_task[tid])
        cohorts[name] = {"frozen_tasks": len(members), "eligible_tasks": len(members.keys() & eligible),
                         "task_ids_with_decision_changes": sorted(members.keys() & set(decision_ids)),
                         "task_ids_with_verified_rescues": sorted(members.keys() & set(rescues)), "counts": dict(counters)}
    return {"manifest_sha256": manifest_hash, "runtime_commit": manifest["runtime_commit"],
            "public_results_sha256": file_digest(results_path),
            "private_edge_archive_sha256": file_digest(edge_file), "frozen_tasks": len(bank),
            "eligible_tasks": len(eligible), "ineligible_tasks": sorted(bank.keys() - eligible),
            "independently_recomputed_controls_pass": controls_ok, "tasks_with_changed_root_action": sorted(decision_ids),
            "tasks_with_verified_single_edge_rescue": sorted(rescues), "counts": dict(aggregate),
            "task_counts": per_task, "cohorts": cohorts,
            "limits": "The audit reads recorded snapshots and never executes models. Within-state alias path hashes are checked. Cross-object numeric IDs can be checked for consistency only; saved values cannot prove physical identity across independent objects."}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bundle", type=Path, required=True)
    parser.add_argument("--manifest-sha256", help="expected digest recorded before the search began")
    parser.add_argument("--summary", type=Path, help="write a new public-safe JSON summary")
    args = parser.parse_args()
    summary = verify(args.bundle, args.manifest_sha256)
    if args.summary is not None:
        with args.summary.open("x", encoding="utf-8", newline="\n") as out:
            json.dump(summary, out, sort_keys=True, indent=2)
            out.write("\n")
    print(json.dumps({k: v for k, v in summary.items() if k not in ("task_counts", "cohorts")}, sort_keys=True))


if __name__ == "__main__":
    main()
