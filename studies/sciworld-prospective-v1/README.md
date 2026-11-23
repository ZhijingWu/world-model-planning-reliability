# Reproduce the prospective SciWorld study

On **7 of 64** sampled states, Raw and Full Copy selected different first actions in at least one of six visit orders. The finite sampling frame contained 231 distinct, held-out source-item representatives. The exact 95% interval for positives in that frame is 13–45 of 231 (5.63–19.48%). Six orders from one state count once. The repaired runtime matched Full Copy on every path and used a whole-state copy on all 4,608 WCTR search calls. [Protocol](protocol.md) · [Frozen sample and frame](public/manifest.json) · [Numerical analysis](public/analysis.json) · [Independent trace verification](public/verification.json)

The three levels below use PowerShell from the repository root. Python, Git and the standard library suffice. The original run and local repeat used 64-bit Windows, CPython 3.13.5 and `PYTHONHASHSEED=0`. Provide a clone containing this study and the `wctr-runtime-repair-2026-11` release. Its runtime commit is `4ba67940378b959a07e63426cf4d3d3bdaf93c86`. [Runtime contract](../../docs/SUPPORTED_STATE.md)

## Level 1 · Illustrate the failure

```powershell
$env:PYTHONPATH = (Resolve-Path src).Path
python -B -S examples/branch_isolation.py
```

The example asserts that a raw shallow-copy model can return the expected successor while changing its caller's state. It checks isolated sibling execution as well. This is a synthetic fixture. The experimental counts come from the recorded SciWorld searches. [Example source](../../examples/branch_isolation.py)

## Level 2 · Verify the retained evidence

```powershell
$v2 = 'studies/sciworld-prospective-v1'
$seal = 'cfc5992f9293378fca1b6ad3809a3e60c987ab89121b37a200f44c7a7ad8537e'
python -B -S -W error "$v2/verify.py" --repo . --bundle $v2 --manifest-sha256 $seal
python -B -S -W error "$v2/verify.py" --repo . --case-study
```

The first command verifies sample membership, 12 transitions per arm/order, frozen ties, scores and decisions, reference controls, replay outcomes, rescue summaries, unique-state counts and the hypergeometric interval. It checks the computed analysis against both published JSON records. The second command checks the earlier 11-state case study separately. Its nine historical failures and two comparison states never enter the prospective denominator. [Verification code](verify.py) · [Selected-state study and reconstruction](../sciworld-fixed-work-v1/README.md)

The public edge table is losslessly compressed. The verifier accepts a local `public/results.json` or directly reads `public/results.json.gz`. Its committed digest is computed on the **uncompressed** result bytes: `3fd6991b5d4b0fa68f88dbebc40e855be8bec01911caf9210c21634ca08359a6`. Exact object values, action strings and snapshots stay in a locally reconstructed bundle. With that bundle available, add `--private` to verify the leaf scores, alias fingerprints, continuously carried changes and isolated writing edges against the actual snapshots. The public report commits to the snapshot archive digest. [Public edge table](public/results.json.gz) · [Private trace audit record](public/verification.json)

## Level 3 · Reconstruct and execute the experiment

Use a fresh local destination for each new execution. The setup command downloads both complete files from the pinned dataset, checks them against SHA-256 and validates both historical prefixes. It reconstructs the entire sampling frame, reproduces the seeded sample and its candidate lists and goal walks, checks the published seal and writes the private inputs locally. The runner reads only the trusted task pickles produced by this setup. The final command derives fresh public counts and verifies them against the local private traces.

```powershell
$env:PYTHONHASHSEED = '0'
$v1 = 'studies/sciworld-fixed-work-v1'
$v2 = 'studies/sciworld-prospective-v1'
$scratch = '.runs/prospective-reproduction'
$bundle = "$scratch/bundle"
python -B -S -W error "$v2/prepare.py" --repo . --fetch --data-root "$scratch/inputs" --check-manifest "$v2/public/manifest.json" --bundle $bundle
$seal = (Get-FileHash "$bundle/public/manifest.json" -Algorithm SHA256).Hash.ToLowerInvariant()
python -B -S -W error "$v1/sciworld_run.py" --repo . --bundle $bundle --manifest-sha256 $seal
python -B -S -W error "$v2/verify.py" --repo . --bundle $bundle --manifest-sha256 $seal --private --write-summary "$bundle/public/analysis.json" --write-verification "$bundle/public/verification.json"
```

| Complete upstream input | Trajectories | SHA-256 |
| --- | ---: | --- |
| SciWorld test | 1,359 | `ebe6b9dbd9838bed92433fd3405d5ac8e5185eca74a77519c6b936b15921422b` |
| SciWorld train | 4,065 | `a6687372d3e305e7065825e52451b8799a6d3b9e5f5ab93c5e39984e75199492` |

Training source items are excluded from sampling. Initial WCTR calibration consumes 32 training **transitions** every time a fresh adapter starts. The complete test file supplies the held-out frame after removing the historical first 100 trajectories, their source items and prohibited or duplicate canonical root values. The dataset revision is `9342e2cbee1f8579b5423ed5821f6ad8a81ab773`. Observe the source terms when retrieving data, and keep the `inputs` and `bundle/private` directories local. [Pinned source files](https://huggingface.co/datasets/HKBU-KnowComp/patchworld-trajectories/tree/9342e2cbee1f8579b5423ed5821f6ad8a81ab773/sciworld) · [Licensing and redistribution](../../docs/LICENSING.md)

## What the fresh-checkout repeat established

A second, clean, detached checkout of the pre-intervention commit downloaded both upstream files again into an empty directory. It reconstructed all 231 frame records, 64 tasks, 32 calibration transitions and three private setup files. All 64 parsed public task records, the complete 15,743,528-byte public results file, the compressed and uncompressed private archive, and the regenerated analysis and verification JSON matched byte for byte. The compressed private trace SHA-256 was `481304c983973c0a21aba3efdd013d6b0a597c1029d3f4837b57e99d5d9a7900`. The decompressed SHA-256 was `4198a875108557f0bcc1425bcaa11e0816c418c2e8439227157b02a06d3af3ee` for 14,365 trace records. The verifier from this release was applied to that checkout's seal and outputs. This was a same-host local repeat; it adds zero independent sample units. [Pre-intervention commit](https://github.com/ZhijingWu/world-model-planning-reliability/commit/31f7691304728af5c5dc032453ec3e08cbfb297d)
