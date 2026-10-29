"""Bounded diagnostics on unmodified, published PatchWorld programs/traces.

No LLM calls. All source modules are retained with immutable revisions and MIT
attribution. The actual BaseWorldModel has only stdlib declarations; the three
generated models import re/collections plus this interface.
"""
from pathlib import Path
import sys,types,importlib.util,json,copy,collections,time,re

import os
REPO=Path(__file__).resolve().parents[2]
ROOT=Path(os.environ.get('WCTR_RUN_ROOT', str(REPO/'.runs/stage2'))).resolve()
SOURCE=Path(os.environ.get('WCTR_DATA_ROOT', str(REPO/'.data'))).resolve()
MODEL_SOURCE=REPO/'third_party/PatchWorld'
CONFIG_ROOT=Path(__file__).resolve().parent

def load_model(env):
    package=types.ModuleType('patchworld')
    package.__path__=[str(MODEL_SOURCE/'patchworld')]
    sys.modules['patchworld']=package
    path=MODEL_SOURCE/'examples/generated_world_models'/f'{env}_benchmark_world_model.py'
    spec=importlib.util.spec_from_file_location('published_'+env,path)
    mod=importlib.util.module_from_spec(spec);spec.loader.exec_module(mod)
    return next(v for k,v in vars(mod).items() if isinstance(v,type) and k!='BaseWorldModel' and k.lower().startswith(env))()

def trajectories(env,split):
    p=SOURCE/'trajectories'/env/f'{env}_traj_{split}.jsonl'
    return [json.loads(x) for x in p.read_text(encoding='utf-8').splitlines()]

def maze_parse(text):
    goals=re.findall(r'The goal is at position (\d+), (\d+)',text)
    pos=re.findall(r'Your current position is at position (\d+), (\d+)',text)
    if not goals or not pos:return None
    # Interface normalization baseline: separate current observation from demos.
    text=text[text.rfind('The goal is at position'):]
    walls=tuple(d for d,s in [('up','above you'),('down','below you'),('left','to your left'),('right','to your right')] if s in text)
    return dict(goal=tuple(map(int,goals[-1])),position=tuple(map(int,pos[-1])),walls=walls)

def outcome(text):
    if text.startswith('Crafted'):return 'crafted'
    if text.startswith('Got '):return 'got'
    if 'enough items' in text:return 'not_enough_items'
    if 'valid recipe' in text:return 'invalid_recipe'
    if 'Could not' in text:return 'not_found'
    if text.startswith('Inventory'):return 'inventory'
    return 'other'

def main():
    tic=time.perf_counter(); results={}; examples=[]
    for env,splits in [('maze',['train','val']),('textcraft',['train','val']),('babyai',['val'])]:
        model=load_model(env); stats=collections.Counter(); times=[]; clone_times=[]
        for split in splits:
            ts=trajectories(env,split)
            for ti,traj in enumerate(ts):
                belief=model.init_belief()
                for j,t in enumerate(traj['transitions']):
                    stats['transitions']+=1
                    belief=model.correct_belief(belief,t['observation'])
                    saved=copy.deepcopy(belief)
                    t0=time.perf_counter();pred=model.predict_belief(belief,t['action']);times.append(time.perf_counter()-t0)
                    if belief!=saved:
                        stats['predict_mutates_input']+=1
                        if len(examples)<30:examples.append(dict(env=env,split=split,trajectory=ti,step=j,issue='input mutation',action=t['action']))
                    t0=time.perf_counter();copy.deepcopy(saved);clone_times.append(time.perf_counter()-t0)
                    if env=='maze':
                        observed=maze_parse(t['observation']);nxt=maze_parse(t['next_observation'])
                        if observed and observed['position']!=saved['position']:stats['wrong_current_position_parse']+=1
                        if nxt:
                            stats['next_position_evaluable']+=1
                            if pred['position']!=nxt['position']:stats['next_position_error']+=1
                            if set(pred['walls'])!=set(nxt['walls']):stats['next_local_walls_error']+=1
                            # Cheap parser correction alone, same original transition code.
                            b=copy.deepcopy(saved);b.update(observed)
                            npred=model.predict_belief(b,t['action'])
                            if npred['position']!=nxt['position']:stats['position_error_after_interface_fix']+=1
                        # Initial greedy root decision changes from interface fix.
                        if j==0 and observed:
                            def act(b):
                                values=[]
                                for a in ['move up','move down','move left','move right']:
                                    p=model.predict_belief(copy.deepcopy(b),a)['position'];g=b['goal']
                                    values.append(-abs(p[0]-g[0])-abs(p[1]-g[1]))
                                return max(range(4),key=lambda k:values[k])
                            normalized=copy.deepcopy(saved);normalized.update(observed)
                            stats['initial_roots']+=1
                            if act(saved)!=act(normalized):stats['greedy_root_changed_by_interface_fix']+=1
                    if env=='textcraft':
                        obs=outcome(t['next_observation']);guess=pred['last_action_outcome']
                        if obs!='other':
                            stats['outcome_evaluable']+=1
                            if guess!=obs:
                                stats['outcome_error']+=1
                                stats['outcome_error_'+obs]+=1
                                if guess in ['got','crafted'] and obs.startswith(('not_','invalid')):stats['false_predicted_success']+=1
                                if len(examples)<30:examples.append(dict(env=env,split=split,trajectory=ti,step=j,issue='outcome mismatch',action=t['action'],predicted=guess,observed=obs))
                        if t['next_observation'].startswith('Inventory:') and '[' in t['next_observation']:
                            stats['nonempty_inventory_observations']+=1
                            if not model.parse_observation(t['next_observation'])['inventory']:stats['nonempty_inventory_parse_empty']+=1
                    belief=model.correct_belief(pred,t['next_observation'])
                stats['trajectories']+=1
        stats['predict_mean_microseconds']=sum(times)/len(times)*1e6
        stats['deepcopy_mean_microseconds']=sum(clone_times)/len(clone_times)*1e6
        results[env]=dict(stats)
    results['seconds']=time.perf_counter()-tic
    results['disclosure']='Source replay, not an online planning evaluation. Root-change measure is a specified greedy Manhattan diagnostic. No counterfactual true returns are inferred from logs.'
    output=ROOT/'RESULTS';output.mkdir(exist_ok=True)
    (output/'discovery.json').write_text(json.dumps(results,indent=2),encoding='utf-8')
    (output/'discovery_examples.json').write_text(json.dumps(examples,indent=2),encoding='utf-8')
    print(json.dumps(results,indent=2))

if __name__=='__main__':main()
