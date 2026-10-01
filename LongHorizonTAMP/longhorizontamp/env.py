"""Tabletop manipulation environments with end-effector control.

``make(env_id)`` returns a :class:`TabletopEnv`. An episode starts from a sampled scene and ends with
success (the goal holds: reward 1, ``terminated``) or at the time limit (``truncated``).
"""

from __future__ import annotations

import dataclasses
from typing import Any, Dict, List, Optional, Sequence, Tuple

import gym
import numpy as np
from robosuite.utils import transform_utils as T

from longhorizontamp import predicates
from longhorizontamp.geometry import LIFT_HEIGHT
from longhorizontamp.scene import TabletopScene, load_yaml

ENV_IDS: Dict[str, str] = {
    "LongHorizonTAMP/LiftRedBox-v0": "tasks/lift_red_box.yaml",
    "LongHorizonTAMP/RedBoxOnRack-v0": "tasks/red_box_on_rack.yaml",
    "LongHorizonTAMP/RedBoxUnderRack-v0": "tasks/red_box_under_rack_0.yaml",
    "LongHorizonTAMP/RedBoxUnderRack-v1": "tasks/red_box_under_rack_1.yaml",
    "LongHorizonTAMP/RedBoxToBlueSpot-v0": "tasks/red_box_to_blue_spot_0.yaml",
    "LongHorizonTAMP/RedBoxToBlueSpot-v1": "tasks/red_box_to_blue_spot_1.yaml",
    "LongHorizonTAMP/PackRack-v0": "tasks/pack_rack_0.yaml",
    "LongHorizonTAMP/PackRack-v1": "tasks/pack_rack_1.yaml",
    "LongHorizonTAMP/PackRack-v2": "tasks/pack_rack_2.yaml",
}
"""Environment id -> scene file (inside the package)."""

MAX_EPISODE_STEPS: Dict[str, int] = {
    "LongHorizonTAMP/LiftRedBox-v0": 1500,
    "LongHorizonTAMP/RedBoxOnRack-v0": 1800,
    "LongHorizonTAMP/RedBoxUnderRack-v0": 1300,
    "LongHorizonTAMP/RedBoxUnderRack-v1": 2500,
    "LongHorizonTAMP/RedBoxToBlueSpot-v0": 1000,
    "LongHorizonTAMP/RedBoxToBlueSpot-v1": 2400,
    "LongHorizonTAMP/PackRack-v0": 1000,
    "LongHorizonTAMP/PackRack-v1": 1600,
    "LongHorizonTAMP/PackRack-v2": 2000,
}
"""Default time limit per environment (control steps at 20 Hz)."""


@dataclasses.dataclass
class _Control:
    mode: str = "delta"
    max_delta_pos: float = 0.05
    max_delta_rot: float = 0.25
    gripper_threshold: float = 0.0
    position_low: Tuple[float, float, float] = (0.1, -0.5, 0.0)
    position_high: Tuple[float, float, float] = (0.95, 0.5, 0.6)


