"""Integration smoke only. Original AgentGym/LMRL transitions, reward and done.

No hidden environment state or filtered vocabulary is exposed to the planner.
The only environment adaptation is the location of the pinned vocabulary file.
"""
import time
SCRIPT_START = time.perf_counter()
import argparse, copy, cProfile, hashlib, importlib.util, json, pstats, sys
from contextlib import contextmanager
from pathlib import Path

import os
REPO=Path(__file__).resolve().parents[2]
ROOT=Path(os.environ.get('WCTR_RUN_ROOT', str(REPO/'.runs/stage3'))).resolve()
SOURCE=Path(os.environ.get('WCTR_DATA_ROOT', str(REPO/'.data'))).resolve()
MODEL_SOURCE=REPO/'third_party/PatchWorld'
CONFIG_ROOT=Path(__file__).resolve().parent
SEED=20261028

def normal(x):
    if isinstance(x,dict):return {str(k):normal(v) for k,v in sorted(x.items(),key=lambda kv:str(kv[0]))}
    if isinstance(x,(set,frozenset)):return sorted((normal(v) for v in x),key=repr)
    if isinstance(x,(list,tuple)):return [normal(v) for v in x]
    return x

def digest(x):return hashlib.sha256(json.dumps(normal(x),sort_keys=True).encode()).hexdigest()

class Ledger:
    def __init__(self):self.rows=[]
    @contextmanager
    def phase(self,name):
        w,c=time.perf_counter(),time.process_time()
        try:yield
        finally:self.rows.append({'phase':name,'wall_s':time.perf_counter()-w,'cpu_s':time.process_time()-c})

def load_environment():
    sys.path.insert(0,str(SOURCE/'LMRL-Gym'))
    path=SOURCE/'AgentGym/agentenv-lmrlgym/agentenv_lmrlgym/wordle/environment.py'
    spec=importlib.util.spec_from_file_location('released_agentgym_wordle',path)
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    module.vocab_base=str(SOURCE/'LMRL-Gym/llm_rl_scripts/wordle/vocab')
    return module

def calibration_cases(raw):
    rows=[json.loads(s) for s in (SOURCE/'trajectories/wordle/wordle_traj_train.jsonl').read_text(encoding='utf-8').splitlines()]
    cases=[]
    for row in rows:
        belief=raw.init_belief()
        for tr in row['transitions']:
            belief=raw.correct_belief(copy.deepcopy(belief),tr['observation'])
            cases.append((copy.deepcopy(belief),tr['action']))
            belief=raw.predict_belief(copy.deepcopy(belief),tr['action'])
            if len(cases)==32:return cases
    return cases

