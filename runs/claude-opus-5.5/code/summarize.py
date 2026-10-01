"""Prints a markdown success table from an evaluate.py results file.

Usage: python summarize.py results/final_iter10_all60.json [--first 20]
"""

import argparse
import collections
import json
import os

HERE = os.path.dirname(os.path.abspath(__file__))


def main():
    p = argparse.ArgumentParser()
    p.add_argument("path")
    args = p.parse_args()
    results = json.load(open(args.path))
    seeds = json.load(open(os.path.join(HERE, "results", "scene_seeds.json")))
    by_env = collections.OrderedDict()
    for r in results:
        by_env.setdefault(r["env"], []).append(r)
    print("| environment | first 20 seeds | seeds 21-40 | seeds 41-60 | all | mean steps (min-max) of successes | time limit | failed seeds |")
    print("|---|---|---|---|---|---|---|---|")
    limits = {
        "LiftRedBox-v0": 1500, "RedBoxOnRack-v0": 1800, "RedBoxUnderRack-v0": 1300, "RedBoxUnderRack-v1": 2500,
        "RedBoxToBlueSpot-v0": 1000, "RedBoxToBlueSpot-v1": 2400, "PackRack-v0": 1000, "PackRack-v1": 1600,
        "PackRack-v2": 2000,
    }
    tot = [0, 0]
    for env, rs in by_env.items():
        order = seeds[env]
        groups = [order[:20], order[20:40], order[40:60]]
        cells = []
        for g in groups:
            sub = [r for r in rs if r["seed"] in g]
            cells.append(f"{sum(r['success'] for r in sub)}/{len(sub)}" if sub else "-")
        ok = [r for r in rs if r["success"]]
        steps = [r["steps"] for r in ok]
        fails = sorted(r["seed"] for r in rs if not r["success"])
        tot[0] += len(ok)
        tot[1] += len(rs)
        print(
            f"| {env} | {cells[0]} | {cells[1]} | {cells[2]} | **{len(ok)}/{len(rs)}** | "
            f"{sum(steps) / max(len(steps), 1):.0f} ({min(steps)}-{max(steps)}) | {limits.get(env, '')} | "
            f"{fails if fails else '-'} |"
        )
    print(f"\nTotal: {tot[0]}/{tot[1]}")


if __name__ == "__main__":
    main()
