# Reproducing the SciWorld fixed-work study

This study follows the frozen Stage 2 state-selection procedure, then searches a fixed depth-two tree over the released SciWorld program. The bank contains nine historical replay failures and two historical comparisons. The original input manifest and search code were committed before running any arm. [Study report](public/report.md) · [Proposal](../../proposals/sciworld-fixed-work.md) · [Input seal](https://github.com/ZhijingWu/world-model-planning-reliability/commit/aa5e25ca293691331800762499cdd1a3f033cf85)

## Inspect the published evidence

| File | Contents |
| --- | --- |
| [manifest.json](public/manifest.json) | Pinned program, data, runtime and study code. All eleven root values, alias groups, action orders, goal walks and calibration inputs have fingerprints. |
| [results.json](public/results.json) | Every paired order, edge fingerprints, sharing IDs, scores, selected paths, replays, intervention targets and outcomes. Candidate indices are local to each task. |
| [verification.json](public/verification.json) | Counts recomputed from the private snapshots, separated by task and selection cohort. The verifier uses the recorded values without calling a model. |
| [Frozen runtime](https://github.com/ZhijingWu/world-model-planning-reliability/tree/wctr-runtime-repair-2026-11) | Merge commit `4ba67940378b959a07e63426cf4d3d3bdaf93c86`. Both Stage 2 and Stage 3 continue to import the historical runtime. |

The original manifest SHA-256 is `c269fc2ceefd9afdf4b11ed98e56750016169ef7c456eee5a3100ca776a5ba8a`. The public result SHA-256 is `5f523bc87db0454af6c89515d3052ea0408b22fe8c9f6d704c492f917af38f17`. Value and alias fingerprints support path comparisons. Private canonical snapshots, action text, observations and local task pickles can be reconstructed from the pinned public inputs.

## Reproduce from public inputs

Use a full Git checkout containing this study and the release tag. The original execution used Windows x86-64, CPython 3.13.5, the standard library and `PYTHONHASHSEED=0`. The commands below run in PowerShell at the repository root. A fresh bundle keeps each observation linked to the specific manifest that produced it.

```powershell
$env:PYTHONHASHSEED = '0'
$study = 'studies/sciworld-fixed-work-v1'
$bundle = '.runs/sciworld-fixed-work-reproduction'
$release = '4ba67940378b959a07e63426cf4d3d3bdaf93c86'
python -B -S "$study/fetch_prefixes.py" --data-root .data
python -B -S "$study/sciworld_prepare.py" --repo . --data-root .data --reference-manifest "$study/public/manifest.json" --bundle $bundle --runtime-sha $release --release-ref wctr-runtime-repair-2026-11 --study-code "$study/sciworld_run.py" --study-code "$study/sciworld_study_engine.py"
$seal = (Get-FileHash "$bundle/public/manifest.json" -Algorithm SHA256).Hash.ToLowerInvariant()
python -B -S "$study/sciworld_run.py" --repo . --bundle $bundle --manifest-sha256 $seal
python -B -S "$study/sciworld_verify.py" --bundle $bundle --manifest-sha256 $seal --summary "$bundle/public/verification.json"
python -B -S "$study/sciworld_report.py" --manifest "$bundle/public/manifest.json" --results "$bundle/public/results.json" --verification "$bundle/public/verification.json" --private-edges "$bundle/private/edges.jsonl.gz" --output "$bundle/public/report.md"
```

The download reads the first 100 test trajectories and 32 training trajectories from the pinned revision. Calibration consumes the first 32 **transitions**. The original seal cross-checked the reconstructed walks against the retained full planning CSV and all common fields against 240 public raw rows. Public reconstruction checks the originally sealed digests for all 80 candidate lists and goal walks, all eleven selected task records, and the 32 calibration inputs. A fresh public download and reconstruction reproduced the three private setup files byte for byte. [Pinned data](https://huggingface.co/datasets/HKBU-KnowComp/patchworld-trajectories/tree/9342e2cbee1f8579b5423ed5821f6ad8a81ab773/sciworld) · [Source terms](../../docs/LICENSING.md)

A new manifest records the public reproduction route, so its SHA and the enclosing results-file SHA differ from the original run. Compare the per-task records, including all edge fingerprints and counters. To check traversal, tie-breaking and rescue mechanics on a small synthetic fixture, run `python -B -S studies/sciworld-fixed-work-v1/test_fixed_work_engine.py`. The repaired runtime's regression suite runs separately with `python tools/release_gate.py`.
