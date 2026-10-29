"""Public packaging integrity and fresh-run setup accounting."""
import hashlib,json,os
from pathlib import Path
REPO=Path(__file__).resolve().parents[2]
def verify_sources():
    manifest=json.loads((REPO/'docs/public_source_hashes.json').read_text())
    for name,expected in manifest.items():
        if hashlib.sha256((REPO/name).read_bytes()).hexdigest()!=expected:
            raise RuntimeError('Public source integrity failure: '+name)
def load_protocol():
    p=json.loads(Path(__file__).with_name('FROZEN_LIVE_PROTOCOL.json').read_text())
    for env,key in [('WCTR_SHARED_SETUP_CPU','shared_environment_setup_cpu_per_arm_s'),('WCTR_SHARED_SETUP_WALL','shared_environment_setup_wall_per_arm_s')]:
        if env not in os.environ:raise RuntimeError('Fresh setup accounting required: '+env)
        p[key]['webshop']=float(os.environ[env])
    return p
