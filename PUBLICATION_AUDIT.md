# Publication audit

Audit date: 2026-10-29. Author: Zhijing Wu, Sichuan University. This is independent research. The authorized publication target is https://github.com/ZhijingWu/world-model-planning-reliability.

## Presentation and scientific integrity

The release emphasizes the diagnosed state-ownership failure, its significance for branching search, the implemented WCTR runtime, the finite supported-state checks and a precise proposed question about decision-relevant simulator error. The final outreach PDF is the latest finalized version and is unchanged.

The README and [claims ledger](CLAIMS_AND_LIMITATIONS.md) distinguish input ownership, same-program output equivalence, finite branch-isolation checks, controlled program-goal completion, actual native success and runtime cost. The WebShop +17.5 pp result carries its generated-goal, 80-task, three-repeat, soft-10-ms context and source-item interval. Wordle's −9.2 pp controlled decline remains explicit. The four-way native tie (6/12 WebShop and 43/100 Wordle) and competitive cheaper simpler controls remain explicit. No general success, efficiency, superiority, theoretical-novelty or real-world-robot claim is made. The full-copy reference is not described as ground truth.

The future action-ranking experiment is explicitly proposed and unexecuted. References to RAP/LLM Reasoners motivate a research connection and do not imply validation, affiliation or endorsement by UC San Diego, Prof. Zhiting Hu or MixLab.

## Inclusion, condensation and exclusions

- Included unchanged: frozen WCTR core, latest final PDF, manuscript/style/vector figures/reference metadata, the small licensed upstream source subset, and selected numerical/configuration evidence where public-safe.
- Adapted transparently: test imports and optional harness packaging paths, source integrity namespace, isolated run output and fresh-run setup accounting. The changes are enumerated in [PACKAGING.md](docs/PACKAGING.md), with original/public hashes in [PROVENANCE.json](docs/PROVENANCE.json).
- Condensed: experimental presentation in the README and note. The public numerical tables retain all final controlled arms/programs and all final native method-task records, including negative or tied outcomes. Detailed CPU interpretation is in [EVALUATION.md](docs/EVALUATION.md), rather than dominating the note.
- Omitted: intermediate experiments/report generators, raw action/observation traces, product/catalog and human-instruction text, dependency environments, checkpoints, private logs, profiling paths and original archive ZIPs. Numeric projections preserve all highlighted quantities. Hashes replace raw action sequences/source-item labels where needed for pairing.
- Sanitized note source ZIP: unchanged manuscript assets plus public-safe evidence metadata and build guidance; original private provenance and compilation logs excluded. The original local source bundle remains intact.

These choices do not materially change the interpretation of any highlighted result. The complete frozen archives remain authoritative; the release is a selected research artifact, not their replacement.

## Evidence verification and preservation

`experiments/verify_evidence.py` reconstructs all 30 controlled summary rows, all 25 paired effects and bootstrap intervals from 7,200 numerical records, and verifies native completion/check/action-hash/cost aggregates from 448 records. All checks passed. It analyzes completed records only. [REPRODUCIBILITY_CHECK.md](REPRODUCIBILITY_CHECK.md) gives the tested commands and exact scope.

Before packaging, SHA-256 snapshots were taken of 232 frozen implementation, result, protocol, report/archive and final-note files; all were rechecked unchanged. Included upstream source files also match both retained originals and their immutable official revision. No original evidence or original Git history was modified/imported. No new study, paid API, training or checkpoint download was performed.

## License and privacy outcome

No material unresolved redistribution issue remains for the included material. All nine redistributed upstream files (eight Python source files and LICENSE) were compared byte-for-byte with official PatchWorld revision `5079da9203913381f45ed2e1df92c73c30571e2e`. The complete MIT notice, copyright (c) 2026 HKBU KnowComp, is retained. Original software uses the author's scoped MIT license. The note/PDF/figures retain author copyright outside that software license. The committed PDF's embedded TrueType fonts report editable-embedding flags (`fsType=8`); no font binaries are shipped separately.

Dataset metadata reports MIT for the pinned PatchWorld trajectory release, but raw trajectories and underlying benchmark content are excluded. Redistribution rights of WebShop acquisition-mirror data were not independently established, so that content is not included. Official acquisition references and content hashes replace rehosting. WebShop, AgentGym and LMRL-Gym remain external dependencies under their own terms. See [LICENSING.md](docs/LICENSING.md).

The candidate public tree, source ZIP members, extracted PDF text/metadata/annotations and complete reachable Git blobs were checked for credential patterns and personal filesystem paths. No detected credentials, private correspondence or personal local paths remain in the public content/history. A custom regex/content scanner and manual scope review were used; gitleaks was not installed. Such checks reduce disclosure risk and are not a guarantee that every possible secret format is recognized. Git author metadata uses the account's GitHub noreply address, not a personal email.

## Publication and remaining boundaries

The publication uses a fresh initial Git history, not the original experiment history. The initial tree is checked before committing; all reachable history is scanned before pushing. Remote verification covers the public URL, rendered README, exact PDF bytes, source/tests and published commit identity. The commit identifier and final remote status are reported with delivery, avoiding a self-referential hash inside this file.

The self-contained reproduction scope is the core tests/example and completed-record analysis. Optional full native reruns remain dependent on independently obtained matching assets, Windows accounting and a compatible runtime; no fresh native reproduction is claimed. There is no native-success or general efficiency advantage in the frozen study. The CV was not edited; [CV_PROJECT_ENTRY.md](CV_PROJECT_ENTRY.md) supplies two accurate draft bullets. No outreach email was sent.
