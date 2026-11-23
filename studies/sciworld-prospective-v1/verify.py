"""Recompute prospective SciWorld endpoints from public edge records, optionally from private snapshots.

The core verifier uses only the Python standard library. Private mode also loads the historical
fixed-work snapshot verifier from the checkout; it does not load a transition model or a pickle.
"""
import argparse
from collections import Counter
import gzip
import hashlib
from itertools import groupby, permutations
import json
from math import comb
from pathlib import Path
import random
import sys


ORDERS = tuple(permutations(range(3)))
ARMS = ("raw", "full_copy", "wctr")
RUNTIME = "4ba67940378b959a07e63426cf4d3d3bdaf93c86"
DATASET = "9342e2cbee1f8579b5423ed5821f6ad8a81ab773"
V1_MANIFEST_HASH = "c269fc2ceefd9afdf4b11ed98e56750016169ef7c456eee5a3100ca776a5ba8a"
METRICS = (
    "parent_value_changed", "input_changed", "leaf_score_changed", "root_score_changed",
    "optimal_set_changed", "ranking_changed", "strict_appeared", "strict_disappeared",
    "strict_winner_identity_changed", "highest_index_changed", "decision_changed",
    "single_edge_rescue", "unresolved_decision", "score_only", "raw_false_goal",
)


def check(ok, message):
    if not ok:
        raise ValueError(message)


def fingerprint(value):
    data = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)
    return hashlib.sha256(data.encode("utf-8")).hexdigest()


def sha(path):
    result = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1048576), b""):
            result.update(chunk)
    return result.hexdigest()


def exact_interval(N, n, x):
    """Invert the two hypergeometric tails for the integer total in the fixed finite frame."""
    check(0 <= x <= n <= N and n > 0, "invalid finite population or endpoint count")
    denom = comb(N, n)

    def accepted(K, upper_tail):
        low, high = max(0, n - (N - K)), min(K, n)
        possible = range(max(x, low), high + 1) if upper_tail else range(low, min(x, high) + 1)
        # Compare to 0.025 exactly, with no floating point cancellation.
        return 40 * sum(comb(K, j) * comb(N - K, n - j) for j in possible) >= denom

    left, right = x, N - n + x
    for lower in (True, False):
        lo, hi = x, N - n + x
        while lo < hi:
            mid = (lo + hi + int(not lower)) // 2
            if accepted(mid, upper_tail=lower):
                if lower:
                    hi = mid
                else:
                    lo = mid
            elif lower:
                lo = mid + 1
            else:
                hi = mid - 1
        if lower:
            left = lo
        else:
            right = lo
    return [left, right]


def edges_in_order(order):
    return [path for a in order for path in ((a,), (a, 0), (a, 1), (a, 2))]


