import argparse,os,sys,json
from pathlib import Path
from run_recorded import run
from live_wordle import ROOT
from public_config import load_protocol,verify_sources

def main():
    parser=argparse.ArgumentParser(description='Optional native rerun; assets and Windows required.')
    parser.add_argument('--execute',action='store_true',help='Explicitly run the eight native workers')
    parser.add_argument('--shared-setup-cpu',type=float,required=True,help='New measured WebShop conversion/index CPU per arm, not the archived value')
    parser.add_argument('--shared-setup-wall',type=float,required=True)
    a=parser.parse_args()
    if not a.execute:parser.error('--execute is required to run experiments')
    if sys.platform!='win32':parser.error('Windows is required for the original lifetime accounting')
    if min(a.shared_setup_cpu,a.shared_setup_wall)<0:parser.error('Setup costs cannot be negative')
    os.environ['WCTR_SHARED_SETUP_CPU']=str(a.shared_setup_cpu)
    os.environ['WCTR_SHARED_SETUP_WALL']=str(a.shared_setup_wall)
    os.environ['PYTHONHASHSEED']='0'
    verify_sources();protocol=load_protocol()
    for name in ['RESULTS','TRACES','LOGS']:(ROOT/name).mkdir(parents=True,exist_ok=True)
    if '\\venv\\Scripts\\' in sys.executable:raise RuntimeError('Use direct CPython executable: venv launcher omits child CPU')
    costs=[]
    for domain,method in protocol['execution_order']:
        label=f'final_{domain}_{method}'
        cost=run(label,[sys.executable,str(Path(__file__).with_name('live_study.py')),'--domain',domain,'--method',method],protocol['worker_wall_cap_s'])
        cost['domain']=domain;cost['method']=method
        cost['shared_setup_cpu_s']=protocol['shared_environment_setup_cpu_per_arm_s'].get(domain,0.0)
        cost['shared_setup_wall_s']=protocol['shared_environment_setup_wall_per_arm_s'].get(domain,0.0)
        cost['total_charged_cpu_s']=cost['process_cpu_s']+cost['shared_setup_cpu_s']
        cost['total_charged_wall_s']=cost['wall_s']+cost['shared_setup_wall_s']
        cost['within_cpu_allowance']=cost['total_charged_cpu_s']<=protocol['total_cpu_allowance_s']
        costs.append(cost)
        (ROOT/'RESULTS/complete_process_costs.json').write_text(json.dumps(costs,indent=2),encoding='utf-8')
        if cost['exit_code'] or not cost['within_cpu_allowance']:
            raise RuntimeError('Incomplete worker / cost audit failure; preserve results and investigate without tuning method')

if __name__=='__main__':main()
