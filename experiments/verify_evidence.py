"""Verify completed archived results. Does not run models or environments.

The percentile calculation matches NumPy's default linear quantile used by the
frozen analysis. Source-item identifiers are hashed labels, not observations.
"""
from pathlib import Path
from collections import defaultdict
import csv
import hashlib
import json
import math
import random
import statistics

ROOT = Path(__file__).resolve().parents[1]
METHODS = ['deepcopy', 'topfield', 'journal', 'wctr']


def check(condition, message):
    if not condition:
        raise RuntimeError(message)


def near(a, b, label):
    check(math.isclose(float(a), float(b), abs_tol=1e-12, rel_tol=1e-10), label)


def read_csv(name):
    with (ROOT / name).open(encoding='utf-8', newline='') as f:
        return list(csv.DictReader(f))


def read_json(name):
    return json.loads((ROOT / name).read_text(encoding='utf-8'))


def quantile(values, q):
    x = sorted(values)
    position = (len(x) - 1) * q
    lower = math.floor(position)
    upper = math.ceil(position)
    return x[lower] + (x[upper] - x[lower]) * (position - lower)


def stage2():
    rows = read_csv('results/stage2/final_planning.csv')
    check(len(rows) == 7200, 'Stage 2 row count')
    groups = defaultdict(list)
    tasks = defaultdict(list)
    for r in rows:
        groups[r['program'], r['method']].append(r)
        tasks[r['program'], r['method'], r['task_id']].append(float(r['success']))
    for s in read_csv('results/stage2/final_summary.csv'):
        sample = groups[s['program'], s['method']]
        check(len(sample) == int(s['records']) == 240, 'records per program/method')
        check(len({r['task_id'] for r in sample}) == int(s['tasks']) == 80, 'tasks per program/method')
        check(len({r['trajectory'] for r in sample}) == int(s['source_trajectories']), 'source trajectories')
        check({int(r['repeat']) for r in sample} == {0, 1, 2}, 'timing repeats')
        for k in ['success', 'found', 'false_plan', 'time_ms', 'expansions', 'model_calls',
                  'cloned_containers', 'deoptimizations', 'full_clones', 'trivial']:
            near(statistics.mean(float(r[k]) for r in sample), s[k], 'summary: ' + k)
        near(sample[0]['adaptation_ms'], s['adaptation_ms'], 'adaptation cost')

    cluster_map = {(r['program'], int(r['trajectory'])): r['source_item_sha256']
                   for r in read_csv('results/stage2/source_item_clusters.csv')}
    task_cluster = {(r['program'], r['task_id']): cluster_map[r['program'], int(r['trajectory'])]
                    for r in rows}
    means = {k: statistics.mean(v) for k, v in tasks.items()}
    paired = read_csv('results/stage2/paired_success.csv')
    check(len(paired) == 25, 'paired comparison count')
    for p in paired:
        env, base = p['program'], p['baseline']
        ids = sorted(k[2] for k in means if k[:2] == (env, 'wctr'))
        deltas = {i: means[env, 'wctr', i] - means[env, base, i] for i in ids}
        near(statistics.mean(deltas.values()), p['difference'], 'paired effect')
        clusters = defaultdict(list)
        for i in ids:
            clusters[task_cluster[env, i]].append(deltas[i])
        check(len(clusters) == int(p['source_item_clusters']), 'source-item clusters')
        for name, count in [('better_tasks', sum(d > 1e-12 for d in deltas.values())),
                            ('worse_tasks', sum(d < -1e-12 for d in deltas.values())),
                            ('ties', sum(abs(d) <= 1e-12 for d in deltas.values()))]:
            check(count == int(p[name]), name)
        values = list(clusters.values())
        rng = random.Random(20261028)
        bs = []
        for _ in range(5000):
            sample = [values[rng.randrange(len(values))] for _ in values]
            bs.append(sum(sum(v) for v in sample) / sum(map(len, sample)))
        near(quantile(bs, .025), p['lower95'], 'lower bootstrap interval')
        near(quantile(bs, .975), p['upper95'], 'upper bootstrap interval')
    for env, expected in [('webshop', .175), ('wordle', -.09166666666666667)]:
        p = next(p for p in paired if p['program'] == env and p['baseline'] == 'deepcopy')
        near(p['difference'], expected, env + ' headline')
    discovery = read_json('results/stage2/discovery.json')['babyai']
    check(discovery['transitions'] == 3942 and discovery['predict_mutates_input'] == 59, 'BabyAI discovery')
    contracts = read_csv('results/stage2/final_contracts.csv')
    for env, mutations in [('webshop',261), ('wordle',300), ('sciworld',70), ('alfworld',5)]:
        r = next(r for r in contracts if r['program']==env and r['method']=='raw')
        check(int(r['n'])==300 and int(r['input_mutation'])==mutations and int(r['output_mismatch'])==0, 'raw contracts')
    print('PASS: 7,200 Stage 2 rows; 30 summaries; all 25 paired effects and 5,000-resample intervals; discovery and selected contracts.')