def audit_search(run, arm, order, task, counts):
    expected = edges_in_order(order)
    check(run["arm"] == arm and tuple(run["order"]) == order and run["status"] == "complete",
          "incomplete search/control; retain the failed state and stop endpoint reporting")
    check([tuple(e["path"]) for e in run["edges"]] == expected, "wrong 12-edge schedule")
    check(run["calibration_calls"] == (32 if arm == "wctr" else 0), "calibration calls")
    counts["calibration_calls"] += run["calibration_calls"]
    edges = {}
    last_root = task["root"]
    for i, (p, e) in enumerate(zip(expected, run["edges"])):
        check(e["step"] == i and e["root_before"] == last_root, "root continuity")
        parent = last_root if len(p) == 1 else (edges[p[:1]]["successor"] if p[1] == 0 else edges[p[0], p[1]-1]["parent_after"])
        check(e["parent_before"] == parent and e["successor"] is not None, "parent continuity or missing successor")
        if len(p) == 1:
            check(e["parent_after"] == e["root_after"], "root and parent differ at depth one")
        for role in ("root", "parent"):
            pre, post = e[role + "_before"], e[role + "_after"]
            check(bool(e[role + "_changed_paths"]) == (pre[0] != post[0]), "inconsistent changed paths")
            counts[arm + "_" + role + "_value_changes"] += pre[0] != post[0]
            counts[arm + "_" + role + "_alias_changes"] += pre[1] != post[1]
            if arm in ("full_copy", "wctr"):
                check(pre == post, "reference or WCTR changed parent/root")
        if arm == "wctr":
            delta = e["runtime_delta"]
            check(delta["calls"] == 1 and all(type(v) is int and v >= 0 for v in delta.values()), "runtime accounting")
            for key, value in delta.items():
                counts["wctr_" + key] += value
            counts["wctr_edges_with_full_copy"] += delta["full_clones"] > 0
        if len(p) == 2:
            check(type(e["goal_fields_equal"]) is int and e["goal_fields_equal"] >= 0, "bad leaf score")
            check(e["exact_goal"] is (e["successor"][0] == task["goal_sha256"]), "exact goal digest mismatch")
        last_root = e["root_after"]
        edges[p] = e
    scores, ties = [], []
    for a in range(3):
        leaf = [edges[a, b]["goal_fields_equal"] for b in range(3)]
        scores.append(max(leaf))
        ties.append([b for b, s in enumerate(leaf) if s == max(leaf)])
    best = [i for i, s in enumerate(scores) if s == max(scores)]
    selected = [min(best), min(ties[min(best)])]
    check([run["root_scores"], run["child_ties"], run["root_ties"], run["selected"]]
          == [scores, ties, best, selected], "incorrect leaf aggregation, ties or selected path")
    search_exact = edges[tuple(selected)]["exact_goal"]
    check(run["search_exact_goal"] is search_exact and run["all_root_scores_equal"] is (len(best) == 3), "tie/exact flag")
    counts[arm + "_search_calls"] += len(edges)
    counts[arm + "_tied"] += len(best) > 1
    counts[arm + "_all_tied"] += len(best) == 3
    if arm != "rescue":
        replay = run["replay"]
        check(replay["status"] == "complete" and len(replay["snapshots"]) == replay["calls"] == 2, "failed independent replay")
        exact = replay["snapshots"][-1][0] == task["goal_sha256"]
        check(replay["exact_goal"] is exact and replay["false_goal"] is (search_exact and not exact), "false goal accounting")
        match = replay["snapshots"] == [edges[tuple(selected[:1])]["successor"], edges[tuple(selected)]["successor"]]
        check(replay["matches_search_path"] is match, "incorrect replay path flag")
        counts[arm + "_search_exact"] += search_exact
        counts[arm + "_replay_exact"] += exact
        counts[arm + "_false_goals"] += search_exact and not exact
        counts["replay_calls"] += 2
    return edges


def levels(scores):
    return tuple(sum(x > score for x in scores) for score in scores)