class TabletopEnv:
    """One tabletop environment (see ``README.md`` for spaces, state layout and goal format).

    Args:
        env_id: One of :data:`ENV_IDS`.
        control: ``"delta"`` or ``"absolute"`` end-effector actions.
        max_episode_steps: Time limit in control steps (default: :data:`MAX_EPISODE_STEPS`).
        image_size: Height and width of the camera images in the observation.
        cameras: Cameras included in the observation.
        render_size: Height and width of ``render()`` images.
    """

    def __init__(
        self,
        env_id: str,
        control: str = "delta",
        max_episode_steps: Optional[int] = None,
        image_size: int = 84,
        cameras: Sequence[str] = ("agentview", "robot0_eye_in_hand"),
        render_size: int = 256,
    ):
        if env_id not in ENV_IDS:
            raise KeyError(f"Unknown environment {env_id!r}; choose from {sorted(ENV_IDS)}.")
        if control not in ("delta", "absolute"):
            raise ValueError(f"Unknown control mode {control!r} (use 'delta' or 'absolute').")
        self.env_id = env_id
        self._control = _Control(mode=control)
        self.max_episode_steps = (
            MAX_EPISODE_STEPS[env_id] if max_episode_steps is None else int(max_episode_steps)
        )
        self._cameras = tuple(cameras)
        self._image_size = int(image_size)
        self._render_size = int(render_size)
        config = load_yaml(ENV_IDS[env_id])
        self._scene = TabletopScene(**config, camera_size=self._image_size)
        self._steps = 0
        self._objects = [obj for obj in self._scene.objects.values() if not obj.is_static]

        num_gripper = len(self._scene.robot.robot._ref_gripper_joint_pos_indexes)
        spaces: Dict[str, gym.spaces.Space] = {
            f"{camera}_image": gym.spaces.Box(0, 255, (self._image_size, self._image_size, 3), dtype=np.uint8)
            for camera in self._cameras
        }
        spaces["robot0_joint_pos"] = gym.spaces.Box(-np.inf, np.inf, (7,), dtype=np.float32)
        spaces["robot0_joint_vel"] = gym.spaces.Box(-np.inf, np.inf, (7,), dtype=np.float32)
        spaces["robot0_eef_pos"] = gym.spaces.Box(-np.inf, np.inf, (3,), dtype=np.float32)
        spaces["robot0_eef_quat"] = gym.spaces.Box(-1.0, 1.0, (4,), dtype=np.float32)
        spaces["robot0_gripper_qpos"] = gym.spaces.Box(-np.inf, np.inf, (num_gripper,), dtype=np.float32)
        spaces["robot0_gripper_opening"] = gym.spaces.Box(0.0, 1.0, (1,), dtype=np.float32)
        self.observation_space = gym.spaces.Dict(spaces)
        if control == "delta":
            self.action_space = gym.spaces.Box(-1.0, 1.0, (7,), dtype=np.float32)
        else:
            c = self._control
            low = np.array([*c.position_low, -np.pi, -np.pi, -np.pi, -1.0], dtype=np.float32)
            high = np.array([*c.position_high, np.pi, np.pi, np.pi, 1.0], dtype=np.float32)
            self.action_space = gym.spaces.Box(low, high, dtype=np.float32)

    # ------------------------------------------------------------------ API

    def reset(self, seed: Optional[int] = None) -> Tuple[Dict[str, np.ndarray], dict]:
        """Samples a new scene. Seeds whose scene is invalid are skipped (``info["scene_seed"]``)."""
        self._scene.reset(seed=seed)
        self._scene.robot._set_gripper(closed=False, steps=2)
        self._steps = 0
        return self._observation(), self._info(success=False)

    def get_state(self) -> np.ndarray:
        """Flat float32 simulator state (layout in ``README.md``)."""
        robot = self._scene.robot
        eef = robot.eef_pose()
        parts: List[np.ndarray] = [
            robot.joint_positions(),
            robot.joint_velocities(),
            robot.gripper_joint_positions(),
            eef.pos,
            eef.quat,
        ]
        for obj in self._objects:
            pose = obj.pose()
            parts += [pose.pos, pose.quat]
        return np.concatenate(parts).astype(np.float32)

    def get_goal(self) -> Dict[str, Any]:
        """Goal of the current episode (format in ``README.md``)."""
        conditions = [_describe(prop, self._scene) for prop in self._scene.goal]
        return {"text": "; ".join(c["text"] for c in conditions), "conditions": conditions}

    def step(self, action: np.ndarray) -> Tuple[Dict[str, np.ndarray], float, bool, bool, dict]:
        action = np.asarray(action, dtype=np.float64).reshape(-1)
        if action.shape != (7,):
            raise ValueError(f"Expected a 7-dimensional action, got shape {action.shape}.")
        position, quat = self._target_pose(action)
        closed = bool(action[6] > self._control.gripper_threshold)
        self._scene.robot.control_step(position, quat, closed)
        self._steps += 1
        success = bool(self._scene.is_goal())
        truncated = not success and self._steps >= self.max_episode_steps
        return self._observation(), float(success), success, truncated, self._info(success)

    def render(self) -> np.ndarray:
        """``agentview`` camera image ``[render_size, render_size, 3]`` (uint8)."""
        return self._scene.camera_images(["agentview"], size=self._render_size)["agentview"]

    def close(self) -> None:
        self._scene.close()

    # ------------------------------------------------------------------ helpers

    def _target_pose(self, action: np.ndarray) -> Tuple[np.ndarray, np.ndarray]:
        control = self._control
        if control.mode == "delta":
            pose = self._scene.robot.eef_pose()
            delta = np.clip(action[:6], -1.0, 1.0)
            position = pose.pos + delta[:3] * control.max_delta_pos
            rotation = T.axisangle2quat(delta[3:6] * control.max_delta_rot)
            quat = T.quat_multiply(rotation, pose.quat)
        else:
            position = action[:3]
            quat = T.axisangle2quat(action[3:6])
        position = np.clip(position, control.position_low, control.position_high)
        return position, quat / np.linalg.norm(quat)

    def _observation(self) -> Dict[str, np.ndarray]:
        robot = self._scene.robot
        observation: Dict[str, np.ndarray] = {
            f"{camera}_image": image
            for camera, image in self._scene.camera_images(self._cameras, size=self._image_size).items()
        }
        eef = robot.eef_pose()
        observation["robot0_joint_pos"] = robot.joint_positions().astype(np.float32)
        observation["robot0_joint_vel"] = robot.joint_velocities().astype(np.float32)
        observation["robot0_eef_pos"] = eef.pos.astype(np.float32)
        observation["robot0_eef_quat"] = eef.quat.astype(np.float32)
        observation["robot0_gripper_qpos"] = robot.gripper_joint_positions().astype(np.float32)
        opening = robot.gripper_opening() / max(robot.open_gap, 1e-6)
        observation["robot0_gripper_opening"] = np.array([np.clip(opening, 0.0, 1.0)], dtype=np.float32)
        return observation

    def _info(self, success: bool) -> dict:
        return {
            "success": success,
            "step": self._steps,
            "scene_seed": self._scene.seed,
            "goal": self.get_goal()["text"],
        }


