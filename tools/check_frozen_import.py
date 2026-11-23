"""Inspect actual harness bindings in a fresh interpreter per stage."""

import hashlib
import inspect
from pathlib import Path
import sys
from unittest.mock import patch


EXPERIMENTS = Path(__file__).resolve().parents[1] / "experiments"
FROZEN = EXPERIMENTS / "frozen" / "isolation.py"


def check_bindings(adapter, compiler):
    for obj in (adapter, compiler):
        source = Path(inspect.getfile(obj)).resolve()
        if source != FROZEN:
            raise SystemExit(f"{obj.__name__} came from {source}, expected {FROZEN}")


def check_stage3():
    import live_study

    # load_models binds Adapter and compile_source locally, immediately before
    # calling discover.load_model. Inspect those bindings and stop at that call.
    class ImportsChecked(Exception):
        pass

    def stop_before_model(domain):
        bindings = sys._getframe(1).f_locals
        check_bindings(bindings["Adapter"], bindings["compile_source"])
        raise ImportsChecked

    with patch("discover.load_model", new=stop_before_model):
        try:
            live_study.load_models("wordle", "wctr", live_study.Ledger())
        except ImportsChecked:
            return
    raise SystemExit("Stage 3 model-loader import check did not run")


if __name__ == "__main__":
    stage, = sys.argv[1:]
    if stage not in ("stage2", "stage3"):
        raise SystemExit("Expected stage2 or stage3")
    sys.path.insert(0, str(EXPERIMENTS / stage))
    if stage == "stage2":
        import benchmark
        check_bindings(benchmark.Adapter, benchmark.compile_source)
    else:
        check_stage3()
    print(f"PASS: {stage} imports {FROZEN} (SHA-256 {hashlib.sha256(FROZEN.read_bytes()).hexdigest()})")