def compare_state(task, frozen):
    check((task["task_id"], task["trajectory"], task["transition"]) ==
          (frozen["task_id"], frozen["trajectory"], frozen["source_step"]), "wrong frozen triple")
    check(task["root"] == [frozen["root_sha256"], frozen["root_alias_sha256"]] and
          task["candidate_ids"] == frozen["branch_action_ids"] and task["goal_sha256"] == frozen["goal_sha256"],
          "frozen root, goal or candidates differ")
    check(task["eligible"] and len(set(task["candidate_ids"])) == task["candidate_count"] == 3, "eligibility mismatch")
    pairs = task["comparisons"]
    check(sorted(tuple(pair["order"]) for pair in pairs) == list(ORDERS), "missing or duplicated paired order")
    order_counts, counts, order_rows, base = Counter(), Counter(), [], None
    for pair in pairs:
        order = tuple(pair["order"])
        arms = pair["arms"]
        check(set(arms) == set(ARMS), "arm membership")
        E = {arm: audit_search(arms[arm], arm, order, task, counts) for arm in ARMS}
        full, raw = arms["full_copy"], arms["raw"]
        ref = E["full_copy"]
        # Freeze a map indexed by action path, independently of the root visitation order.
        projection = lambda edges: {p: (e["parent_before"], e["successor"], e.get("goal_fields_equal")) for p,e in edges.items()}
        path_values = projection(ref)
        if base is None:
            base = path_values
        check(path_values == base and projection(E["wctr"]) == path_values, "reference order instability or WCTR mismatch")
        for arm in ARMS:
            first, second = arms[arm]["selected"]
            check(arms[arm]["replay"]["snapshots"] == [ref[first,]["successor"], ref[first,second]["successor"]],
                  "independent replay disagrees with Full Copy path")
        check(pair["wctr_agrees"] and pair["wctr_preserves"], "reported WCTR control failed")
        score, reference = raw["root_scores"], full["root_scores"]
        best, ref_best = set(raw["root_ties"]), set(full["root_ties"])
        changes = [p for p, e in E["raw"].items() if len(p) == 2 and e["goal_fields_equal"] != ref[p]["goal_fields_equal"]]
        drift = sum(e["parent_before"] != ref[p]["parent_before"] for p, e in E["raw"].items())
        writes = sum(e["parent_before"][0] != e["parent_after"][0] for e in E["raw"].values())
        decision = min(best) != min(ref_best)
        rank = levels(score) != levels(reference)
        check(pair["decision_changed"] is decision and pair["raw_score_change"] is (score != reference)
              and pair["ranking_changed"] is rank and sorted(map(tuple,pair["leaf_score_changes"])) == sorted(changes),
              "reported paired endpoint mismatch")
        rescue = pair["rescue"]
        restored = False
        if rescue is not None:
            check(decision and rescue["changed_paths"] and rescue["candidate_writer_count"] >= 1, "unqualified intervention")
            writer, reader = tuple(rescue["writer"]), tuple(rescue["reader"])
            run = rescue["run"]
            check(tuple(run["isolated_path"]) == writer, "wrong isolation target")
            rescue_edges = audit_search(run, "rescue", order, task, counts)
            raw_edges = E["raw"]
            pos, after = raw_edges[writer]["step"], raw_edges[reader]["step"]
            check(pos < after and raw_edges[reader]["parent_before"] != ref[reader]["parent_before"],
                  "reader is not a later contaminated input")
            check(rescue["source"] in ("parent","root") and
                  set(rescue["changed_paths"]) <= set(raw_edges[writer][rescue["source"]+"_changed_paths"]), "writer field mismatch")
            for path in edges_in_order(order)[:pos]:
                for field in ("root_before","root_after","parent_before","parent_after","successor"):
                    check(rescue_edges[path][field] == raw_edges[path][field], "rescue changed prefix")
            for role in ("root","parent"):
                check(rescue_edges[writer][role+"_before"] == raw_edges[writer][role+"_before"]
                      and rescue_edges[writer][role+"_before"] == rescue_edges[writer][role+"_after"],
                      "isolated writer changed input")
            sibling = rescue_edges[reader]["parent_before"] == ref[reader]["parent_before"]
            first_action = run["selected"][0] == full["selected"][0]
            check(rescue["sibling_restored"] is sibling and rescue["reference_decision_restored"] is first_action,
                  "unsupported rescue claim")
            restored = sibling and first_action
            counts["rescue_trials"] += 1
            counts["sibling_restored"] += sibling
            counts["decision_only_restored"] += first_action and not sibling
            counts["sibling_only_restored"] += sibling and not first_action
            counts["rescued_first_but_not_second"] += restored and run["selected"][1] != full["selected"][1]
        label = pair["classification"]
        if restored:
            expected = "verified_single_edge_rescue"
        elif decision:
            expected = ("unresolved_no_carried_write" if rescue is None else
                        "unresolved_multiple_writes" if rescue["candidate_writer_count"] > 1 else "unresolved_rescue")
        else:
            expected = "score_only" if score != reference or changes else "same_decision_and_scores"
        check(label == expected, "incorrect causal classification")
        counts["class_" + label] += 1
        counts["input_drift_edges"] += drift
        counts["changed_leaf_scores"] += len(changes)
        observed = {
            "parent_value_changed": bool(writes), "input_changed": bool(drift), "leaf_score_changed": bool(changes),
            "root_score_changed": score != reference, "optimal_set_changed": best != ref_best, "ranking_changed": rank,
            "strict_appeared": len(best) == 1 and len(ref_best) > 1,
            "strict_disappeared": len(best) > 1 and len(ref_best) == 1,
            "strict_winner_identity_changed": len(best) == len(ref_best) == 1 and best != ref_best,
            "highest_index_changed": max(best) != max(ref_best), "decision_changed": decision,
            "single_edge_rescue": restored, "unresolved_decision": decision and not restored,
            "score_only": label == "score_only", "raw_false_goal": raw["replay"]["false_goal"],
        }
        order_counts.update(observed)
        order_rows.append({"order": list(order), "class": label, "observed": [k for k in METRICS if observed[k]]})
    check(task["reference_controls_pass"] and task["wctr_controls_pass"], "recorded state controls failed")
    check(task["calls"] == {"search": 3*6*12, "initial_calibration": 32*6, "replay": 3*6*2,
                            "rescue": counts["rescue_search_calls"], "trace_inspection": 0}, "incorrect reported call budget")
    return {"task_id": task["task_id"], "orders_with_endpoint": dict(order_counts),
            "counts": dict(counts), "orders": order_rows}


