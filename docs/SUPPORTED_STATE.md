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

`compile_source` executes trusted Python. Supply a model with `predict_belief(state, action)` and a deterministic transition on the state described below. Use an uninstrumented instance of the same model for the `deepcopy` and `raw` controls.

Calibration is optional. It runs model calls on copied inputs and retains the observed write paths. After calibration the adapter resets its work counters and keeps its witnesses. Later successful calls can update the same paths when the journal captures an unexpected write. The action signature is the lowercased prefix before the first literal space after trimming the action string. For example, `"Pick up box"` and `"pick key"` share the signature `"pick"`. A learned path predicts which objects to copy before the next call.

## Scope and assumptions

- The selective path operates on plain dict/list/tuple graphs with immutable scalar leaves and keys. The instrumented write forms are a single subscript assignment, deletion with subscript targets, and subscript `+=`, `-=`, `*=`, `|=` or `&=`. The right-hand side of an augmented update must be side-effect-free. Chained assignments, dynamic method lookup via `getattr`, or external helpers that write through aliases can bypass instrumentation. Callers must keep these forms outside the workload.
- A listed mutator such as `items.append` or `list.append` is guarded when called, including through an alias for the class or a method captured from the instrumented attribute. The guard identifies the actual built-in receiver. An unrecognized receiver raises `TypeError` during speculation before the method body executes. Code inspecting the callable's identity or metadata falls outside this calling contract. The compiler marks containers created by literals and comprehensions as private. A method called `copy` or a variable called `list` can return a parent alias, so those names alone confer no private ownership. See the [guard and list of mutators](../src/wctr/isolation.py).
- At protected call entry, the adapter scans the reachable container graph even when the witness list is empty. A reachable set or `defaultdict` selects full-copy execution, including when introduced after initialization. A set can choose a different member for `pop()` after copying, and a missing-key read can write to a `defaultdict`. The initial-belief `defaultdict` policy also applies to later calls. Traversal follows dictionary values and list/tuple elements. Use immutable keys and set members. The optional `_wctr_raw_model` supplies the original transition on the full-copy path. This entry scan adds work whose cost depends on the graph size. Historical timing measurements predate it.
- Alias closure preserves tested dict/list sharing and cycles. When selective copying encounters a back-edge to an unfinished tuple, it deep-copies the whole graph being forked. This can occur while forking the input or grafting the output. Each such fallback increments `full_clones` in the current runtime. At `3c902203`, these copies contributed to the copied-container count only. An archived zero in `full_clones` cannot establish the absence of tuple-cycle fallbacks.
- State must not be concurrently mutated or exposed to external observers during speculative execution and rollback.
- Untouched objects can remain shared between parent and successor. Arbitrary direct mutation after a call is outside the supported usage; subsequent rollouts should pass through the adapter.

Globals, custom attributes/descriptors, arbitrary container subclasses, C-extension mutation, I/O/external resources and uncontrolled random state are outside this contract. Restoring container values does not reverse those effects. No claim of general referential transparency follows.

## What the tests establish

The original seven tests check augmented-list behavior, output grafting and parent restoration, unexpected writes, alias closure and a dict cycle, exception rollback, assignment evaluation and selector-based copying. The added [runtime regression cases](../tests/test_runtime_regressions.py) check method dispatch, parent aliases returned by helpers, order-sensitive sets, full-copy accounting and exceptional exits.

The completed native study recorded zero parent/output value failures in 33,692 WCTR branch transitions on historical revision [`3c902203`](https://github.com/ZhijingWu/world-model-planning-reliability/tree/3c9022030323bd22e05b3f5276531eaa542cb1eb). The four protected methods together accounted for 134,768 checks. Those counts describe the historical workload. The current regression suite uses separate fixtures.
