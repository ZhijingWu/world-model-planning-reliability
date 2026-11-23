# When a shared write changes a planning decision

Raw and Full Copy chose different first actions on **7 of 64 prospectively sampled SciWorld states** (10.94%). A state counted once if at least one of six fixed visit orders produced a difference. The equal-tailed 95% interval for the 231 eligible source-item representatives is **13–45 representatives, or 5.63%–19.48%**. Blocking one traced write restored the affected sibling input and the reference first action on six of the seven states, in 10 of the 28 orders with a decision difference. [Protocol](protocol.md) · [Frozen frame and sampled IDs](public/manifest.json) · [Recomputed statistics](public/analysis.json)

## Sampling and work

The first 100 test trajectories and every item seen in that prefix or the training split were excluded. Of 1,359 test trajectories, 100 were in the prefix, two further trajectories shared a prohibited item, and 54 had fewer than three distinct commands. The remaining 1,203 trajectories represented 408 source items. The protocol preassigned one trajectory and step per item. Historical-root matches removed 167 representatives and duplicate roots removed another ten. The simple random draw selected 64 of the remaining 231. Each selected source item, trajectory and canonical root is distinct. The actions are commands observed over the complete source trajectory, so they can include commands logged after the sampled step. This is a program-planning candidate bank with a synthetic goal walk. [Sampling procedure](prepare.py) · [Input manifest](public/manifest.json)

Each state contributed six paired orders, three candidate actions and nine depth-two leaves per order. Raw, independent per-edge Full Copy and frozen WCTR each made 4,608 search calls. Together they made 13,824 search calls, with 12,288 WCTR calibration calls, 2,304 independent replay calls and 336 intervention search calls separately accounted for. All 64 states completed the reference and WCTR controls. Full Copy gave the same path values and decision across orders. WCTR preserved its callers and matched those values on every path. It took Full Copy on **4,608/4,608** search calls, with zero deoptimizations and zero added witness paths. [Public edge fingerprints and decisions](public/results.json.gz) · [Snapshot verification](public/verification.json)

## What changed between branches

Each state and paired order contributes at most once to a row. Rows measure successive or overlapping effects. Counts in the final column use individual calls or leaves where indicated. [Per-state and per-order analysis](public/analysis.json)

| Raw compared with Full Copy | States / 64 | Orders / 384 | Edge or leaf count |
| --- | ---: | ---: | ---: |
| Raw changed its immediate parent value | 15 | 90 | 90 / 4,608 calls |
| A corresponding edge received a different input | 15 | 90 | 604 / 4,608 inputs |
| At least one leaf score differed | 15 | 90 | 304 / 3,456 leaves |
| Root score vector differed | 8 | 46 | |
| Set of maximizing roots differed | 8 | 46 | |
| Root ranking, including ties, differed | 8 | 46 | |
| Chosen first action differed under the primary rule | 7 | 28 | |

Fifteen states showed a changed leaf score. Eight of those kept the same first action in all six orders. In 62 orders, scores changed and the primary decision held. In 294 orders both scores and first action held. This explains why a contaminated branch input alone is insufficient evidence of a decision change. [Paired records](public/analysis.json)

## Ties and causal interventions

The primary decision rule chooses the lowest frozen index among maximizing roots. Full Copy had a tied maximum in all 384 orders, including 306 three-way ties. Raw had a tied maximum in 372 orders, including 330 three-way ties. A strict winner appeared under Raw in 12 orders on four states. No reference strict winner disappeared or was replaced. Among the 28 primary decision differences, the number of maximizing roots changed from two to three in 18 orders, two to one in six, three to one in two, and three to two in two. [Per-arm scores and tie sets](public/results.json.gz)

Under the predeclared **highest-index** sensitivity rule there were differences on 3/64 states and 10/384 orders. Those three states also showed a lowest-index difference in at least one order. Only two paired orders changed under both rules. Another 26 changed only under lowest index and eight only under highest index. The published tie rule therefore matters both to the estimated frequency and to which specific comparisons change. [Sensitivity records](public/analysis.json)

| Task ID | Primary flips / 6 orders | Rescues / primary flips | Highest-index flips / 6 orders |
| ---: | ---: | ---: | ---: |
| 3155 | 6 | 2 / 6 | 0 |
| 10696 | 2 | 1 / 2 | 2 |
| 10965 | 4 | 2 / 4 | 4 |
| 14645 | 2 | 1 / 2 | 4 |
| 23529 | 6 | 2 / 6 | 0 |
| 26388 | 6 | 2 / 6 | 0 |
| 27103 | 2 | 0 / 2 | 0 |
| Other 57 states combined | 0 / 342 | No intervention triggered | 0 / 342 |

Each intervention reran its Raw order from a fresh root and changed only the earliest traceable writing edge to a per-edge full copy. All 28 interventions restored the measured downstream sibling input. Ten restored the reference first action, with the same second action in those ten prospective cases. The other 18 retained a different first action. Every one of the seven affected states had at least one unresolved order. The tracing rule found one candidate writing edge per changed order. The 18 unresolved comparisons provide no proof that multiple writes were necessary. No additional rescue variants were tried. [Private-snapshot audit counts](public/verification.json) · [Public rescue fingerprints and selected paths](public/results.json.gz)

## Replay and interpretation

| Arm | Search reports exact / 384 | Exact on independent replay / 384 | Search exact, replay misses | Search misses, replay exact |
| --- | ---: | ---: | ---: | ---: |
| Raw | 328 | 310 | 24 | 6 |
| Full Copy | 354 | 354 | 0 | 0 |
| Repaired WCTR | 354 | 354 | 0 | 0 |

The 24 false goals occurred on six states. None of those six had a primary root-action flip. Replay tests the two-action sequence, while the primary endpoint compares its first action. A partial-score winner can still be consistent with its replay. [Public replay records](public/results.json.gz) · [Recomputed counts](public/analysis.json)

The prospective study extends the original task-1975 case. A controlled intervention restored the first action on additional held-out states, while leaf-score differences were more common than decision differences. The strength of that conclusion depends on the comparator and decision rule. All Full Copy maxima in the sample were tied, so strict-to-strict reversals could not be assessed. The finite-population interval inverts the hypergeometric tails for random sampling without replacement over the sealed frame. Shared code, related tasks, the depth-two search, recorded command pool and goal construction limit transfer to other planners. The unique-state estimate neither weights all transitions equally nor measures native environment success. [Original case study](../sciworld-fixed-work-v1/public/report.md) · [Preregistered analysis](protocol.md)

**Next question.** Does contaminated search change an action when the isolated planner has a unique best choice? A further prospective test could freeze a state-disjoint bank and an externally justified scoring rule before looking at outcomes, then measure decisions by the reference margin. Native utility would require an independently measured environment endpoint.
