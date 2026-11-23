"""Check guarded callbacks and Python match syntax against uninstrumented source."""
import copy
import unittest

from wctr import Adapter, compile_source


def models(source):
    raw = {}
    exec(compile(source, "raw_callbacks.py", "exec"), raw)
    instrumented = compile_source(source, "guarded_callbacks.py")
    return raw["Model"](), Adapter(instrumented["Model"]())


class AstCompatibility(unittest.TestCase):
    def test_recaptured_callback_tracks_receiver_and_restores_on_exception(self):
        source = """from types import SimpleNamespace
class Model:
    def predict_belief(self, state, action):
        hooks = SimpleNamespace(append=state["nested"][0].append)
        more_hooks = SimpleNamespace(update=hooks.append)
        more_hooks.update(1)
        hooks.append(2)
        if action == "fail":
            raise ValueError("after both writes")
        return state
"""
        raw, adapter = models(source)
        events = []
        parent = {"nested": [events], "alias": events}
        for action in ("change", "change", "fail"):
            with self.subTest(action=action):
                if action == "fail":
                    with self.assertRaisesRegex(ValueError, "after both writes"):
                        raw.predict_belief(copy.deepcopy(parent), action)
                    with self.assertRaisesRegex(ValueError, "after both writes"):
                        adapter.transition(parent, action)
                else:
                    expected = raw.predict_belief(copy.deepcopy(parent), action)
                    actual = adapter.transition(parent, action)
                    self.assertEqual(actual, expected)
                    self.assertIs(actual["nested"][0], actual["alias"])
                self.assertIs(parent["nested"][0], events)
                self.assertIs(parent["alias"], events)
                self.assertEqual(events, [])

    def test_class_attribute_preserves_builtin_descriptor_binding(self):
        source = """class Hooks:
    append = list.append
    add = staticmethod(list.append)

class Model:
    def predict_belief(self, state, action):
        try:
            Hooks().append(state["events"], "invalid receiver")
        except TypeError:
            Hooks().add(state["events"], "static")
        Hooks.append(state["events"], "unbound")
        try:
            Hooks.append(42, "wrong type")
        except TypeError:
            state["events"].append("native argument error")
        return state
"""
        raw, adapter = models(source)
        parent = {"events": []}
        expected = raw.predict_belief(copy.deepcopy(parent), "")
        self.assertEqual(adapter.transition(parent, ""), expected)
        self.assertEqual(parent, {"events": []})

    def test_caught_unknown_receiver_still_rejects_the_transition(self):
        source = """from types import SimpleNamespace
class Model:
    def update(self):
        raise AssertionError("custom callback executed")

    def predict_belief(self, state, action):
        hooks = SimpleNamespace(append=self.update)
        state["events"].append("started")
        try:
            hooks.append()
        except TypeError:
            return "would publish an incorrect successor"
"""
        raw, adapter = models(source)
        parent = {"events": []}
        with self.assertRaisesRegex(AssertionError, "custom callback executed"):
            raw.predict_belief(copy.deepcopy(parent), "")
        with self.assertRaisesRegex(TypeError, "receiver"):
            adapter.transition(parent, "")
        self.assertEqual(parent, {"events": []})

    def test_mutator_name_in_value_pattern_with_guard_and_body_writes(self):
        source = """class Action:
    clear = "clear"

class Model:
    def predict_belief(self, state, action):
        match state["queue"].pop():
            case Action.clear if state["guard"].append("tested") is None:
                state["body"].append("matched")
                del state["one"], state["two"]
        return state
"""
        raw, adapter = models(source)
        for item in ("clear", "other"):
            with self.subTest(item=item):
                parent = {"queue": [item], "guard": [], "body": [], "one": 1, "two": 2}
                before = copy.deepcopy(parent)
                expected = raw.predict_belief(copy.deepcopy(parent), "")
                self.assertEqual(adapter.transition(parent, ""), expected)
                self.assertEqual(parent, before)

    def test_mutator_names_as_mapping_key_and_class_pattern(self):
        source = """class Action:
    clear = "value"
    update = str

class Model:
    def predict_belief(self, state, action):
        match state:
            case {Action.clear: Action.update(text)}:
                return text
        return None
"""
        raw, adapter = models(source)
        parent = {"value": "matched"}
        self.assertEqual(adapter.transition(parent, ""), raw.predict_belief(copy.deepcopy(parent), ""))
        self.assertEqual(parent, {"value": "matched"})

    def test_implicit_class_pattern_callback_cannot_escape_journal(self):
        source = """class Model:
    def predict_belief(self, state, action):
        state["started"].append(0)
        match state["events"]:
            case list(append=callback) if callback(1) is None:
                callback(2)
        return state
"""
        raw, adapter = models(source)
        parent = {"events": [], "started": []}
        expected = raw.predict_belief(copy.deepcopy(parent), "")
        self.assertEqual(Adapter(adapter.model, "deepcopy").transition(parent, ""), expected)
        with self.assertRaisesRegex(TypeError, "pattern"):
            adapter.transition(parent, "")
        self.assertEqual(parent, {"events": [], "started": []})
