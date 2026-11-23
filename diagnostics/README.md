# Runtime cost diagnostic

## Measurements from 2026-11-23

The implementation commit was `eb913f4d620ce5ff412d1cbab717b144b45da548`. The harness verified that its Runtime bytes matched the checkout (SHA-256 `4ca52ea1cf27dc8fc38b27957ea2c8a935d49dd508560b1192f02bb46728fb8a`). The measurements came from one 64-bit CPython 3.13.5 process (Anaconda, MSC v.1929), Windows 11 build 26300, on an Intel Core Ultra 7 155H. Times are elapsed microseconds per transition. The first five timing columns give medians of batch means. The last two give the repaired WCTR interquartile range of batch means and its individually measured p95. [Raw timings, source hashes and counts](results/2026-11-23-runtime-costs.json)

| Rows | Operation | Original WCTR | Previous PR | Repaired WCTR | Journal Only | Full Copy | Repaired Q1–Q3 | Repaired p95 |
| ---: | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 4 | Read | 2.42 | 21.04 | 7.53 | 7.07 | 16.41 | 7.23–7.88 | 22.50 |
| 4 | First append | 39.15 | 40.62 | 40.54 | 46.50 | 17.58 | 37.04–46.99 | 90.40 |
| 4 | Calibrated append | 26.34 | 32.30 | 26.07 | 51.30 | 15.40 | 23.10–27.88 | 63.00 |
| 4 | Reachable-set read | 2.93 | 58.78 | 37.09 | 40.66 | 29.55 | 27.94–41.85 | 81.70 |
| 64 | Read | 2.94 | 201.29 | 84.90 | 78.17 | 198.88 | 73.04–89.61 | 147.30 |
| 64 | First append | 362.50 | 401.63 | 409.10 | 434.00 | 202.06 | 366.28–481.49 | 514.10 |
| 64 | Calibrated append | 169.45 | 212.39 | 162.17 | 431.41 | 181.19 | 149.48–172.54 | 313.40 |
| 64 | Reachable-set read | 2.71 | 352.64 | 212.42 | 190.87 | 196.81 | 184.78–246.36 | 369.60 |
| 256 | Read | 3.83 | 879.44 | 432.73 | 383.34 | 905.55 | 267.60–507.47 | 909.50 |
| 256 | First append | 1342.74 | 1509.40 | 1391.33 | 1379.53 | 811.81 | 1320.70–1656.55 | 2477.10 |
| 256 | Calibrated append | 847.82 | 832.95 | 683.90 | 1855.12 | 876.48 | 579.93–846.25 | 6380.40 |
| 256 | Reachable-set read | 3.59 | 1709.14 | 830.48 | 895.79 | 983.07 | 798.45–1048.59 | 2586.00 |

The original's 2.94 µs clean read at 64 rows avoids the entry safety check. The repaired read still grows with graph size. Journal Only had lower read medians at all three sizes. Full Copy was faster on every first append, including 202.06 µs against repaired WCTR's 409.10 µs at 64 rows. The calibrated 64-row append was faster with WCTR than either control. At four rows Full Copy also won on calibrated appends. The 256-row calibrated append had a 6.38 ms individual p95, with substantial variation across timing rounds.

Across the three sizes, each arm executed 2,400 timed transitions per operation. On reachable-set reads, the previous PR, repaired WCTR and repaired Journal Only each recorded 2,400 whole-state copies. They recorded zero on the other 7,200 calls. Original WCTR recorded zero copies in all four scenarios, including this particular order-insensitive set read. Full Copy made one copy on every call (9,600). These counts reflect fixture placement and the chosen mixture of actions.

### Where time went at 64 rows

