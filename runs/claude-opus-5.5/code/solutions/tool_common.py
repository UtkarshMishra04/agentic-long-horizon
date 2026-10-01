"""Shared plan for the scenes whose red box starts beyond the arm's reach: hook it with the L-stick.

Stick frame: long bar along x at y=-0.09 (x in [-0.2, 0.18]); short bar (the hook) along y at x=0.18.
The box is hooked at stick coordinates BOX_LOCAL (inside the L, 3 cm in front of the hook) and pulled
along -x of the stick. The pull direction ``phi`` and the grasp point ``gx`` on the long bar are chosen
so that the gripper stays well inside the reachable radius (the arm locks up beyond ~0.78 m), the
stick stays on the table and away from other objects.
"""

import numpy as np

from common import (
    BOX_SIZE, Skills, rect_point_dist, stick_point_dist, stick_pose, stick_rect_dist, stick_segments, to_world, wrap,
)

REACH_R = 0.76  # boxes farther than this from the robot base are pulled in with the stick first
BOX_LOCAL = np.array([0.095, 0.02])
EE_MAX_R = 0.72
EE_MIN_R = 0.45


def plan_pull(a, name, r_goal=0.62, avoid=()):
    """Returns (phi, gx, distance, box_local) for hooking box ``name`` or None."""
    k = Skills(a)
    b = a.pos(name)[:2]
    az = float(np.arctan2(b[1], b[0]))
    rects = k.obstacles(exclude=(name,)) if not avoid else avoid
    sp, sy, hand = stick_pose(a)
    all_rects = k.obstacles()
    best = None
    for dphi, by in [(dp, by) for dp in np.linspace(-0.9, 0.9, 19) for by in (0.02, 0.0, -0.02)]:
        phi = az + dphi
        u = np.array([np.cos(phi), np.sin(phi)])
        box_local = np.array([BOX_LOCAL[0], by * hand])
        o = b - to_world(box_local, [0, 0], phi)
        # pull distance so that the box ends at r_goal: |b - d u| = r_goal
        bu = float(np.dot(b, u))
        disc = bu * bu - (np.dot(b, b) - r_goal ** 2)
        if disc < 0:
            continue
        d = bu - np.sqrt(disc)
        if d < 0.05 or d > 0.45:
            continue
        ends = [p for seg in stick_segments(o, phi, hand) for p in seg]
        if any(p[0] > 1.1 or abs(p[1]) > 0.62 for p in ends):  # the held stick may overhang the edge
            continue
        ok = True
        for t in np.linspace(0, 1, 6):  # the stick along the pull (1.5 cm from the rack, 3 cm from boxes)
            ot = o - t * d * u
            if any(stick_rect_dist(ot, phi, c, y, h, hand=hand) < (0.015 if h[0] > 0.1 else 0.03) for c, y, h in rects):
                ok = False
                break
        if not ok:
            continue
        for gx in np.linspace(-0.17, 0.05, 12):
            # the open gripper must not touch another box when it grasps the stick at gx
            g = to_world([gx, -0.09 * hand], sp, sy)
            if min([rect_point_dist(c, y, h, g) for c, y, h in all_rects] + [1.0]) < 0.075:
                continue
            ee = to_world([gx, -0.09 * hand], o, phi)
            r_ee = float(np.hypot(*ee))
            if r_ee > EE_MAX_R or abs(ee[1]) > 0.46:  # actions are clipped to |y| <= 0.5
                continue
            # the gripper must not be dragged close to the robot base (the arm folds into its limits)
            dd = d
            while dd > 0.05 and (np.hypot(*(ee - dd * u)) < EE_MIN_R or (ee - dd * u)[0] < 0.38):
                dd -= 0.01
            if np.hypot(*(b - dd * u)) > 0.68:  # the box must end within comfortable reach
                continue
            margin = k.stick_grasp_plan(gx, phi, ee)[0]
            if margin < 0.05:  # the wrist could not turn the stick to phi
                continue
            cost = abs(dphi) + 2.0 * abs(gx + 0.05) + 3.0 * max(r_ee - 0.66, 0) + 5.0 * abs(by - 0.02)
            cost += 2.0 * max(np.hypot(*(b - dd * u)) - r_goal, 0)
            if best is None or cost < best[0]:
                best = (cost, phi, gx, dd, box_local)
    return None if best is None else best[1:]


