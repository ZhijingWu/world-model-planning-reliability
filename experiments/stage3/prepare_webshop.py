"""Run the official conversion script unchanged; no model downloads."""
import os, sys, runpy
from pathlib import Path
from live_wordle import SOURCE
code=SOURCE/'WebShop'
sys.path.insert(0,str(code))
os.chdir(code/'search_engine')
for name in ['resources','resources_100','resources_1k','resources_100k']:
    Path(name).mkdir(exist_ok=True)
runpy.run_path(str(code/'search_engine/convert_product_file_format.py'),run_name='__main__')
print('OFFICIAL_CONVERSION_COMPLETED',flush=True)
# End this preprocessing worker after all requested files have been closed.
# The environment study workers use normal exit and measure their entire life.
sys.stdout.flush();sys.stderr.flush();os._exit(0)
