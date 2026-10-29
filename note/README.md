# Final independent research technical note

The [PDF](Zhijing_Wu_World_Model_Planning_Note_Final.pdf) is the exact finalized two-page outreach note, SHA-256 `4d29fead79bf244b57198abc3d9c04af1f338a85d546c5b0dbd1d9a19e4479d1`. It emphasizes state ownership, WCTR and decision-relevant future work, while retaining mixed controlled outcomes, the native tie and competitive simpler controls. It does not imply UC San Diego affiliation or endorsement.

The manuscript, style, vector TikZ/PGFPlots figures and reference metadata are unchanged. The public source ZIP omits private filesystem provenance and compilation logs; `assets/public-evidence.json` points to the public evidence. The complete frozen local archive remains authoritative. The original local source ZIP is not redistributed.

## Build

Use XeLaTeX with `geometry`, `lmodern`, `fontspec`, `amsmath`, `amssymb`, `xcolor`, `tikz`, `pgfplots`, `fancyhdr` and `hyperref`. The original style uses locally installed Arial and Consolas. No font binaries are included. From this directory:

```sh
xelatex -interaction=nonstopmode -halt-on-error -output-directory=build Zhijing_Wu_World_Model_Planning_Note_Final.tex
```

Create `build/` first. A local rebuild may differ in PDF metadata/font versions; the committed PDF remains the exact final artifact. The public source was compiled during publication in a separate scratch directory, and its two-page output was checked. Both pages of the committed final PDF were rendered and visually inspected. No regenerated PDF replaces the finalized one.

Copyright (c) 2026 Zhijing Wu; note/PDF/figures are outside the root software MIT license. Third-party cited works retain their own rights.
