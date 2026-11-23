"""Render the actual task-1975 edge and decisions from the public v1 study."""
import argparse
import hashlib
import io
import json
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt


def require(condition, message):
    if not condition:
        raise ValueError(message)


def evidence(study):
    public = study / "public"
    raw_bytes = (public / "results.json").read_bytes()
    verified = json.loads((public / "verification.json").read_bytes())
    require(hashlib.sha256(raw_bytes).hexdigest() == verified["public_results_sha256"],
            "Public records differ from the verified run")
    require(verified["manifest_sha256"] == "c269fc2ceefd9afdf4b11ed98e56750016169ef7c456eee5a3100ca776a5ba8a",
            "Expected the frozen selected-state study")
    data = json.loads(raw_bytes)
    task = next(t for t in data["tasks"] if t["task_id"] == 1975)
    pairs = task["comparisons"]
    example = next(p for p in pairs if p["order"] == [0, 1, 2])
    intervention = example["rescue"]
    writer, sibling = tuple(intervention["writer"]), tuple(intervention["reader"])
    arms = {k: example["arms"][k] for k in ("raw", "full_copy")}
    arms["rescue"] = intervention["run"]
    edges = {name: {tuple(e["path"]): e for e in arm["edges"]} for name, arm in arms.items()}
    w, ref = edges["raw"][writer], edges["full_copy"][writer]
    require(writer == (0, 1) and sibling == (0, 2), "Wrong paired example")
    require(w["successor"] == ref["successor"], "Writing-edge successor mismatch")
    require(w["parent_before"] == ref["parent_before"] == ref["parent_after"], "Reference parent mismatch")
    require(w["parent_before"] != w["parent_after"] == edges["raw"][sibling]["parent_before"],
            "Missing carried change to the raw sibling input")
    require(edges["rescue"][sibling]["parent_before"] == edges["full_copy"][sibling]["parent_before"],
            "Rescue did not restore the shown input")
    require(w["shared_ids"]["parent_successor"] and not ref["shared_ids"]["parent_successor"],
            "Writing edge lacks the expected sharing relation")
    successes = sum(p["rescue"]["sibling_restored"] and p["rescue"]["reference_decision_restored"]
                    for p in pairs)
    input_only = sum(p["rescue"]["sibling_restored"] and not p["rescue"]["reference_decision_restored"]
                     for p in pairs)
    require(successes + input_only == len(pairs), "Unexpected rescue outcomes")
    return arms, {name: ed[sibling] for name, ed in edges.items()}, successes, input_only


def draw(study, destination):
    arms, sibling, successes, input_only = evidence(study)
    plt.rcParams.update({"font.family": "DejaVu Sans", "svg.fonttype": "none",
                         "pdf.fonttype": 42, "svg.hashsalt": "wctr-sciworld-task-1975-v1"})
    fig = plt.figure(figsize=(7.3, 3.72), facecolor="white")
    ax = fig.add_axes([0, 0, 1, 1], xlim=(0, 1), ylim=(0, 1))
    ax.axis("off")
    ink, secondary, muted = "#203442", "#344E58", "#5C6C70"
    raw_color, copy_color, divider = "#994826", "#11645F", "#ACBFBC"

    def label(x, y, message, size=9.7, color=ink, **options):
        return ax.text(x, y, message, fontsize=size, color=color, ha=options.pop("ha", "left"),
                       va="center", **options)

    label(.025, .941, "A correct successor can leave its sibling with the wrong input",
          13.0, ink, weight="bold")
    label(.025, .856, "SCIWORLD TASK 1975", 9.0, copy_color, weight="bold")
    label(.315, .856, "Root visit order  0 → 1 → 2", 9.6, secondary)

    label(.025, .711, "Parent at [0]", 11.0, weight="bold")
    label(.025, .634, "Shared object_states", 9.0, secondary)
    ax.plot([.272, .305, .305], [.689, .689, .755], color=muted, lw=1)
    ax.plot([.305, .305], [.689, .625], color=muted, lw=1)
    for y in (.755, .625):
        ax.annotate("", xy=(.342, y), xytext=(.304, y),
                    arrowprops={"arrowstyle": "-|>", "color": muted, "lw": 1, "shrinkA": 0, "shrinkB": 0})
    label(.360, .755, "Writer [0, 1]", 9.7, raw_color, weight="bold")
    label(.550, .755, "Raw and Full Copy return the same value.", 9.1, secondary)
    label(.360, .625, "Sibling [0, 2]", 9.7, raw_color, weight="bold")
    label(.550, .625, "Raw reads the change left in the parent.", 9.1, secondary)

    columns = (.025, .327, .515, .702, .893)
    headers = ("Execution", "Sibling input¹", "Leaf score", "Root scores²", "First → second")
    for i, (x, heading) in enumerate(zip(columns, headers)):
        label(x, .508, heading, 9, secondary, weight="bold", ha="left" if i == 0 else "center")
    ax.plot([.025, .976], [.468, .468], color=divider, lw=.95)
    display = [("raw", "Raw", raw_color), ("full_copy", "Full Copy", ink),
               ("rescue", "Copy [0, 1] only", copy_color)]
    for (key, arm_name, color), y in zip(display, (.416, .333, .250)):
        trial = arms[key]
        label(columns[0], y, arm_name, 10.1, color, weight="bold")
        label(columns[1], y, sibling[key]["parent_before"][0][:7], 9.7, color, ha="center",
              family="DejaVu Sans Mono")
        label(columns[2], y, str(sibling[key]["goal_fields_equal"]), 10.2, color, ha="center")
        label(columns[3], y, ", ".join(map(str, trial["root_scores"])), 10.1, color, ha="center")
        label(columns[4], y, " → ".join(map(str, trial["selected"])), 10.2, color, ha="center")
    ax.plot([.025, .976], [.201, .201], color=divider, lw=.8)
    label(.025, .147, "¹ First seven digits of the input SHA-256.   ² Best leaf score for roots 0, 1, 2. Lowest index wins ties.",
          8.3, muted)
    label(.025, .065, f"Of six interventions, {successes} restored the input and first action. "
          f"The other {input_only} restored the input alone.", 9.0, ink)
    destination.mkdir(parents=True, exist_ok=True)
    fig.savefig(destination / "task-1975.pdf", metadata={"CreationDate": None, "ModDate": None})
    svg = io.StringIO()
    fig.savefig(svg, format="svg", metadata={"Date": None})
    lines = (line.rstrip() for line in svg.getvalue().splitlines())
    (destination / "task-1975.svg").write_bytes(("\n".join(lines) + "\n").encode("utf-8"))
    plt.close(fig)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--study", required=True, type=Path, help="studies/sciworld-fixed-work-v1")
    parser.add_argument("--output", required=True, type=Path, help="figure output directory")
    args = parser.parse_args()
    draw(args.study, args.output)
