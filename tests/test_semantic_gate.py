"""Independent Python/adapter comparisons for the AST release gate."""
import copy
import sys
import types
import unittest
from unittest.mock import patch

from wctr import Adapter, compile_source


def raw_model(source):
    namespace = {}
    exec(compile(source, "native_gate.py", "exec", dont_inherit=True), namespace)
    return namespace["Model"]()


def describe(root):
    """Describe values and internal aliases without comparing cyclic containers."""
    positions = {}
    objects = []

    def visit(value):
        kind = type(value)
        if kind not in (dict, list, tuple):
            return ("leaf", kind, value)
        oid = id(value)
        if oid in positions:
            return ("ref", positions[oid])
        positions[oid] = len(objects)
        objects.append(value)
        if kind is dict:
            return (kind, tuple((key, visit(item)) for key, item in value.items()))
        return (kind, tuple(visit(item) for item in value))

    return visit(root), objects


def call(transition, state, action):
    try:
        return transition(state, action), None
    except Exception as exc:
        return None, exc


def explicit_rejection(exc):
    return isinstance(exc, (TypeError, ValueError)) and "WCTR" in str(exc)


class IndependentSemanticGate(unittest.TestCase):
    def compare(self, source, make_state, actions, *, may_reject=False, uninstrumented=False):
        raw = raw_model(source)
        try:
            candidate = raw_model(source) if uninstrumented else compile_source(source, "wctr_gate.py")["Model"]()
            adapter = Adapter(candidate)
        except (TypeError, ValueError) as exc:
            if may_reject and explicit_rejection(exc):
                return
            raise
        for action in actions:
            with self.subTest(action=action):
                parent = make_state()
                before, old_objects = describe(parent)
                expected, raw_error = call(raw.predict_belief, copy.deepcopy(parent), action)
                actual, wctr_error = call(adapter.transition, parent, action)
                after, new_objects = describe(parent)
                self.assertEqual(after, before)
                self.assertEqual(len(new_objects), len(old_objects))
                self.assertTrue(all(a is b for a, b in zip(new_objects, old_objects)))
                if may_reject and explicit_rejection(wctr_error):
                    continue
                if raw_error is None:
                    self.assertIsNone(wctr_error)
                    self.assertEqual(describe(actual)[0], describe(expected)[0])
                else:
                    self.assertIs(type(wctr_error), type(raw_error))
                    self.assertEqual(wctr_error.args, raw_error.args)
        return adapter

    def test_annotation_order_and_bare_annotation(self):
        source = """class Model:
    def predict_belief(self, state, action):
        def mark(label, value):
            state["trace"].append(label)
            if action.endswith(" " + label):
                raise LookupError(label, tuple(state["trace"]))
            return value

        mark("base", state["box"])[mark("index", 0)]: mark("annotation", int) = mark("rhs", 4)
        mark("bare_base", state["box"])[mark("bare_index", 99)]: mark("bare_annotation", int)
        return state
"""
        self.compare(source, lambda: {"box": [1], "trace": []},
                     ["run ok", "run ok", "run rhs", "run base", "run index", "run bare_index"])

    def test_annotations_use_the_models_own_future_directives(self):
        source = """seen = []
def annotation(where):
    seen.append(where)
    return int
table = {}
table["key"]: annotation("module subscript") = 1
value: annotation("module name") = 1
class Model:
    value: annotation("class name") = 1
    def predict_belief(self, state, action):
        return tuple(seen)
"""
        for prefix in ("", "from __future__ import annotations\n"):
            with self.subTest(postponed=bool(prefix)):
                self.compare(prefix + source, dict, ["read"])

    def test_callback_comprehension_guard_and_finally_with_cycles(self):
        source = """class Model:
    def predict_belief(self, state, action):
        emit = state["trace"].append
        def bump(row):
            row["n"] += 1
            emit(row["n"])
            return row["n"]
        try:
            match [bump(row) for row in state["rows"]]:
                case [first, second] if second > first:
                    state["ring"][0].append((first, second))
            if action.endswith("fail"):
                raise LookupError(tuple(state["trace"]))
            return state
        finally:
            emit("finished")
"""

        def make_state():
            row = {"n": 0}
            links = []
            ring = (links,)
            links.append(ring)
            root = {"rows": [row, row], "selected": row, "ring": ring, "trace": []}
            root["parent"] = root
            return root

        self.compare(source, make_state, ["act ok", "act ok", "act fail"])

    def test_augmented_rhs_binds_in_model_scope_and_alias_rebinding_is_local(self):
        source = """class Model:
    def predict_belief(self, state, action):
        state["count"] += (amount := len(state["shared"]))
        alias = state["shared"]
        alias += [amount]
        alias = alias + [amount + 1]
        alias.append(amount + 2)
        if action.endswith("fail"):
            raise ValueError(amount, tuple(state["shared"]), tuple(alias))
        return {"shared": state["shared"], "other": state["other"], "rebound": alias, "count": state["count"]}
"""

        def make_state():
            shared = [7, 8]
            return {"count": 1, "shared": shared, "other": shared}

        self.compare(source, make_state, ["act ok", "act ok", "act fail"])

    def test_selective_subscript_augassign_preserves_walrus_and_local_add(self):
        source = """class Model:
    def predict_belief(self, state, action):
        Add = 17
        state["count"] += (increment := len(state["events"]))
        state["events"].append(increment)
        return [state, increment, Add]
"""
        adapter = self.compare(source, lambda: {"count": 4, "events": [7, 8]}, ["tick", "tick"])
        self.assertEqual(adapter.full_clones, 0)
        self.assertGreater(adapter.deopts, 0)

    def test_captured_native_callable_equality_and_identity(self):
        source = """class Model:
    def predict_belief(self, state, action):
        callback = state["a"].append
        alias = callback
        return (callback is alias, callback is state["a"].append,
                callback == state["a"].append, callback == state["b"].append)
"""
        self.compare(source, lambda: {"a": [1], "b": [1]}, ["inspect"])

    def test_mutable_exception_args_keep_finally_writes_after_parent_restore(self):
        def exception_snapshot(transition, state):
            try:
                transition(state, "raise")
            except Exception as exc:
                # Capture only after the public call exits and its finally blocks finish.
                return type(exc), describe(exc.args)[0]
            self.fail("the model returned instead of raising")

        for setup, raise_line in (
            ("", 'raise ValueError(state["values"], state["also_values"])'),
            ('def ValueError(marker):\n            return LookupError(state["values"], state["also_values"])',
             'raise ValueError("constant")'),
        ):
            with self.subTest(raise_line=raise_line):
                source = f"""class Model:
    def predict_belief(self, state, action):
        {setup}
        state["values"].append(1)
        try:
            {raise_line}
        finally:
            state["values"].append(2)
"""
                raw = raw_model(source)
                guarded = Adapter(compile_source(source, "exception_gate.py")["Model"]())
                shared = [7]
                parent = {"values": shared, "also_values": shared}
                expected = exception_snapshot(raw.predict_belief, copy.deepcopy(parent))
                actual = exception_snapshot(guarded.transition, parent)
                self.assertEqual(actual, expected)
                self.assertIs(parent["values"], shared)
                self.assertIs(parent["also_values"], shared)
                self.assertEqual(shared, [7])

    def test_model_import_parameter_class_and_closure_names(self):
        source = """from operator import neg as _wctr_bind_mutator
_wctr_private = None
class Model:
    _wctr_private = 2
    units = [2]
    def predict_belief(self, state, action, _wctr_write=None):
        _wctr_augment = self.units[0]
        def bump():
            nonlocal _wctr_augment
            state["count"] += _wctr_augment
        bump()
        state["items"].append(state["count"])
        state["copy"] = [*state["items"]]
        return state
"""
        self.compare(source, lambda: {"count": 2, "items": []}, ["bump", "bump"])

    def test_wildcard_import_can_export_underscore_names(self):
        module = types.ModuleType("wctr_gate_exports")
        module.__all__ = ["_wctr_write", "_wctr_private", "_wctr_bind_mutator", "Add"]
        for name in module.__all__:
            setattr(module, name, "model export")
        source = """from wctr_gate_exports import *
class Model:
    def predict_belief(self, state, action):
        state["items"].append(1)
        state["copy"] = [*state["items"]]
        state["count"] += 1
        return state
"""
        with patch.dict(sys.modules, {module.__name__: module}):
            self.compare(source, lambda: {"items": [], "count": 0}, ["add", "add"])

    def test_slices_starred_assignment_and_loop_target(self):
        source = """class Model:
    def predict_belief(self, state, action):
        state["items"][1:3] = [7, 8]
        first, *state["middle"], state["items"][0] = [10, 20, 30, 40]
        for state["latest"] in state["middle"]:
            state["items"].append(first)
        del state["items"][::2], state["discard"]
        if action.endswith("fail"):
            raise LookupError(tuple(state["items"]))
        return state
"""
        self.compare(source, lambda: {"items": [1, 2, 3], "discard": True},
                     ["act ok", "act fail"], may_reject=True)

    def test_opaque_write_forms_isolate_or_explicitly_reject(self):
        for statement in (
            'assign(state["row"], 0, 7)',
            'getattr(state["row"], "append")(7)',
            'list.__setitem__(state["row"], 0, 7)',
        ):
            source = f"""from operator import setitem as assign
class Model:
    def predict_belief(self, state, action):
        try:
            {statement}
        except TypeError:
            return "caught"
        if action.endswith("fail"):
            raise ValueError(tuple(state["row"]))
        return state
"""
            with self.subTest(operation=statement):
                self.compare(source, lambda: {"row": [1]}, ["act ok", "act fail"], may_reject=True)

    def test_native_sort_invokes_captured_mutator_as_key(self):
        source = """class Model:
    def predict_belief(self, state, action):
        sorter = list.sort
        sorter(state["items"], key=state["events"].append)
        return state
"""
        for items in ([7], [7, 8]):
            # With two keys native sort raises after both calls to append.
            with self.subTest(items=items):
                self.compare(source, lambda: {"items": list(items), "events": []},
                             ["sort", "sort"], may_reject=True)

    def test_mapping_constructor_invokes_captured_keys_callback(self):
        source = """from types import SimpleNamespace
class Model:
    def predict_belief(self, state, action):
        source = SimpleNamespace(keys=state["events"].clear)
        try:
            dict(source)
        except TypeError:
            pass
        return state
"""
        self.compare(source, lambda: {"events": [7]}, ["construct", "construct"], may_reject=True)

    def test_plain_adapter_model_isolates_or_explicitly_rejects(self):
        source = """class Model:
    def predict_belief(self, state, action):
        state["events"].append(1)
        if action.endswith("fail"):
            raise ValueError(tuple(state["events"]))
        return state
"""
        self.compare(source, lambda: {"events": []}, ["act ok", "act fail"],
                     may_reject=True, uninstrumented=True)
