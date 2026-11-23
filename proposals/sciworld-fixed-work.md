# Proposed SciWorld fixed-work branch-isolation study

**Status** — Design only. Execution requires review of the runtime repair first. The only observations cited here come from archived Stage 2 records.

## Question and endpoint

Does a write through a shared parent in the released SciWorld program change the input to a later sibling and thereby change the first action selected at a fixed search budget? The hypothesis is existential for the nine selected failure states. The primary endpoint is a paired difference in the chosen root action between raw execution and per-edge Full Copy for the same state and expansion order, with the causal checks below. A changed score, ranking or replay outcome is a separate observation.

## Frozen state bank

Identifiers are zero-based. `task_id` indexes transitions flattened in test-file order. Each triple refers to the belief after correcting the current observation and immediately before predicting the logged action.

| Historical selection | (task_id, trajectory, transition) |
| --- | --- |
| Nontrivial, raw found a plan that failed independent replay in all three archived repeats | (364, 23, 3), (374, 24, 3), (476, 27, 16), (863, 41, 17), (925, 44, 0), (1560, 68, 10), (1963, 82, 18), (1975, 83, 0), (2166, 90, 12) |
| Nontrivial comparison states, raw found a replay-valid plan in all three repeats | (390, 24, 19), (465, 27, 5) |

The two comparisons are the closest eligible source steps in the same trajectories as 374 and 476. Valid historical replay does not establish that their parents were unchanged. Timing repeats select nine failure states and do not increase that sample size. This outcome-selected bank cannot estimate how often failures occur across SciWorld. [Historical public planning records](https://github.com/ZhijingWu/world-model-planning-reliability/blob/3c9022030323bd22e05b3f5276531eaa542cb1eb/results/stage2/final_planning.csv)

| Frozen input | SHA-256 |
| --- | --- |
| SciWorld test JSONL, first 100 trajectories | `9795ea9106a6cfa4d909a6767aed7598d9406d22a8a6e4521f47329464b68641` |
| SciWorld training JSONL, first 32 trajectories | `b7a093870e5905f1e35161fd353ff464cbf1f4dbada4ffecf3646c3648b9ecfa` |
| Vendored SciWorld program | `9d7c24064d030d15d68c833b031e8a24c5b897a177562e1ee0642c464cfcac72` |
| Public Stage 2 final planning CSV | `804541d198f00a8216adbcba397675e4b08988940cddf9c04546649be884f567` |

For the future run, verify these digests before reconstructing states. Use the frozen Stage 2 `cases` procedure, including prediction on a fresh deep copy and correction with the logged next observation at each preceding step. Rebuild the full `make_tasks('sciworld', 'test', 80, 20261028)` selection before extracting the eleven triples. The order affects the RNG draws for candidate lists and goal walks. Check IDs against the public rows and walks against the retained full planning CSV. Freeze SHA-256 digests of each root's canonical value, ordered candidates, goal and goal walk before any intervention. Record the serializer and its version plus a separate alias fingerprint mapping each shared mutable object's paths to a stable group identifier. No such root digests have been measured yet. [Frozen harness](https://github.com/ZhijingWu/world-model-planning-reliability/blob/3c9022030323bd22e05b3f5276531eaa542cb1eb/experiments/stage2/benchmark.py#L38-L68) · [Pinned trajectory revision](https://huggingface.co/datasets/HKBU-KnowComp/patchworld-trajectories/tree/9342e2cbee1f8579b5423ed5821f6ad8a81ab773)

## Interventions and fixed work

1. Run three paired arms. **Raw** calls the original program on the live parent. **Full Copy** calls that same original program on a fresh deep copy at every edge and serves as the independent reference. **WCTR** runs the reviewed repair against the identical program source. Pin the exact reviewed commit, interpreter, hash seed and input manifest before execution. Start each arm and order from a pristine copy of the same root and a fresh model. Start each WCTR adapter with the same initial calibration on the first 32 training **transitions**, recording online witness updates during the subsequent 12 calls separately.
2. Keep the first three distinct candidates in their frozen order, indexed 0–2. If fewer than three exist, mark the state ineligible and report the denominator. Make no substitutions. Run all six permutations of the root candidates. For each root action, expand its three children immediately in frozen index order before visiting the next root action. Reuse the live parent and first-level successor in their respective sibling loops. Each arm and permutation executes exactly 12 search transitions, with no deadline, deduplication or goal-based stop. Calibration, trace inspection, replay and rescue calls are counted separately.
3. At each depth-two leaf record the integer count of top-level goal fields present and equal under the frozen harness's canonical value comparison. Score missing fields zero. For each root action use its best leaf score, resolving child ties by frozen candidate index. Select the highest-scoring root action, resolving ties by the same index independent of visitation order. Store scalar readings and canonical snapshots immediately so subsequent writes cannot change the recorded scores. Report ties, including all-equal rankings. Separately record exact whole-goal equality for every leaf.

## Measurements and decision rule

- Log each edge in visitation order with its path, read-only pre/post snapshots of the root and edge parent, successor value, differing paths and shared-container identifiers. Log every leaf score, root score vector in frozen index order, tied action set and chosen action. Record WCTR full-copy fallbacks and deoptimizations per edge. SciWorld initializes `facts` and `frontier` as sets, so disclose whether isolation on these calls used fallback or selective copying.
- Validate the reference first. Full Copy must preserve parents and give identical values and scores for each action path and the same decision across all six orders. WCTR must preserve parents and agree path-by-path with the independent reference. Report an unsupported transition or a mismatch explicitly. If Full Copy controls fail on a state, label its causal comparison uninterpretable.
- For a decision difference, identify the earliest raw parent write carried into a later sibling's input, the differing paths and the downstream action scores. From a fresh root rerun the same raw order, changing only the identified writing edge to raw-on-deep-copy. Require restoration of the affected sibling input and the reference decision before attributing a decision change to that edge. Retain unresolved, multiple-write and score-only cases as such.
- Independently replay the selected two-action sequence from the pristine root with the original program on fresh full copies. Record exact goal equality. Count a false goal only when search reported exact equality and replay disagreed. A partial-score winner need not reach the goal.
- Report each task's six paired orders, the number of eligible task IDs with a decision change, verified single-edge rescues, ties, replay failures and null results. Keep the two historical comparison states separate. A null result applies to this depth, score, candidate set and bank. Any positive claim concerns planning over the released program. Native environment success and the cause of the original deadline-limited failures require different evidence.

A future run should record its manifest, traces and derived tables in a separately versioned study directory, leaving the historical evidence and technical note intact.