def validate_frame(m, historical):
    s = m["sampling"]
    frame = m["frame"]
    check(m["runtime_commit"] == RUNTIME and m["dataset_revision"] == DATASET, "unfrozen runtime or dataset")
    check(s["seed"] == 20261123 and s["target_n"] == 64 and s["first_heldout_trajectory"] == 100, "changed sampling rule")
    check(len(frame) == s["frame_size"] and fingerprint(frame) == s["frame_sha256"], "incorrect frame commitment")
    check(m["phase"] == "pre-intervention" and m["fixed_work"] == historical["protocol"] and
          m["initial_calibration"] == historical["initial_calibration"] and
          m["runtime_sha256"] == historical["runtime_sha256"], "changed protocol, calibration or runtime")
    banned_ids = {r["task_id"] for r in historical["tasks"]}
    banned_roots = set(s["excluded_root_sha256"])
    banned_items = set(s["excluded_source_item_sha256"])
    check(all(t["root_sha256"] in banned_roots for t in historical["tasks"]), "missing historical exclusion")
    items = [f["source_item_sha256"] for f in frame]
    check(items == sorted(set(items)), "frame must consist of distinct sorted source items")
    for k in ("task_id", "trajectory", "root_sha256"):
        check(len({f[k] for f in frame}) == len(frame), "duplicate frame " + k)
    for f in frame:
        check(f["trajectory"] >= 100 and f["source_item_sha256"] not in banned_items
              and f["root_sha256"] not in banned_roots and f["task_id"] not in banned_ids,
              "prohibited overlap")
    candidates = dict((f["root_sha256"], f["source_item_sha256"]) for f in frame)
    rejected = m["excluded_representatives"]
    rejected_items = {r["source_item_sha256"] for r in rejected}
    check(len(rejected_items) == len(rejected) and rejected_items.isdisjoint(items)
          and len(frame) + len(rejected) == s["representative_items_before_root_exclusions"], "exclusion accounting")
    reasons = Counter()
    for row in rejected:
        root, item = row["root_sha256"], row["source_item_sha256"]
        check(row["trajectory"] >= 100 and item not in banned_items, "rejected representative eligibility")
        reason = "historical_root" if root in banned_roots else "duplicate_root"
        check(row["reason"] == reason and (reason == "historical_root" or candidates.get(root, item) < item),
              "representative excluded without historical overlap or earlier duplicate")
        reasons[reason] += 1
    excluded = s["excluded_counts"]
    check(all(excluded["items_excluded_" + k] == count for k, count in reasons.items())
          and s["test_trajectories"] == sum(excluded.get(k, 0) for k in ("historical_prefix_trajectories",
              "additional_trajectories_sharing_prohibited_item", "trajectories_with_fewer_than_three_actions",
              "eligible_trajectories_before_representative_selection")), "exclusion totals")
    n = min(64, len(frame))
    draw = random.Random(20261123).sample(frame, n)
    check(len(m["tasks"]) == s["sample_size"] == n and m["tasks"], "wrong sealed bank size")
    for wanted, task in zip(draw, m["tasks"]):
        for key in ("task_id", "trajectory", "source_step", "source_item_sha256", "root_sha256",
                    "ordered_candidates_sha256", "goal_walk_sha256"):
            check(wanted[key] == task[key], "wrong public draw or task digest: " + key)


def read_results(public):
    path = public / "results.json"
    if path.is_file():
        with path.open("rb") as f:
            data = f.read()
    else:
        with gzip.open(public / "results.json.gz", "rb") as f:
            data = f.read()
    return json.loads(data), hashlib.sha256(data).hexdigest()


def summarize(tasks, rows):
    order_counts, state_counts, counts = Counter(), Counter(), Counter()
    for row in rows:
        order_counts.update(row["orders_with_endpoint"])
        state_counts.update({k: v > 0 for k, v in row["orders_with_endpoint"].items()})
        counts.update(row["counts"])
    primary_ids = [r["task_id"] for r in rows if r["orders_with_endpoint"]["decision_changed"]]
    rescued_ids = [r["task_id"] for r in rows if r["orders_with_endpoint"]["single_edge_rescue"]]
    return {
        "n_states": len(tasks), "n_paired_orders": 6 * len(tasks), "n_leaves_per_arm": 54 * len(tasks),
        "n_edges_per_arm": 72 * len(tasks), "tasks_with_decision_change": primary_ids,
        "tasks_with_verified_rescue": rescued_ids, "states_with_endpoint": dict(state_counts),
        "orders_with_endpoint": dict(order_counts), "counts": dict(counts), "states": rows,
    }


