# Reproducibility check

The current regression suite exercises the repaired package. The historical evidence command checks archived records from [publication commit 3c902203](https://github.com/ZhijingWu/world-model-planning-reliability/tree/3c9022030323bd22e05b3f5276531eaa542cb1eb). The 33,692 checked WCTR transitions were produced by that earlier runtime.

## Commands

From the repository root, with Python 3.10+ and pip/setuptools available:

```sh
python -m pip install --no-deps --no-build-isolation -e .
python -m unittest discover -s tests -v
python examples/branch_isolation.py
python experiments/verify_evidence.py
python experiments/stage2/benchmark.py --help
python experiments/stage3/live_study.py --help
python experiments/stage3/run_study.py --help
```

The core, fixtures and evidence verifier import only the Python standard library. For an installation-free regression run, set `PYTHONPATH` to the repository's `src` directory (`$env:PYTHONPATH = (Resolve-Path src)` in PowerShell or `export PYTHONPATH="$PWD/src"` in a POSIX shell). The evidence verifier can run directly from a source checkout. It checks the historical runtime digest, the published records and the current source manifest. The Stage 2 and Stage 3 harnesses load the historical runtime for any optional experiment rerun.

## Correctness repair checks on 2026-11-23

On Windows, all 17 test methods (seven original and ten new), the branch-isolation example, and the public evidence verifier passed on CPython 3.10.21, 3.11.16, 3.12.13 and 3.13.5 with site packages disabled and `src` on `PYTHONPATH`. The regression-first commit reproduced all four audited defects on the original core. The new fixtures include exception rollback, aliased receivers, non-fresh copy results, set-order behavior, and tuple-cycle accounting on input forks and output grafts.

The verifier recomputed the published summaries from 7,200 historical controlled-planning records and checked 448 historical native method-task records. This repair ran no new controlled timing or native environment study. The original 33,692 WCTR checks remain attributed to the frozen runtime.

## Original publication checks on 2026-10-29

The following table records checks for the frozen publication. The dates, Python versions and test counts refer to that snapshot.

| Check | Outcome |
| --- | --- |
| Existing seven regression tests | 7/7 pass on CPython 3.10.21 and 3.13.5, including with site packages disabled (`-S`). |
| Minimal illustrative example | Pass on both versions; asserts unprotected parent mutation, same-program reference agreement, parent preservation and isolated siblings with WCTR. |
| Independent clean source copy and fresh Python 3.10 venv | Editable installation with no runtime dependencies succeeds; all seven tests, example and full evidence verifier pass without the original archive or private paths. |
| Controlled archived evidence | All 7,200 records checked; all 30 summary rows reconstructed, all 25 paired effects and their original 5,000-resample source-item intervals reconstructed; selected discovery and mutation-contract counts verified. |
| Native archived evidence | All 448 method-task rows checked against frozen IDs/seeds; four-way completion tie, paired action/initial-observation hashes, 33,692 WCTR checks and 134,768 four-arm checks verified; complete-lifetime CPU totals match. |
| Provenance/integrity | Public source/projection hashes check; WCTR core and final PDF equal their frozen originals byte-for-byte. |
| Optional harness entry points | Three `--help` commands pass on Python 3.10 without loading environments or executing studies. Python sources also pass syntax compilation. |
| Note source ZIP | Extracted independently and compiled successfully twice with XeLaTeX; exactly two pages. Rebuilt render is pixel-identical to the committed final PDF at 1,200-pixel page height. |
| Final PDF and figures | Exactly two A4 pages, 87,327 bytes; both pages rendered and visually inspected at normal viewing size. Vector diagrams, selected evidence and readable limitations are intact. |
| Documentation links | All local Markdown targets resolve. Twelve external reference/homepage/setup URLs returned HTTP 200 during prepublication checks. Public-repository URLs are checked after publication. |

## Exact artifact identifiers

- Frozen core [experiments/frozen/isolation.py](experiments/frozen/isolation.py), SHA-256 `4528627f1922286e3058a81c2439f682dde33f8deb9a10ebb5170b8a11b7b612`.
- Final PDF SHA-256: `4d29fead79bf244b57198abc3d9c04af1f338a85d546c5b0dbd1d9a19e4479d1`.
- Original Stage 3 reproducibility ZIP SHA-256: `ea86bad26a721ea751a2a2a4d0b3c812eda89ecb06dcb6c00bb8f5ec83587c5c`. The original ZIP is not redistributed because it contains raw assets/logs and machine-specific provenance.

## Scope that was not rerun

No controlled planning or native environment study was rerun. No paid inference, model training, checkpoint acquisition or new action-ranking experiment occurred. The proposed fixed-state/rollout-order experiment remains future work.

Optional harnesses preserve original planning/model semantics while adapting paths, imports, output isolation and integrity checks. See [PACKAGING.md](docs/PACKAGING.md). The native harness requires Windows and independently acquired matching environment/data assets; its installation and full execution were not freshly verified. CLI parsing is a limited check, not a claim of native reproduction. The original runtime inventory is descriptive rather than a portable dependency lock.

Excluded raw observations/action strings mean some trace-level analysis fields cannot be independently reconstructed from this small release. Published completion rates, paired action equality, check counts, controlled intervals and lifetime cost aggregates can be reconstructed from the retained numerical records and hashes. Exact catalog availability, external source terms and host timing remain reproducibility constraints.
