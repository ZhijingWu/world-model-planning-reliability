# Public packaging changes

Frozen originals were read-only. `src/wctr/isolation.py` is byte-identical to the frozen Stage 2/3 core, SHA-256 `4528627f1922286e3058a81c2439f682dde33f8deb9a10ebb5170b8a11b7b612`. The seven test bodies are unchanged; only their import points to `wctr.isolation`. No planner parameter or generated-model dynamics was tuned for this release.

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

The retained frozen protocols still identify original implementation/source hashes, including omitted files. Public adapted files are not claimed to have those original hashes. `docs/PROVENANCE.json` records original and public hashes and transformations; `docs/public_source_hashes.json` hashes the public Python source. New example/verification/setup guidance are packaging work, not new experimental evidence.

Original report generators, acquisition probes, intermediate experiments, raw traces, full environment copies, profiling logs and old source ZIPs are omitted to keep this release small and avoid private paths/third-party text. Reconstructing completed aggregate results and testing the core is self-contained; exact native re-execution depends on external assets and a compatible runtime.
