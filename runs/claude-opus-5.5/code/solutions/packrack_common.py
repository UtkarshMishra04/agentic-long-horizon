"""PackRack-v0/v1/v2: pick every goal box that is not on the rack yet and place it on a free slot."""

import numpy as np

from common import BOX_SIZE, Skills, to_local, to_world, upright

# Candidate slot centres in the rack frame (rack top: x in [-0.11, 0.11], y in [-0.16, 0.16]).
CANDIDATES = [np.array([x, y]) for x in np.linspace(-0.055, 0.055, 5) for y in np.linspace(-0.105, 0.105, 7)]
MIN_SEP = 0.095  # centre distance between two 0.07 m boxes on the rack


def on_rack(a, name):
    p = a.pos(name)
    loc = to_local(p, a.pos("rack"), a.yaw("rack"))
    return (
        upright(a.quat(name))
        and abs(loc[0]) < 0.11
        and abs(loc[1]) < 0.16
        and abs(p[2] - BOX_SIZE[name][2] / 2 - a.pos("rack")[2]) < 0.02
    )


def choose_slot(a, targets_on_rack):
    rp, ry = a.pos("rack"), a.yaw("rack")
    occupied = [to_local(a.pos(n), rp, ry) for n in targets_on_rack]
    best, best_score = None, -np.inf
    for c in CANDIDATES:
        dmin = min([np.linalg.norm(c - o) for o in occupied] + [1.0])
        # prefer slots far from other boxes, then slots near the rack corners (leaves room for others)
        score = min(dmin, 0.2) + 0.2 * np.linalg.norm(c / [0.055, 0.105])
        if dmin >= MIN_SEP - 1e-9 and score > best_score:
            best, best_score = c, score
    if best is None:  # fall back to the slot with the most clearance
        best = max(CANDIDATES, key=lambda c: min(np.linalg.norm(c - o) for o in occupied))
    return to_world(best, rp, ry)


def solve_packrack(a):
    k = Skills(a)
    targets = [c["objects"][0] for c in a.goal["conditions"] if c["type"] == "on" and c["objects"][1] == "rack"]
    for _attempt in range(12):
        todo = [n for n in targets if not on_rack(a, n)]
        if not todo:
            a.hold(10)
            continue
        done = [n for n in a.names if n != "rack" and on_rack(a, n)]
        # nearest box to the gripper first
        name = min(todo, key=lambda n: np.linalg.norm(a.pos(n)[:2] - a.ee_pos[:2]))
        slot = choose_slot(a, done)
        if not k.pick(name):
            k.a.move([a.ee_pos[0], a.ee_pos[1], k.SAFE_Z], closed=False)
            continue
        k.place(name, slot, a.pos("rack")[2], a.yaw("rack"))