def private_checks(bundle, manifest, records, rows, historical_folder):
    sys.path.insert(0, str(historical_folder))
    import sciworld_verify as v1
    for name in ("private/tasks.pkl", "private/calibration.pkl", "private/manifest.json"):
        check(sha(bundle / name) == manifest["private_file_sha256"][name], "private setup digest mismatch")
    sources = v1.indexed(v1.read_json(bundle / "private/manifest.json")["tasks"], "task_id")
    material = bundle / "private/edges.jsonl.gz"
    private_sums, seen = Counter(), []
    with gzip.open(material, "rt", encoding="utf-8") as stream:
        grouped = groupby(map(json.loads, stream), lambda r: r["task_id"])
        for i, (tid, private_rows) in enumerate(grouped):
            check(i < len(rows) and tid == rows[i]["task_id"], "private trace stream out of order")
            t, r, frozen = records[i], rows[i], manifest["tasks"][i]
            source = sources[tid]
            check(fingerprint(source["ordered_candidates"]) == frozen["ordered_candidates_sha256"] and
                  fingerprint(source["goal_walk"]) == frozen["goal_walk_sha256"] and
                  list(map(fingerprint,list(dict.fromkeys(source["ordered_candidates"]))[:3])) == frozen["branch_action_ids"],
                  "private candidate, branch order or goal-walk digest mismatch")
            groups = sorted(sorted(fingerprint(path) for path in group) for group in source["root_alias_path_groups"])
            check(groups == frozen["root_alias_groups"] and fingerprint(groups) == frozen["root_alias_sha256"],
                  "private root alias topology differs")
            raw = v1.audit_task(t, frozen, source, v1.PrivateEvidence(private_rows))
            check(all(raw.get(k, 0) == 0 for k in ("reference_control_failures","wctr_control_failures",
                      "raw_replay_vs_reference_failures")), "private controls failed")
            comparisons = (("raw_parent_inputs_different_from_reference", r["counts"]["input_drift_edges"]),
                           ("leaf_scores_changed", r["counts"]["changed_leaf_scores"]),
                           ("decision_changes", r["orders_with_endpoint"]["decision_changed"]),
                           ("verified_single_edge_rescue", r["orders_with_endpoint"]["single_edge_rescue"]),
                           ("rank_changes", r["orders_with_endpoint"]["ranking_changed"]))
            for k, expected in comparisons:
                check(raw.get(k, 0) == expected, "private/public endpoint mismatch " + k)
            private_sums.update(raw)
            seen.append(tid)
    check(seen == [t["task_id"] for t in records] and set(seen) == sources.keys(), "incomplete private evidence")
    return {"private_edges_sha256": sha(material), "n_snapshot_verified_states": len(seen),
            "private_recomputed_counts": dict(private_sums),
            "verified": ["canonical values and internal alias digests", "all 12 edge inputs and successors",
                         "leaf scoring, root and child ties, independent replay", "fixed-work comparator stability",
                         "earliest continuously carried change and single-edge intervention prefix and outcome"],
            "limitation": "Cross-object numeric IDs record runtime identities. Saved canonical values allow a consistency check, not independent recovery of process memory addresses."}


