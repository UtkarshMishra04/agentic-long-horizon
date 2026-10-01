"""RedBoxUnderRack-v0/v1: the rack stands beyond reach with its open side facing the robot.

The gripper cannot reach under the rack top, so the box is staged on the table in front of the rack
and then pushed underneath with the flat short bar of the L-stick (the stick is only 4 cm tall).
"""

import numpy as np

from common import Skills, stick_point_dist, stick_pose, to_world
from tool_common import REACH_R, fetch_far_box

STAGE_GAP = 0.075  # box centre in front of the rack's near edge
PUSH_LOCAL = (0.275, 0.01)  # box position in the stick frame before pushing (short bar behind it)
PUSH_GX = 0.05  # grasp point on the long bar for pushing


def lane_points(a):
    rp, ry = a.pos("rack")[:2], a.yaw("rack")
    d = np.array([np.cos(ry), np.sin(ry)])
    n = np.array([-np.sin(ry), np.cos(ry)])
    stage = rp - (0.11 + STAGE_GAP) * d
    pts = [stage + t * d + s * n for t in np.linspace(-0.5, 0.25, 16) for s in (-0.08, 0.0, 0.08)]
    return stage, d, pts


def solve_underrack(a):
    for _attempt in range(5):
        k = Skills(a)
        stage, d, lane = lane_points(a)
        keep = [(p, 0.0) for p in lane]
        red = a.pos("red_box")
        if np.hypot(*red[:2]) > REACH_R:
            fetch_far_box(a, keep_out=keep)
            continue
        ry = a.yaw("rack")
        # the stick must not lie on the staging spot or in the push lane
        sp, sy, hand = stick_pose(a)
        if min(stick_point_dist(sp, sy, p, hand) for p in lane) < 0.03:
            k.grasp_stick(0.0, sy)
            k.park_stick(keep_out=keep)
            continue
        if np.linalg.norm(red[:2] - stage) > 0.03:
            if k.pick("red_box"):
                k.place("red_box", stage, 0.0, ry)
            else:
                a.move([a.ee_pos[0], a.ee_pos[1], 0.3], closed=False)
            continue
        # push the box under the rack with the short bar
        red = a.pos("red_box")
        hand = stick_pose(a)[2]
        origin = red[:2] - to_world([PUSH_LOCAL[0], PUSH_LOCAL[1] * hand], [0, 0], ry)
        gxs = [PUSH_GX, 0.0, 0.1, -0.05, 0.15]
        margins = [k.stick_grasp_plan(g, ry, to_world([g, -0.09 * hand], origin, ry))[0] for g in gxs]
        gx = gxs[int(np.argmax(np.array(margins) >= 0.05))] if max(margins) >= 0.05 else gxs[int(np.argmax(margins))]
        k.grasp_stick(gx, ry, to_world([gx, -0.09 * hand], origin, ry))
        k.stick_move(origin, ry, 0.2, iters=3)
        k.stick_lower()
        rack = a.pos("rack")[:2]
        dist = float(np.dot(rack - a.pos("red_box")[:2], d)) + 0.02
        k.stick_shift(dist * d, speed=0.006)
        a.hold(10)
        k.stick_shift(-0.05 * d, speed=0.006)
        k.release_stick()
