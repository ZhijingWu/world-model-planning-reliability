"""Fixed 12-edge SciWorld protocol. Importing this module does not run models."""
import copy
from itertools import permutations

from sciworld_prepare import alias_groups, digest, shared_paths


ORDERS = tuple(permutations(range(3)))
MISSING = object()


def _children(node):
    # The supplied Stage 2 canonical() returns tagged tuples. A set is one
    # field for path differences; its complete sorted canonical value is saved.
    if isinstance(node, tuple) and len(node) == 2:
        if node[0] == "dict":
            return dict(node[1])
        if node[0] in ("list", "tuple"):
            return dict(enumerate(node[1]))
    return None


def changed_paths(before, after, path=()):
    if before == after:
        return []
    left, right = _children(before), _children(after)
    if left is None or right is None or before[0] != after[0]:
        return [path]
    changes = []
    for key in sorted(left.keys() | right.keys()):
        changes.extend(changed_paths(left.get(key, MISSING), right.get(key, MISSING), path + (key,)))
    return changes


def _at(value, path):
    for key in path:
        mapping = _children(value)
        if mapping is None:
            return MISSING
        value = mapping.get(key, MISSING)
    return value


class Snapshots:
    """Immutable values and shape digests; full data goes only to the private sink."""
    def __init__(self, canonical, task_id, sink):
        self.canonical = canonical
        self.task_id = task_id
        self.sink = sink
        self.values = {}
        self.shapes = set()

    def capture(self, state):
        value = self.canonical(state)
        value_key = digest(value)
        shape = alias_groups(state)
        shape_key = digest(shape)
        if value_key not in self.values:
            self.values[value_key] = value
            self.sink({"type": "canonical_snapshot", "task_id": self.task_id,
                       "sha256": value_key, "canonical": value})
        if shape_key not in self.shapes:
            self.shapes.add(shape_key)
            self.sink({"type": "shared_paths", "task_id": self.task_id,
                       "sha256": shape_key, "groups": shape, "paths": shared_paths(state)})
        return [value_key, shape_key]

    def delta(self, before, after):
        return changed_paths(self.values[before[0]], self.values[after[0]])


class ObjectIds:
    """Assign stable opaque IDs to mutable containers for the life of one search."""
    def __init__(self):
        self.index = {}

    def reachable(self, root):
        seen, result = set(), set()
        stack = [root]
        while stack:
            value = stack.pop()
            if type(value) not in (dict, list, set, tuple) or id(value) in seen:
                continue
            seen.add(id(value))
            if type(value) is not tuple:
                if id(value) not in self.index:
                    # A strong reference prevents address reuse during this search.
                    self.index[id(value)] = (len(self.index), value)
                result.add(self.index[id(value)][0])
            if type(value) is dict:
                stack.extend(value[key] for key in reversed(sorted(value, key=str)))
            elif type(value) in (list, tuple):
                stack.extend(reversed(value))
        return result


def _score(canonical_leaf, goal):
    if canonical_leaf[0] != "dict" or goal[0] != "dict":
        raise ValueError("The frozen top-level goal-field score requires dictionaries")
    leaf = dict(canonical_leaf[1])
    return sum(leaf.get(key, MISSING) == value for key, value in goal[1])


def _stats(adapter):
    return {"calls": adapter.calls, "full_clones": adapter.full_clones,
            "deoptimizations": adapter.deopts, "sites": adapter.sites,
            "copied_containers": adapter.copied,
            "witness_paths": sum(map(len, adapter.frontiers.values()))}


def _replay(task, actions, selected, snapshots, raw_factory, search_exact):
    model = raw_factory()
    state = copy.deepcopy(task["state"])
    visited = []
    for index in selected:
        try:
            state = model.predict_belief(copy.deepcopy(state), actions[index])
        except Exception as error:
            return {"status": "replay_error", "exception_type": type(error).__name__,
                    "calls": len(visited) + 1, "snapshots": visited, "exact_goal": None,
                    "false_goal": None}
        visited.append(snapshots.capture(state))
    exact = snapshots.values[visited[-1][0]] == task["goal"]
    return {"status": "complete", "calls": len(visited), "snapshots": visited,
            "exact_goal": exact, "false_goal": search_exact and not exact}


