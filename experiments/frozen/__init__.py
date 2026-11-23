"""Load the exact WCTR runtime used to produce the Stage 2/3 evidence."""
import hashlib
from pathlib import Path

FROZEN_CORE_SHA256 = "4528627f1922286e3058a81c2439f682dde33f8deb9a10ebb5170b8a11b7b612"
core_path = Path(__file__).with_name("isolation.py")
if hashlib.sha256(core_path.read_bytes()).hexdigest() != FROZEN_CORE_SHA256:
    raise RuntimeError("Stage 2/3 historical WCTR runtime does not match its frozen SHA-256")
