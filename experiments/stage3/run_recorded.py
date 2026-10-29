"""Run a bounded subprocess and retain complete process CPU / wall cost.

Windows GetProcessTimes after process termination includes interpreter startup,
imports, all process threads, model setup and final trace/report serialization.
"""
import argparse, ctypes, json, os, subprocess, time
from pathlib import Path
from live_wordle import ROOT

def run(label,command,timeout=120):
    wall=time.perf_counter();parent_cpu=time.process_time()
    with (ROOT/'LOGS'/f'{label}.txt').open('w',encoding='utf-8') as log:
        p=subprocess.Popen(command,stdout=log,stderr=subprocess.STDOUT,cwd=ROOT,env=os.environ.copy())
        timed_out=False
        try:code=p.wait(timeout=timeout)
        except subprocess.TimeoutExpired:
            timed_out=True;p.kill();code=p.wait()
        filetimes=[ctypes.c_uint64() for _ in range(4)]
        ok=ctypes.windll.kernel32.GetProcessTimes(ctypes.c_void_p(int(p._handle)),*(ctypes.byref(v) for v in filetimes))
        cpu=(filetimes[2].value+filetimes[3].value)/10**7 if ok else None
    result={'label':label,'command':command,'exit_code':code,'timed_out':timed_out,
            'wall_s':time.perf_counter()-wall,'process_cpu_s':cpu,
            'driver_cpu_s':time.process_time()-parent_cpu,'cpu_source':'Windows GetProcessTimes user+kernel after exit',
            'includes':'interpreter startup, imports, all threads, setup, work, profiles and final serialization'}
    (ROOT/'LOGS'/f'{label}_process_cost.json').write_text(json.dumps(result,indent=2),encoding='utf-8')
    print(json.dumps(result),flush=True)
    return result

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--label',required=True);p.add_argument('--timeout',type=int,default=120);p.add_argument('command',nargs=argparse.REMAINDER)
    a=p.parse_args();raise SystemExit(run(a.label,a.command,a.timeout)['exit_code'])
