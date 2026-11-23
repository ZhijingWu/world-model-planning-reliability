# Build the research note and figure

The editable [LaTeX source](WCTR_Research_Note.tex) includes the [vector PDF figure](figures/task-1975.pdf). The [SVG figure](figures/task-1975.svg) uses the same data and layout. Both exports use the task-1975 paths from the public [selected-state study](../studies/sciworld-fixed-work-v1/public/report.md).

To regenerate the figure from the repository root, use Python with Matplotlib. The original build used CPython 3.13.5 and Matplotlib 3.10.0.

```sh
python professor-release/figures/draw_case.py --study studies/sciworld-fixed-work-v1 --output professor-release/figures
```

To typeset the note, use XeLaTeX with fontspec, geometry, graphicx, xcolor, booktabs, tabularx, fancyhdr and hyperref. The source uses locally installed Georgia, Arial and Consolas when available and includes TeX font fallbacks. The committed PDF embeds the fonts it uses. With the committed figure, typesetting requires no research data or Python packages.

```sh
cd professor-release
xelatex -interaction=nonstopmode -halt-on-error WCTR_Research_Note.tex
xelatex -interaction=nonstopmode -halt-on-error WCTR_Research_Note.tex
pdfinfo WCTR_Research_Note.pdf
```

The release PDF has two A4 pages. The authoring host set `SOURCE_DATE_EPOCH=1795420800`. Font and TeX versions can affect a rebuild's bytes and line breaks. The PDF's numerical evidence links target immutable study, runtime and historical publication commits.
