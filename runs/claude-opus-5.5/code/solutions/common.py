"""Shared scripted-control helpers for the LongHorizonTAMP solutions.

Only the public environment interface is used: make/reset/get_state/get_goal/step/render.
Actions use control="absolute": target end-effector position, axis-angle orientation, gripper.
"""

import os
import sys

import logging
import warnings

import numpy as np

warnings.filterwarnings("ignore")
logging.disable(logging.WARNING)
sys.path.insert(0, "/opt/LongHorizonTAMP")
os.environ.setdefault("MUJOCO_GL", "osmesa")

import longhorizontamp  # noqa: E402

OBJECTS = {
    "LongHorizonTAMP/LiftRedBox-v0": ["rack", "lstick", "red_box"],
    "LongHorizonTAMP/RedBoxOnRack-v0": ["rack", "lstick", "red_box"],
    "LongHorizonTAMP/RedBoxUnderRack-v0": ["rack", "lstick", "red_box"],
    "LongHorizonTAMP/RedBoxUnderRack-v1": ["rack", "lstick", "red_box"],
    "LongHorizonTAMP/RedBoxToBlueSpot-v0": ["lstick", "red_box", "blue_box"],
    "LongHorizonTAMP/RedBoxToBlueSpot-v1": ["lstick", "red_box", "blue_box"],
    "LongHorizonTAMP/PackRack-v0": ["rack", "yellow_box", "red_box", "cyan_box"],
    "LongHorizonTAMP/PackRack-v1": ["rack", "blue_box", "yellow_box", "cyan_box"],
    "LongHorizonTAMP/PackRack-v2": ["rack", "blue_box", "yellow_box", "red_box", "cyan_box"],
}
BOX_SIZE = {"red_box": (0.05, 0.05, 0.07)}
for _n in ("blue_box", "cyan_box", "yellow_box"):
    BOX_SIZE[_n] = (0.07, 0.07, 0.07)
RACK_SIZE = (0.22, 0.32, 0.16)  # x, y, height (object frame at the centre of the top surface)

# Gripper pointing straight down (columns: gripper x, y, z axes in the world).
TOP_DOWN = np.array([[0.0, 1.0, 0.0], [1.0, 0.0, 0.0], [0.0, 0.0, -1.0]])
Q7_LIMIT = 2.6  # keep the last joint away from its +-2.90 rad limit


# ---------------------------------------------------------------- math


def wrap(a):
    return float((a + np.pi) % (2 * np.pi) - np.pi)


def az_of(xy):
    return float(np.arctan2(xy[1], xy[0]))


def rotz(t):
    c, s = np.cos(t), np.sin(t)
    return np.array([[c, -s, 0.0], [s, c, 0.0], [0.0, 0.0, 1.0]])


def quat2mat(q):
    x, y, z, w = np.asarray(q, dtype=np.float64) / np.linalg.norm(q)
    return np.array(
        [
            [1 - 2 * (y * y + z * z), 2 * (x * y - z * w), 2 * (x * z + y * w)],
            [2 * (x * y + z * w), 1 - 2 * (x * x + z * z), 2 * (y * z - x * w)],
            [2 * (x * z - y * w), 2 * (y * z + x * w), 1 - 2 * (x * x + y * y)],
        ]
    )


def mat2axisangle(m):
    angle = np.arccos(np.clip((np.trace(m) - 1) / 2, -1.0, 1.0))
    if angle < 1e-9:
        return np.zeros(3)
    if np.pi - angle < 1e-3:
        # 180 degrees: R + I = 2 a a^T.
        m2 = m + np.eye(3)
        i = int(np.argmax(np.diag(m2)))
        axis = m2[:, i] / np.linalg.norm(m2[:, i])
        return axis * angle
    axis = np.array([m[2, 1] - m[1, 2], m[0, 2] - m[2, 0], m[1, 0] - m[0, 1]]) / (2 * np.sin(angle))
    return axis * angle


def axis_rot(n, ang):
    """Rotation matrix of angle ``ang`` about unit axis ``n``."""
    n = np.asarray(n, dtype=np.float64) / np.linalg.norm(n)
    k = np.array([[0, -n[2], n[1]], [n[2], 0, -n[0]], [-n[1], n[0], 0]])
    return np.eye(3) + np.sin(ang) * k + (1 - np.cos(ang)) * k @ k


def yaw_of(q):
    """Yaw of an object quaternion (x, y, z, w)."""
    m = quat2mat(q)
    return float(np.arctan2(m[1, 0], m[0, 0]))


def ee_yaw_of(q):
    m = quat2mat(q) @ TOP_DOWN.T
    return float(np.arctan2(m[1, 0], m[0, 0]))


def upright(q):
    return abs(quat2mat(q)[2, 2]) > 0.99


def topdown_axisangle(yaw):
    return mat2axisangle(rotz(yaw) @ TOP_DOWN)


def finger_axis(yaw):
    """World x-y direction along which the fingers close for gripper yaw ``yaw``."""
    return np.array([-np.sin(yaw), np.cos(yaw)])


