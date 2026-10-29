"""Planning over published executable programs with independent branch truth.

The environment here is each published program's pure transition semantics.
It is a program-planning benchmark, not a claim of AgentGym task performance.
The reference executes the original program on a fresh deepcopy at every edge.
No source environment installation or LLM inference is required.
"""
from __future__ import annotations
import argparse,collections,copy,csv,hashlib,importlib.util,json,platform,random,sys,time,types
from pathlib import Path
from isolation import Adapter,compile_source
from discover import load_model,trajectories,ROOT,SOURCE,MODEL_SOURCE,CONFIG_ROOT

# Paths are supplied by the public packaging layer in discover.py.
METHODS=['raw','deepcopy','memo_deepcopy','topfield','journal','wctr']

def canonical(x,active=None):
    active=set() if active is None else active
    if id(x) in active:return ('cycle',)
    if isinstance(x,(dict,list,tuple,set)):
        active.add(id(x))
        if isinstance(x,dict):v=('dict',tuple((str(k),canonical(v,active)) for k,v in sorted(x.items(),key=lambda z:str(z[0]))))
        elif isinstance(x,set):v=('set',tuple(sorted(map(repr,x))))
        else:v=(type(x).__name__,tuple(canonical(v,active) for v in x))
        active.remove(id(x));return v
    return x if isinstance(x,(str,int,float,bool,type(None))) else repr(x)

def get_model(env,instrumented):
    if not instrumented:return load_model(env)
    # Initialize the same lightweight BaseWorldModel import path as original.
    load_model(env)
    p=MODEL_SOURCE/'examples/generated_world_models'/f'{env}_benchmark_world_model.py'
    ns=compile_source(p.read_text(encoding='utf-8'),str(p))
    cls=next(v for k,v in ns.items() if isinstance(v,type) and k!='BaseWorldModel' and k.lower().startswith(env))
    model=cls();model._wctr_raw_model=load_model(env)
    return model

def cases(env,split,limit=None):
    model=load_model(env);out=[]
    for ti,t in enumerate(trajectories(env,split)):
        belief=model.init_belief()
        actions=list(dict.fromkeys(x['action'] for x in t['transitions']))
        for j,tr in enumerate(t['transitions']):
            belief=model.correct_belief(belief,tr['observation'])
            out.append((copy.deepcopy(belief),tr['action'],ti,j,actions))
            pred=model.predict_belief(copy.deepcopy(belief),tr['action'])
            belief=model.correct_belief(pred,tr['next_observation'])
            if limit is not None and len(out)>=limit:return out
    return out

def make_tasks(env,split,count,seed):
    c=cases(env,split);rng=random.Random(seed)
    indices=list(range(len(c)));rng.shuffle(indices);tasks=[]
    for idx in indices[:count]:
        state,logged,ti,step,pool=c[idx]
        # Uniform action pools from actual recorded commands, independent of
        # mutation labels. At most four actions; target walk is also independent.
        pool=list(pool)
        rng.shuffle(pool);pool=pool[:4]
        if not pool:pool=[logged]
        rng.shuffle(pool)
        walk=[rng.choice(pool) for _ in range(rng.choice([2,3,4]))]
        ref=load_model(env);goal=copy.deepcopy(state)
        for action in walk:goal=ref.predict_belief(copy.deepcopy(goal),action)
        tasks.append(dict(task_id=idx,trajectory=ti,step=step,state=state,actions=pool,
                          goal=canonical(goal),walk=walk,
                          trivial=canonical(state)==canonical(goal)))
    return tasks

def search(adapter,task,deadline_ms=10.,node_cap=4096):
    start=time.perf_counter_ns();end=start+int(deadline_ms*1e6)
    init=copy.deepcopy(task['state'])
    q=collections.deque([(init,[])])
    seen={canonical(init)};expanded=0;found=None
    while q and expanded<node_cap:
        if time.perf_counter_ns()>end:break
        state,path=q.popleft()
        if canonical(state)==task['goal']:found=path;break
        if len(path)>=6:continue
        for action in task['actions']:
            if time.perf_counter_ns()>end:break
            nxt=adapter.transition(state,action);expanded+=1
            key=canonical(nxt)
            if key not in seen:
                seen.add(key);q.append((nxt,path+[action]))
    elapsed=(time.perf_counter_ns()-start)/1e6
    realized=copy.deepcopy(task['state'])
    valid=False
    if found is not None:
        # The independent execution uses original source on isolated states.
        reference=adapter.reference
        for action in found:realized=reference.predict_belief(copy.deepcopy(realized),action)
        valid=canonical(realized)==task['goal']
    return dict(success=int(valid),found=int(found is not None),
        false_plan=int(found is not None and not valid),time_ms=elapsed,
        expansions=expanded,path=json.dumps(found),trivial=int(task['trivial']))

