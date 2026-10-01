"""Runs every solution on N seeds per environment and reports success rates.

By default each environment is evaluated on N (=20) distinct scenes: reset(seed) skips invalid
scenes, so e.g. seeds 1..16 of RedBoxToBlueSpot-v0 all give scene 16. We therefore use the first N
seeds that a freshly created environment maps to themselves (info["scene_seed"] == seed); they are
cached in results/scene_seeds.json.

Usage: python evaluate.py [--n 20 | --seeds 0-19] [--envs PackRack-v0,...] [--jobs 10] [--out results/eval.json]
Success = the episode ends with terminated=True before the environment's default time limit.
"""

import argparse
import importlib.util
import json
import os
import sys
import time
from multiprocessing import Pool

HERE = os.path.dirname(os.path.abspath(__file__))
SOL = os.path.join(HERE, "solutions")
sys.path.insert(0, SOL)

ENVS = [
    "LiftRedBox-v0", "RedBoxOnRack-v0", "RedBoxUnderRack-v0", "RedBoxUnderRack-v1", "RedBoxToBlueSpot-v0",
    "RedBoxToBlueSpot-v1", "PackRack-v0", "PackRack-v1", "PackRack-v2",
]


def load(env_name, sol=SOL):
    if sol not in sys.path:
        sys.path.insert(0, sol)
    spec = importlib.util.spec_from_file_location(env_name.replace("-", "_"), os.path.join(sol, env_name + ".py"))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def job(args):
    env_name, seed, sol = args
    import io
    import contextlib

    with contextlib.redirect_stderr(io.StringIO()):
        if sol != SOL:  # evaluate a frozen copy of the solutions
            sys.path.remove(SOL) if SOL in sys.path else None
        mod = load(env_name, sol)
        from common import run_episode

        t = time.time()
        result, _ = run_episode(mod.ENV_ID, mod.solve, seed)
    result["env"] = env_name
    result["time"] = round(time.time() - t, 1)
    return result


def print_line(r):
    flag = "OK  " if r["success"] else "FAIL"
    print(f"{flag} {r['env']:22s} seed {r['seed']:3d} (scene {r['scene_seed']}) steps {r['steps']:5d} "
          f"{r['time']:6.1f}s" + (" ERROR" if r["error"] else ""), flush=True)


def parse_seeds(s):
    out = []
    for part in s.split(","):
        if "-" in part:
            a, b = part.split("-")
            out += list(range(int(a), int(b) + 1))
        else:
            out.append(int(part))
    return out


def _scene_of(args):
    env_name, seed = args
    import io
    import contextlib

    with contextlib.redirect_stderr(io.StringIO()):
        from common import Agent

        mod = load(env_name)
        agent = Agent(mod.ENV_ID, seed)
        scene = agent.scene_seed
        agent.close()
    return seed, scene


def distinct_scene_seeds(env_name, n, jobs=10, cache=os.path.join(HERE, "results", "scene_seeds.json")):
    """The first ``n`` seeds s >= 0 for which a fresh environment's reset(seed=s) uses scene s itself.

    reset(seed) skips invalid scenes (info["scene_seed"] is the scene used), and which scenes are valid
    depends slightly on the simulator history, so we evaluate on seeds that a fresh environment (as
    used by run_episode) maps to themselves: every evaluated episode is then a distinct scene."""
    import multiprocessing

    data = json.load(open(cache)) if os.path.exists(cache) else {}
    if len(data.get(env_name, [])) >= n:
        return data[env_name][:n]
    # continue after the cached seeds (all seeds up to the last cached one were already scanned)
    seeds = list(data.get(env_name, []))
    start = max(seeds) + 1 if seeds else 0
    with multiprocessing.get_context("spawn").Pool(jobs) as pool:
        while len(seeds) < n:
            batch = [(env_name, s) for s in range(start, start + 3 * jobs)]
            for seed, scene in pool.map(_scene_of, batch):
                if seed == scene:
                    seeds.append(seed)
            start += 3 * jobs
    seeds = sorted(seeds)[:n]
    data = json.load(open(cache)) if os.path.exists(cache) else {}
    data[env_name] = seeds
    os.makedirs(os.path.dirname(cache), exist_ok=True)
    json.dump(data, open(cache, "w"), indent=1)
    return seeds


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--seeds", default=None, help="explicit seeds, e.g. 0-19 (default: distinct scenes)")
    p.add_argument("--n", type=int, default=20, help="number of distinct scenes per environment")
    p.add_argument("--skip", type=int, default=0, help="skip the first SKIP distinct scenes (held-out runs)")
    p.add_argument("--envs", default=",".join(ENVS))
    p.add_argument("--jobs", type=int, default=8, help="parallel episodes (~0.8 GB RAM each)")
    p.add_argument("--out", default=os.path.join(HERE, "results", "eval.json"))
    p.add_argument("--snapshot", action="store_true", help="evaluate a frozen copy of solutions/ (saved next to --out)")
    args = p.parse_args()
    sol = SOL
    if args.snapshot:
        import shutil

        sol = os.path.splitext(args.out)[0] + "_solutions"
        shutil.rmtree(sol, ignore_errors=True)
        shutil.copytree(SOL, sol, ignore=shutil.ignore_patterns("__pycache__"))
    envs = args.envs.split(",")
    if args.seeds:
        jobs = [(e, s, sol) for e in envs for s in parse_seeds(args.seeds)]
    else:
        jobs = [(e, s, sol) for e in envs for s in distinct_scene_seeds(e, args.skip + args.n)[args.skip:]]
    results = []
    import multiprocessing

    # spawn: the parent may hold an OSMesa context (scene-seed scan), which must not be forked
    with multiprocessing.get_context("spawn").Pool(args.jobs, maxtasksperchild=4) as pool:
        pending = {j: pool.apply_async(job, (j,)) for j in jobs}
        last = time.time()
        while pending:
            done = [j for j, h in pending.items() if h.ready()]
            if not done:
                # an episode takes < 10 min; silence for 20 min means a worker died (e.g. OOM)
                if time.time() - last > 1200:
                    print("timeout: episodes still pending:", sorted(pending), flush=True)
                    break
                time.sleep(1)
                continue
            last = time.time()
            for j in done:
                h = pending.pop(j)
                try:
                    r = h.get()
                except Exception as e:  # a crashed worker counts as a failure
                    r = dict(env=j[0], seed=j[1], scene_seed=-1, success=False, steps=-1, time=0, error=repr(e))
                results.append(r)
                print_line(r)
    for j in jobs:  # episodes lost to a killed worker count as failures
        if not any(r["env"] == j[0] and r["seed"] == j[1] for r in results):  # noqa: E501
            results.append(dict(env=j[0], seed=j[1], scene_seed=-1, success=False, steps=-1, time=0, error="lost"))
    os.makedirs(os.path.dirname(args.out), exist_ok=True)
    with open(args.out, "w") as f:
        json.dump(results, f, indent=1)
    print("\nenvironment              success   mean steps (successes)")
    for e in envs:
        rs = [r for r in results if r["env"] == e]
        ok = [r for r in rs if r["success"]]
        mean = sum(r["steps"] for r in ok) / max(len(ok), 1)
        fails = sorted(r["seed"] for r in rs if not r["success"])
        print(f"{e:24s} {len(ok):3d}/{len(rs):<3d}  {mean:7.0f}   failed seeds: {fails}")


if __name__ == "__main__":
    main()