def _run(task, actions, arm, order, snapshots, raw_factory, wctr_factory, calibration, rescue=None):
    root = copy.deepcopy(task["state"])
    adapter = None
    result = {"arm": arm, "order": list(order), "status": "complete", "edges": [],
              "calibration_calls": 0, "initial_witness_paths": None}
    if arm == "wctr":
        adapter = wctr_factory()
        def observe_calibration():
            for example in calibration:
                result["calibration_calls"] += 1
                yield example
        try:
            adapter.calibrate(observe_calibration())
        except Exception as error:
            result.update(status="calibration_error", exception_type=type(error).__name__)
            return result
        result["initial_witness_paths"] = _stats(adapter)["witness_paths"]
        model = None
    else:
        model = raw_factory()
    objects = ObjectIds()
    if rescue is not None:
        result["isolated_path"] = list(rescue)

    def step(parent, path):
        action = actions[path[-1]]
        root_before = snapshots.capture(root)
        parent_before = root_before if parent is root else snapshots.capture(parent)
        root_ids_before = objects.reachable(root)
        parent_ids_before = root_ids_before if parent is root else objects.reachable(parent)
        before = _stats(adapter) if adapter is not None else {}
        error_type = None
        try:
            if adapter is not None:
                successor = adapter.transition(parent, action)
            else:
                isolate = arm == "full_copy" or path == rescue
                successor = model.predict_belief(copy.deepcopy(parent) if isolate else parent, action)
        except Exception as error:
            error_type = type(error).__name__
            successor = None
        root_after = snapshots.capture(root)
        parent_after = root_after if parent is root else snapshots.capture(parent)
        root_changes = snapshots.delta(root_before, root_after)
        parent_changes = snapshots.delta(parent_before, parent_after)
        root_ids_after = objects.reachable(root)
        parent_ids_after = root_ids_after if parent is root else objects.reachable(parent)
        successor_ids = objects.reachable(successor)
        edge = {"step": len(result["edges"]), "path": list(path),
                "root_before": root_before, "root_after": root_after,
                "parent_before": parent_before, "parent_after": parent_after,
                "successor": snapshots.capture(successor) if error_type is None else None,
                "root_changed_paths": [digest(p) for p in root_changes],
                "parent_changed_paths": [digest(p) for p in parent_changes],
                "shared_ids": {"root_parent_before": sorted(root_ids_before & parent_ids_before),
                               "root_parent_after": sorted(root_ids_after & parent_ids_after),
                               "root_successor": sorted(root_ids_after & successor_ids),
                               "parent_successor": sorted(parent_ids_after & successor_ids)}}
        if adapter is not None:
            edge["runtime_delta"] = {k: value - before[k] for k, value in _stats(adapter).items()}
        snapshots.sink({"type": "edge_paths", "task_id": task["task_id"], "arm": arm,
                        "order": order, "path": path, "rescue_writer": rescue,
                        "root_changed": root_changes, "parent_changed": parent_changes,
                        "snapshot_ids": {k: edge[k] for k in ("root_before", "root_after",
                            "parent_before", "parent_after", "successor")}})
        result["edges"].append(edge)
        if error_type is not None:
            result.update(status="transition_error", exception_type=error_type, failed_path=list(path))
        elif len(path) == 2:
            leaf = snapshots.values[edge["successor"][0]]
            edge["goal_fields_equal"] = _score(leaf, task["goal"])
            edge["exact_goal"] = leaf == task["goal"]
        return successor

    leaf_by_path = {}
    for first in order:
        # Child calls reuse precisely this first-level object, including any
        # changes the preceding raw child made to it or to the root.
        child_parent = step(root, (first,))
        if result["status"] != "complete":
            return result
        for child in range(3):
            step(child_parent, (first, child))
            if result["status"] != "complete":
                return result
            leaf_by_path[(first, child)] = result["edges"][-1]
    if len(result["edges"]) != 12:
        raise RuntimeError("Incorrect fixed search work")
    scores, winners = [], []
    for first in range(3):
        child_scores = [leaf_by_path[first, j]["goal_fields_equal"] for j in range(3)]
        scores.append(max(child_scores))
        winners.append([j for j, value in enumerate(child_scores) if value == scores[-1]])
    tied = [i for i, value in enumerate(scores) if value == max(scores)]
    selected = [tied[0], winners[tied[0]][0]]
    result.update(root_scores=scores, child_ties=winners, root_ties=tied, selected=selected,
                  all_root_scores_equal=len(tied) == 3,
                  search_exact_goal=leaf_by_path[tuple(selected)]["exact_goal"])
    if arm != "rescue":
        result["replay"] = _replay(task, actions, selected, snapshots, raw_factory,
                                   result["search_exact_goal"])
        result["replay"]["matches_search_path"] = (
            result["replay"]["status"] == "complete" and result["replay"]["snapshots"] ==
            [_by_path(result)[(selected[0],)]["successor"], leaf_by_path[tuple(selected)]["successor"]])
    return result