def main(method,run_tag='smoke'):
    label=f'wordle_{run_tag}_{method}'
    if (ROOT/'TRACES'/f'{label}.jsonl').exists():raise RuntimeError('Never append a new execution to an existing trace')
    ledger=Ledger();profile=cProfile.Profile(timer=time.process_time);profile.enable()
    with ledger.phase('environment_loading'):
        env_module=load_environment()
        allowed=sorted((SOURCE/'LMRL-Gym/llm_rl_scripts/wordle/vocab/tweet_words.txt').read_text().split())
    with ledger.phase('model_loading'):
        from discover import load_model
        raw=load_model('wordle')
        from isolation import Adapter,compile_source,signature
    with ledger.phase('runtime_compilation'):
        path=MODEL_SOURCE/'examples/generated_world_models/wordle_benchmark_world_model.py'
        if method=='deepcopy':model=raw
        else:
            namespace=compile_source(path.read_text(encoding='utf-8'),str(path))
            model=namespace['WordleWorldModel']();model._wctr_raw_model=raw
    with ledger.phase('adapter_initialization'):
        adapter=Adapter(model,method)
    with ledger.phase('train_only_case_preparation'):
        cases=calibration_cases(raw)
    with ledger.phase('train_only_calibration'):
        adapter.calibrate(cases)
    with ledger.phase('environment_and_belief_initialization'):
        server=env_module.Lmrlgym_WordleEnv();created=server.create()
        if 'error' in created:raise RuntimeError(created['error'])
        env_id=created['id'];payload=server.reset(env_id,SEED)
        if 'error' in payload:raise RuntimeError(payload['error'])
        observation=payload['observation'];initial=observation
        belief=raw.correct_belief(raw.init_belief(),observation)
    trace=[];real_guesses=[];contract_failures=0;false_plans=0;done=False;env_calls=0
    matched_frontiers=0;forecast_checks=0;forecast_exact=0
    for decision in range(6):
        with ledger.phase('candidate_generation'):
            remaining=[a for a in allowed if a not in real_guesses]
            plausible=[a for a in remaining if a in belief['possible_words']]
            candidates=(plausible or remaining)[:4]
        before_env_calls=env_calls
        with ledger.phase('planning_inclusive'):
            branches=[]
            for action in candidates:
                with ledger.phase('verification_parent_snapshot'):
                    saved=copy.deepcopy(belief)
                known=bool(adapter.frontiers.get(signature(action))) if method=='wctr' else False
                d=adapter.deopts
                with ledger.phase('transition_including_isolation'):
                    predicted=adapter.transition(belief,action)
                with ledger.phase('readout'):
                    forecast=model.readout_observation(predicted,action).strip()
                    score=2*forecast.split().count('g')+forecast.split().count('y')
                with ledger.phase('verification_reference_and_parent'):
                    reference=raw.predict_belief(copy.deepcopy(saved),action)
                    isolated=(belief==saved);equivalent=(predicted==reference)
                    contract_failures+=int(not (isolated and equivalent))
                matched_frontiers+=int(known and adapter.deopts==d)
                branches.append({'action':action,'score':score,'forecast':forecast,'predicted':predicted,
                                 'parent_unchanged':isolated,'reference_equal':equivalent})
            chosen=max(branches,key=lambda r:r['score'])
        assert env_calls==before_env_calls, 'real environment advanced during planning'
        with ledger.phase('real_environment_step'):
            actual=server.step(env_id,chosen['action']);env_calls+=1
            if 'error' in actual:raise RuntimeError(actual['error'])
        with ledger.phase('belief_correction'):
            observation=actual['observation'].strip();done=actual['done']
            belief=raw.correct_belief(chosen['predicted'],observation)
            real_guesses.append(chosen['action'])
        forecast_checks+=1;forecast_exact+=int(chosen['forecast']==observation)
        false_plans+=int(chosen['forecast']=='g g g g g' and actual['reward']!=1)
        with ledger.phase('trace_serialization'):
            entry={'task_id':f'agentgym_wordle_seed_{SEED}','seed':SEED,'decision':decision,
                   'current_observation':initial if not trace else trace[-1]['actual_observation'],
                   'candidates':candidates,'chosen_action':chosen['action'],'predicted_observation':chosen['forecast'],
                   'model_claims_success':chosen['forecast']=='g g g g g','actual_observation':observation,
                   'actual_environment_reward':actual['reward'],'actual_environment_done':done,
                   'actual_environment_success':bool(actual['reward']==1 and done),
                   'planning_environment_step_calls':env_calls-before_env_calls-1,
                   'branches':[{k:normal(v) for k,v in b.items() if k!='predicted'} for b in branches],
                   'belief_after_observation':normal(belief)}
            trace.append(entry)
            with (ROOT/'TRACES'/f'{label}.jsonl').open('a',encoding='utf-8') as f:f.write(json.dumps(entry)+'\n')
        if done:break
    profile.disable()
    stats=pstats.Stats(profile)
    functions=[{'file':fn[0],'line':fn[1],'name':fn[2],'primitive_calls':v[0],'calls':v[1],'self_cpu_s':v[2],'inclusive_cpu_s':v[3]} for fn,v in stats.stats.items()]
    with ledger.phase('profile_serialization'):
        (ROOT/'RESULTS'/f'{label}_profile.json').write_text(json.dumps(functions,indent=2),encoding='utf-8')
    result={'scope':'integration smoke, not final evaluation','domain':'wordle','method':method,
            'task_id':f'agentgym_wordle_seed_{SEED}','seed':SEED,'unique_tasks':1,
            'success':bool(done and trace[-1]['actual_environment_reward']==1),'done':done,
            'reward_sum':sum(r['actual_environment_reward'] for r in trace),'interactions':env_calls,
            'model_transition_calls':adapter.calls,'contract_checks':sum(len(r['branches']) for r in trace),
            'contract_failures':contract_failures,'false_plan_count':false_plans,'forecast_checks':forecast_checks,
            'forecast_exact':forecast_exact,'compiled_frontier_matched_no_deopt':matched_frontiers,
            'full_clones':adapter.full_clones,'deopts':adapter.deopts,'copied_containers':adapter.copied,
            'calibration_calls':len(cases),'initial_observation':initial,'allowed_actions':allowed,
            'env_revision':'3ef9235d23e68e7c2920c5422ad957dc8ced5c6c',
            'lmrl_revision':'83abeedb3a461c3d7d20572b73318a259d85f2ac','phases':ledger.rows,
            'cpu_at_report_s':time.process_time(),'wall_since_script_start_s':time.perf_counter()-SCRIPT_START,
            'smoke_pass':bool(done and env_calls>0 and contract_failures==0)}
    (ROOT/'RESULTS'/f'{label}.json').write_text(json.dumps(result,indent=2),encoding='utf-8')
    print(json.dumps({k:v for k,v in result.items() if k not in ['phases','allowed_actions']}))

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--method',choices=['deepcopy','topfield','journal','wctr'],required=True)
    p.add_argument('--run-tag',default='smoke');args=p.parse_args()
    main(args.method,args.run_tag)
