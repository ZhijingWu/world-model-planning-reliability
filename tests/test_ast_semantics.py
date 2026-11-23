"""Compare the public transition API with independently compiled Python."""
import copy
import unittest

from wctr import Adapter, compile_source


def models(source):
    original = {}
    exec(compile(source, "native_fixture.py", "exec"), original)
    instrumented = compile_source(source, "wctr_fixture.py")
    return original["Model"](), Adapter(instrumented["Model"]())


def observe(call, state, action):
    try:
        return call(state, action), None
    except Exception as exc:
        return None, (type(exc), exc.args)


class ReleaseBlockers(unittest.TestCase):
    def compare_write(self, statements):
        source = f"""class Model:
    def predict_belief(self, state, action):
        {statements}
        if action == "fail":
            raise ValueError("after write", state["count"], tuple(state["events"]))
        return state
"""
        for action in ("write", "fail"):
            with self.subTest(action=action):
                raw, adapter = models(source)
                events = []
                parent = {"events": events, "mirror": events, "count": 0}
                before = copy.deepcopy(parent)
                expected, raw_error = observe(raw.predict_belief, copy.deepcopy(parent), action)
                actual, wctr_error = observe(adapter.transition, parent, action)
                self.assertEqual(parent, before)
                self.assertIs(parent["events"], events)
                self.assertIs(parent["mirror"], events)
                self.assertEqual(wctr_error, raw_error)
                if raw_error is None:
                    self.assertEqual(actual, expected)
                    self.assertEqual(actual["events"] is actual["mirror"],
                                     expected["events"] is expected["mirror"])

    def test_name_augassign_on_parent_alias(self):
        self.compare_write('alias = state["events"]\n        alias += [1]')

    def test_annotated_subscript_rebinds_one_alias(self):
        self.compare_write('state["events"]: list = [1]')

    def test_local_add_name_does_not_change_subscript_augassign(self):
        self.compare_write('Add = 1\n        state["count"] += 1')