def _by_path(run):
    return {tuple(edge["path"]): edge for edge in run["edges"]}


def _preserves(run):
    return all(edge["parent_before"] == edge["parent_after"] and edge["root_before"] == edge["root_after"]
               for edge in run["edges"])


def _agrees(run, reference):
    if run["status"] != "complete" or reference["status"] != "complete":
        return False
    expected = _by_path(reference)
    fields = ("parent_before", "successor", "goal_fields_equal", "exact_goal")
    return (all(all(edge.get(key) == expected[path].get(key) for key in fields)
                for path, edge in _by_path(run).items())
            and all(run[k] == reference[k] for k in ("root_scores", "child_ties", "root_ties", "selected")))


def _carry(edges, reference, snapshots):
    """All earliest-to-latest writer/reader pairs with an observed carried value."""
    for writer in edges:
        source_path = writer["path"]
        for reader in edges[writer["step"] + 1:]:
            reader_path = reader["path"]
            if len(reader_path) == 1 and reader_path[0] != source_path[0]:
                source = "root"
            elif len(source_path) == len(reader_path) == 2 and source_path[0] == reader_path[0]:
                source = "parent"
            else:
                continue
            before = snapshots.values[writer[source + "_before"][0]]
            after = snapshots.values[writer[source + "_after"][0]]
            expected = snapshots.values[reference[tuple(reader_path)]["parent_before"][0]]
            actual = snapshots.values[reader["parent_before"][0]]
            between = edges[writer["step"] + 1:reader["step"]]
            retained = [snapshots.values[mid[source + suffix][0]]
                        for mid in between for suffix in ("_before", "_after")]
            carried = [p for p in changed_paths(before, after)
                       if _at(before, p) == _at(expected, p) and _at(after, p) == _at(actual, p)
                       and all(_at(mid, p) == _at(after, p) for mid in retained)]
            if carried:
                yield {"writer": source_path, "reader": reader_path, "source": source,
                       "paths": carried}


