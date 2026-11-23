"""Regression cases comparing the public adapter to the uninstrumented model."""
import copy
import unittest

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