def stage3():
    analysis = read_json('results/stage3/analysis.json')
    protocol = read_json('experiments/stage3/FROZEN_LIVE_PROTOCOL.json')
    costs = read_json('results/stage3/complete_process_costs.json')
    total_records = total_checks = total_interactions = 0
    wctr_checks = 0
    for domain, n, successes, checks in [('webshop', 12, 6, 240), ('wordle', 100, 43, 33452)]:
        reference = None
        assigned = [(r['task_id'], r['seed']) for r in protocol['tasks'][domain]]
        for method in METHODS:
            rows = read_json(f'results/stage3/{domain}_{method}_tasks.json')
            check(len(rows) == n, 'native assigned tasks')
            check([(r['task_id'], r['seed']) for r in rows] == assigned, 'frozen task order')
            check(sum(r['success'] for r in rows) == successes, 'native completion')
            check(all(r['success'] == bool(r['done'] and r['reward']==1) for r in rows), 'native success definition')
            check(sum(r['contract_checks'] for r in rows) == checks, 'checked transitions')
            check(sum(r['model_transitions'] for r in rows) == checks, 'model transition count')
            check(sum(r['contract_failures'] for r in rows) == 0, 'sampled contract failures')
            signatures = [(r['task_id'], r['seed'], r['success'], r['action_sequence_sha256'], r['initial_observation_hash']) for r in rows]
            if reference is None:
                reference = signatures
            check(signatures == reference, 'paired task/action/initial-observation equality')
            a = analysis['domains'][domain][method]
            check(a['tasks']==n and a['successes']==successes and a['verification_calls']==checks and a['contract_failures']==0, 'native summary')
            near(a['success_rate'], successes/n, 'native rate')
            c = next(c for c in costs if c['domain']==domain and c['method']==method)
            near(c['total_charged_cpu_s'], c['process_cpu_s']+c['shared_setup_cpu_s'], 'complete lifetime cost')
            near(c['total_charged_cpu_s'], a['total_charged_cpu_s'], 'cost summary')
            check(c['exit_code']==0 and not c['timed_out'] and c['total_charged_cpu_s']<=180, 'worker completion/budget')
            total_records += len(rows);total_checks += checks
            total_interactions += sum(r['interactions'] for r in rows)
            if method == 'wctr':
                wctr_checks += checks
    expected_cpu = {'deepcopy':261.30859375,'topfield':245.96484375,'journal':248.40234375,'wctr':257.62109375}
    for method in METHODS:
        summed = sum(c['total_charged_cpu_s'] for c in costs if c['method']==method)
        near(summed, expected_cpu[method], 'aggregate lifetime CPU')
        near(summed, analysis['aggregate'][method]['summed_two_lifetime_cpu_s'], 'aggregate analysis')
        near(analysis['aggregate'][method]['equal_domain_success_rate'], .465, 'equal-domain rate')
    check((total_records,total_checks,wctr_checks,total_interactions)==(448,134768,33692,1996), 'native totals')
    print('PASS: 448 native method-task records; four-way completion tie; paired action hashes; 33,692 WCTR / 134,768 total checks; lifetime costs.')


def integrity():
    for name, expected in read_json('docs/public_source_hashes.json').items():
        check(hashlib.sha256((ROOT/name).read_bytes()).hexdigest()==expected, 'source hash: '+name)
    for p in read_json('docs/PROVENANCE.json'):
        check(hashlib.sha256((ROOT/p['public_path']).read_bytes()).hexdigest()==p['public_sha256'], 'provenance: '+p['public_path'])
    check(hashlib.sha256((ROOT/'src/wctr/isolation.py').read_bytes()).hexdigest()=='4528627f1922286e3058a81c2439f682dde33f8deb9a10ebb5170b8a11b7b612', 'frozen core')
    check(hashlib.sha256((ROOT/'note/Zhijing_Wu_World_Model_Planning_Note_Final.pdf').read_bytes()).hexdigest()=='4d29fead79bf244b57198abc3d9c04af1f338a85d546c5b0dbd1d9a19e4479d1', 'exact final PDF')
    print('PASS: public source/provenance hashes; byte-identical frozen core and final PDF.')


def main():
    integrity()
    stage2()
    stage3()
    print('Completed-result verification only. No new rollout, environment evaluation or inference was performed.')


if __name__ == '__main__':
    main()
