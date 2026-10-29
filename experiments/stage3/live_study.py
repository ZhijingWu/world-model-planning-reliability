"""Frozen paired live study. Planner sees observations and public action forms.

Only live env.step calls produce rewards / success. All hypothetical transitions
use the unchanged released model and frozen Stage 2 isolation implementation.
"""
import time
SCRIPT_START=time.perf_counter()
import argparse, copy, cProfile, ctypes, hashlib, json, pstats, random, re, sys
from collections import deque
from pathlib import Path
from live_wordle import ROOT,SOURCE,MODEL_SOURCE,Ledger,normal,digest,load_environment
from public_config import load_protocol,verify_sources
from live_webshop_smoke import load_webshop,canon_action

def words(text):return set(re.findall(r'[a-z]+',text.lower()))

def candidates(domain,state,history,allowed=None,visible=None):
    """Pure candidate generator; no environment transition or hidden access."""
    if domain=='wordle':
        seen={str(a).replace(' ','') for a in state.get('guess_history',[])}|set(history)
        remaining=[a for a in allowed if a not in seen]
        plausible=[a for a in remaining if a in state['possible_words']]
        return [(a,0.0) for a in (plausible or remaining)[:4]]
    instruction=state.get('instruction','');tokens=words(instruction)
    if visible is not None:
        clickables=visible['clickables']
        if visible['has_search_bar']:
            clean=' '.join(re.findall(r'[a-z0-9]+',instruction.lower()))
            terms=clean.split()
            queries=list(dict.fromkeys([clean,' '.join(terms[:8]),' '.join(terms[-8:])]))
            return [('search['+q+']',0.0) for q in queries if q][:4]
        asins=[a for a in clickables if re.fullmatch(r'b[a-z0-9]{9}',a)]
        if asins:
            titles={x['asin'].lower():x.get('title','') for x in state.get('items',[])}
            ranked=sorted(asins,key=lambda a:(-len(words(titles.get(a,''))&tokens),a))[:4]
            return [(canon_action(a),len(words(titles.get(a,''))&tokens)/max(1,len(tokens))) for a in ranked]
        nav={'buy now','back to search','< prev','next >','description','features','reviews','search'}
        options=[a for a in clickables if a not in nav and a.strip() and a.lower() in instruction.lower() and canon_action(a) not in history]
        if options:return [(canon_action(a),len(a)/max(1,len(instruction))) for a in sorted(options,key=lambda x:(-len(x),x))[:4]]
        if 'buy now' in clickables:return [('click[Buy Now]',0.0)]
        return [(canon_action(a),0.0) for a in sorted(clickables)[:4]]
    # Future actions come solely from predicted model state and its public forms.
    if state.get('page_type')=='product':return [('click[Buy Now]',0.0)]
    if state.get('page_type')=='purchase_complete':return []
    items=state.get('items',[])
    if items:return [('click['+i['asin']+']',len(words(i.get('title',''))&tokens)/max(1,len(tokens))) for i in items[:4]]
    return [('search['+instruction+']',0.0)] if instruction else []

def value(domain,state,forecast):
    if domain=='wordle':return 2*forecast.split().count('g')+forecast.split().count('y')
    return {'purchase_complete':100.0,'product':20.0,'results':10.0,'initial':0.0}.get(state.get('page_type'),0.0)

