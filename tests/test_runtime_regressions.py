"""Regression cases comparing the public adapter to the uninstrumented model."""
import copy
import unittest
from collections import defaultdict

from wctr import Adapter, compile_source


def models(source):
    namespace = {}
    exec(compile(source, "raw_fixture.py", "exec"), namespace)
    raw = namespace["Model"]()
    instrumented = compile_source(source, "wctr_fixture.py")["Model"]()
    return raw, Adapter(instrumented, "wctr")


class RuntimeRegressions(unittest.TestCase):
    def check_list_mutation(self, mutation):
        source = f"""class Model:
    def copy(self, value):
        return value

    def predict_belief(self, state, action):
        {mutation}
        if action == "fail":
            raise ValueError("after write")
        return state
"""
        for action in ("change", "fail"):
            with self.subTest(action=action):
                raw, adapter = models(source)
                events = []
                parent = {"events": events, "also_events": events}
                before = copy.deepcopy(parent)
                if action == "fail":
                    with self.assertRaisesRegex(ValueError, "after write"):
                        raw.predict_belief(copy.deepcopy(parent), action)
                    with self.assertRaisesRegex(ValueError, "after write"):
                        adapter.transition(parent, action)
                else:
                    expected = raw.predict_belief(copy.deepcopy(parent), action)
                    actual = adapter.transition(parent, action)
                    self.assertEqual(actual, expected)
                    self.assertIs(actual["events"], actual["also_events"])
                self.assertEqual(parent, before)
                self.assertIs(parent["events"], events)
                self.assertIs(parent["also_events"], events)

    def test_unbound_list_append(self):
        self.check_list_mutation("list.append(state['events'], 1)")

    def test_unbound_list_append_with_class_alias(self):
        self.check_list_mutation("kind = list\n        kind.append(state['events'], 1)")

    def test_captured_builtin_mutators(self):
        for mutation in (
            "callback = state['events'].append\n        callback(1)",
            "callback = list.append\n        callback(state['events'], 1)",
        ):
            with self.subTest(mutation=mutation):
                self.check_list_mutation(mutation)

    def test_unknown_mutator_is_rejected_before_invocation(self):
        source = """class Model:
    def append(self, events):
        raise AssertionError("custom mutator was invoked")

    def predict_belief(self, state, action):
        state["events"].append("started")
        self.append(state["events"])
        return state
"""
        raw, adapter = models(source)
        parent = {"events": []}
        with self.assertRaisesRegex(AssertionError, "custom mutator was invoked"):
            raw.predict_belief(copy.deepcopy(parent), "change")
        with self.assertRaisesRegex(TypeError, "receiver"):
            adapter.transition(parent, "change")
        self.assertEqual(parent, {"events": []})

    def test_model_copy_returning_input_list(self):
        self.check_list_mutation("self.copy(state['events']).append(1)")

    def test_shadowed_list_constructor_returning_input(self):
        self.check_list_mutation("list = self.copy\n        list(state['events']).append(1)")

    def test_order_sensitive_set_pop(self):
        source = """class Model:
    def predict_belief(self, state, action):
        state["events"].append("started")
        picked = state["members"].pop()
        if action == "fail":
            raise ValueError("after pop")
        return {"picked": picked, "remaining": state["members"]}
"""
        for action in ("pick", "fail"):
            with self.subTest(action=action):
                raw, adapter = models(source)
                members = set(range(3))
                # The reference deep copy can reset the original iteration history.
                previous = members.pop()
                members.add(previous)
                parent = {"members": members, "events": []}
                before = copy.deepcopy(parent)
                if action == "fail":
                    with self.assertRaisesRegex(ValueError, "after pop"):
                        raw.predict_belief(copy.deepcopy(parent), action)
                    with self.assertRaisesRegex(ValueError, "after pop"):
                        adapter.transition(parent, action)
                else:
                    expected = raw.predict_belief(copy.deepcopy(parent), action)
                    actual = adapter.transition(parent, action)
                    self.assertEqual(actual, expected)
                self.assertEqual(parent, before)
                self.assertIs(parent["members"], members)

    def test_reachable_set_or_defaultdict_selects_fallback_before_execution(self):
        source = """class Model:
    def __init__(self):
        self.invocations = 0

    def init_belief(self):
        return {}

    def predict_belief(self, state, action):
        self.invocations += 1
        leaf = state["nested"][0]["leaf"]
        state["observed"] = leaf.pop() if action == "set" else leaf["new"]
        return state
"""
        for action, leaf in (("set", {0, 1, 2}), ("mapping", defaultdict(int))):
            with self.subTest(action=action):
                raw, adapter = models(source)
                fallback = type(raw)()
                adapter.model._wctr_raw_model = fallback
                shared = {"leaf": leaf}
                parent = {"nested": [shared], "also_nested": (shared,)}
                before = copy.deepcopy(parent)
                expected = raw.predict_belief(copy.deepcopy(parent), action)
                output = adapter.transition(parent, action)
                self.assertEqual(output, expected)
                self.assertEqual(parent, before)
                self.assertIs(output["nested"][0], output["also_nested"][0])
                self.assertIsNot(output["nested"][0], shared)
                self.assertIs(parent["also_nested"][0], shared)
                self.assertEqual(adapter.model.invocations, 0)
                self.assertEqual(fallback.invocations, 1)
                self.assertEqual(adapter.full_clones, 1)

    def test_ordinary_selective_fork_counts_no_full_copy(self):
        source = """class Model:
    def predict_belief(self, state, action):
        state["changed"].append(1)
        return state
"""
        raw, adapter = models(source)
        parent = {"changed": [], "untouched": []}
        adapter.calibrate([(parent, "append")])
        expected = raw.predict_belief(copy.deepcopy(parent), "append")
        output = adapter.transition(parent, "append")
        self.assertEqual(output, expected)
        self.assertEqual(parent, {"changed": [], "untouched": []})
        self.assertIs(output["untouched"], parent["untouched"])
        self.assertEqual(adapter.deopts, 0)
        self.assertGreater(adapter.copied, 0)
        self.assertEqual(adapter.full_clones, 0)

    def test_tuple_cycle_fallback_counts_full_copy(self):
        source = """class Model:
    def predict_belief(self, state, action):
        state["ring"][0].append(9)
        return state
"""
        for calibrate in (False, True):
            with self.subTest(calibrate=calibrate):
                raw, adapter = models(source)
                items = []
                ring = (items,)
                items.append(ring)
                parent = {"ring": ring}
                if calibrate:
                    adapter.calibrate([(parent, "append")])
                expected = raw.predict_belief(copy.deepcopy(parent), "append")
                output = adapter.transition(parent, "append")
                # Compare the value payload and back-edges separately. Recursive
                # equality of two independently constructed cycles is undefined.
                self.assertIs(parent["ring"], ring)
                self.assertIs(ring[0], items)
                self.assertEqual(len(items), 1)
                self.assertIs(items[0], ring)
                self.assertIs(expected["ring"][0][0], expected["ring"])
                self.assertIs(output["ring"][0][0], output["ring"])
                self.assertEqual(output["ring"][0][1:], expected["ring"][0][1:])
                self.assertIsNot(output["ring"][0], items)
                self.assertEqual(adapter.full_clones, 1)
