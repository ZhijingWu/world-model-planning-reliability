"""Illustrative fixture, not a benchmark or new experimental measurement."""
import copy
from wctr import Adapter, compile_source

SOURCE = """
class Model:
    def predict_belief(self,s,a):
        n=s.copy()
        if a=='move':n['objects'][0]['x'] += 1
        elif a=='new':n['objects'][1]['x'] = 5
        return n
"""

def main():
    # This small fixture follows the frozen unit-test example.
    # Dedent source explicitly; compile_source executes trusted Python.
    import textwrap
    source = textwrap.dedent(SOURCE)
    raw = {}; exec(compile(source, 'illustrative.py', 'exec'), raw)
    initial = {'objects': [{'x': 0}, {'x': 2}]}
    reference = raw['Model']().predict_belief(copy.deepcopy(initial), 'move')
    parent = copy.deepcopy(initial)
    returned = raw['Model']().predict_belief(parent, 'move')
    assert returned == reference and parent != initial
    print('Unprotected: reference-equivalent output; parent changed.')

    adapter = Adapter(compile_source(source, 'illustrative.py')['Model'](), 'wctr')
    adapter.calibrate([(initial, 'move')])
    parent = copy.deepcopy(initial)
    first = adapter.transition(parent, 'move')
    second = adapter.transition(parent, 'new')
    assert first == reference and parent == initial
    assert second == raw['Model']().predict_belief(copy.deepcopy(initial), 'new')
    assert first['objects'][1]['x'] == 2
    print('WCTR: reference-equivalent successors; reusable parent; isolated siblings.')
    print('Output equivalence is to the same program, not environment ground truth.')

if __name__ == '__main__':
    main()