| Isolated operation | Median µs |
| --- | ---: |
| Previous PR entry graph | 167.67 |
| Previous PR type scan on already indexed nodes | 14.05 |
| Previous PR frontier match | 0.61 |
| Previous PR reverse alias closure alone | 0.67 |
| Previous PR alias fork with graph supplied | 2.55 |
| Previous PR alias fork including graph construction | 171.93 |
| Full `deepcopy` alone | 196.17 |
| Previous PR guarded append + plain pop / direct append + plain pop | 0.99 / 0.13 |
| Repaired type discovery, clean state | 67.57 |
| Repaired type discovery, set under last / first root key | 0.66 / 70.94 |
| Repaired reverse index with type check | 137.79 |

The read and fallback measurements support deferring the reverse index until a witness or actual write needs it. First writes can still pay for discovery, an input graph and a successor graph. The measured closure and frontier costs provided little motivation to specialize them on this fixture. Caching by root identity would miss changes below that root between calls. Certifying a method as read-only from the absence of an explicit write would miss implicit defaultdict insertion and order-sensitive set observation. The implementation keeps per-call discovery and whole-state fallback for these containers.

This is one shared host and one model with simple reads and a single aliased write. The two timing passes are separate and include ordinary scheduling and allocator variability. CPU affinity, frequency, thermal state and system load were uncontrolled. The retained samples permit inspection of unusually large tails. They do not establish native planner timing, fallback prevalence on application inputs or a general speedup. The 33,692 original checks remain historical.

## Reproduction and timing boundaries

Run the same synthetic comparisons from a repository checkout with the two historical commits available. Set `PYTHONHASHSEED=0` before starting the interpreter. For example, in PowerShell:

```powershell
$env:PYTHONHASHSEED = '0'
python diagnostics/runtime_costs.py --output runtime-costs-local.json
```

The script loads the original and previous PR implementations from Git objects at `3c9022030323bd22e05b3f5276531eaa542cb1eb` and `7e57af85d0e8a6c7ee16a325c51eabdbcb015822`. It checks the original against the frozen Runtime. The repaired WCTR and Journal Only arms use the working copy of `src/wctr/isolation.py`. The JSON identifies the exact source by SHA-256. Full Copy calls the ordinary model on one `copy.deepcopy(parent)` per transition, with a counter. Each instrumented model has its ordinary counterpart attached for fallback.

Each fixture has 4, 64 or 256 distinct rows, each containing a dictionary and a list. Two keys point to the same event list. A single model implements a read returning a small dictionary, one append returning the state, and a read returning the size of a reachable set. The set is under the **last** root key. This placement matters for traversals that can stop at the first set. The first append gets a fresh, preconstructed adapter per call. The calibrated append gives each supported adapter one witness before timing. Journal Only still journals the append. Fixture creation, calibration, model compilation, collection and correctness comparisons are outside the measured intervals. Each batch checks its final successor against raw-on-deep-copy, the parent's value and alias identity, and the written successor's alias identity.

For each size and scenario, every arm gets twelve warmup transitions. Ten matched throughput rounds then rotate and reverse arm order so every arm occupies every position twice. The table reports the median of ten batch means in microseconds per transition. The JSON also gives inclusive Q1/Q3, raw batch durations and independently sampled per-call wall times. Empirical p95 is nearest rank over 160 individually timed transitions per cell in a second counterbalanced pass. Throughput includes the Python loop, while individual times include the cost of reading the clock. Both include result replacement inside the measured interval and disable cyclic GC only during timing. Full-clone counts cover both timed passes and exclude warmup and calibration.

The component probes isolate individual calls on 64-row states. Names starting with `repaired_` use the working copy. Other probes use the previous PR. Each has 26 counterbalanced batches of 128 calls after twelve warmups. The reverse-closure probe repeats the work-list traversal in `alias_fork`. The prebuilt-graph fork includes that traversal and selective copying. The graph-inclusive fork also constructs the graph. The guarded dispatch probe binds and invokes an append on a receiver already known to be private, then removes the new element by a plain pop. Its control does the same append and pop directly. These primitive times overlap and cannot be summed into a transition cost.
