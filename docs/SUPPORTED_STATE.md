# Supported-state contract and API

The intended operational target for one instrumented transition is (1) parent values restored after the call, including supported exceptional exits, and (2) returned values equal to the same model's raw transition on a full deep copy. This is an implementation target checked on finite workloads, not a formal proof or arbitrary-Python guarantee.

```python
from wctr import Adapter, compile_source
namespace = compile_source(trusted_python_source, "model.py")
model = namespace["Model"]()
adapter = Adapter(model, "wctr")
adapter.calibrate([(belief, action)])  # Optional finite execution witnesses
successor = adapter.transition(belief, action)
```

`compile_source` executes trusted Python. It is not a sandbox. Calibration executes model transitions; it is not learning ground-truth dynamics. Action signatures use the first whitespace-delimited token. Witnessed paths guide selective copying; unexpected supported writes use a journal and update witnesses. `deepcopy` and `raw` methods should receive the uninstrumented model for the intended control semantics. See the example and retained harness.

## Scope and assumptions

- Plain dict/list/set/tuple state graphs with instrumented subscript assignment/deletion, listed mutator calls and supported augmented subscript operations. Only the AST patterns implemented in `isolation.py` are covered. Chained/multi-target assignments, attribute mutation and other syntax are not generally covered.
- Graph traversal follows dictionary values and sequence elements; arbitrary mutable objects as dictionary keys or inside sets are not a general supported case.
- Alias closure preserves tested dict/list sharing and cycles. Tuple cycles fall back to `deepcopy`.
- The adapter detects defaultdicts in `init_belief` and uses full copying because missing-key reads can mutate them. It cannot assume that arbitrary later defaultdicts or custom mappings are automatically covered. The optional `_wctr_raw_model` supplies the uninstrumented fallback, as in the retained harnesses.
- Augmented assignments assume the released models' side-effect-free numeric right-hand sides. Arbitrary Python evaluation/side-effect patterns are outside the contract.
- State must not be concurrently mutated or exposed to external observers during speculative execution and rollback.
- Untouched objects can remain shared between parent and successor. Arbitrary direct mutation after a call is outside the supported usage; subsequent rollouts should pass through the adapter.

Globals, custom attributes/descriptors, arbitrary container subclasses, C-extension mutation, I/O/external resources and uncontrolled random state are outside this contract. Restoring container values does not reverse those effects. No claim of general referential transparency follows.

## What the tests establish

The seven retained tests check augmented-list behavior, output grafting and parent restoration, unseen-write fallback, alias closure and a dict cycle, exception rollback, one assignment-evaluation case, and selector-based copying. All are regression fixtures; they do not prove coverage of Python or all generated models.

The 33,692 WCTR checked transitions belong to the completed native study. They are distinct from the seven unit tests and from the 134,768 checks across all four protected methods. Zero sampled contract failures do not establish environment predictive correctness.