def contract_check(adapter,reference,c):
    mismatch=mutated=0
    for state,action,*_ in c:
        before=canonical(state);expected=reference.predict_belief(copy.deepcopy(state),action)
        got=adapter.transition(state,action)
        mismatch+=canonical(got)!=canonical(expected);mutated+=canonical(state)!=before
    return mismatch,mutated

def main():
    p=argparse.ArgumentParser()
    p.add_argument('--mode',choices=['dev','final'],default='dev')
    p.add_argument('--out',type=Path,default=ROOT/'RESULTS')
    args=p.parse_args();args.out.mkdir(parents=True,exist_ok=True)
    cfg=json.loads((CONFIG_ROOT/'EXPERIMENT_CONFIG.json').read_text(encoding='utf-8'))
    envs=cfg['development_programs'] if args.mode=='dev' else cfg['final_programs']
    count=cfg['dev_tasks_per_program'] if args.mode=='dev' else cfg['final_tasks_per_program']
    repeats=cfg['repeats'];rows=[];contracts=[]
    tic=time.perf_counter()
    for env in envs:
        calibration=cases(env,'train',cfg['calibration_calls'])
        tasks=make_tasks(env,'val' if args.mode=='dev' else 'test',count,
                         cfg['development_seed'] if args.mode=='dev' else cfg['final_seed'])
        checks=cases(env,'val' if args.mode=='dev' else 'test',cfg['contract_check_calls'])
        for method in METHODS:
            model=get_model(env,method not in ['raw','deepcopy','memo_deepcopy'])
            adapter=Adapter(model,method);adapter.reference=load_model(env)
            t0=time.perf_counter();adapter.calibrate([(x[0],x[1]) for x in calibration]);adapt_ms=(time.perf_counter()-t0)*1000
            mm,mut=contract_check(adapter,adapter.reference,copy.deepcopy(checks))
            contracts.append(dict(program=env,method=method,n=len(checks),output_mismatch=mm,input_mutation=mut,adapt_ms=adapt_ms))
            # Contract checks are measurement-only: do not let them train the
            # evaluated adapter. Reconstruct and calibrate it afresh.
            adapter=Adapter(get_model(env,method not in ['raw','deepcopy','memo_deepcopy']),method)
            adapter.reference=load_model(env)
            adapter.calibrate([(x[0],x[1]) for x in calibration])
            for repeat in range(repeats):
                adapter=Adapter(get_model(env,method not in ['raw','deepcopy','memo_deepcopy']),method)
                adapter.reference=load_model(env)
                adapter.calibrate([(x[0],x[1]) for x in calibration])
                order=list(range(len(tasks)));random.Random(cfg['final_seed']+repeat).shuffle(order)
                for i in order:
                    task=tasks[i];prior=(adapter.calls,adapter.copied,adapter.deopts,adapter.full_clones)
                    res=search(adapter,task,cfg['deadline_ms'],cfg['node_cap'])
                    rows.append(dict(program=env,method=method,repeat=repeat,task_id=task['task_id'],
                        trajectory=task['trajectory'],source_step=task['step'],
                        **res,model_calls=adapter.calls-prior[0],cloned_containers=adapter.copied-prior[1],
                        deoptimizations=adapter.deopts-prior[2],full_clones=adapter.full_clones-prior[3],
                        adaptation_ms=adapt_ms,goal_walk=json.dumps(task['walk'])))
            print(args.mode,env,method,'contracts',mm,mut,'elapsed',round(time.perf_counter()-tic,2),flush=True)
    for label,data in [('planning',rows),('contracts',contracts)]:
        target=args.out/f'{args.mode}_{label}.csv'
        if target.exists():raise FileExistsError(target)
        with target.open('w',newline='',encoding='utf-8') as f:
            w=csv.DictWriter(f,fieldnames=list(data[0]));w.writeheader();w.writerows(data)
    metadata=dict(config=cfg,mode=args.mode,seconds=time.perf_counter()-tic,
        python=sys.version,platform=platform.platform(),source_hashes={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in Path(__file__).parent.glob('*.py')})
    (args.out/f'{args.mode}_metadata.json').write_text(json.dumps(metadata,indent=2),encoding='utf-8')

if __name__=='__main__':main()
