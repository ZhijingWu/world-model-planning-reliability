# Release review · 2026-11-23

## Decision and provenance

The original SciWorld research passed the Phase A review and was merged as PR #2. PR #3 contains the prospective protocol, evidence and professor-facing materials. [Original PR](https://github.com/ZhijingWu/world-model-planning-reliability/pull/2) · [Prospective PR](https://github.com/ZhijingWu/world-model-planning-reliability/pull/3) · [Prospective preregistration](https://github.com/ZhijingWu/world-model-planning-reliability/commit/31f7691304728af5c5dc032453ec3e08cbfb297d) · [Evidence commit](https://github.com/ZhijingWu/world-model-planning-reliability/commit/8c6bfc9dc92f3e0e53be7def3b867036cb1b8e2a)

| Review item | Verified record |
| --- | --- |
| PR #2 reviewed head | `11ddff4d1a3a7af5da2728c0b5e368b8573c41ee`. Eight Windows/Ubuntu jobs passed on CPython 3.10–3.13. [PR CI](https://github.com/ZhijingWu/world-model-planning-reliability/actions/runs/45168734228) |
| PR #2 merge on main | `512fddf272aed7f6a73d8b81b4787e4c8b1be301`. The merged and reviewed trees are identical. All eight main-branch jobs passed. [Main CI](https://github.com/ZhijingWu/world-model-planning-reliability/actions/runs/45172043534) |
| Research runtime for both SciWorld banks | `wctr-runtime-repair-2026-11` → `4ba67940378b959a07e63426cf4d3d3bdaf93c86`. Core SHA-256 `15f0f1c7e0baade3987a3bfb0730b941ae0048a846142cbeaa2aefc928f841e4`. [Pinned contract](https://github.com/ZhijingWu/world-model-planning-reliability/blob/4ba67940378b959a07e63426cf4d3d3bdaf93c86/docs/SUPPORTED_STATE.md) |
| Original input seal | SHA-256 `c269fc2ceefd9afdf4b11ed98e56750016169ef7c456eee5a3100ca776a5ba8a`, committed with the original search code before intervention runs. [Original seal](https://github.com/ZhijingWu/world-model-planning-reliability/commit/aa5e25ca293691331800762499cdd1a3f033cf85) |
| Prospective input seal | SHA-256 `cfc5992f9293378fca1b6ad3809a3e60c987ab89121b37a200f44c7a7ad8537e`. The input manifest, public frame, sample, verifier and protocol were pushed before any prospective arm executed. [Manifest](../studies/sciworld-prospective-v1/public/manifest.json) |

## Research review

**Research question.** The README opens with the writing edge whose successor agrees with the reference while its parent changes. The figure follows that write into the next sibling, shows its score and selected action, and preserves the unresolved interventions. The note links directly to that trace, then tests the mechanism on held-out states. These checks review content and layout; no timed reader study was conducted. [Figure](figures/task-1975.svg) · [Research note](WCTR_Research_Note.pdf)

**Empirical ML.** The independent check regenerated the equal-probability sample from its finite frame, excluded repeated/prohibited roots and source items, recomputed leaf-to-root score reductions and ties, compared each corresponding edge, and inspected actual private values for the earliest carried writes. The 384 prospective orders contribute 64 sample units. The finite-frame interval accounts for sampling without replacement. All seven affected states also had an unresolved order. The six states with Raw false goals were disjoint from the seven with primary flips. These are separate endpoints. [Statistics](../studies/sciworld-prospective-v1/public/analysis.json) · [Private-snapshot verification record](../studies/sciworld-prospective-v1/public/verification.json)

**Systems.** Both SciWorld bank verifications confirmed path-wise agreement, parent preservation and Full Copy fallback on all WCTR search calls. The figure compares three actual recorded paths, including the rescue whose second action still differs from the reference. The historical eight worker records across four methods and two domains and historical runtime cost comparisons retain their own pinned sources. Publication checks compare 47 original files, the earlier proposal and actual Stage 2/3 imports to their frozen bytes. The local CPython 3.13.5 release gate ran 47 unit tests, the example, the historical evidence verifier and both import checks. [Release gate](../tools/release_gate.py) · [Historical costs](../diagnostics/ast-gate/README.md)

## Repeatability, privacy and visual checks

- A fresh local checkout of the pre-intervention commit independently retrieved both full dataset files and reconstructed all private study inputs. The rerun matched all 64 public task records, the complete results-file digest, all 14,365 private trace records, and both derived JSON artifacts byte for byte. This same-host repeat adds no states to the sample. [Commands and digests](../studies/sciworld-prospective-v1/README.md)
- The public tables retain fingerprints, local action indices, scores and counts. Public string fields were also compared against raw action, observation and original source-ID strings from the two complete splits. No exact raw-string matches appeared. The hashed source IDs can be linked to the public upstream corpus. Reconstructed observations, task pickles, native logs and exact edge snapshots stay local. [Dataset terms](../docs/LICENSING.md)
- The note was compiled twice with XeLaTeX. Both A4 pages and the vector figure were rendered and visually inspected. All fonts are embedded. Of the 20 clickable annotations, 16 point to 12 distinct project files at immutable revisions. The other four link to three primary papers and OpenSpiel’s versioned state interface. The released PDF SHA-256 is `cfbe8de0078a912336c86b824efe8efbc01d9b8caeab62f4681d993726009dd1`. [Build recipe](BUILD.md) · [Editable source](WCTR_Research_Note.tex)
- The figure generator checks the writing-edge successor, caller and successor sharing, later sibling input and restored reference first action before drawing the worked case. The SVG and PDF are generated from numerical records. [Figure source](figures/draw_case.py) · [Public case records](../studies/sciworld-fixed-work-v1/public/results.json)

For an installation-free public check, run the two SciWorld verification commands from the [three-level reproduction guide](../studies/sciworld-prospective-v1/README.md). To repeat the Phase A private audit after reconstructing that bank, run the following from the repository root with the original bundle in `.runs/v1`.

```sh
python -B -S -W error studies/sciworld-fixed-work-v1/sciworld_verify.py --bundle .runs/v1 --manifest-sha256 c269fc2ceefd9afdf4b11ed98e56750016169ef7c456eee5a3100ca776a5ba8a
python -B tools/release_gate.py
```

The same eleven original study inputs can be regenerated publicly. A public reconstruction writes its own setup manifest and that run must use its newly printed seal. [Original bank reconstruction instructions](../studies/sciworld-fixed-work-v1/README.md)