def _paired(task, actions, order, raw, full, wctr, controls_ok, snapshots, factories, calibration):
    pair = {"order": list(order), "arms": {"raw": raw, "full_copy": full, "wctr": wctr},
            "wctr_preserves": _preserves(wctr), "wctr_agrees": _agrees(wctr, full),
            "decision_changed": None, "raw_score_change": None, "rescue": None}
    if not controls_ok or raw["status"] != "complete":
        pair["classification"] = "uninterpretable_reference" if not controls_ok else "raw_transition_error"
        return pair
    pair["decision_changed"] = raw["selected"][0] != full["selected"][0]
    pair["raw_score_change"] = raw["root_scores"] != full["root_scores"]
    ref = _by_path(full)
    raw_paths = _by_path(raw)
    pair["leaf_score_changes"] = [list(p) for p, edge in raw_paths.items()
                                  if len(p) == 2 and edge["goal_fields_equal"] != ref[p]["goal_fields_equal"]]
    def ranking(scores):
        return [[i for i, entry in enumerate(scores) if entry == value]
                for value in sorted(set(scores), reverse=True)]
    pair["ranking_changed"] = ranking(raw["root_scores"]) != ranking(full["root_scores"])
    if not pair["decision_changed"]:
        pair["classification"] = ("score_only" if pair["raw_score_change"] or pair["leaf_score_changes"]
                                  else "same_decision_and_scores")
        return pair
    carried = list(_carry(raw["edges"], ref, snapshots))
    if not carried:
        pair["classification"] = "unresolved_no_carried_write"
        return pair
    first = carried[0]
    source_path = tuple(first["writer"])
    reader_path = tuple(first["reader"])
    snapshots.sink({"type": "carry_candidates", "task_id": task["task_id"],
                    "order": order, "candidates": carried})
    rescue = _run(task, actions, "rescue", order, snapshots, *factories, calibration, rescue=source_path)
    restored = (rescue["status"] == "complete"
                and _by_path(rescue)[reader_path]["parent_before"] == ref[reader_path]["parent_before"])
    decision = rescue["status"] == "complete" and rescue["selected"][0] == full["selected"][0]
    writers = {tuple(c["writer"]) for c in carried}
    pair["rescue"] = {"writer": list(source_path), "reader": list(reader_path), "source": first["source"],
                      "changed_paths": [digest(p) for p in first["paths"]],
                      "candidate_writer_count": len(writers), "sibling_restored": restored,
                      "reference_decision_restored": decision, "run": rescue}
    if restored and decision:
        pair["classification"] = "verified_single_edge_rescue"
    elif len(writers) > 1:
        pair["classification"] = "unresolved_multiple_writes"
    else:
        pair["classification"] = "unresolved_rescue"
    return pair


def evaluate_task(task, *, canonical, raw_factory, wctr_factory, calibration, private_sink):
    """Return an index-and-hash-only public record; send raw canonical values only to private_sink."""
    actions = list(dict.fromkeys(task["actions"]))[:3]
    public = {"task_id": task["task_id"], "trajectory": task["trajectory"], "transition": task["step"],
              "candidate_count": len(actions), "eligible": len(actions) == 3}
    if len(actions) < 3:
        return public
    if len(calibration) != 32:
        raise ValueError("The frozen study requires exactly 32 training transitions")
    snapshots = Snapshots(canonical, task["task_id"], private_sink)
    public.update(root=snapshots.capture(task["state"]), goal_sha256=digest(task["goal"]),
                  candidate_ids=[digest(action) for action in actions])
    factories = (raw_factory, wctr_factory)
    def run(arm, order):
        return _run(task, actions, arm, order, snapshots, *factories, calibration)
    references = [run("full_copy", order) for order in ORDERS]
    controls_ok = all(_preserves(r) and _agrees(r, references[0])
                      and r["replay"]["matches_search_path"] and not r["replay"]["false_goal"]
                      and r["search_exact_goal"] == r["replay"]["exact_goal"] for r in references)
    protected = [run("wctr", order) for order in ORDERS]
    comparisons = [_paired(task, actions, order, run("raw", order), full, wctr, controls_ok,
                           snapshots, factories, calibration)
                   for order, full, wctr in zip(ORDERS, references, protected)]
    public.update(reference_controls_pass=controls_ok,
                  wctr_controls_pass=all(p["wctr_preserves"] and p["wctr_agrees"]
                                         and p["arms"]["wctr"]["replay"]["matches_search_path"]
                                         for p in comparisons), comparisons=comparisons)
    searches = [arm for pairing in comparisons for arm in pairing["arms"].values()]
    public["calls"] = {"search": sum(len(arm["edges"]) for arm in searches),
                       "initial_calibration": sum(arm["calibration_calls"] for arm in searches),
                       "replay": sum(arm.get("replay", {}).get("calls", 0) for arm in searches),
                       "rescue": sum(len(p["rescue"]["run"]["edges"]) for p in comparisons if p["rescue"]),
                       "trace_inspection": 0}
    return public
