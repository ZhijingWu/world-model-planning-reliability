# Evaluation contexts

## Discovery and controlled program planning (Stage 2)

The discovery replay observed 59 input mutations in 3,942 BabyAI predictions. This is a fixed artifact observation, not an estimate of prevalence across models. The 300-call unprotected final samples were WebShop 261, Wordle 300, SciWorld 70 and ALFWorld 5 input mutations; each had zero output mismatch against full-copy execution. Predictive correctness in the source environment is a different question.

The controlled benchmark covers BabyAI, ALFWorld, SciWorld, WebShop and Wordle released programs. BabyAI was also a development program; it is not an independent held-out program. Six methods share the same BFS, action pool and generated goal construction. Each has 80 task states/program, three timing repeats, 32 calibration calls and 300 contract-check calls. Planning is bounded at depth six, 4,096 transitions and a soft 10 ms deadline; adaptation/calibration are outside it. Goals are states obtained by executing a short action walk in the released program. An independent raw-model execution on deep copies verifies returned plans. Completion is program-goal completion, not native reward/success.

Task timing repeats are averaged before pairing; source items cluster related trajectories. The retained analysis uses 5,000 seeded bootstrap resamples (seed 20261028), percentile 95% intervals, conditional on these fixed programs. Hashed source-item labels permit reconstruction without distributing source text. They preserve cluster membership, not hidden task content.

## Native evaluation (Stage 3)

Full Copy, Top-Field, Journal Only and WCTR use identical released models and one frozen planner: BFS depth three, 96 expansions/decision, at most four candidates, discount 0.95; at most 12 real WebShop interactions or six Wordle interactions/task. No environment stepping occurs in hypothetical search. Native success requires actual `done` and reward exactly 1.0 (the official AgentGym Wordle reward shift is retained).

All four methods completed 6/12 final WebShop goals and 43/100 Wordle seed tasks. Their equal-domain average is 46.5%, not a pooled 112-task rate. Paired task action sequences were identical. All had zero sampled parent/output failures. Counts per arm are 240 WebShop and 33,452 Wordle; WCTR therefore has 33,692 and the four-arm total is 134,768. The study has 448 method-task records, 112 unique final tasks and 1,996 actual steps across arms.

WebShop uses a small 1k-product catalog with 13 available human goals: one smoke goal was excluded and 12 evaluated. The previous full-catalog task fingerprint was unavailable, so global disjointness of numeric IDs across catalogs cannot be certified. Instruction overlap in retained prior material was checked. Wordle uses the official seeded stochastic 40-word game, which resamples from filtered vocabulary across turns. The released model hardcodes `target_word="frame"`; it was neither fixed nor given hidden environment targets.

The per-domain/method allowance was 180 CPU seconds per model lifetime. Complete process CPU was measured after normal process exit on Windows using `GetProcessTimes` and includes startup, imports, setup, calibration, all tasks, verification, profiling and final serialization. Actual shared WebShop conversion/index setup was apportioned across four arms. Package provisioning CPU was unmeasured. All eight final workers completed within allowance. One measured lifetime per arm on one host cannot establish a universal speed ranking or startup-noise confidence interval.

| Method | WebShop lifetime CPU (s) | Wordle lifetime CPU (s) | Sum (s) |
| --- | ---: | ---: | ---: |
| Full Copy | 101.96484375 | 159.34375 | 261.30859375 |
| Top-Field | 98.10546875 | 147.859375 | 245.96484375 |
| Journal Only | 87.40234375 | 161 | 248.40234375 |
| WCTR | 94.99609375 | 162.625 | 257.62109375 |

The frozen Stage 3 decision was **RESULT C — NO COMPETITIVE ADVANTAGE**. WCTR has no incremental native-success benefit and is more expensive overall than simpler protected controls. This conclusion is retained alongside its successful branch-isolation checks.