def to_local(xy, origin, yaw):
    d = np.asarray(xy, dtype=np.float64)[:2] - np.asarray(origin)[:2]
    c, s = np.cos(yaw), np.sin(yaw)
    return np.array([c * d[0] + s * d[1], -s * d[0] + c * d[1]])


def to_world(local, origin, yaw):
    c, s = np.cos(yaw), np.sin(yaw)
    return np.asarray(origin)[:2] + np.array([c * local[0] - s * local[1], s * local[0] + c * local[1]])


# ---------------------------------------------------------------- agent


class Done(Exception):
    """Raised when the episode ended (success or time limit)."""


class Agent:
    def __init__(self, env_id, seed, record=False, frame_every=3):
        self.env_id = env_id
        self.env = longhorizontamp.make(env_id, control="absolute", cameras=("agentview",), image_size=16)
        _, info = self.env.reset(seed=seed)
        self.scene_seed = info["scene_seed"]
        self.goal = self.env.get_goal()
        self.names = OBJECTS[env_id]
        self.record = record
        self.frame_every = frame_every
        self.frames = []
        self.steps = 0
        self.success = False
        self.truncated = False
        self.closed = False
        self.tilt = 0.0  # forward tilt of the gripper (rad) towards its yaw direction; 0 = top-down
        self.roll = 0.0  # roll of the gripper (rad) about its yaw direction (along a held stick's bar)
        self.read()
        self.cmd_pos = self.ee_pos.copy()
        self.cmd_yaw = self.ee_yaw
        if record:
            self.frames.append(self.env.render())

    # ------------------------------------------------ state
    def read(self):
        s = self.env.get_state().astype(np.float64)
        self.q = s[0:7]
        self.gripper_q = s[14:20]
        self.ee_pos = s[20:23]
        self.ee_quat = s[23:27]
        self.ee_yaw = ee_yaw_of(self.ee_quat)
        self.objs = {}
        for i, n in enumerate(self.names):
            o = s[27 + 7 * i : 34 + 7 * i]
            self.objs[n] = (o[:3].copy(), o[3:7].copy())
        return s

    def pos(self, name):
        return self.objs[name][0].copy()

    def quat(self, name):
        return self.objs[name][1].copy()

    def yaw(self, name):
        return yaw_of(self.objs[name][1])

    # ------------------------------------------------ low level
    def safe(self, pos):
        """Caps the height of far targets: being high and far (r >= 0.74 m) straightens the elbow into
        its joint limit, where the OSC gets stuck (radial singularity)."""
        pos = np.array(pos, dtype=np.float64)
        r = float(np.hypot(pos[0], pos[1]))
        if self.tilt > 0.3:  # a forward-tilted gripper keeps the wrist back: reach is ~0.15 m longer
            if r > 0.93:
                pos[:2] *= 0.93 / r
            return pos
        if r > 0.80:  # hard limit: the arm cannot recover from a locked elbow
            pos[:2] *= 0.80 / r
            r = 0.80
        if r < 0.40:  # too close to the base the arm folds into its joint limits
            pos[:2] = pos[:2] * 0.40 / max(r, 1e-6) if r > 1e-6 else np.array([0.40, 0.0])
            r = 0.40
        pos[2] = min(pos[2], float(np.interp(r, [0.66, 0.72, 0.76, 0.80, 0.86], [0.45, 0.25, 0.14, 0.08, 0.03])))
        return pos

    def step(self, pos, yaw, closed):
        pos = np.clip(self.safe(pos), [0.1, -0.5, 0.0], [0.95, 0.5, 0.6])
        rot = rotz(yaw) @ TOP_DOWN
        if self.tilt:
            n = np.array([-np.sin(yaw), np.cos(yaw), 0.0])  # finger axis: tilt about it
            rot = axis_rot(n, -self.tilt) @ rot
        if self.roll:
            u = np.array([np.cos(yaw), np.sin(yaw), 0.0])  # along the held bar: roll about it
            rot = axis_rot(u, self.roll) @ rot
        action = np.concatenate([pos, mat2axisangle(rot), [1.0 if closed else -1.0]])
        _, reward, terminated, truncated, info = self.env.step(action)
        self.steps += 1
        self.closed = closed
        self.cmd_pos = np.array(pos, dtype=np.float64)
        self.cmd_yaw = yaw
        if self.record and (self.steps % self.frame_every == 0 or terminated or truncated):
            self.frames.append(self.env.render())
        self.read()
        self.q4_max = max(getattr(self, "q4_max", -9.0), float(self.q[3]))
        if self.q[3] > -0.15 and getattr(self, "lock_info", None) is None:
            self.lock_info = dict(phase=getattr(self, "phase", ""), step=self.steps, cmd=np.round(pos, 3).tolist(), ee=np.round(self.ee_pos, 3).tolist())
        if terminated:
            self.success = True
            raise Done()
        if truncated:
            self.truncated = True
            raise Done()

    def hold(self, n, closed=None):
        closed = self.closed if closed is None else closed
        for _ in range(n):
            self.step(self.cmd_pos, self.cmd_yaw, closed)

    def set_gripper(self, closed, n=10):
        self.hold(n, closed)

    def pred_q7(self, yaw, xy):
        """Predicted last-joint angle after turning the gripper to continuous yaw ``yaw`` (from the
        commanded yaw) and moving to ``xy``: q7 changes by -d(yaw) + d(azimuth)."""
        return float(self.q[6] + wrap(az_of(xy) - az_of(self.ee_pos)) - (yaw - self.cmd_yaw))

    def best_yaw(self, yaw, period, target_xy=None):
        """Among yaw + k*period, the one reachable with the smallest wrist rotation and |q7| margin."""
        target_xy = self.ee_pos[:2] if target_xy is None else target_xy
        d_az = wrap(np.arctan2(target_xy[1], target_xy[0]) - np.arctan2(self.ee_pos[1], self.ee_pos[0]))
        best, best_cost = None, None
        n = int(round(2 * np.pi / period))
        for k in range(n):
            cand = wrap(yaw + k * period)
            change = wrap(cand - self.cmd_yaw)
            for ch in (change, change - np.sign(change) * 2 * np.pi):
                q7 = self.q[6] + d_az - ch
                cost = abs(ch) + (10.0 if abs(q7) > Q7_LIMIT else 0.0)
                if best_cost is None or cost < best_cost:
                    best, best_cost = self.cmd_yaw + ch, cost
        return best

    def move(self, pos, yaw=None, closed=None, speed=0.03, yaw_speed=0.12, tol=0.006, settle=25):
        """Straight-line move of the end effector (continuous yaw ``yaw``, not wrapped)."""
        pos = self.safe(pos)
        closed = self.closed if closed is None else closed
        yaw = self.cmd_yaw if yaw is None else yaw
        start = self.cmd_pos.copy()
        if np.linalg.norm(start - self.ee_pos) > 0.05:
            start = self.ee_pos.copy()
        y0 = self.cmd_yaw
        dist = np.linalg.norm(pos - start)
        n = int(max(np.ceil(dist / speed), np.ceil(abs(yaw - y0) / yaw_speed), 1))
        for i in range(1, n + 1):
            a = i / n
            self.step(start + a * (pos - start), y0 + a * (yaw - y0), closed)
        for _ in range(settle):
            if np.linalg.norm(self.ee_pos - pos) < tol:
                break
            self.step(pos, yaw, closed)
        return np.linalg.norm(self.ee_pos - pos)

    def finish(self, max_steps=None):
        """Idle until the time limit (called when the plan is exhausted)."""
        while True:
            self.hold(1)

    def close(self):
        self.env.close()


