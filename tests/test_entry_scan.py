"""Live fallback detection and lazy alias indexing on the public transition path."""
import copy
import unittest
from collections import defaultdict
from unittest.mock import patch

from wctr import Adapter, compile_source
from wctr.isolation import graph


SOURCE = """class Model:
    def predict_belief(self, state, action):
        leaf = state['path'][0]['leaf']
        if action.endswith('read'):
            return len(leaf)
        if isinstance(leaf, set):
            return leaf.pop()
        if isinstance(leaf, dict):
            return leaf['missing']
        leaf.append(1)
        return state
"""


def models(source, method):
    env = {}
    exec(compile(source, 'raw.py', 'exec'), env)
    raw = env['Model']()
    guarded = compile_source(source, 'guarded.py')['Model']()
    return raw, Adapter(guarded, method)


class EntryScanTests(unittest.TestCase):
    def test_read_only_cycle_needs_no_reverse_edges(self):
        raw, adapter = models(SOURCE, 'wctr')
        leaf = [1, 2]
        state = {'path': ({'leaf': leaf},)}
        state['cycle'] = state
        expected = raw.predict_belief(copy.deepcopy(state), 'go read')
        with patch('wctr.isolation.graph', wraps=graph) as index:
            self.assertEqual(adapter.transition(state, 'go read'), expected)
            index.assert_not_called()
        self.assertIs(state['cycle'], state)
        self.assertEqual(leaf, [1, 2])
        self.assertEqual(adapter.full_clones, 0)

    def test_same_parent_reclassifies_nested_leaves_on_every_call(self):
        class ListSubclass(list):
            pass

        for method in ('journal', 'wctr', 'topfield'):
            with self.subTest(method=method):
                raw, adapter = models(SOURCE, method)
                branch = {'leaf': []}
                parent = {'path': (branch,), 'alias': branch}
                members = set(range(8))
                members.add(members.pop())
                for leaf, should_clone in (([], False), (members, True),
                                           (defaultdict(int), True), (ListSubclass(), True),
                                           ([2], False)):
                    # Keep the root, tuple and dictionary identities fixed across calls.
                    branch['leaf'] = leaf
                    before = copy.deepcopy(parent)
                    start = adapter.full_clones
                    expected = raw.predict_belief(copy.deepcopy(parent), 'go write')
                    result = adapter.transition(parent, 'go write')
                    self.assertEqual(result, expected)
                    self.assertEqual(parent, before)
                    self.assertIs(parent['path'][0], parent['alias'])
                    self.assertIs(branch['leaf'], leaf)
                    self.assertEqual(adapter.full_clones - start, int(should_clone))
                    if isinstance(leaf, list):
                        self.assertIs(result['path'][0], result['alias'])
                        self.assertIsNot(result['alias']['leaf'], leaf)
                        self.assertIs(type(result['alias']['leaf']), type(leaf))

    def test_first_parent_write_indexes_alias_before_it_is_detached(self):
        source = """class Model:
    def predict_belief(self, state, action):
        detached = state['items']
        del state['items']
        detached.append(9)
        if action == 'fail':
            raise ValueError('after detach')
        return detached
"""
        for action in ('write', 'fail'):
            with self.subTest(action=action):
                raw, adapter = models(source, 'wctr')
                original = [1]
                parent = {'items': original}
                if action == 'fail':
                    with self.assertRaisesRegex(ValueError, 'after detach'):
                        raw.predict_belief(copy.deepcopy(parent), action)
                    with self.assertRaisesRegex(ValueError, 'after detach'):
                        adapter.transition(parent, action)
                else:
                    expected = raw.predict_belief(copy.deepcopy(parent), action)
                    self.assertEqual(adapter.transition(parent, action), expected)
                self.assertIs(parent['items'], original)
                self.assertEqual(original, [1])
