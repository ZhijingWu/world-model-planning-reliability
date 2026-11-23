# Cost of the AST semantic gate

This synthetic diagnostic compares the blocked PR head `9e28df1463f9a878a0df853926243ef9bcbc1642` with implementation commit `dd3aa05f9fc064a5293650e75a55f00308495fbb`. It loads both Runtime files from their Git objects in one process. The controls are Journal Only on the candidate and one ordinary Python prediction on `deepcopy(parent)`. Source hashes, raw durations, quartiles, per-call p95s and clone counts are available for every timed arm. [Measurement record](2026-11-23-runtime-costs.json)

The table shows median batch-mean wall time in µs per transition. The final column is the candidate WCTR's separately sampled individual-call p95.

| Rows | Operation | Blocked WCTR | Candidate WCTR | Candidate Journal Only | Raw Full Copy | Candidate p95 |
| ---: | --- | ---: | ---: | ---: | ---: | ---: |
| 4 | Read | 6.09 | 10.42 | 8.06 | 12.09 | 21.3 |
| 4 | First append | 31.84 | 37.18 | 41.18 | 12.69 | 63.7 |
| 4 | Calibrated append | 14.99 | 21.15 | 33.67 | 14.92 | 41.0 |
| 4 | Reachable-set read | 18.16 | 20.21 | 19.76 | 17.12 | 73.6 |
| 64 | Read | 59.18 | 79.17 | 94.86 | 197.32 | 176.4 |
| 64 | First append | 340.89 | 374.56 | 388.19 | 178.68 | 802.5 |
| 64 | Calibrated append | 173.91 | 153.05 | 332.47 | 175.84 | 304.2 |
| 64 | Reachable-set read | 202.31 | 212.56 | 168.21 | 175.62 | 211.3 |
| 4 | Name-bound list `+=` | Parent changed | 16.25 | 12.97 | 12.18 | 21.7 |
| 64 | Name-bound list `+=` | Parent changed | 149.49 | 182.67 | 194.16 | 393.8 |
| 4 | Annotated subscript write | Parent changed | 13.58 | 12.98 | 11.93 | 29.1 |
| 64 | Annotated subscript write | Parent changed | 173.59 | 144.53 | 186.92 | 402.2 |

At 64 rows the candidate had higher medians on reads and first appends, and a lower median on calibrated appends. Full Copy remained cheaper for first append at both sizes. The old Runtime failed the parent-preservation check for the two additional source forms before timing. The candidate and Journal Only made exactly one whole-state copy per transition for those forms (1,200/1,200 per form across both sizes). Each made 1,600/1,600 whole-state copies for the reachable-set read and zero across the other 4,800 mixed-model calls. The previous WCTR's copy counts matched on the four mixed-model scenarios.

For the mixed model, compiling and executing the source to create its class took a median 323.95 µs on the blocked Runtime and 689.08 µs on the candidate. Constructing a model and adapter from the compiled class took 1.63 and 1.62 µs respectively. The setup probe alternated versions over eight paired batches of 32 compilations or 128 constructions. Compilation is a one-time cost when a caller reuses a compiled model.

## Measurement conditions

On 2026-11-23, a single 64-bit CPython 3.13.5 process (Anaconda, Windows 11 build 26300, Intel Core Ultra 7 155H) used `perf_counter_ns` and a fixed hash seed. Four or 64 rows yielded 11 or 131 reachable containers, plus one in the set case. Two state keys alias the same event list. The four mixed-model scenarios use the [earlier fixture and timing primitives](../runtime_costs.py). Separate models isolate the two previously incorrect forms. All reference outputs use uninstrumented source on a deep copy.

Each valid cell had 12 warmups. The harness rotated and reversed arm order across eight throughput rounds for the four-arm cases and six rounds for three-arm cases. Batches had 128 calls at four rows and 48 at 64 rows. A second pass used the same order with 12 individually timed calls per arm per round. P95 is the empirical nearest rank of 96 or 72 samples respectively. The record includes every sample from 32,800 timed transitions. The candidate's 64-row first-append batch means had Q1–Q3 of 360.49–413.80 µs and an individual-call p95 of 802.5 µs in the second pass.

Transitions include dispatch, input inspection or copying, model execution and output replacement. Validation, collection, compilation, construction and calibration are outside those intervals. The first-write samples use preconstructed fresh adapters. The calibrated samples use one witness acquired before timing. Cyclic GC is disabled during timed intervals. Each batch checks its final successor, original parent values and alias identity. One host, two sizes and these synthetic operations leave workload frequency, native planning costs and other interpreter timings unmeasured. Scheduling, processor frequency and thermal state were uncontrolled.

To reproduce from a checkout containing both implementation commits, run from the repository root in PowerShell:

```powershell
$env:PYTHONHASHSEED = '0'
python -B -S -W error diagnostics/ast-gate/runtime_costs.py --output ast-gate-local.json
```
