"""Historical Stage 2/3 runtime for standalone experiment scripts."""
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from frozen.isolation import *