# ---------------------------------------------------------------- primitives


class Skills:
    """Pick-and-place and tool-use primitives built on :class:`Agent`."""

    SAFE_Z = 0.34

    def __init__(self, agent):
        self.a = agent

    # ------------------------------------------------ boxes
    def finger_yaw(self, name, xy, box_yaw, avoid, hold_rel=0.0):
        """Gripper yaw for a box at ``xy``/``box_yaw`` whose finger positions keep the most clearance
        from ``avoid`` (a function point -> distance) and that is reachable by the wrist."""
        a = self.a
        half = BOX_SIZE[name][0] / 2
        options = []
        for k in range(2):
            gy = box_yaw + k * np.pi / 2 - hold_rel
            ax = finger_axis(gy)
            clear = min(avoid(np.asarray(xy)[:2] + sgn * (half + 0.025) * ax) for sgn in (-1, 1)) if avoid else 1.0
            options.append((clear, gy))
        c0, c1 = options[0][0], options[1][0]
        if avoid and abs(c0 - c1) > 0.01 and min(c0, c1) < 0.05:
            gy = options[0][1] if c0 > c1 else options[1][1]
            return a.best_yaw(gy, np.pi, xy)
        return a.best_yaw(box_yaw - hold_rel, np.pi / 2, xy)

    def pick(self, name, speed=0.03, avoid=None):
        a = self.a
        a.phase = "pick"
        p, y = a.pos(name), a.yaw(name)
        yaw = self.finger_yaw(name, p[:2], y, avoid)
        a.move([a.ee_pos[0], a.ee_pos[1], max(a.ee_pos[2], self.SAFE_Z)], closed=False)
        r = float(np.hypot(p[0], p[1]))
        if r > 0.64:
            # far box: come in low from the inside (descending from high up at r > 0.72 locks the elbow)
            inner = p[:2] * (r - 0.1) / r
            a.move([inner[0], inner[1], self.SAFE_Z], yaw, closed=False, speed=speed)
            a.move([inner[0], inner[1], p[2] + 0.085], closed=False, speed=speed)
            a.move([p[0], p[1], p[2] + 0.085], closed=False, speed=0.015)
        else:
            a.move([p[0], p[1], self.SAFE_Z], yaw, closed=False, speed=speed)
        # re-read the box (it may have moved) and descend
        p = a.pos(name)
        a.move([p[0], p[1], p[2] + 0.08], closed=False, speed=speed)
        p = a.pos(name)
        a.move([p[0], p[1], max(p[2] - 0.005, 0.02)], closed=False, speed=0.015, settle=15)
        a.set_gripper(True, 10)
        a.move([a.ee_pos[0], a.ee_pos[1], p[2] + 0.06], closed=True, speed=0.015)
        return self.holding(name)

    def holding(self, name):
        a = self.a
        p = a.pos(name)
        return bool(np.linalg.norm(p[:2] - a.ee_pos[:2]) < 0.04 and p[2] > BOX_SIZE[name][2] / 2 + 0.02)

    def place(self, name, xy, bottom_z, yaw=None, speed=0.03, release_gap=0.006, avoid=None):
        """Places the held box with its centre at ``xy`` and its bottom at ``bottom_z``."""
        a = self.a
        a.phase = "place"
        h = BOX_SIZE[name][2]
        off = a.ee_pos[2] - a.pos(name)[2]  # ee height above the box centre
        ee_off_xy = a.ee_pos[:2] - a.pos(name)[:2]
        cz = bottom_z + h / 2 + off
        carry = max(self.SAFE_Z, bottom_z + h + off + 0.04)
        a.move([a.ee_pos[0], a.ee_pos[1], carry], speed=speed)
        if avoid is not None:
            rel = wrap(a.yaw(name) - a.ee_yaw)
            target_yaw = self.finger_yaw(name, xy, a.yaw(name) if yaw is None else yaw, avoid, hold_rel=rel)
        elif yaw is None:
            target_yaw = a.cmd_yaw
        else:
            # box yaw relative to the gripper is preserved; symmetric under 90 degrees
            rel = wrap(a.yaw(name) - a.ee_yaw)
            target_yaw = a.best_yaw(yaw - rel, np.pi / 2, xy)
        a.move([xy[0] + ee_off_xy[0], xy[1] + ee_off_xy[1], carry], target_yaw, speed=speed)
        # correct for the measured offset once more
        for _ in range(2):
            err = np.asarray(xy) - a.pos(name)[:2]
            a.move([a.cmd_pos[0] + err[0], a.cmd_pos[1] + err[1], carry], speed=speed, settle=10)
        a.move([a.cmd_pos[0], a.cmd_pos[1], cz + 0.05], speed=speed)
        err = np.asarray(xy) - a.pos(name)[:2]
        a.move([a.cmd_pos[0] + err[0], a.cmd_pos[1] + err[1], cz + release_gap], speed=0.01, settle=15)
        a.set_gripper(False, 8)
        a.move([a.cmd_pos[0], a.cmd_pos[1], carry], closed=False, speed=0.02)

    # ------------------------------------------------ far boxes without the stick
    TILT = 0.6

    def set_tilt(self, tilt, steps=8):
        a = self.a
        for t in np.linspace(a.tilt, tilt, steps + 1)[1:]:
            a.tilt = float(t)
            a.hold(3)

    def tilt_pick(self, name):
        """Grasps a box beyond the top-down reach with the gripper tilted forward by TILT (approaching
        along the box's azimuth), and brings it back to r = 0.6 m. Returns True if held."""
        a = self.a
        a.phase = "tilt_pick"
        b = a.pos(name)
        az = az_of(b)
        # gripper yaw: aligned with the box faces (fingers on two faces), within 0.6 rad of the azimuth,
        # and with the tilted gripper body (behind and above the box) clear of the rack and other boxes
        rects = self.obstacles(exclude=(name,))
        best = None
        for k4 in range(4):
            for dy in np.linspace(-0.2, 0.2, 9):
                yaw_c = a.yaw(name) + k4 * np.pi / 2 + dy
                dev = abs(wrap(yaw_c - az))
                if dev > 0.6:
                    continue
                u = np.array([np.cos(yaw_c), np.sin(yaw_c)])
                n = np.array([-u[1], u[0]])
                body = [b[:2] - s_u * u + s_n * n for s_u in (0.0, 0.08, 0.16) for s_n in (-0.075, 0.0, 0.075)]
                clear = min([rect_point_dist(c, y, h, p) for c, y, h in rects for p in body] + [1.0])
                if clear < 0.01:  # the tilted gripper body would hit the rack or a box
                    continue
                cost = -min(clear, 0.05) * 20 + abs(dy) + 0.3 * dev
                if best is None or cost < best[0]:
                    best = (cost, yaw_c)
        if best is None:
            return False
        yaw = a.cmd_yaw + wrap(best[1] - a.cmd_yaw)
        u = np.array([np.cos(yaw), np.sin(yaw)])
        a.move([a.ee_pos[0], a.ee_pos[1], max(a.ee_pos[2], 0.25)], closed=False)
        a.move([0.5 * np.cos(az), 0.5 * np.sin(az), 0.25], yaw, closed=False, speed=0.03)
        self.set_tilt(self.TILT)
        appr = np.array([np.sin(self.TILT) * u[0], np.sin(self.TILT) * u[1], -np.cos(self.TILT)])
        target = np.array([b[0], b[1], b[2]])
        a.move(target - 0.12 * appr, closed=False, speed=0.02, settle=20, tol=0.008)
        a.move(target, closed=False, speed=0.01, settle=30)
        a.set_gripper(True, 12)
        back = b[:2] - 0.12 * u
        a.move([back[0], back[1], 0.15], closed=True, speed=0.01)
        a.move([0.6 * np.cos(az), 0.6 * np.sin(az), 0.2], closed=True, speed=0.015)
        self.set_tilt(0.0)
        return self.holding(name)

    # ------------------------------------------------ L-stick
    # Object frame of the stick: long bar along x at y=-0.09 (x in [-0.2, 0.18]), short bar along y
    # at x=0.18 (y in [-0.11, 0.11]); bars are 0.04 thick. The hook's inner face is at x=0.16.
    STICK_BAR_Y = -0.09
    STICK_Z = 0.02

    Q7_SAFE = 2.65

    def stick_grasp_plan(self, gx, final_yaw, final_xy=None):
        """Plans the gripper yaw for grasping the long bar at ``gx`` (stick yaw or stick yaw + pi, any
        2*pi unwrap) and the continuous gripper yaw after turning the stick to ``final_yaw`` with the
        gripper at ``final_xy``. Returns (margin, grasp_yaw, final_ee_yaw); margin < 0 means the wrist
        (q7, which changes by -d(yaw) + d(azimuth)) would leave its safe range."""
        a = self.a
        sp, sy, hand = stick_pose(a)
        g = to_world([gx, self.STICK_BAR_Y * hand], sp, sy)
        final_xy = g if final_xy is None else np.asarray(final_xy)[:2]
        best = None
        for flip in (0.0, np.pi):
            base = a.cmd_yaw + wrap(sy + flip - a.cmd_yaw)
            for kg in (-1, 0, 1):
                gyaw = base + 2 * np.pi * kg
                q7g = a.pred_q7(gyaw, g)
                fbase = gyaw + wrap(final_yaw - sy)
                for kf in (-1, 0, 1):
                    fyaw = fbase + 2 * np.pi * kf
                    q7f = q7g + wrap(az_of(final_xy) - az_of(g)) - (fyaw - gyaw)
                    margin = self.Q7_SAFE - max(abs(q7g), abs(q7f))
                    cost = abs(gyaw - a.cmd_yaw) + abs(fyaw - gyaw) - 10 * min(margin, 0.3)
                    if best is None or cost < best[0]:
                        best = (cost, margin, gyaw, fyaw)
        return best[1:]

    def grasp_stick(self, gx, final_yaw, final_xy=None):
        """Grasps the long bar at object-frame x=``gx`` with a gripper yaw that lets the wrist turn
        the stick to ``final_yaw`` later (see :meth:`stick_grasp_plan`)."""
        a = self.a
        a.phase = "grasp_stick"
        sp, sy, hand = stick_pose(a)
        g = to_world([gx, self.STICK_BAR_Y * hand], sp, sy)
        _, gyaw, fyaw = self.stick_grasp_plan(gx, final_yaw, final_xy)
        a.move([a.ee_pos[0], a.ee_pos[1], max(a.ee_pos[2], 0.15)], closed=False)
        a.move([g[0], g[1], 0.15], gyaw, closed=False)
        a.move([g[0], g[1], 0.06], closed=False, speed=0.02)
        a.move([g[0], g[1], 0.015], closed=False, speed=0.01, settle=15)
        a.set_gripper(True, 12)
        a.move([g[0], g[1], 0.03], closed=True, speed=0.004)
        a.move([g[0], g[1], 0.14], closed=True, speed=0.008)  # clear the 7 cm boxes before turning
        self.final_ee_yaw = fyaw
        self.update_stick_grasp()
        return a.pos("lstick")[2] > 0.04

    def update_stick_grasp(self):
        a = self.a
        self.rel = to_local(a.pos("lstick"), a.ee_pos, a.ee_yaw)
        self.rel_yaw = wrap(a.yaw("lstick") - a.ee_yaw)
        self.rel_z = a.ee_pos[2] - a.pos("lstick")[2]

    def stick_ok(self):
        """True if the stick is still held flat."""
        a = self.a
        return upright(a.quat("lstick")) and np.linalg.norm(a.pos("lstick")[:2] - a.ee_pos[:2]) < 0.3

    def ee_for_stick(self, origin, stick_yaw):
        """End-effector xy and continuous yaw that put the held stick at ``origin``/``stick_yaw``;
        among the 2*pi unwraps of the yaw, the smallest turn that keeps q7 in its safe range."""
        a = self.a
        base = a.cmd_yaw + wrap(stick_yaw - self.rel_yaw - a.cmd_yaw)
        best = None
        for kk in (0, -1, 1):
            eyaw = base + 2 * np.pi * kk
            xy = np.asarray(origin)[:2] - to_world(self.rel, [0, 0], eyaw)
            q7 = a.pred_q7(eyaw, xy)
            cost = abs(eyaw - a.cmd_yaw) + (10 + abs(q7) if abs(q7) > self.Q7_SAFE else 0)
            if best is None or cost < best[0]:
                best = (cost, xy, eyaw, q7)
        self.last_q7 = best[3]
        return best[1], best[2]

    def stick_move(self, origin, stick_yaw, stick_z, speed=0.012, yaw_speed=0.035, settle=15, iters=1):
        """Moves the held stick to a pose; ``iters`` > 1 re-measures the grasp and corrects."""
        a = self.a
        a.phase = "stick_move"
        if a.cmd_pos[2] < stick_z + self.rel_z - 0.01:  # rise first, then turn and translate
            a.move([a.cmd_pos[0], a.cmd_pos[1], stick_z + self.rel_z], speed=speed)
        if stick_z > 0.1:
            # a stick held far from its centre of mass droops: lift until its lowest point is where a
            # flat stick's bottom would be
            droop = (stick_z - 0.02) - self.stick_min_z()
            if droop > 0.01:
                stick_z += droop
                a.move([a.cmd_pos[0], a.cmd_pos[1], a.cmd_pos[2] + droop], speed=speed)
        for it in range(iters):
            if it > 0:
                a.hold(4)
                self.update_stick_grasp()
            xy, eyaw = self.ee_for_stick(origin, stick_yaw)
            a.move([xy[0], xy[1], stick_z + self.rel_z], eyaw, speed=speed, yaw_speed=yaw_speed, settle=settle)

    def stick_lower(self, z=0.021, speed=0.006):
        a = self.a
        a.move([a.cmd_pos[0], a.cmd_pos[1], z + self.rel_z], speed=speed, settle=10)

    def stick_shift(self, delta_xy, z=None, speed=0.008, settle=10):
        """Translates the held stick (and the end effector) by ``delta_xy``."""
        a = self.a
        zz = a.cmd_pos[2] if z is None else z + self.rel_z
        a.move([a.cmd_pos[0] + delta_xy[0], a.cmd_pos[1] + delta_xy[1], zz], speed=speed, settle=settle)

    def release_stick(self, lift=0.15):
        a = self.a
        a.phase = "release_stick"
        a.move([a.cmd_pos[0], a.cmd_pos[1], self.rel_z + self.STICK_Z + 0.002], speed=0.006, settle=10)
        a.set_gripper(False, 8)
        a.move([a.cmd_pos[0], a.cmd_pos[1], lift], closed=False, speed=0.015)

    def set_roll(self, roll, steps=15):
        a = self.a
        for t in np.linspace(a.roll, roll, steps + 1)[1:]:
            a.roll = float(t)
            a.hold(3)

    def stick_min_z(self):
        """Height of the lowest corner of the stick's two bars."""
        a = self.a
        p, rot = a.pos("lstick"), quat2mat(a.quat("lstick"))
        z = []
        for cx, cy, hx, hy in ((-0.01, -0.09, 0.19, 0.02), (0.18, 0.01, 0.02, 0.1)):
            for sx in (-1, 1):
                for sy in (-1, 1):
                    for sz in (-1, 1):
                        z.append((p + rot @ np.array([cx + sx * hx, cy + sy * hy, sz * 0.02]))[2])
        return float(min(z))

    def stick_point(self, local):
        """World position of a point given in the (3D) stick frame."""
        a = self.a
        return a.pos("lstick") + quat2mat(a.quat("lstick")) @ np.asarray(local, dtype=np.float64)

    def post_pull(self, name, distance, gap=0.07):
        """Pulls box ``name`` towards the robot base by ``distance`` with the stick rolled 90 degrees
        about its long bar, so that the short bar hangs down as a vertical post just beyond the box
        while the long bar passes high above everything (used when the box lies so close to the rack
        that the flat L cannot be laid around it). The stick must already be held."""
        a = self.a
        a.phase = "post_pull"
        b = a.pos(name)
        phi = az_of(b)
        u = np.array([np.cos(phi), np.sin(phi)])
        post_xy = b[:2] + gap * u
        hand = stick_hand(a.quat("lstick"))
        # flat stick with its long bar straight over the box and the corner above the post spot
        origin = post_xy - to_world([0.18, -0.09 * hand], [0, 0], phi)
        # roll high: while turning down, the short bar sweeps a quarter circle (radius 0.2 m) that may
        # pass over the rack top (0.16 m) when the box is next to the rack
        self.stick_move(a.pos("lstick")[:2], a.yaw("lstick"), 0.42, speed=0.01)
        self.stick_move(origin, phi, 0.42, iters=2)
        # roll so that the short bar (+y of the stick) swings down: about the gripper yaw direction,
        # which is +x or -x of the stick depending on how the stick was grasped
        sign = (1.0 if abs(self.rel_yaw) > np.pi / 2 else -1.0) * hand
        self.set_roll(sign * np.pi / 2, steps=30)
        # the arm may not realize the full roll: keep rolling until the post (stick y axis) hangs down
        while quat2mat(a.quat("lstick"))[2, 1] > -0.97 and abs(a.roll) < 2.1:
            self.set_roll(a.roll + sign * 0.05, steps=1)
            a.hold(2)
        tip_local = [0.18, 0.09, 0.0]
        y_axis_z = quat2mat(a.quat("lstick"))[2, 1]
        if self.stick_point(tip_local)[2] > a.ee_pos[2] - 0.12 or y_axis_z > -0.8:
            # the stick slipped in the grasp instead of hanging down: undo
            self.set_roll(0.0, steps=30)
            self.settle_stick()
            return False
        for z_tip, sp in ((0.12, 0.01), (0.012, 0.006)):
            for _ in range(3):
                want = np.array([post_xy[0], post_xy[1], z_tip])
                off = self.stick_point(tip_local) - a.ee_pos
                a.move(want - off, speed=sp, settle=15)
        start = a.cmd_pos.copy()
        a.move([start[0] - distance * u[0], start[1] - distance * u[1], start[2]], speed=0.006, settle=10)
        a.move([a.cmd_pos[0], a.cmd_pos[1], a.cmd_pos[2] + 0.15], speed=0.01)
        self.set_roll(0.0, steps=30)
        self.settle_stick()
        return True

    def settle_stick(self):
        """After rolling: if the held stick is not flat any more, set it down on the table (it then
        lies flat, possibly upside down, which the geometry handles) and grasp it again."""
        a = self.a
        self.update_stick_grasp()
        if abs(quat2mat(a.quat("lstick"))[2, 2]) > 0.95:
            return
        a.move([a.cmd_pos[0], a.cmd_pos[1], 0.25], speed=0.01)
        low = self.stick_min_z()
        a.move([a.cmd_pos[0], a.cmd_pos[1], a.cmd_pos[2] - low + 0.005], speed=0.006, settle=10)
        a.set_gripper(False, 10)
        a.move([a.cmd_pos[0], a.cmd_pos[1], 0.25], closed=False, speed=0.015)
        a.hold(10)
        self.grasp_stick(-0.05, a.yaw("lstick"))

    def pull(self, name, phi, distance, carry_z=0.2, box_local=(0.095, 0.02)):
        """Hooks box ``name`` with the short bar (stick x axis at yaw ``phi``) and pulls it by
        ``distance`` along -x of the stick. The stick must already be held."""
        a = self.a
        a.phase = "pull"
        b = a.pos(name)
        o = b[:2] - to_world(box_local, [0, 0], phi)
        self.stick_move(o, phi, carry_z, iters=3)
        self.stick_lower()
        d = np.array([np.cos(phi), np.sin(phi)])
        self.stick_shift(-distance * d, speed=0.008)
        # lift straight up (the grasp may have slipped during the pull, so do not use the stale offset)
        a.move([a.cmd_pos[0], a.cmd_pos[1], carry_z + self.rel_z], speed=0.008)
        self.update_stick_grasp()

    def obstacles(self, exclude=()):
        """(centre, yaw, half extents) rectangles of the boxes and the rack."""
        a = self.a
        out = []
        for n in a.names:
            if n in exclude or n == "lstick":
                continue
            half = (0.11, 0.16) if n == "rack" else (BOX_SIZE[n][0] / 2, BOX_SIZE[n][1] / 2)
            out.append((a.pos(n)[:2], a.yaw(n), half))
        return out

    def stick_clearance(self, origin, yaw, rects, hand=1.0):
        return min([stick_rect_dist(origin, yaw, c, y, h, hand=hand) for c, y, h in rects] + [1.0])

    def park_stick(self, carry_z=0.2, clearance=0.07, keep_out=(), valid=None, hard_keep_out=False):
        """Parks the held stick; relaxes the clearance (and finally the keep-out zones, unless they are
        hard constraints) if needed."""
        levels = [(clearance, keep_out), (0.05, keep_out), (0.035, keep_out)]
        if not hard_keep_out:
            levels.append((0.035, ()))
        for clr, ko in levels:
            try:
                return self._park_stick(carry_z, clr, ko, valid)
            except RuntimeError:
                continue
        raise RuntimeError("no parking pose for the stick")

    def _park_stick(self, carry_z=0.2, clearance=0.07, keep_out=(), valid=None):
        """Lifts the held stick, moves it to the nearest pose (same yaw) with ``clearance`` from all
        boxes/rack and ``keep_out`` points (point, radius), and releases it on the table."""
        a = self.a
        a.phase = "park_stick"
        o, y, hand = stick_pose(a)
        rects = self.obstacles()
        best = None
        reasons = {"table": 0, "reach": 0, "valid": 0, "clear": 0}
        for x in np.linspace(0.35, 0.9, 23):
            for yy in np.linspace(-0.4, 0.4, 33):
                cand = np.array([x, yy])
                d = float(np.linalg.norm(cand - o))
                for cy in y + np.linspace(-np.pi, np.pi, 16, endpoint=False):
                    dy = abs(wrap(cy - y))
                    cost = d + 0.1 * dy
                    if best is not None and cost >= best[0]:
                        continue
                    ends = [p for seg in stick_segments(cand, cy, hand) for p in seg]
                    if any(p[0] < 0.3 or p[0] > 0.95 or abs(p[1]) > 0.43 for p in ends):
                        reasons["table"] += 1
                        continue
                    xy, _ = self.ee_for_stick(cand, cy)
                    if np.hypot(*xy) > 0.72 or np.hypot(*xy) < 0.42 or xy[0] < 0.3:
                        reasons["reach"] += 1
                        continue
                    if abs(self.last_q7) > self.Q7_SAFE:
                        reasons["wrist"] = reasons.get("wrist", 0) + 1
                        continue
                    if valid is not None and not valid(cand, cy):
                        reasons["valid"] += 1
                        continue
                    c = self.stick_clearance(cand, cy, rects, hand)
                    for p, r in keep_out:  # keep-out points need less margin than objects
                        c = min(c, stick_point_dist(cand, cy, p, hand) - r + clearance - 0.03)
                    if c < clearance:
                        reasons["clear"] += 1
                        continue
                    best = (cost, cand, cy)
        if best is None:
            raise RuntimeError(f"no parking pose for the stick {reasons} rel={self.rel}")
        _, cand, cy = best
        self.stick_move(a.pos("lstick")[:2], y, carry_z, speed=0.008)
        self.stick_move(cand, cy, carry_z, iters=2)
        self.release_stick()
        return cand, cy


