"""Evaluate all nine hand-written controllers using default episode limits.

Example: PYTHONPATH=/opt/LongHorizonTAMP /usr/local/bin/python evaluate.py --seeds 20
"""
import argparse
import concurrent.futures
import hashlib
import json
import os
import time
os.environ.setdefault('LP_NUM_THREADS', '1')
os.environ.setdefault('OPENBLAS_NUM_THREADS', '1')
os.environ.setdefault('OMP_NUM_THREADS', '1')
from controllers import episode, ORDERS
from revision_compat import compatible


def job(args):
    name, seed = args
    started = time.monotonic()
    try:
        result = episode(name, seed)
    except Exception as exc:
        result = dict(env='LongHorizonTAMP/' + name, seed=seed, success=False, error=repr(exc))
    result['seconds'] = round(time.monotonic() - started, 3)
    return result


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--seeds', type=int, default=20)
    parser.add_argument('--start', type=int, default=0)
    parser.add_argument('--stride', type=int, default=1000)
    parser.add_argument('--workers', type=int, default=8)
    parser.add_argument('--env', nargs='+', choices=list(ORDERS), default=list(ORDERS))
    parser.add_argument('--output', default='/workspace/results.jsonl')
    parser.add_argument('--resume', action='store_true', help='Keep completed matching episodes and run missing ones')
    args = parser.parse_args()
    jobs = [(env, args.start + i * args.stride) for i in range(args.seeds) for env in args.env]
    digest = hashlib.sha256(open(os.path.join(os.path.dirname(__file__), 'controllers.py'), 'rb').read()).hexdigest()
    helper_digest = hashlib.sha256(open(os.path.join(os.path.dirname(__file__), 'tool_control.py'), 'rb').read()).hexdigest()
    results = []
    if args.resume and os.path.exists(args.output):
        results = [json.loads(line) for line in open(args.output) if line.strip()]
        assert all(compatible(r['env'], r.get('controller_sha256')) and r.get('tool_control_sha256') == helper_digest for r in results), 'Cannot resume results from a different controller version'
        completed = {(r['env'].split('/')[-1], r['seed']) for r in results}
        jobs = [job for job in jobs if job not in completed]
    with open(args.output, 'a' if args.resume else 'w', buffering=1) as output, concurrent.futures.ProcessPoolExecutor(args.workers) as pool:
        futures = [pool.submit(job, item) for item in jobs]
        for future in concurrent.futures.as_completed(futures):
            result = future.result()
            result['controller_sha256'] = digest
            result['tool_control_sha256'] = helper_digest
            results.append(result)
            output.write(json.dumps(result) + '\n')
            print(json.dumps({k: v for k, v in result.items() if k not in ('final_objects','goal')}), flush=True)
    summary = {}
    for env in args.env:
        records = [r for r in results if r['env'] == 'LongHorizonTAMP/' + env]
        successes = sum(r['success'] for r in records)
        summary[env] = dict(successes=successes, episodes=len(records), success_rate=successes / len(records),
                            unique_scene_seeds=len({r.get('scene_seed') for r in records}))
        print(env, json.dumps(summary[env]), flush=True)
    with open(args.output + '.summary.json', 'w') as output:
        json.dump(summary, output, indent=2)
