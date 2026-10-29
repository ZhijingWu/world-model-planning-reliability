# Claims and limitations

Independent research by Zhijing Wu, Sichuan University. No UC San Diego affiliation or endorsement by Prof. Zhiting Hu or MixLab is implied.

| Claim | Frozen basis | Essential qualification |
| --- | --- | --- |
| A successor may match full-copy execution while its parent is mutated. | `results/stage2/discovery.json` and `final_contracts.csv`; illustrative fixture in `examples/`. | Full copying defines same-program value semantics, not ground truth. The fixture is not a measured benchmark. |
| WCTR is an implemented runtime for witnessed selective forks and transactional rollback. | Byte-identical frozen core in `src/wctr/isolation.py`; seven retained unit tests. | Restricted operations/assumptions; neither arbitrary-Python correctness nor theoretical novelty established. |
| The live workload recorded no WCTR parent/output mismatch. | 33,692 WCTR checks, 0 failures, in `results/stage3/`. | Other protected methods also passed. Across all four methods there were 134,768 checks. Finite checks are not proof. |
| Controlled WebShop program-goal completion increased by 17.5 pp. | 47.0833% Full Copy vs 64.5833% WCTR; source-item 95% interval [10.5882, 24.8064] pp. | Generated structured-state goals, 80 tasks, 3 repeats, shared BFS depth ≤6, 4,096 cap, soft 10 ms excluding setup/calibration. Not native WebShop success. |
| Controlled outcomes were mixed. | Wordle 54.1667% → 45.0%, −9.1667 pp; interval [−14.1026, −4.7619] pp. | Same controlled protocol. WebShop and Wordle paired intervals use 29/30 source-item clusters, not independent timing repeats. |
| Native completion tied across protected methods. | Each: 6/12 WebShop goals, 43/100 Wordle seed tasks; identical paired actions. | Small 1k-product WebShop catalog and stochastic 40-word Wordle; no incremental success benefit. |
| Simpler controls were competitive and cheaper overall on this host. | Lifetime CPU seconds: Full Copy 261.30859375, Top-Field 245.96484375, Journal 248.40234375, WCTR 257.62109375. | One lifetime per arm on one machine; provisioning unmeasured. WCTR Wordle CPU exceeded all three controls. No general efficiency/superiority claim. |
| Action-order sensitivity is a promising question. | Proposed fixed-state, paired-randomness experiment in the final note. | Future work; no action-ranking experiment was executed or reported as a result. |

All public headline aggregates are checked against public projections of the frozen records by `experiments/verify_evidence.py`. It also reconstructs all 25 Stage 2 source-item bootstrap comparisons. The complete original archives remain authoritative and unchanged; the public selection omits raw observations/actions and intermediate negative experiments rather than replacing their results.

## Interpretation boundaries

WCTR does not repair inaccurate generated dynamics, establish a general-purpose learned world model, or demonstrate robotic/real-world validation. It can preserve a reusable parent while a model confidently predicts the wrong outcome. Isolation correctness, program-goal completion, native success and runtime cost are separate quantities.

The Wordle environment resamples targets from its filtered 40-word vocabulary; its 100 distinct seeds are not 100 fixed hidden answers. The generated model's hardcoded `target_word="frame"` was preserved. Native actions matched, so this study supplies no evidence of better decisions from WCTR. The prior full-catalog WebShop task fingerprint was unavailable: numeric task IDs cannot be certified globally disjoint across catalogs. Retained normalized instruction overlap was checked, and the smoke goal was excluded.

No broad speed claim follows from either the controlled deadline or lifetime measurements. The finite contract scope, shared untouched objects, unsupported Python/global/external state and stochasticity boundaries are detailed in [SUPPORTED_STATE.md](docs/SUPPORTED_STATE.md).
