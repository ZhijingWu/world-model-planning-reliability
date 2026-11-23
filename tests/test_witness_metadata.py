"""Witness metadata must not change the outcome of a model that ignores it."""
import copy
import sys
import unittest

from wctr import Adapter, compile_source


LARGE_INT = 10 ** 4300
SOURCE = """class Model:
    def predict_belief(self, state, action):
        state["rows"][0]["visits"] += 1
        if state["fail"]:
            raise RuntimeError("after update")
        return state
"""


def observe(transition, state, action):
    try:
        return transition(state, action), None
    except Exception as exc:
        return None, (type(exc), exc.args)


class WitnessMetadata(unittest.TestCase):
    def compare_transition(self, fields, action, *, fail, warm=False):
        ordinary = {}
        exec(compile(SOURCE, "raw.py", "exec", dont_inherit=True), ordinary)
        raw = ordinary["Model"]()
        adapter = Adapter(compile_source(SOURCE, "guarded.py")["Model"]())
        if warm:
            training = {"rows": [{"label": "blue", "visits": 0}], "fail": False}
            adapter.calibrate([(training, "visit blue")])
        row = {**fields, "visits": 0}
        rows = [row]
        parent = {"rows": rows, "fail": fail}
        before = copy.deepcopy(parent)
        expected, raw_error = observe(raw.predict_belief, copy.deepcopy(parent), action)

        # Observe actual model entry, including an error before or after that entry.
        # A counter inside the fixture would change its AST and admission decision.
        calls = 0
        model_code = adapter.model.predict_belief.__func__.__code__

        def count_model_calls(frame, event, arg):
            nonlocal calls
            if event == "call" and frame.f_code is model_code:
                calls += 1

        previous = sys.getprofile()
        try:
            sys.setprofile(count_model_calls)
            actual, wctr_error = observe(adapter.transition, parent, action)
        finally:
            sys.setprofile(previous)
        self.assertTrue(parent == before)
        self.assertIs(parent["rows"], rows)
        self.assertIs(rows[0], row)
        self.assertEqual(calls, 1)
        self.assertEqual(wctr_error, raw_error)
        if raw_error is None:
            self.assertTrue(actual == expected)
            self.assertIsNot(actual["rows"][0], row)
        return adapter

    def test_string_selector_ignores_large_integer_label(self):
        for label, name in (("blue", "string hit"), (LARGE_INT, "integer miss")):
            for fail in (False, True):
                with self.subTest(label=name, fail=fail):
                    adapter = self.compare_transition({"label": label}, "visit blue",
                                                      fail=fail, warm=True)
                    if not fail:
                        self.assertEqual(adapter.deopts, int(name == "integer miss"))
                        self.assertEqual(adapter.full_clones, 0)

    def test_ignored_large_integer_action(self):
        for fail in (False, True):
            with self.subTest(fail=fail):
                self.compare_transition({}, LARGE_INT, fail=fail)

    def test_large_integer_key_during_witness_learning(self):
        for fail in (False, True):
            with self.subTest(fail=fail):
                self.compare_transition({LARGE_INT: "blue"}, "visit blue", fail=fail)
