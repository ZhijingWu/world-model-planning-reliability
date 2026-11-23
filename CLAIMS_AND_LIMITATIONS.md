# Claims and limitations

Independent research by Zhijing Wu, Sichuan University. No UC San Diego affiliation or endorsement by Prof. Zhiting Hu or MixLab is implied.

## From a write to a decision

| Claim | Selected 11-state bank | Prospective 64-state bank | Evidence and boundary |
| --- | --- | --- | --- |
| A. Raw changed a caller-owned parent. | 54 / 792 edges | 90 / 4,608 edges | Before/after snapshots of the same live parent. [Selected-state verification](studies/sciworld-fixed-work-v1/public/verification.json) · [Prospective trace verification](studies/sciworld-prospective-v1/public/verification.json) |
| B. A later branch received a different input. | 328 / 792 edge inputs | 604 / 4,608 edge inputs | Paired corresponding path against Full Copy. A mismatching input can propagate to descendants. [Original report](studies/sciworld-fixed-work-v1/public/report.md) · [New report](studies/sciworld-prospective-v1/report.md) |
| C. A numeric score changed. | 148 / 594 leaf scores | 304 / 3,456 leaf scores | Count of matching top-level goal fields. These are model-relative scores. [Original records](studies/sciworld-fixed-work-v1/public/verification.json) · [Prospective statistics](studies/sciworld-prospective-v1/public/analysis.json) |
| D. The fixed planner chose a different first action. | 1 / 11 states, 6 / 66 orders | 7 / 64 states, 28 / 384 orders | A state counts once. The original bank was outcome-selected. The prospective finite-frame interval is 5.63%–19.48%. [Original selection](proposals/sciworld-fixed-work.md) · [Prospective protocol](studies/sciworld-prospective-v1/protocol.md) · [Analysis](studies/sciworld-prospective-v1/public/analysis.json) |
| E. Isolating one writing edge restored the sibling input and reference first action. | 2 / 6 interventions on task 1975. The second action still differed. | 10 / 28 interventions across 6 of the 7 affected states. | All 4 other original and 18 other prospective interventions recovered the tested input while the decision difference persisted. They remain unresolved. [Worked example](studies/sciworld-fixed-work-v1/public/report.md) · [Prospective interventions](studies/sciworld-prospective-v1/report.md) |
| F. Actual native task success improved. | Unmeasured | Unmeasured | Replay evaluates the released program. The historical native comparison below found four-way ties in two other environments. [Historical records](results/README.md) |

Full Copy and WCTR preserved parents and agreed on every checked SciWorld path. WCTR executed all 792 selected-bank and all 4,608 prospective search calls with a full copy. This provides evidence about isolation on these workloads. Selective-path costs and compatibility require separate evidence. [Selected-bank checks](studies/sciworld-fixed-work-v1/public/verification.json) · [Prospective checks](studies/sciworld-prospective-v1/public/verification.json) · [Synthetic costs](diagnostics/ast-gate/README.md)

## Runtime and historical evidence

| Claim | Frozen basis | Essential qualification |
| --- | --- | --- |
| A successor may match full-copy execution while its parent is mutated. | `results/stage2/discovery.json` and `final_contracts.csv`; illustrative fixture in `examples/`. | Full copying defines same-program value semantics, not ground truth. The fixture is not a measured benchmark. |
| WCTR is an implemented runtime for witnessed selective forks and transactional rollback. | The [historical core](experiments/frozen/isolation.py) is byte-identical to the experiment version. The [current runtime](src/wctr/isolation.py) has separate regression coverage. | Restricted operations and state assumptions. Theoretical novelty remains unestablished. |
| The live workload recorded no WCTR parent/output mismatch. | 33,692 WCTR checks and 0 failures in `results/stage3/`, published at [`3c902203`](https://github.com/ZhijingWu/world-model-planning-reliability/tree/3c9022030323bd22e05b3f5276531eaa542cb1eb). | Other protected methods also passed. Across all four methods there were 134,768 finite checks. |
| Controlled WebShop program-goal completion increased by 17.5 pp. | 47.0833% Full Copy vs 64.5833% WCTR; source-item 95% interval [10.5882, 24.8064] pp. | Generated structured-state goals, 80 tasks, 3 repeats, shared BFS depth ≤6, nominal 4,096-expansion cap, soft 10 ms excluding setup/calibration. Native success was measured separately. |
| Controlled outcomes were mixed. | Wordle 54.1667% → 45.0%, −9.1667 pp; interval [−14.1026, −4.7619] pp. | Same controlled protocol. WebShop and Wordle paired intervals use 29/30 source-item clusters, not independent timing repeats. |
| Native completion tied across protected methods. | Each: 6/12 WebShop goals, 43/100 Wordle seed tasks; identical paired actions. | Small 1k-product WebShop catalog and stochastic 40-word Wordle; no incremental success benefit. |
| Simpler controls were competitive and cheaper overall on this host. | Lifetime CPU seconds: Full Copy 261.30859375, Top-Field 245.96484375, Journal 248.40234375, WCTR 257.62109375. | One lifetime per arm on one machine; provisioning unmeasured. WCTR Wordle CPU exceeded all three controls. No general efficiency/superiority claim. |
| State contamination changed a fixed-work root decision on task 1975. | Six of six orders changed root choice on this task. A single-edge intervention restored the sibling input and the reference first action in two orders. [SciWorld outcomes](studies/sciworld-fixed-work-v1/public/report.md) | Nine selected historical failure states and two comparison states. Four interventions left the decision difference unresolved. WCTR used Full Copy throughout. The stochastic extension proposed in the historical note remains future work. |

The [historical verifier](experiments/verify_evidence.py) checks Stage 2/3 aggregates and reconstructs all 25 Stage 2 source-item bootstrap comparisons. The [SciWorld verifier](studies/sciworld-prospective-v1/verify.py) separately checks the selected-state and prospective studies. Public artifacts contain numerical records and fingerprints. Full trace recomputation uses locally reconstructed observations and actions.

## Interpretation boundaries

WCTR does not repair inaccurate generated dynamics, establish a general-purpose learned world model, or demonstrate robotic/real-world validation. It can preserve a reusable parent while a model confidently predicts the wrong outcome. Isolation correctness, program-goal completion, native success and runtime cost are separate quantities.

The Wordle environment resamples targets from its filtered 40-word vocabulary; its 100 distinct seeds are not 100 fixed hidden answers. The generated model's hardcoded `target_word="frame"` was preserved. Native actions matched, so this study supplies no evidence of better decisions from WCTR. The prior full-catalog WebShop task fingerprint was unavailable: numeric task IDs cannot be certified globally disjoint across catalogs. Retained normalized instruction overlap was checked, and the smoke goal was excluded.

No broad speed claim follows from either the controlled deadline or lifetime measurements. The finite contract scope, shared untouched objects, unsupported Python/global/external state and stochasticity boundaries are detailed in [SUPPORTED_STATE.md](docs/SUPPORTED_STATE.md).