def plan(domain,belief,history,allowed,visible,model,raw,adapter,ledger,limit_cpu):
    from isolation import signature,match_targets
    with ledger.phase('candidate_generation'):
        root_actions=candidates(domain,belief,history,allowed,visible)
    queue=deque([(belief,[],None,None,0.0)]);branches=[];best=None;expansions=0;failures=0;matches=0;root_states={}
    with ledger.phase('planning_inclusive'):
        while queue and expansions<96 and time.process_time()<limit_cpu:
            state,path,root_action,root_state,hint=queue.popleft()
            if len(path)>=3:continue
            with ledger.phase('candidate_generation'):
                choices=root_actions if not path else candidates(domain,state,history,allowed,None)
            for action,action_hint in choices:
                if expansions>=96 or time.process_time()>=limit_cpu:break
                with ledger.phase('verification_snapshot'):
                    saved=copy.deepcopy(state);before=digest(state)
                    matched=bool(match_targets(state,adapter.frontiers.get(signature(action),set()),action)) if adapter.method=='wctr' else False
                old_deopts=adapter.deopts
                with ledger.phase('transition_including_isolation'):
                    output=adapter.transition(state,action)
                with ledger.phase('model_readout_and_scoring'):
                    forecast=model.readout_observation(output,action).strip()
                    first=root_action or action;first_state=root_state if path else output
                    first_hint=hint if path else action_hint
                    score=(0.95**len(path))*value(domain,output,forecast)+first_hint
                with ledger.phase('verification_reference_and_parent'):
                    expected=raw.predict_belief(copy.deepcopy(saved),action)
                    equal=output==expected;isolated=state==saved
                    failures+=int(not(equal and isolated));matches+=int(matched and adapter.deopts==old_deopts)
                expansions+=1
                row={'path':path+[action],'root_action':first,'predicted_observation':forecast,'score':score,
                     'parent_hash_before':before,'parent_unchanged':isolated,'reference_equal':equal,
                     'predicted_state_hash':digest(output),'compiled_frontier_match':matched,
                     'deoptimization':adapter.deopts>old_deopts}
                branches.append(row)
                if not path:root_states[action]={'state':output,'forecast':forecast}
                if best is None or score>best['score']:best={'score':score,'action':first}
                if len(path)+1<3:queue.append((output,path+[action],first,first_state,first_hint))
    if best is None:return None,branches,failures,matches,root_actions
    best.update(root_states[best['action']])
    return best,branches,failures,matches,root_actions

def load_models(domain,method,ledger):
    with ledger.phase('model_loading'):
        from discover import load_model
        from isolation import Adapter,compile_source
        raw=load_model(domain)
    with ledger.phase('runtime_compilation'):
        path=MODEL_SOURCE/f'examples/generated_world_models/{domain}_benchmark_world_model.py'
        if method=='deepcopy':model=raw
        else:
            ns=compile_source(path.read_text(encoding='utf-8'),str(path))
            cls='WordleWorldModel' if domain=='wordle' else 'WebshopWorldModel'
            model=ns[cls]();model._wctr_raw_model=raw
    with ledger.phase('adapter_initialization'):adapter=Adapter(model,method)
    with ledger.phase('calibration_case_preparation'):
        cases=[]
        for row in [json.loads(s) for s in (SOURCE/f'trajectories/{domain}/{domain}_traj_train.jsonl').read_text(encoding='utf-8').splitlines()]:
            b=raw.init_belief()
            for tr in row['transitions']:
                b=raw.correct_belief(copy.deepcopy(b),tr['observation'])
                cases.append((copy.deepcopy(b),tr['action']))
                b=raw.predict_belief(copy.deepcopy(b),tr['action'])
                if len(cases)==32:break
            if len(cases)==32:break
    with ledger.phase('train_only_calibration'):adapter.calibrate(cases)
    return raw,model,adapter

def peak_memory():
    class Info(ctypes.Structure):
        _fields_=[('cb',ctypes.c_ulong),('PageFaultCount',ctypes.c_ulong)]+[(x,ctypes.c_size_t) for x in ['PeakWorkingSetSize','WorkingSetSize','QuotaPeakPagedPoolUsage','QuotaPagedPoolUsage','QuotaPeakNonPagedPoolUsage','QuotaNonPagedPoolUsage','PagefileUsage','PeakPagefileUsage']]
    info=Info();info.cb=ctypes.sizeof(info)
    ok=ctypes.windll.psapi.GetProcessMemoryInfo(ctypes.c_void_p(-1),ctypes.byref(info),info.cb)
    return info.PeakWorkingSetSize if ok else None

