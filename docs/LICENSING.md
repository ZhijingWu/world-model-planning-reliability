# License and redistribution review

The root MIT license covers Zhijing Wu's original runtime, tests, example, public packaging/verification code and associated repository documentation. Numerical measurements in `results/` are factual research records; no rights to excluded third-party content are granted by including those numbers. The root license does not assign Zhijing Wu's copyright to upstream files.

## Redistributed upstream software

`third_party/PatchWorld/` contains seven released generated-model Python files and their base interface, unchanged from retained source at `5079da9203913381f45ed2e1df92c73c30571e2e`. Their license is MIT, copyright (c) 2026 HKBU KnowComp. The complete original notice is retained at `third_party/PatchWorld/LICENSE`; file hashes and immutable origins are recorded in `PROVENANCE.json`. The retained license was compared byte-for-byte with [the pinned upstream LICENSE](https://raw.githubusercontent.com/HKBU-KnowComp/PatchWorld/5079da9203913381f45ed2e1df92c73c30571e2e/LICENSE). No upstream code was relicensed as the author's invention.

## Material not redistributed

- PatchWorld trajectory dataset: [upstream dataset](https://huggingface.co/datasets/HKBU-KnowComp/patchworld-trajectories), pinned revision `9342e2cbee1f8579b5423ed5821f6ad8a81ab773`. Its primary metadata reports MIT. Raw trajectories and underlying benchmark text are nevertheless excluded; users must check source terms when acquiring them.
- WebShop product/catalog and human-instruction assets: excluded. Redistribution rights of the acquisition mirrors were not independently established. Official acquisition references and exact hashes replace rehosting; exact reruns depend on obtaining matching lawful assets.
- WebShop, AgentGym and LMRL-Gym code: external source references only; no vendored files. Their original terms apply to independent acquisition. No broad relicensing claim is made for them.
- Font binaries, dependency environments, model checkpoints and source archives containing private logs: excluded.

## Note and figures

Copyright (c) 2026 Zhijing Wu. The files under `note/`, including the PDF, manuscript, original diagrams and public source ZIP, retain the author's copyright; no additional reuse license is granted here. Citations refer to separately owned works. The PDF has subset-embedded fonts from the existing finalized artifact; font files are not redistributed. The manuscript uses locally installed fonts when compiled.

This review establishes a redistribution basis for the included software subset. It does not grant rights to excluded data or certify every possible downstream use.
