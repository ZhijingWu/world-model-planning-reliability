# Evaluation contexts

The counts, outcomes, counters and timings on this page describe the frozen studies published at [`3c902203`](https://github.com/ZhijingWu/world-model-planning-reliability/tree/3c9022030323bd22e05b3f5276531eaa542cb1eb). The current runtime is covered separately by its regression suite.

## Discovery and controlled program planning (Stage 2)

The discovery replay observed 59 input mutations in 3,942 BabyAI predictions. This is a fixed artifact observation, not an estimate of prevalence across models. The 300-call unprotected final samples were WebShop 261, Wordle 300, SciWorld 70 and ALFWorld 5 input mutations; each had zero output mismatch against full-copy execution. Predictive correctness in the source environment is a different question.

The controlled benchmark covers five released programs. BabyAI also appeared in development. ALFWorld, SciWorld, WebShop and Wordle were the four held-out programs. Six methods shared the BFS, action pool and generated goals. Each program had 80 task states, three timing repeats, 32 initial calibration calls and 300 separate contract-check calls per method. The planner rebuilt and calibrated its adapter for each repeat. Witnesses discovered during search could persist across tasks within that repeat.

Stage 2 bounded depth at six. The historical BFS checked the 4,096-expansion limit before dequeuing a node. Since a node could supply up to four actions, the inner loop could exceed the limit by at most three transitions. The largest count in the 7,200 retained records was 204. The separate soft 10 ms wall deadline was checked before nodes and edges. One operation could finish after it expired. Setup and calibration preceded the search timer. Full-copy replay of the returned plan followed it and verified completion against the generated program goal. [Historical search loop](https://github.com/ZhijingWu/world-model-planning-reliability/blob/3c9022030323bd22e05b3f5276531eaa542cb1eb/experiments/stage2/benchmark.py#L70-L96)

Task timing repeats are averaged before pairing; source items cluster related trajectories. The retained analysis uses 5,000 seeded bootstrap resamples (seed 20261028), percentile 95% intervals, conditional on these fixed programs. Hashed source-item labels permit reconstruction without distributing source text. They preserve cluster membership, not hidden task content.

## Native evaluation (Stage 3)

Full Copy, Top-Field, Journal Only and WCTR use identical released models and one frozen planner: BFS depth three, 96 expansions/decision, at most four candidates, discount 0.95; at most 12 real WebShop interactions or six Wordle interactions/task. No environment stepping occurs in hypothetical search. Native success requires actual `done` and reward exactly 1.0 (the official AgentGym Wordle reward shift is retained).

All four methods completed 6/12 final WebShop goals and 43/100 Wordle seed tasks. Their equal-domain average is 46.5%, not a pooled 112-task rate. Paired task action sequences were identical. All had zero sampled parent/output failures. Counts per arm are 240 WebShop and 33,452 Wordle; WCTR therefore has 33,692 and the four-arm total is 134,768. The study has 448 method-task records, 112 unique final tasks and 1,996 actual steps across arms.

WebShop uses a small 1k-product catalog with 13 available human goals: one smoke goal was excluded and 12 evaluated. The previous full-catalog task fingerprint was unavailable, so global disjointness of numeric IDs across catalogs cannot be certified. Instruction overlap in retained prior material was checked. Wordle uses the official seeded stochastic 40-word game, which resamples from filtered vocabulary across turns. The released model hardcodes `target_word="frame"`; it was neither fixed nor given hidden environment targets.

The per-domain/method allowance was 180 CPU seconds per model lifetime. The harness read Windows `GetProcessTimes` after normal exit and summed the worker's user and kernel CPU across its threads. This includes startup, imports, model/environment setup, calibration, the tasks, per-branch snapshot and reference replay, profiling, serialization and shutdown. For WebShop, conversion (11.78125 CPU s) and indexing (9.078125 CPU s) added 5.21484375 CPU s per arm. This shared charge is already in the totals below. Wordle had no such charge. Driver CPU was recorded separately. Package installation and asset acquisition were unmeasured.

All eight workers completed within allowance. There was one instrumented lifetime per method and domain on one host. The WCTR diagnostic also matched the frontier when taking the verification snapshot. These measurements describe that benchmark configuration. Production throughput and between-run startup variability remain unmeasured. [Worker clock](../experiments/stage3/run_recorded.py) · [Per-branch verification](../experiments/stage3/live_study.py)

| Method | WebShop lifetime CPU (s) | Wordle lifetime CPU (s) | Sum (s) |
| --- | ---: | ---: | ---: |
| Full Copy | 101.96484375 | 159.34375 | 261.30859375 |
| Top-Field | 98.10546875 | 147.859375 | 245.96484375 |
| Journal Only | 87.40234375 | 161 | 248.40234375 |
| WCTR | 94.99609375 | 162.625 | 257.62109375 |

The frozen Stage 3 decision was **RESULT C — NO COMPETITIVE ADVANTAGE**. WCTR has no incremental native-success benefit and is more expensive overall than simpler protected controls. This conclusion is retained alongside its successful branch-isolation checks.