def main(domain,method):
    verify_sources()
    protocol=load_protocol()
    if sys.platform!='win32':raise RuntimeError('Native lifetime accounting requires Windows')
    for name in ['RESULTS','TRACES','LOGS']:(ROOT/name).mkdir(parents=True,exist_ok=True)
    label=f'{domain}_{method}'
    trace_path=ROOT/'TRACES'/f'{label}.jsonl'
    if trace_path.exists():raise RuntimeError('Never overwrite a final trace')
    tasks=protocol['tasks'][domain];ledger=Ledger();profile=cProfile.Profile(timer=time.process_time);profile.enable()
    limit_cpu=protocol['total_cpu_allowance_s']-protocol['shared_environment_setup_cpu_per_arm_s'].get(domain,0.0)
    with ledger.phase('environment_loading_and_initialization'):
        if domain=='webshop':env=load_webshop();env_id=None;allowed=None
        else:
            module=load_environment();env=module.Lmrlgym_WordleEnv();made=env.create()
            if 'error' in made:raise RuntimeError(made['error'])
            env_id=made['id'];allowed=sorted((SOURCE/'LMRL-Gym/llm_rl_scripts/wordle/vocab/tweet_words.txt').read_text().split())
    raw,model,adapter=load_models(domain,method,ledger)
    setup_end_cpu=time.process_time();setup_end_wall=time.perf_counter()-SCRIPT_START
    results=[];step_calls=0
    for task_number,task in enumerate(tasks):
        start_cpu=time.process_time();start_wall=time.perf_counter();start_calls=adapter.calls;start_deopts=adapter.deopts;start_clones=adapter.full_clones
        if start_cpu>=limit_cpu:
            results.append({'domain':domain,'method':method,'task_id':task['task_id'],'seed':task['seed'],'success':False,'reward':0.0,'status':'unattempted_budget','interactions':0,'task_cpu_s':0.0,'task_wall_s':0.0})
            continue
        with ledger.phase('task_reset_and_belief_initialization'):
            if domain=='wordle':
                reset=env.reset(env_id,task['seed'])
                if 'error' in reset:raise RuntimeError(reset['error'])
                observation=reset['observation']
            else:observation,_=env.reset(session=task['environment_task_id'])
            initial_observation=observation;belief=raw.correct_belief(raw.init_belief(),observation)
        history=[];done=False;reward=0.0;contract_checks=0;contract_failures=0;false_plans=0;success_claims=0;matches=0;forecast_exact=0
        for decision in range(6 if domain=='wordle' else 12):
            if time.process_time()>=limit_cpu:break
            with ledger.phase('public_action_interface'):
                visible=env.get_available_actions() if domain=='webshop' else None
            before_steps=step_calls
            chosen,branches,failures,hits,root_actions=plan(domain,belief,history,allowed,visible,model,raw,adapter,ledger,limit_cpu)
            if chosen is None:break
            assert step_calls==before_steps
            with ledger.phase('real_environment_step'):
                if domain=='wordle':
                    actual=env.step(env_id,chosen['action'])
                    if 'error' in actual:raise RuntimeError(actual['error'])
                    next_ob,reward,done=actual['observation'],actual['reward'],actual['done']
                else:next_ob,reward,done,_=env.step(chosen['action'])
                step_calls+=1
            with ledger.phase('belief_correction'):
                belief=raw.correct_belief(chosen['state'],next_ob)
            predicted_success=(chosen['forecast']=='g g g g g') if domain=='wordle' else chosen['state'].get('page_type')=='purchase_complete'
            success=bool(done and reward==1.0)
            contract_checks+=len(branches);contract_failures+=failures;matches+=hits
            success_claims+=int(predicted_success);false_plans+=int(predicted_success and not success)
            forecast_exact+=int(chosen['forecast']==next_ob.strip())
            with ledger.phase('trace_serialization'):
                row={'task_id':task['task_id'],'seed':task['seed'],'decision':decision,'observation':observation,
                     'public_available_actions':visible if domain=='webshop' else allowed,
                     'root_candidates':root_actions,'chosen_action':chosen['action'],
                     'predicted_observation':chosen['forecast'],'model_claims_success':predicted_success,
                     'actual_observation':next_ob,'actual_reward':reward,'actual_done':done,'actual_success':success,
                     'planning_environment_step_calls':step_calls-before_steps-1,'model_branches':branches,
                     'belief_after_real_observation':normal(belief),'process_cpu_at_record_s':time.process_time()}
                with trace_path.open('a',encoding='utf-8') as f:f.write(json.dumps(row)+'\n')
            history.append(chosen['action']);observation=next_ob
            if done:break
        with ledger.phase('task_result_serialization'):
            result={'domain':domain,'method':method,'task_id':task['task_id'],'seed':task['seed'],
                    'initial_observation':initial_observation,'initial_observation_hash':digest(initial_observation),
                    'success':bool(done and reward==1.0),'reward':reward,'done':done,
                    'status':'terminated' if done else ('budget_exhausted' if time.process_time()>=limit_cpu else 'interaction_cap'),
                    'interactions':len(history),'actions':history,'model_transitions':adapter.calls-start_calls,
                    'contract_checks':contract_checks,'contract_failures':contract_failures,'frontier_matches':matches,
                    'deopts':adapter.deopts-start_deopts,'full_clones':adapter.full_clones-start_clones,
                    'success_claims':success_claims,'false_plans':false_plans,'forecast_exact':forecast_exact,
                    'task_cpu_s':time.process_time()-start_cpu,'task_wall_s':time.perf_counter()-start_wall}
            results.append(result)
            (ROOT/'RESULTS'/f'{label}_tasks.json').write_text(json.dumps(results,indent=2),encoding='utf-8')
        print(json.dumps({'domain':domain,'method':method,'completed':task_number+1,'assigned':len(tasks),'successes':sum(r['success'] for r in results),'cpu_s':time.process_time()}),flush=True)
    profile.disable()
    stats=pstats.Stats(profile)
    functions=[{'file':fn[0],'line':fn[1],'name':fn[2],'primitive_calls':v[0],'calls':v[1],'self_cpu_s':v[2],'inclusive_cpu_s':v[3]} for fn,v in stats.stats.items()]
    with ledger.phase('profile_and_cost_serialization'):
        (ROOT/'RESULTS'/f'{label}_profile.json').write_text(json.dumps(functions,indent=2),encoding='utf-8')
        (ROOT/'RESULTS'/f'{label}_tasks.json').write_text(json.dumps(results,indent=2),encoding='utf-8')
    summary={'domain':domain,'method':method,'assigned_tasks':len(tasks),'attempted_tasks':sum(r['status']!='unattempted_budget' for r in results),
             'successes':sum(r['success'] for r in results),'setup_end_process_cpu_s':setup_end_cpu,
             'setup_end_wall_s':setup_end_wall,'cpu_at_report_s':time.process_time(),
             'wall_at_report_s':time.perf_counter()-SCRIPT_START,'peak_working_set_bytes':peak_memory(),
             'calls':adapter.calls,'deopts':adapter.deopts,'full_clones':adapter.full_clones,
             'copied_containers':adapter.copied,'phases':ledger.rows,
             'shared_environment_setup_cpu_s':protocol['shared_environment_setup_cpu_per_arm_s'].get(domain,0.0)}
    (ROOT/'RESULTS'/f'{label}_summary.json').write_text(json.dumps(summary,indent=2),encoding='utf-8')
    print(json.dumps({k:v for k,v in summary.items() if k!='phases'}),flush=True)
    if domain=='webshop':env.close()

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--domain',required=True,choices=['webshop','wordle']);p.add_argument('--method',required=True,choices=['deepcopy','topfield','journal','wctr'])
    a=p.parse_args();main(a.domain,a.method)