# ---------------------------------------------------------------- geometry helpers


def stick_hand(q):
    """+1 if the stick lies the right way up, -1 if it is upside down (then it is the mirror-image L:
    with the yaw of its x axis, every stick-frame y coordinate is negated)."""
    return 1.0 if quat2mat(q)[2, 2] >= 0 else -1.0


def stick_pose(a):
    """(xy, yaw, hand) of the stick."""
    return a.pos("lstick")[:2], a.yaw("lstick"), stick_hand(a.quat("lstick"))


def stick_segments(origin, yaw, hand=1.0):
    """The two bars of the stick as (start, end) world segments (bar half-width 0.02)."""
    return [
        (to_world([-0.2, -0.09 * hand], origin, yaw), to_world([0.18, -0.09 * hand], origin, yaw)),
        (to_world([0.18, -0.09 * hand], origin, yaw), to_world([0.18, 0.11 * hand], origin, yaw)),
    ]


def seg_point_dist(p, a, b):
    p, a, b = (np.asarray(v, dtype=np.float64)[:2] for v in (p, a, b))
    ab = b - a
    t = np.clip(np.dot(p - a, ab) / max(np.dot(ab, ab), 1e-12), 0, 1)
    return float(np.linalg.norm(p - (a + t * ab)))


def stick_point_dist(origin, yaw, p, hand=1.0):
    return min(seg_point_dist(p, s, e) for s, e in stick_segments(origin, yaw, hand)) - 0.02


