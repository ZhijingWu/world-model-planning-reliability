# Public packaging changes

The Stage 2/3 studies used the historical runtime in [publication commit 3c902203](https://github.com/ZhijingWu/world-model-planning-reliability/tree/3c9022030323bd22e05b3f5276531eaa542cb1eb). Its exact bytes are now in [experiments/frozen/isolation.py](../experiments/frozen/isolation.py), SHA-256 `4528627f1922286e3058a81c2439f682dde33f8deb9a10ebb5170b8a11b7b612`. Both historical experiment entry points import this file through a digest-checked loader. The installable runtime in [src/wctr/isolation.py](../src/wctr/isolation.py) includes subsequent repairs and is exercised by the current unit tests.

| File(s) | Adaptation |
| --- | --- |
| `experiments/stage*/discover.py` | Source/data/model paths are repository-relative or environment-configured. Model code comes from the vendored MIT subset; raw assets from `.data/` or `WCTR_DATA_ROOT`. Outputs use `.runs/stage2` or `.runs/stage3`, optionally `WCTR_RUN_ROOT`. |
| `stage2/benchmark.py` | Imports shared portable paths; reads the retained config beside the script; creates parent output directories. Original planner/task/deadline semantics retained. |
| `stage3/live_wordle.py`, `live_webshop_smoke.py` | Portable paths to models/data; original environment interface adaptation retained. Helpers are used by the final study. Their standalone historical smoke entry points are archival helpers, not publication-verified rerun commands. |
| `stage3/live_study.py` | Uses the public source manifest in place of original-layout implementation-hash checks; requires Windows, creates isolated output directories and uses fresh measured shared setup accounting. Original search/runtime/evaluation logic retained. |
| `stage3/run_recorded.py`, `prepare_webshop.py` | Portable output/data locations; original Windows CPU accounting and official conversion call retained. |
| `stage3/run_study.py` | Added main/CLI guard and explicit `--execute`; fresh measured shared setup CPU/wall required; sets `PYTHONHASHSEED=0`; resolves worker by script location. Original eight-worker order and cost checks retained. |
| `stage3/public_config.py` | New packaging helper checks public source hashes and overrides historical shared setup costs with new measured values. Historical costs remain in archived evidence, not silently reused as fresh costs. |
| Public results/protocol | Numerical projections and omission of one excluded smoke instruction; documented in `results/README.md` and provenance. |
| Note source package | Exact final PDF/manuscript/style/figures/reference metadata; replaces private evidence/provenance with public-safe metadata and excludes compilation logs. |

The frozen protocols and [original provenance ledger](PROVENANCE.json) retain the paths and hashes from publication. The evidence verifier resolves the ledger's original `src/wctr/isolation.py` entry to the archived runtime above. The [current source manifest](public_source_hashes.json) covers both runtimes and the import shims. The [historical source manifest](https://github.com/ZhijingWu/world-model-planning-reliability/blob/3c9022030323bd22e05b3f5276531eaa542cb1eb/docs/public_source_hashes.json) identifies the original packaging files.

Original report generators, acquisition probes, intermediate experiments, raw traces, full environment copies, profiling logs and old source ZIPs are omitted to keep this release small and avoid private paths/third-party text. Reconstructing completed aggregate results and testing the core is self-contained; exact native re-execution depends on external assets and a compatible runtime.
