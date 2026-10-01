"""Renders 5 random seeds per environment to videos/<env_name>_seed<seed>.gif.

The seeds are drawn (fixed RNG) from the evaluation seeds of each environment (results/scene_seeds.json).
Every frame carries a banner with the episode result (SUCCESS / FAILURE); the whole episode is shown
(one frame every 4 control steps, plus the final frame).

Usage: python make_videos.py [--envs A,B] [--jobs 4]
"""

import argparse
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "solutions"))

from evaluate import ENVS, distinct_scene_seeds, load  # noqa: E402

VIDEO_DIR = os.path.join(HERE, "videos")


def pick_seeds(env_name, n=5, rng_seed=2026):
    import numpy as np

    pool = distinct_scene_seeds(env_name, 20)
    rng = np.random.default_rng(rng_seed + ENVS.index(env_name))
    return sorted(int(s) for s in rng.choice(pool, size=n, replace=False))


def render(args):
    env_name, seed = args
    import io
    import contextlib

    with contextlib.redirect_stderr(io.StringIO()):
        from common import run_episode, save_video

        mod = load(env_name)
        result, frames = run_episode(mod.ENV_ID, mod.solve, seed, record=True, frame_every=4)
        path = os.path.join(VIDEO_DIR, f"{env_name}_seed{seed}.gif")
        save_video(frames, path, result["success"])
    result["video"] = os.path.relpath(path, HERE)
    return result


def main():
    import multiprocessing

    p = argparse.ArgumentParser()
    p.add_argument("--envs", default=",".join(ENVS))
    p.add_argument("--jobs", type=int, default=4)
    args = p.parse_args()
    os.makedirs(VIDEO_DIR, exist_ok=True)
    jobs = [(e, s) for e in args.envs.split(",") for s in pick_seeds(e)]
    out_path = os.path.join(HERE, "results", "videos.json")
    results = json.load(open(out_path)) if os.path.exists(out_path) else []
    with multiprocessing.get_context("spawn").Pool(args.jobs, maxtasksperchild=2) as pool:
        for r in pool.imap_unordered(render, jobs):
            results = [x for x in results if x["video"] != r["video"]] + [r]
            print(("OK  " if r["success"] else "FAIL"), r["video"], "steps", r["steps"], flush=True)
            json.dump(results, open(out_path, "w"), indent=1)


if __name__ == "__main__":
    main()
