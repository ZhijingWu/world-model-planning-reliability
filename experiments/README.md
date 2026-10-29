# Reproduction levels

## Self-contained lightweight checks

From the repository root, follow the tested commands in [REPRODUCIBILITY_CHECK.md](../REPRODUCIBILITY_CHECK.md). Core tests, the illustrative example and `verify_evidence.py` need no environment assets, model downloads or inference APIs.

## Optional controlled planning harness

`stage2/benchmark.py` is the original controlled planner with packaging-only path adaptations. `--help` is lightweight; running it is a new measurement and was **not** done for publication. Use the unchanged [configuration](stage2/EXPERIMENT_CONFIG.json). Raw trajectories are excluded. Independently obtain the dataset at revision `9342e2cbee1f8579b5423ed5821f6ad8a81ab773` from https://huggingface.co/datasets/HKBU-KnowComp/patchworld-trajectories and check its terms. The frozen final acquisition used the first 32 nonempty train JSONL records and first 100 nonempty test records per final program, selected by order, not performance. Serialize retained records as original UTF-8 lines joined by LF plus a final LF; compare [asset hashes](../docs/ASSET_HASHES.json). `--mode final` uses train/test; development uses train/val and requires the separately hashed development prefixes.

The final command uses `--mode final`. Data layout (relative to `.data/` or `WCTR_DATA_ROOT`):

```text
trajectories/<program>/<program>_traj_train.jsonl
trajectories/<program>/<program>_traj_test.jsonl
```

The seven generated-model sources and base interface are included under `third_party/PatchWorld/`. No paid API or inference dependency is used by the planner.

```sh
python experiments/stage2/benchmark.py --help
# Optional, only after acquiring assets; runs a new measurement:
python experiments/stage2/benchmark.py --mode final
```

Generated results default to ignored `.runs/stage2/RESULTS/`; no frozen public evidence is overwritten. Deadline-dependent rates are machine-sensitive. A fresh run should not be presented as reproducing the exact historical timing result without comparison.

## Optional native evaluation

This release includes the retained planner/environment adapters and protocol, but **does not provide a one-command native environment installation or a verified fresh native rerun**. The following are acquisition/setup requirements, not claims of installation performed during publication.

Obtain these external repositories at the exact revisions, inspect their licenses, and install according to their pinned setup instructions in a separate compatible environment:

| Relative data directory | Upstream | Revision |
| --- | --- | --- |
| `WebShop` | https://github.com/princeton-nlp/WebShop | `64fa2a5c15c7daa698b9ac93f5bb5437b634c9bd` |
| `AgentGym` | https://github.com/WooooDyy/AgentGym | `3ef9235d23e68e7c2920c5422ad957dc8ced5c6c` |
| `LMRL-Gym` | https://github.com/abdulhaim/LMRL-Gym | `83abeedb3a461c3d7d20572b73318a259d85f2ac` |

The Wordle wrapper loads `AgentGym/agentenv-lmrlgym/agentenv_lmrlgym/wordle/environment.py` and points its vocabulary to `LMRL-Gym/llm_rl_scripts/wordle/vocab`. Its imported interfaces require packages such as numpy, transformers and tqdm even though no neural checkpoint is used. WebShop also needs its pinned Python dependencies, spaCy language package, Java/Lucene search/index tooling and official 1k-product/human-goal files. The [recorded runtime inventory](../docs/native_runtime_inventory.txt) lists the original Python environment; it is not a minimal dependency lock, a cross-platform installation guarantee, or an instruction to install every listed package. The measured native study used Windows and Python 3.10.21.

Obtain WebShop data through the [official setup instructions](https://github.com/princeton-nlp/WebShop/blob/64fa2a5c15c7daa698b9ac93f5bb5437b634c9bd/setup.sh); this repository deliberately does not host data from acquisition mirrors whose redistribution rights were not established. Match the exact files in `docs/ASSET_HASHES.json`, especially the three `SOURCES/WebShop/data/` JSON hashes and LMRL vocabulary. If the matching catalog cannot be obtained, an exact native rerun is unavailable; a different catalog is a different evaluation.

The final protocol identifies all task IDs/seeds, action/expansion/interaction limits and historical accounting. Ensure `PYTHONHASHSEED=0`, use a direct Windows CPython executable (the original venv launcher can omit child CPU), and isolate a new `WCTR_RUN_ROOT` for each rerun. Convert/index WebShop with its official tools; `stage3/prepare_webshop.py` retains the original official conversion call. Measure complete shared preparation CPU/wall afresh and divide the shared charge over four arms. Then use the guarded runner:

```sh
python experiments/stage3/run_study.py --help
# Optional, substitute newly measured nonnegative per-arm setup seconds:
# python experiments/stage3/run_study.py --execute --shared-setup-cpu <seconds> --shared-setup-wall <seconds>
```

The runner sets the worker hash seed, uses fresh shared setup charges and enforces the frozen 180 CPU-second lifetime allowance and 300-second wall cap. Asset provisioning CPU was not included in the original measurement. Paths/configuration/imports and run safeguards were adapted for packaging; see [PACKAGING.md](../docs/PACKAGING.md). No changes to planner/model semantics are claimed or required. External environments/data were not downloaded or executed for publication.