def rect_point_dist(center, yaw, half, p):
    loc = np.abs(to_local(p, center, yaw)) - np.asarray(half)
    return float(np.linalg.norm(np.maximum(loc, 0)) + min(max(loc[0], loc[1]), 0))


def stick_rect_dist(origin, yaw, center, rect_yaw, half, samples=24, hand=1.0):
    """Approximate distance between the stick and a rectangle (sampled along the bars)."""
    d = np.inf
    for s, e in stick_segments(origin, yaw, hand):
        for t in np.linspace(0, 1, samples):
            p = s + t * (e - s)
            d = min(d, rect_point_dist(center, rect_yaw, half, p) - 0.02)
    return d


# ---------------------------------------------------------------- running


HOME = np.array([0.5, 0.0, 0.3])


def run_episode(env_id, solve, seed, record=False, frame_every=3):
    agent = Agent(env_id, seed, record=record, frame_every=frame_every)
    error = None
    try:
        # Leave the random start pose at once: holding some start poses (far and high) lets the
        # elbow drift to its joint limit, where the OSC gets stuck (radial singularity).
        agent.move(HOME, agent.ee_yaw, speed=0.03, settle=5)
        solve(agent)
        agent.finish()
    except Done:
        pass
    except Exception as e:  # a planning error: idle until the time limit so the episode ends
        import traceback

        error = traceback.format_exc()
        try:
            agent.finish()
        except Done:
            pass
    result = dict(
        env_id=env_id, seed=seed, scene_seed=agent.scene_seed, success=agent.success, steps=agent.steps,
        error=error, q4_max=round(getattr(agent, "q4_max", -9.0), 3), lock=getattr(agent, "lock_info", None),
    )
    frames = agent.frames
    agent.close()
    return result, frames


def save_video(frames, path, success):
    """Writes frames with a SUCCESS/FAILURE banner to ``path`` (.gif or .mp4)."""
    import imageio
    from PIL import Image, ImageDraw

    out = []
    for i, f in enumerate(frames):
        im = Image.fromarray(f)
        d = ImageDraw.Draw(im)
        last = i == len(frames) - 1
        text = ("SUCCESS" if success else "FAILURE") if last else ("result: " + ("SUCCESS" if success else "FAILURE"))
        d.rectangle([0, 0, im.width, 14], fill=(0, 120, 0) if success else (160, 0, 0))
        d.text((4, 2), text, fill=(255, 255, 255))
        out.append(np.asarray(im))
    out += [out[-1]] * 15
    if path.endswith(".gif"):
        imageio.mimsave(path, out, duration=0.1)
    else:
        imageio.mimsave(path, out, fps=10)


def main(env_id, solve):
    import argparse

    p = argparse.ArgumentParser()
    p.add_argument("--seed", type=int, default=0)
    p.add_argument("--video", default=None, help="output .gif/.mp4 path")
    args = p.parse_args()
    result, frames = run_episode(env_id, solve, args.seed, record=args.video is not None)
    print(result)
    if args.video:
        save_video(frames, args.video, result["success"])