def free_spot(a, avoid_pts, min_pts=0.17, min_stick=0.12):
    """A free table spot in the workspace, away from the stick, the boxes and the given points."""
    sp, sy, hand = stick_pose(a)
    pts = list(avoid_pts) + [a.pos(n)[:2] for n in a.names if n not in ("lstick", "rack")]
    rack = [(a.pos("rack")[:2], a.yaw("rack"), (0.11, 0.16))] if "rack" in a.names else []
    best, best_score = None, -np.inf
    for x in np.linspace(0.45, 0.68, 10):
        for y in np.linspace(-0.40, 0.40, 33):
            p = np.array([x, y])
            if np.hypot(x, y) > 0.68:
                continue
            ds = stick_point_dist(sp, sy, p, hand)
            dp = min([np.linalg.norm(p - q) for q in pts] + [1.0])
            dr = min([rect_point_dist(c, yy, h, p) for c, yy, h in rack] + [1.0])
            if ds < min_stick or dp < min_pts or dr < 0.12:
                continue
            score = min(ds, 0.25) + min(dp, 0.3) + min(dr, 0.2)
            if score > best_score:
                best, best_score = p, score
    return best


def clear_stick(a, k, keep_out=()):
    """Moves boxes that rest on the stick (scenes can start like that) to a free spot."""
    sp, sy, hand = stick_pose(a)
    for n in a.names:
        if n in ("lstick", "rack"):
            continue
        p = a.pos(n)
        if p[2] > BOX_SIZE[n][2] / 2 + 0.02 and stick_point_dist(sp, sy, p[:2], hand) < 0.06:
            spot = free_spot(a, [q for q, _ in keep_out])
            if spot is not None and k.pick(n):
                k.place(n, spot, 0.0)


def fetch_far_box(a, name="red_box", r_goal=0.62, carry_z=0.2, keep_out=(), valid=None, hard_keep_out=False):
    """Pulls ``name`` to about ``r_goal`` from the robot base with the stick's hook and parks the stick."""
    k = Skills(a)
    b = a.pos(name)
    if float(np.hypot(b[0], b[1])) < REACH_R:
        return k
    clear_stick(a, k, keep_out)
    plan = plan_pull(a, name, r_goal)
    if plan is None:
        # No collision-free flat hook pose: the box is next to the rack and, with this L's handedness,
        # the long bar would have to lie between them. Roll the stick so that the short bar hangs down
        # as a post beyond the box (the long bar then passes high above the rack) and pull with it.
        r = float(np.hypot(b[0], b[1]))
        gx = float(np.clip(0.71 - r, -0.17, 0.05))  # gripper at r ~ 0.6 over the box line (rolls fully)
        phi = float(np.arctan2(b[1], b[0]))
        if k.stick_grasp_plan(gx, phi)[0] > 0.0:
            k.grasp_stick(gx, phi)
            if k.post_pull(name, r - r_goal):
                k.park_stick(carry_z=carry_z, keep_out=keep_out, valid=valid, hard_keep_out=hard_keep_out)
                return k
            k.park_stick(carry_z=carry_z, keep_out=keep_out, valid=valid, hard_keep_out=hard_keep_out)
        # last resort: grasp the box directly with a forward-tilted gripper
        if k.tilt_pick(name):
            p = a.pos(name)[:2]
            k.place(name, p * r_goal / np.hypot(*p), 0.0)
        else:
            a.move([a.ee_pos[0], a.ee_pos[1], 0.25], closed=False)
            a.hold(20)
        return k
    phi, gx, d, box_local = plan
    k.grasp_stick(gx, phi)
    k.pull(name, phi, d, carry_z=carry_z, box_local=tuple(box_local))
    k.park_stick(carry_z=carry_z, keep_out=keep_out, valid=valid, hard_keep_out=hard_keep_out)
    return k
