# Selected evidence, not fresh experimental runs

`stage2/` retains all 7,200 final per-run numerical records (five programs × 80 tasks × six methods × three repeats), all 30 summary/contract rows, and all 25 paired comparisons. The `path` and `goal_walk` text columns were removed. `source_item_clusters.csv` contains only program/trajectory indices and SHA-256 labels of original source-item identifiers; it enables exactly the original cluster bootstrap without rehosting source text. `discovery.json` contains aggregate diagnostics only.

`stage3/` retains all 448 final method-task numerical records plus the completed analysis and complete-process cost table. Initial observations and action text were omitted; canonical action-sequence SHA-256 values were added to support paired-action equality. Machine-specific command arrays were removed from cost records. No numerical fields were changed.

Public projections are linked to original SHA-256 values by [PROVENANCE.json](../docs/PROVENANCE.json). Original protocols' implementation/source hashes identify archival files, not the adapted portable harness; the latter has its own [manifest](../docs/public_source_hashes.json). The full original archives remain authoritative and are not uploaded wholesale.

Run `python experiments/verify_evidence.py` to check hashes, all controlled summary means, all paired effects/bootstrap intervals, selected discovery/contracts, native rates/check counts/paired hashes and charged lifetime costs. This command does not run world models, environments or new experiments. Aggregate analysis fields whose reconstruction requires excluded raw traces (for example root-candidate/forecast comparability details) remain archived summaries, not independently reconstructed raw-trace claims.