def case_study(folder):
    p = folder / "public"
    m = json.loads((p / "manifest.json").read_bytes())
    r, rh = read_results(p)
    v = json.loads((p / "verification.json").read_bytes())
    check(sha(p / "manifest.json") == r["manifest_sha256"] == v["manifest_sha256"] == V1_MANIFEST_HASH,
          "original manifest mismatch")
    check(rh == v["public_results_sha256"] and r["runtime_commit"] == m["runtime_commit"] == RUNTIME, "original results mismatch")
    check(len(m["tasks"]) == len(r["tasks"]) == 11 and {t["task_id"] for t in m["tasks"]} ==
          {364,374,476,863,925,1560,1963,1975,2166,390,465}, "case bank")
    rows = [compare_state(t, f) for t,f in zip(r["tasks"], m["tasks"])]
    summary = summarize(r["tasks"], rows)
    c = summary["counts"]
    expected = {"raw_parent_value_changes":54, "input_drift_edges":328, "raw_false_goals":18,
                "wctr_edges_with_full_copy":792, "sibling_restored":6, "sibling_only_restored":4,
                "rescued_first_but_not_second":2, "full_copy_false_goals":0, "wctr_false_goals":0}
    check(all(c.get(k,0) == value for k,value in expected.items()), "case published result mismatch")
    check(all(c[arm + "_search_calls"] == 792 for arm in ARMS) and summary["tasks_with_decision_change"] == [1975]
          and summary["orders_with_endpoint"]["decision_changed"] == 6
          and summary["orders_with_endpoint"]["single_edge_rescue"] == 2, "case primary or rescue denominator")
    return {"manifest_sha256": V1_MANIFEST_HASH, "n_states": 11, "paired_orders": 66, "search_calls": 2376,
            **expected, "decision_change_orders":6, "verified_rescue_orders":2, "task_id":1975}


def write_new(path, data):
    with path.open("x", encoding="utf-8", newline="\n") as out:
        json.dump(data, out, sort_keys=True, indent=2)
        out.write("\n")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", required=True, type=Path)
    parser.add_argument("--bundle", type=Path)
    parser.add_argument("--manifest-sha256")
    parser.add_argument("--private", action="store_true")
    parser.add_argument("--case-study", action="store_true")
    parser.add_argument("--write-summary", type=Path)
    parser.add_argument("--write-verification", type=Path)
    args = parser.parse_args()
    original = args.repo.resolve() / "studies/sciworld-fixed-work-v1"
    if args.case_study:
        print(json.dumps(case_study(original), sort_keys=True))
        return
    if not args.bundle or args.write_verification and not args.private:
        parser.error("provide --bundle; writing a verification record requires --private")
    p = args.bundle / "public"
    seal = sha(p / "manifest.json")
    if args.manifest_sha256:
        check(seal == args.manifest_sha256, "pre-execution manifest seal mismatch")
    m = json.loads((p / "manifest.json").read_bytes())
    check(sha(original / "public/manifest.json") == V1_MANIFEST_HASH, "historical manifest mismatch")
    v1 = json.loads((original / "public/manifest.json").read_bytes())
    validate_frame(m, v1)
    data, result_hash = read_results(p)
    check(data["manifest_sha256"] == seal and data["runtime_commit"] == m["runtime_commit"], "result not bound to this study")
    records = data["tasks"]
    check(len(records) == len(m["tasks"]), "missing or extra result states")
    rows = [compare_state(t, f) for t, f in zip(records, m["tasks"])]
    summary = summarize(records, rows)
    n, N = len(records), len(m["frame"])
    x = len(summary["tasks_with_decision_change"])
    ci = exact_interval(N, n, x)
    summary.update(manifest_sha256=seal, results_sha256=result_hash, frame_size=N, primary={
        "numerator": x, "denominator": n, "observed_fraction": x/n, "finite_frame_95pct_count_interval": ci,
        "finite_frame_95pct_fraction_interval": [k/N for k in ci], "method": "equal-tailed exact hypergeometric inversion",
        "estimand": "fraction of sealed eligible item representatives with at least one lowest-index root flip across six orders"})
    if (p / "analysis.json").is_file():
        check(summary == json.loads((p / "analysis.json").read_bytes()), "reported analysis differs from recomputation")
    if (p / "verification.json").is_file():
        saved = json.loads((p / "verification.json").read_bytes())
        check(saved["manifest_sha256"] == seal and saved["results_sha256"] == result_hash
              and saved["public_analysis_fingerprint"] == fingerprint(summary),
              "retained private verification does not identify this public analysis")
    if args.private:
        info = private_checks(args.bundle, m, records, rows, original)
        info.update(manifest_sha256=seal, results_sha256=result_hash, public_analysis_fingerprint=fingerprint(summary))
        if (p / "verification.json").is_file():
            check(info == json.loads((p / "verification.json").read_bytes()), "private trace audit changed")
        if args.write_verification:
            write_new(args.write_verification, info)
    if args.write_summary:
        write_new(args.write_summary, summary)
    print(json.dumps({k:v for k,v in summary.items() if k not in ("states",)}, sort_keys=True))


if __name__ == "__main__":
    main()