def make(env_id: str, **kwargs: Any) -> TabletopEnv:
    """Creates the environment ``env_id`` (see :data:`ENV_IDS`)."""
    return TabletopEnv(env_id, **kwargs)


# ---------------------------------------------------------------------- goal descriptions


def _describe(prop: predicates.Predicate, scene: TabletopScene) -> Dict[str, Any]:
    """Neutral description of one goal condition: what must hold, with its numeric parameters."""
    name, args = type(prop).__name__.lower(), prop.args
    condition: Dict[str, Any] = {"type": name, "objects": list(args)}
    if name == "on":
        condition["text"] = f"{args[0]} rests upright on the {args[1]}"
    elif name == "under":
        condition["text"] = (
            f"at least {predicates.INTERSECTION_THRESHOLD:.0%} of the {args[0]}'s x-y footprint lies "
            f"under the {args[1]}, with the {args[0]} below the {args[1]}'s top"
        )
        condition["min_fraction"] = float(predicates.INTERSECTION_THRESHOLD)
    elif name == "inhand":
        obj = scene.objects[args[0]]
        height = float(LIFT_HEIGHT - 0.5 * obj.size[2])
        condition["text"] = (
            f"{args[0]} is held between the gripper fingers, or its center is higher than {height:.3f} m"
        )
        condition["min_height"] = height
    elif name == "pos":
        obj = scene.objects[args[0]]
        target = scene.symbols[args[1]].pos[:2]
        tolerance = float(predicates.Pos.POS_EPS.get(obj.kind, 0.01))
        condition["text"] = (
            f"{args[0]} is within {tolerance:.2f} m (x-y) of ({target[0]:.3f}, {target[1]:.3f}), "
            f"where {_symbol_owner(args[1], scene)} was at the start of the episode"
        )
        condition["target_xy"] = [float(target[0]), float(target[1])]
        condition["tolerance"] = tolerance
    elif name == "free":
        kind = scene.objects[args[0]].kind
        present = {obj.kind for obj in scene.objects.values() if obj.name != args[0]}
        distances = {
            _other(pair, kind): float(d)
            for pair, d in predicates.Free.DISTANCE_MIN.items()
            if kind in pair and _other(pair, kind) in present
        }
        condition["text"] = f"nothing rests on the {args[0]}" + "".join(
            f", its x-y footprint is at least {d:.2f} m from every {k}" for k, d in distances.items()
        )
        condition["min_distance"] = distances
    elif name == "inworkspace":
        radius = (
            predicates.WORKSPACE["workspace_radius"] - predicates.WORKSPACE["workspace_radius_padding"] / 2
        )
        x_min = predicates.WORKSPACE["workspace_x_min"]
        condition["text"] = (
            f"{args[0]}'s center has x >= {x_min:.2f} m and is within {radius:.2f} m (x-y) of the robot base"
        )
        condition["x_min"], condition["radius"] = float(x_min), float(radius)
    else:
        condition["text"] = str(prop)
    return condition


def _other(pair: Tuple[str, str], kind: str) -> str:
    return pair[1] if pair[0] == kind else pair[0]


def _symbol_owner(symbol: str, scene: TabletopScene) -> str:
    for prop in scene._variant.initial_state:
        if isinstance(prop, predicates.Pos) and prop.args[1] == symbol:
            return f"the {prop.args[0]}"
    return "a reference object"
