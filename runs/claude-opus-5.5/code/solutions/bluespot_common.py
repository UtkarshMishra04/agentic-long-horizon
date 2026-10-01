"""RedBoxToBlueSpot-v0/v1: move the blue box to a free spot, then put the red box where the blue box
started. Grasps pick the finger axis that keeps the fingers away from the L-stick."""

import numpy as np

from common import Skills, stick_point_dist, stick_pose, upright


def find_spot(a, avoid_pts, stick, min_stick=0.12, min_pts=0.17, prefer=None):
    """Free table spot in the workspace, away from the stick and from the given points. The margins
    are relaxed step by step (never below what ``free`` needs) if the workspace is crowded."""
    levels = [(min_stick, min_pts, 0.69), (0.105, 0.15, 0.71), (0.095, 0.14, 0.72)]
    fallback, fallback_clear = None, -np.inf
    for ms, mp, rmax in levels:
        best, best_score = None, -np.inf
        for x in np.linspace(0.43, 0.72, 30):
            for y in np.linspace(-0.42, 0.42, 43):
                p = np.array([x, y])
                if np.hypot(x, y) > rmax:
                    continue
                ds = stick_point_dist(stick[0], stick[1], p, stick[2]) if stick is not None else 1.0
                dp = min([np.linalg.norm(p - q) for q in avoid_pts] + [1.0])
                if min(ds - ms, dp - mp) > fallback_clear:
                    fallback, fallback_clear = p, min(ds - ms, dp - mp)
                if ds < ms or dp < mp:
                    continue
                score = min(ds, 0.25) + min(dp, 0.3) - (0.3 * np.linalg.norm(p - prefer) if prefer is not None else 0)
                if score > best_score:
                    best, best_score = p, score
        if best is not None:
            return best
    return fallback


def solve_bluespot(a, fetch=None, repark=None):
    """``fetch(name)`` (if given) pulls a box that ended up out of reach back with the stick;
    ``repark()`` (if given) moves the stick away from the target spot."""
    k = Skills(a)
    target = np.array([c for c in a.goal["conditions"] if c["type"] == "pos" and c["objects"][0] == "red_box"][0]["target_xy"])
    stick = stick_pose(a)

    def avoid(p):
        return stick_point_dist(stick[0], stick[1], p, stick[2])

    for _attempt in range(6):
        if fetch is not None:
            far = [n for n in ("blue_box", "red_box") if np.hypot(*a.pos(n)[:2]) > 0.76]
            if far:
                fetch(far[0])
                stick = stick_pose(a)
                continue
        blue, red = a.pos("blue_box"), a.pos("red_box")
        cur_stick = stick_pose(a)
        if repark is not None and stick_point_dist(cur_stick[0], cur_stick[1], target, cur_stick[2]) < 0.1:
            repark()
            stick = stick_pose(a)
            continue
        blue_bad = (
            np.linalg.norm(blue[:2] - target) < 0.17
            or stick_point_dist(cur_stick[0], cur_stick[1], blue[:2], cur_stick[2]) < 0.11  # free: >= 0.05 m footprints
            or not upright(a.quat("blue_box"))
            or np.hypot(*blue[:2]) > 0.72
            or blue[0] < 0.42
        )
        if blue_bad:
            spot = find_spot(a, [target, red[:2]], stick, prefer=blue[:2])
            if k.pick("blue_box", avoid=avoid):
                k.place("blue_box", spot, 0.0, avoid=avoid)
            continue
        if np.linalg.norm(red[:2] - target) > 0.02 or red[2] > 0.05:
            if k.pick("red_box", avoid=avoid):
                k.place("red_box", target, 0.0, avoid=avoid)
            continue
        a.move([a.ee_pos[0], a.ee_pos[1], 0.3], closed=False)
        a.hold(20)


