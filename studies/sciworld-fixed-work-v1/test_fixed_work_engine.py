"""Synthetic mechanics audit; no SciWorld source, data, goals or interventions."""
import copy
import unittest
from collections import defaultdict

from sciworld_study_engine import evaluate_task


def canonical(value):
    if type(value) is dict:
        return "dict", tuple((k, canonical(v)) for k, v in sorted(value.items()))
    if type(value) is list:
        return "list", tuple(map(canonical, value))
    return value


class Arithmetic:
    def predict_belief(self, parent, action):
        parent["v"][0] += {"a": 1, "b": 2, "c": -3}[action]
        return parent


class CopyAdapter:
    def __init__(self):
        self.calls = self.full_clones = self.sites = self.copied = self.deopts = 0
        self.frontiers = defaultdict(set)
        self.model = Arithmetic()

    def calibrate(self, calibration):
        for parent, action in calibration:
            self.transition(parent, action)
        self.calls = self.full_clones = 0

    def transition(self, parent, action):
        self.calls += 1
        self.full_clones += 1
        return self.model.predict_belief(copy.deepcopy(parent), action)


class EngineTest(unittest.TestCase):
    def setUp(self):
        self.task = {"task_id": 123, "trajectory": 4, "step": 1,
                     "state": {"v": [0]}, "goal": canonical({"v": [2]}),
                     "actions": ["a", "b", "c", "d"]}
        self.calibration = [({"v": [i]}, "a") for i in range(32)]
        self.private = []

    def evaluate(self):
        return evaluate_task(self.task, canonical=canonical, raw_factory=Arithmetic, wctr_factory=CopyAdapter,
                             calibration=self.calibration, private_sink=self.private.append)

    def test_ineligible_does_not_start_any_arm(self):
        self.task["actions"] = ["a", "a", "b"]
        self.assertFalse(self.evaluate()["eligible"])
        self.assertEqual(self.private, [])

    def test_fixed_traversal_replay_ties_and_controlled_rescue(self):
        result = self.evaluate()
        self.assertTrue(result["reference_controls_pass"])
        self.assertTrue(result["wctr_controls_pass"])
        self.assertEqual(len(result["comparisons"]), 6)
        self.assertEqual(result["calls"]["search"], 6 * 3 * 12)
        self.assertEqual(result["calls"]["initial_calibration"], 6 * 32)
        self.assertEqual(result["calls"]["replay"], 6 * 3 * 2)
        case = next(p for p in result["comparisons"] if p["order"] == [1, 2, 0])
        full, raw = case["arms"]["full_copy"], case["arms"]["raw"]
        self.assertEqual(full["selected"], [0, 0])
        self.assertEqual(raw["selected"], [1, 2])
        self.assertEqual(raw["root_ties"], [1, 2])
        self.assertTrue(raw["replay"]["false_goal"])
        self.assertEqual(case["classification"], "verified_single_edge_rescue")
        self.assertEqual(case["rescue"]["writer"], [1, 0])
        self.assertEqual(case["rescue"]["reader"], [1, 1])
        self.assertEqual(case["rescue"]["run"]["selected"][0], 0)
        self.assertEqual(self.task["state"], {"v": [0]})
        self.assertEqual(self.calibration, [({"v": [i]}, "a") for i in range(32)])
        values = {r["sha256"]: r["canonical"] for r in self.private if r["type"] == "canonical_snapshot"}
        for edge in raw["edges"]:
            for name in ("root_before", "root_after", "parent_before", "parent_after", "successor"):
                self.assertIn(edge[name][0], values)


if __name__ == "__main__":
    unittest.main()
