"""One real WebShop task, four isolation controls, no privileged planner access."""
import argparse, copy, hashlib, json, random, re, sys, time
from pathlib import Path
from live_wordle import ROOT,SOURCE,MODEL_SOURCE,Ledger,normal,calibration_cases

def canon_action(a):
    names={'buy now':'Buy Now','back to search':'Back to Search','< prev':'< Prev','next >':'Next >',
           'description':'Description','features':'Features','reviews':'Reviews','search':'Search'}
    if re.fullmatch(r'b[a-z0-9]{9}',a):a=a.upper()
    else:a=names.get(a,a)
    return f'click[{a}]'

def load_webshop():
    sys.path.insert(0,str(SOURCE/'WebShop'))
    from web_agent_site.envs.web_agent_text_env import WebAgentTextEnv
    random.seed(20261028)
    return WebAgentTextEnv(observation_mode='text',num_products=1000,human_goals=True,get_image=0)

def main(method):
    ledger=Ledger()
    with ledger.phase('environment_loading_and_initialization'):env=load_webshop()
    with ledger.phase('model_loading'):
        from discover import load_model
        from isolation import Adapter,compile_source
        raw=load_model('webshop')
    with ledger.phase('compilation_and_model_initialization'):
        path=MODEL_SOURCE/'examples/generated_world_models/webshop_benchmark_world_model.py'
        model=raw if method=='deepcopy' else compile_source(path.read_text(),str(path))['WebshopWorldModel']()
        model._wctr_raw_model=raw;adapter=Adapter(model,method)
    with ledger.phase('train_case_preparation_and_calibration'):
        rows=[json.loads(s) for s in (SOURCE/'trajectories/webshop/webshop_traj_train.jsonl').read_text(encoding='utf-8').splitlines()]
        cases=[]
        for row in rows:
            b=raw.init_belief()
            for tr in row['transitions']:
                b=raw.correct_belief(copy.deepcopy(b),tr['observation']);cases.append((copy.deepcopy(b),tr['action']))
                b=raw.predict_belief(copy.deepcopy(b),tr['action'])
                if len(cases)==32:break
            if len(cases)==32:break
        adapter.calibrate(cases)
    with ledger.phase('task_reset_and_belief_initialization'):
        obs,_=env.reset(session=0);initial=obs;b=raw.correct_belief(raw.init_belief(),obs)
    trace=[];contract_failures=0;calls=0;done=False
    for decision in range(8):
        with ledger.phase('candidate_generation'):
            available=env.get_available_actions()
            if available['has_search_bar']:
                instruction=b['instruction'];candidates=['search['+instruction+']']
            else:
                asins=[a for a in available['clickables'] if re.fullmatch(r'b[a-z0-9]{9}',a)]
                candidates=[canon_action(a) for a in asins[:4]] if asins else [canon_action('buy now')]
        with ledger.phase('planning_including_verification'):
            branches=[]
            for a in candidates:
                saved=copy.deepcopy(b);p=adapter.transition(b,a)
                forecast=model.readout_observation(p,a)
                equal=p==raw.predict_belief(copy.deepcopy(saved),a);isolated=b==saved
                contract_failures+=int(not(equal and isolated))
                branches.append({'action':a,'forecast':forecast,'parent_unchanged':isolated,'reference_equal':equal,'state':p})
            chosen=branches[0]
        with ledger.phase('real_environment_step'):
            next_ob,reward,done,info=env.step(chosen['action']);calls+=1
        with ledger.phase('belief_correction'):
            b=raw.correct_belief(chosen['state'],next_ob)
        with ledger.phase('serialization'):
            row={'scope':'smoke','task_id':'webshop_0','seed':20261028,'decision':decision,'observation':obs,
                 'available_actions':available,'candidates':candidates,'action':chosen['action'],
                 'predicted_observation':chosen['forecast'],'actual_observation':next_ob,
                 'actual_reward':reward,'actual_done':done,'actual_success':bool(done and reward==1),
                 'branches':[{k:v for k,v in x.items() if k!='state'} for x in branches]}
            trace.append(row)
            with (ROOT/'TRACES'/f'webshop_smoke_{method}.jsonl').open('a',encoding='utf-8') as f:f.write(json.dumps(row)+'\n')
        obs=next_ob
        if done:break
    result={'scope':'integration smoke, not final evaluation','domain':'webshop','method':method,
            'task_id':'webshop_0','seed':20261028,'initial_observation':initial,'interactions':calls,
            'done':done,'reward':reward,'success':bool(done and reward==1),'contract_failures':contract_failures,
            'model_transition_calls':adapter.calls,'deopts':adapter.deopts,'full_clones':adapter.full_clones,
            'copied_containers':adapter.copied,'calibration_calls':len(cases),'phases':ledger.rows,
            'smoke_pass':bool(done and calls>0 and contract_failures==0),'goal_count':len(env.server.goals),
            'cpu_at_report_s':time.process_time()}
    (ROOT/'RESULTS'/f'webshop_smoke_{method}.json').write_text(json.dumps(result,indent=2),encoding='utf-8')
    print(json.dumps({k:v for k,v in result.items() if k not in ['phases','initial_observation']}),flush=True)
    if method=='wctr':
        catalog=[{'task_id':i,'instruction':g['instruction_text']} for i,g in enumerate(env.server.goals)]
        (ROOT/'RESULTS/webshop_catalog_for_freeze.json').write_text(json.dumps(catalog,indent=2),encoding='utf-8')
    env.close()

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--method',required=True);main(p.parse_args().method)
