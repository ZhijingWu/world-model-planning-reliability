# Does state contamination change the first action in SciWorld?

Raw and Full Copy selected different root actions on **1/11 evaluable states** (task 1975) and 6/66 paired visit orders. Copying only the input at the earliest traced writing edge restored both the affected sibling input and the reference action in **2/6 interventions**. In 4 further orders the same intervention restored the sibling input while the decision difference persisted. Those orders remain causally unresolved.

Raw execution changed its caller's edge-parent value on **54/792** search transitions. Across evaluable orders, 328/792 branch inputs differed from the corresponding Full Copy input in value or internal sharing. 148/594 leaf scores differed, and the root score vector differed in 30/66 orders. 36 orders had a score difference with the same selected root action.

## State bank and decisions

The frozen bank contains nine states where a historical Raw plan failed replay and two nearby states from the same trajectories where historical replay succeeded. Each state contributes six repeated orders. The task-level denominator counts each eligible state once.

| Historical cohort | Frozen | Eligible | Evaluable states | States with different action | States with verified rescue |
| --- | ---: | ---: | ---: | ---: | ---: |
| Historical failure | 9 | 9 | 9 | 1 | 1 |
| Comparison | 2 | 2 | 2 | 0 | 0 |

Raw writes count search edges. Changed inputs compare corresponding path inputs. Leaf scores count the nine leaves per order. Root scores and decisions count paired orders. Rows with fewer than three distinct actions remain in the frozen bank.

| Task ID | Cohort | Raw writes / edges | Changed inputs / edges | Changed leaf scores / leaves | Changed root scores / orders | Changed actions / orders | Rescues / interventions |
| ---: | --- | ---: | ---: | ---: | ---: | ---: | ---: |
| 364 | Historical failure | 6/72 | 40/72 | 20/54 | 0/6 | 0/6 | — |
| 374 | Historical failure | 6/72 | 44/72 | 24/54 | 6/6 | 0/6 | — |
| 476 | Historical failure | 6/72 | 36/72 | 16/54 | 4/6 | 0/6 | — |
| 863 | Historical failure | 6/72 | 44/72 | 24/54 | 6/6 | 0/6 | — |
| 925 | Historical failure | 6/72 | 36/72 | 16/54 | 4/6 | 0/6 | — |
| 1560 | Historical failure | 6/72 | 40/72 | 0/54 | 0/6 | 0/6 | — |
| 1963 | Historical failure | 0/72 | 0/72 | 0/54 | 0/6 | 0/6 | — |
| 1975 | Historical failure | 12/72 | 52/72 | 32/54 | 6/6 | 6/6 | 2/6 |
| 2166 | Historical failure | 6/72 | 36/72 | 16/54 | 4/6 | 0/6 | — |
| 390 | Comparison | 0/72 | 0/72 | 0/54 | 0/6 | 0/6 | — |
| 465 | Comparison | 0/72 | 0/72 | 0/54 | 0/6 | 0/6 | — |

## How the search chose an action

The fixed tree uses the first three distinct actions from each task. Each root action is followed immediately by its three children in frozen order. A leaf earns one point per matching top-level goal field. Each root action receives its best leaf score. Frozen candidate index breaks ties. Independent replay executes the selected two actions on fresh copies from the pristine root.

| Arm | Completed searches | Tied best roots | All three tied | Selected leaf exact in search | Exact after replay | False goals | Replay errors |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| Raw | 66 | 66 | 60 | 48 | 30 | 18 | 0 |
| Full Copy | 66 | 66 | 30 | 48 | 48 | 0 | 0 |
| Repaired WCTR | 66 | 66 | 30 | 48 | 48 | 0 | 0 |

A false goal requires exact whole-goal equality during search followed by a replay that misses the goal. A partial-score winner can replay consistently and still miss the goal. Raw and Full Copy ranked the three root actions differently in 30/66 orders.

### One paired order

Task **1975**, root visit order `[0, 1, 2]`. Raw scored the three root actions `[12, 12, 12]` and selected the path `[0, 2]`. Full Copy scored them `[11, 12, 12]` and selected `[1, 2]`. Indices follow the frozen candidate list. The first index is the root decision. The earliest edge whose input differed from Full Copy was `[0, 2]`. At leaf `[0, 2]`, Raw matched 12 goal fields and Full Copy matched 11. Copying only the input to edge `[0, 1]` restored the input to later sibling `[0, 2]` and restored the reference decision. The rescue selected `[1, 0]`, so its second action still differed from Full Copy's `2`. Review of the retained traces identified the model's `object_states` field at the first carried write in each of this task's six orders. The released transition starts with `belief.copy()`, which leaves that nested dictionary shared. [Model source](https://github.com/ZhijingWu/world-model-planning-reliability/blob/3c9022030323bd22e05b3f5276531eaa542cb1eb/third_party/PatchWorld/examples/generated_world_models/sciworld_benchmark_world_model.py#L154-L166)

## Isolation and interpretation

Full Copy passed the state-level controls on 11/11 eligible states. WCTR passed its state-level controls on 11/11. Full Copy had 0 edge-parent value changes and WCTR had 0. WCTR recorded 792 whole-state copies over 792 search calls, 0 deoptimizations and 0 net added witness paths. The three arms recorded 0 incomplete search or calibration runs.

Every WCTR search transition took Full Copy. The released model source selects the native fallback, and its belief includes sets. These trials provide evidence for isolation on this workload. The WCTR search arm did not exercise selective copying.

The run used 2,376 search transitions, 2,112 initial WCTR calibration calls, 396 independent replay calls and 72 rescue search calls. Trace inspection added 0 model calls. The frozen runtime commit was `4ba67940378b959a07e63426cf4d3d3bdaf93c86`.

The bank was selected using historical replay outcomes. It does not estimate prevalence among all SciWorld tasks. This experiment measures choices within a released executable model at depth two. Native environment outcomes and the causes of the earlier deadline-limited failures remain open.

**Next research question.** Test whether the verified single-edge rescues recur on a prospectively sampled bank with a fixed scoring rule and separately measured environment outcomes.

[Frozen inputs and protocol](manifest.json) [Public per-edge records](results.json) [Independent verification](verification.json)
