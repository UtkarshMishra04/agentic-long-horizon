"""Tabletop scene on robosuite (MuJoCo): a Panda arm with a Robotiq 2F-85 gripper, a table and objects.

A scene is described by a YAML file (``longhorizontamp/tasks``): its objects and one or more *variants*,
each with the propositions its initial state satisfies and the propositions of its goal. ``reset``
samples object poses satisfying the initial state and moves the gripper to a random start pose above
the table; the goal holds when every goal proposition holds.
"""

from __future__ import annotations

import collections
import itertools
import logging
import os
import pathlib
import random
from typing import Any, Dict, Generator, Iterator, List, Optional, Sequence, Tuple, Union

import numpy as np
import yaml

os.environ.setdefault("MUJOCO_GL", "egl")

from robosuite import load_controller_config  # noqa: E402
from robosuite.environments.manipulation.single_arm_env import SingleArmEnv  # noqa: E402
from robosuite.models.arenas import TableArena  # noqa: E402
from robosuite.models.tasks import ManipulationTask  # noqa: E402
from robosuite.utils import transform_utils as T  # noqa: E402

from longhorizontamp import predicates  # noqa: E402
from longhorizontamp.geometry import (  # noqa: E402
    START_POSE,
    TABLE_CONSTRAINTS,
    TOP_DOWN_ROTATION,
    Pose,
    TableFrame,
    orientation_error,
    top_down_orientation,
    top_down_yaw,
    wrap_angle,
    yaw_quat,
)
from longhorizontamp.objects import (  # noqa: E402
    OBJECT_STATE_RANGES,
    SceneObject,
    Table,
    create_object,
    object_state_range,
)

PACKAGE_DIR = pathlib.Path(__file__).resolve().parent

AGENTVIEW_POS = (0.7, 0.0, 1.35)
"""World position of the ``agentview`` camera, facing the robot from beyond the far table edge."""
AGENTVIEW_QUAT = (0.653, 0.271, 0.271, 0.653)
"""Orientation (w, x, y, z) of the ``agentview`` camera."""

TABLE_FULL_SIZE = (0.72, 0.9, 0.05)
DEFAULT_GRIPPER = "Robotiq85Gripper"

logger = logging.getLogger(__name__)


def load_yaml(path: Union[str, pathlib.Path]) -> Dict[str, Any]:
    """Loads a YAML file; relative paths are resolved inside the package."""
    path = pathlib.Path(path)
    if not path.is_absolute() and not path.exists():
        path = PACKAGE_DIR / path
    with open(path) as f:
        return yaml.safe_load(f)


class _ControlError(RuntimeError):
    pass


# ---------------------------------------------------------------------- variants


class _Variant:
    """Initial-state and goal propositions of one scene variant."""

    def __init__(self, initial_state: List[str], goal: List[str], prob: Optional[float] = None):
        self.initial_state = [predicates.Predicate.create(prop) for prop in initial_state]
        self.goal = [predicates.Predicate.create(prop) for prop in goal]
        self.prob = float("nan") if prob is None else float(prob)


# ---------------------------------------------------------------------- robosuite world


class _World(SingleArmEnv):
    """robosuite environment holding the arena, the robot and the scene objects."""

    def __init__(
        self,
        scene_objects: Sequence[SceneObject],
        table_full_size: Sequence[float],
        table_offset: Sequence[float],
        robot: str,
        camera_names: Sequence[str],
        camera_size: int,
        control_freq: int,
        agentview_pos: Sequence[float] = AGENTVIEW_POS,
        agentview_quat: Sequence[float] = AGENTVIEW_QUAT,
        gripper: str = "default",
    ):
        self._scene_objects = list(scene_objects)
        self._agentview_pos = np.asarray(agentview_pos, dtype=np.float64)
        self._agentview_quat = np.asarray(agentview_quat, dtype=np.float64)
        self.table_full_size = np.asarray(table_full_size, dtype=np.float64)
        self.table_offset = np.asarray(table_offset, dtype=np.float64)
        controller = load_controller_config(default_controller="OSC_POSE")
        controller["control_delta"] = False
        super().__init__(
            robots=robot,
            env_configuration="default",
            controller_configs=controller,
            mount_types="default",
            gripper_types=gripper,
            initialization_noise=None,
            use_camera_obs=False,
            has_renderer=False,
            has_offscreen_renderer=bool(camera_names),
            render_camera="agentview",
            control_freq=control_freq,
            horizon=10**9,
            ignore_done=True,
            hard_reset=False,
            camera_names=list(camera_names),
            camera_heights=camera_size,
            camera_widths=camera_size,
        )

    def _load_model(self) -> None:
        super()._load_model()
        base_x = -(self.table_full_size[0] / 2 + TABLE_CONSTRAINTS["table_x_min"])
        self.robots[0].robot_model.set_base_xpos(np.array([base_x, 0.0, 0.0]))
        arena = TableArena(table_full_size=self.table_full_size, table_offset=self.table_offset)
        arena.set_origin([0, 0, 0])
        arena.set_camera("agentview", pos=self._agentview_pos, quat=self._agentview_quat)
        self.model = ManipulationTask(
            mujoco_arena=arena,
            mujoco_robots=[robot.robot_model for robot in self.robots],
            mujoco_objects=[
                obj.mujoco_object for obj in self._scene_objects if obj.mujoco_object is not None
            ],
        )

    def reward(self, action: Optional[np.ndarray] = None) -> float:
        return 0.0

    def _check_success(self) -> bool:
        return False


# ---------------------------------------------------------------------- arm


class _Arm:
    """End-effector control of the robosuite Panda through the operational-space controller."""

    POSITION_TOLERANCE = 0.01
    ORIENTATION_TOLERANCE = 0.1
    MAX_STEP_DISTANCE = 0.03
    GRIPPER_RAMP_STEPS = 8
    """Control steps for the gripper command to travel from fully open to fully closed."""
    JOINT_LIMIT_MARGIN = 0.05
    MAX_FINAL_ORIENTATION_ERROR = 0.35
    RECOVERY_QPOS = np.array([0.0, 0.2, 0.0, -2.3, 0.0, 2.5, 0.785])
    RECOVERY_KP = np.array([80.0, 80.0, 80.0, 80.0, 30.0, 15.0, 10.0])
    RECOVERY_KD = np.array([8.0, 8.0, 8.0, 8.0, 3.0, 2.0, 1.0])
    WRIST_LIMIT = 2.8
    MAX_STEP_YAW = 0.3
    HOLD_MARGIN = 0.008
    """The pad gap must exceed the empty-closed gap by this much for the gripper to hold something."""
    MAX_HOLD_DISTANCE = 0.15
    """Maximum distance between the grip site and a held object's origin."""

    def __init__(self, scene: TabletopScene):
        self._scene = scene
        self.gripper_closed = False
        self.open_gap = 0.08
        self.closed_gap = 0.0

    @property
    def world(self) -> _World:
        return self._scene.world

    @property
    def robot(self) -> Any:
        return self.world.robots[0]

    # ------------------------------------------------------------------ state

    def eef_pose(self) -> Pose:
        """End-effector pose (grip site) in the table frame."""
        sim = self.world.sim
        pos = self._scene.frame.to_table(sim.data.site_xpos[self.robot.eef_site_id])
        rotation = sim.data.site_xmat[self.robot.eef_site_id].reshape(3, 3)
        return Pose(pos, T.mat2quat(rotation))

    def eef_yaw(self) -> float:
        return top_down_yaw(self.eef_pose().quat)

    def _pad_geom_ids(self) -> Tuple[int, int]:
        geoms = self.robot.gripper.important_geoms
        model = self.world.sim.model
        return model.geom_name2id(geoms["left_fingerpad"][0]), model.geom_name2id(geoms["right_fingerpad"][0])

    def gripper_opening(self) -> float:
        """Distance between the inner faces of the two finger pads."""
        sim = self.world.sim
        left, right = self._pad_geom_ids()
        centers = float(np.linalg.norm(sim.data.geom_xpos[left] - sim.data.geom_xpos[right]))
        thickness = float(sim.model.geom_size[left].min() + sim.model.geom_size[right].min())
        return max(centers - thickness, 0.0)

    def pads_touch(self, obj: SceneObject) -> bool:
        """True if both finger pads are in contact with the object."""
        if obj.mujoco_object is None:
            return False
        geoms = self.robot.gripper.important_geoms
        return all(
            self.world.check_contact(geoms[pad], obj.contact_geoms)
            for pad in ("left_fingerpad", "right_fingerpad")
        )

    def is_holding(self, obj: SceneObject) -> bool:
        """True if both finger pads touch the object, or the object is held between the fingers."""
        return self.pads_touch(obj) or self._between_fingers(obj)

    def _between_fingers(self, obj: SceneObject) -> bool:
        if obj.mujoco_object is None or not self.gripper_closed:
            return False
        if self.gripper_opening() < self.closed_gap + self.HOLD_MARGIN:
            return False
        offset = obj.pose().pos - self.eef_pose().pos
        return bool(
            np.linalg.norm(offset) < self.MAX_HOLD_DISTANCE and obj.pose().pos[2] > 0.5 * obj.size[2] + 0.02
        )

    def joint_positions(self) -> np.ndarray:
        return np.asarray(self.world.sim.data.qpos[self.robot._ref_joint_pos_indexes], dtype=np.float64)

    def joint_velocities(self) -> np.ndarray:
        return np.asarray(self.world.sim.data.qvel[self.robot._ref_joint_vel_indexes], dtype=np.float64)

    def gripper_joint_positions(self) -> np.ndarray:
        return np.asarray(
            self.world.sim.data.qpos[self.robot._ref_gripper_joint_pos_indexes], dtype=np.float64
        )

    # ------------------------------------------------------------------ control

    def control_step(self, pos: np.ndarray, quat: np.ndarray, closed: bool) -> None:
        """One 20 Hz control step towards an absolute end-effector pose (table frame) with a gripper command."""
        pos, quat = np.asarray(pos, dtype=np.float64), np.asarray(quat, dtype=np.float64)
        action = np.concatenate(
            [self._scene.frame.to_world(pos), T.quat2axisangle(quat), [1.0 if closed else -1.0]]
        )
        # The gripper command moves from open to closed in GRIPPER_RAMP_STEPS control steps.
        gripper = self.robot.gripper
        if hasattr(gripper, "current_action"):
            target = 1.0 if closed else -1.0
            current = np.asarray(gripper.current_action, dtype=np.float64)
            step = np.clip(target - current, -2.0 / self.GRIPPER_RAMP_STEPS, 2.0 / self.GRIPPER_RAMP_STEPS)
            gripper.current_action = current + step
        self.world.step(action)
        self.gripper_closed = closed

    def _set_gripper(self, closed: bool, steps: int = 12) -> None:
        eef = self.eef_pose()
        for _ in range(steps):
            self.control_step(eef.pos, eef.quat, closed)

    def _hold(self, steps: int) -> None:
        eef = self.eef_pose()
        for _ in range(steps):
            self.control_step(eef.pos, eef.quat, self.gripper_closed)

    def _calibrate_gripper(self) -> None:
        """Measures the pad gap of the open and of the fully closed (empty) gripper."""
        self._set_gripper(closed=False, steps=15)
        self.open_gap = self.gripper_opening()
        self._set_gripper(closed=True, steps=25)
        self.closed_gap = self.gripper_opening()
        self._set_gripper(closed=False, steps=15)

    # ------------------------------------------------------------------ start pose (used by reset)

    def _pinned_joints(self) -> np.ndarray:
        robot, sim = self.robot, self.world.sim
        q = sim.data.qpos[robot._ref_joint_pos_indexes]
        limits = sim.model.jnt_range[robot._ref_joint_indexes]
        return np.minimum(q - limits[:, 0], limits[:, 1] - q) < self.JOINT_LIMIT_MARGIN

    def _unfold(self, seconds: float = 2.0, force: bool = False) -> bool:
        """Joint-space move to a comfortable configuration when joints are close to their limits."""
        if not force and not self._pinned_joints()[1:6].any():
            return False
        eef = self.eef_pose()
        lifted = eef.pos.copy()
        lifted[2] = max(lifted[2], START_POSE["height"])
        try:
            self._track(
                lifted, eef.quat, closed=self.gripper_closed, max_steps=40, fail_tolerance=1.0, unfold=False
            )
        except _ControlError:
            pass
        robot, sim = self.robot, self.world.sim
        q_idx, v_idx, a_idx = (
            robot._ref_joint_pos_indexes,
            robot._ref_joint_vel_indexes,
            robot._ref_joint_actuator_indexes,
        )
        target = self.RECOVERY_QPOS.copy()
        target[0] = sim.data.qpos[q_idx][0]
        target[6] = float(np.clip(sim.data.qpos[q_idx][6], -2.0, 2.0))
        start = sim.data.qpos[q_idx].copy()
        total = int(seconds / sim.model.opt.timestep)
        for step in range(total):
            q, dq = sim.data.qpos[q_idx], sim.data.qvel[v_idx]
            blend = min(1.0, 1.5 * (step + 1) / total)
            goal = start + blend * (target - start)
            torque = self.RECOVERY_KP * (goal - q) - self.RECOVERY_KD * dq + sim.data.qfrc_bias[v_idx]
            sim.data.ctrl[a_idx] = np.clip(torque, *robot.torque_limits)
            sim.step()
        return True

    def _track(
        self,
        pos: np.ndarray,
        quat: np.ndarray,
        closed: bool,
        max_steps: int = 120,
        fail_tolerance: float = 0.03,
        allow_yaw_flip: bool = False,
        pos_tolerance: Optional[float] = None,
        step_distance: Optional[float] = None,
        unfold: bool = True,
    ) -> np.ndarray:
        """Tracks an end-effector pose until converged; raises ``_ControlError`` if it is not reached."""
        pos = np.asarray(pos, dtype=np.float64)
        if unfold:
            self._unfold()
        pos_tolerance = self.POSITION_TOLERANCE if pos_tolerance is None else pos_tolerance
        step_distance = self.MAX_STEP_DISTANCE if step_distance is None else step_distance
        if allow_yaw_flip:
            quat = self._closest_symmetric_orientation(pos, quat)
        yaw_change = self._yaw_change_to(pos, quat)
        yaw_steps = int(np.ceil(abs(yaw_change) / self.MAX_STEP_YAW))
        error = float("inf")
        goal = self.eef_pose().pos
        for step in range(max_steps):
            remaining = pos - goal
            distance = float(np.linalg.norm(remaining))
            goal = goal + remaining * (step_distance / distance) if distance > step_distance else pos
            goal_quat = quat
            if step + 1 < yaw_steps:
                lag = yaw_change * (1.0 - (step + 1) / yaw_steps)
                goal_quat = T.mat2quat(T.quat2mat(yaw_quat(-lag)) @ T.quat2mat(quat))
            self.control_step(goal, goal_quat, closed)
            eef = self.eef_pose()
            error = float(np.linalg.norm(eef.pos - pos))
            if error < pos_tolerance and orientation_error(eef.quat, quat) < self.ORIENTATION_TOLERANCE:
                break
        if error > fail_tolerance:
            if unfold and self._pinned_joints()[1:6].any():
                self._unfold(force=True)
                return self._track(
                    pos,
                    quat,
                    closed,
                    max_steps,
                    fail_tolerance,
                    False,
                    pos_tolerance,
                    step_distance,
                    unfold=False,
                )
            raise _ControlError(f"Could not reach {np.round(pos, 3)} (error {error:.3f} m).")
        if orientation_error(self.eef_pose().quat, quat) > self.MAX_FINAL_ORIENTATION_ERROR:
            if unfold:
                self._unfold(force=True)
                return self._track(
                    pos,
                    quat,
                    closed,
                    max_steps,
                    fail_tolerance,
                    False,
                    pos_tolerance,
                    step_distance,
                    unfold=False,
                )
            raise _ControlError("Could not reach the requested orientation.")
        return quat

    def _wrist_angle(self) -> float:
        return float(self.world.sim.data.qpos[self.robot._ref_joint_pos_indexes][-1])

    def _predicted_wrist(self, pos: np.ndarray, yaw_change: float) -> float:
        current = self.eef_pose().pos
        d_azimuth = wrap_angle(float(np.arctan2(pos[1], pos[0]) - np.arctan2(current[1], current[0])))
        return self._wrist_angle() + d_azimuth - yaw_change

    def _yaw_change_to(self, pos: np.ndarray, quat: np.ndarray) -> float:
        delta = wrap_angle(top_down_yaw(quat) - self.eef_yaw())
        if abs(self._predicted_wrist(pos, delta)) > self.WRIST_LIMIT:
            other_way = delta - float(np.sign(delta)) * 2.0 * np.pi
            if abs(self._predicted_wrist(pos, other_way)) <= self.WRIST_LIMIT:
                return float(other_way)
        return float(delta)

    def _closest_symmetric_orientation(self, pos: np.ndarray, quat: np.ndarray) -> np.ndarray:
        flipped = T.mat2quat(T.quat2mat(yaw_quat(np.pi)) @ T.quat2mat(quat))
        current_yaw = self.eef_yaw()
        candidates = [
            (abs(self._predicted_wrist(pos, wrap_angle(top_down_yaw(q) - current_yaw))), q)
            for q in (quat, flipped)
        ]
        return min(candidates, key=lambda item: item[0])[1]

    def _move_to_random_start(self, max_attempts: int = 3) -> bool:
        """Moves the gripper (open, pointing down) to a random pose above the table."""
        x_min, x_max = TABLE_CONSTRAINTS["table_x_min"], START_POSE["radius"]
        y_min, y_max = TABLE_CONSTRAINTS["table_y_min"], TABLE_CONSTRAINTS["table_y_max"]
        for _ in range(max_attempts):
            while True:
                xy = np.random.uniform([x_min, y_min], [x_max, y_max])
                if np.linalg.norm(xy) < START_POSE["radius"]:
                    break
            theta = float(np.random.uniform(*OBJECT_STATE_RANGES["wz"]))
            pos = np.append(xy, START_POSE["height"])
            try:
                self._track(
                    pos,
                    top_down_orientation(theta),
                    closed=False,
                    max_steps=150,
                    fail_tolerance=0.05,
                    allow_yaw_flip=True,
                )
                return True
            except _ControlError as e:
                logger.debug("start pose rejected: %s", e)
        return False


# ---------------------------------------------------------------------- scene


class TabletopScene:
    """A tabletop scene: objects, scene sampling and the goal check."""

    MAX_NUM_OBJECTS = 8
    EE_ROW = 0

    def __init__(
        self,
        name: str,
        objects: List[Any],
        variants: List[Dict[str, Any]],
        robot: str = "Panda",
        gripper: str = DEFAULT_GRIPPER,
        table_full_size: Sequence[float] = TABLE_FULL_SIZE,
        table_height: float = 0.8,
        camera_names: Sequence[str] = ("agentview", "robot0_eye_in_hand"),
        camera_size: int = 84,
        control_freq: int = 20,
    ):
        self.name = name
        self.camera_names = tuple(camera_names)
        self.camera_size = camera_size
        table_full_size = tuple(float(v) for v in table_full_size)
        table_center_x = TABLE_CONSTRAINTS["table_x_min"] + table_full_size[0] / 2
        scene_objects: List[SceneObject] = []
        for entry in objects:
            config = load_yaml(entry) if isinstance(entry, str) else entry
            kwargs = dict(config.get("object_kwargs", {}))
            if config["object_type"] == "Table":
                scene_objects.append(Table(kwargs.get("name", "table"), table_full_size, table_center_x))
            else:
                scene_objects.append(create_object(config["object_type"], kwargs))
        self.objects: Dict[str, SceneObject] = {obj.name: obj for obj in scene_objects}

        self.world = _World(
            scene_objects=scene_objects,
            table_full_size=table_full_size,
            table_offset=(0.0, 0.0, table_height),
            robot=robot,
            camera_names=self.camera_names,
            camera_size=camera_size,
            control_freq=control_freq,
            gripper=gripper,
        )
        self.world.reset()
        base = self.world.robots[0].base_pos
        self.frame = TableFrame(np.array([base[0], base[1], table_height]))
        for obj in scene_objects:
            obj.bind(self.world.sim, self.frame)
        self.robot = _Arm(self)

        self.symbols: Dict[str, Pose] = {}
        self.symbols_registered = False
        self.rejections: collections.Counter = collections.Counter()
        if not variants:
            raise ValueError(f"Scene {name!r} defines no variants.")
        self._variants = [_Variant(**variant) for variant in variants]
        probabilities = np.array([1.0 if np.isnan(v.prob) else v.prob for v in self._variants])
        self._probabilities = probabilities / probabilities.sum()
        self._variant = self._variants[0]
        self.seed: Optional[int] = None
        self.robot._calibrate_gripper()

    # ------------------------------------------------------------------ objects and state

    @property
    def goal(self) -> List[predicates.Predicate]:
        return self._variant.goal

    def movable_objects(self) -> List[SceneObject]:
        return [obj for obj in self.objects.values() if not obj.is_static]

    def object_rows(self) -> Dict[str, int]:
        rows = {"end_effector": TabletopScene.EE_ROW}
        idx_row = 0
        for obj in self.objects.values():
            if idx_row == TabletopScene.EE_ROW:
                idx_row += 1
            rows[obj.name] = idx_row
            idx_row += 1
        return rows

    def object_state(self) -> np.ndarray:
        """``[MAX_NUM_OBJECTS, 12]`` object-state matrix (row 0: end effector)."""
        low = object_state_range()[0]
        matrix = np.zeros((TabletopScene.MAX_NUM_OBJECTS, len(low)), dtype=np.float32)
        eef = self.robot.eef_pose()
        relative = T.mat2quat(eef.rotation() @ TOP_DOWN_ROTATION.T)
        matrix[TabletopScene.EE_ROW, :3] = eef.pos
        matrix[TabletopScene.EE_ROW, 3:6] = T.quat2axisangle(relative)
        for name, row in self.object_rows().items():
            if name != "end_effector":
                matrix[row] = self.objects[name].state_row()
        return matrix

    def camera_images(
        self, cameras: Optional[Sequence[str]] = None, size: Optional[int] = None
    ) -> Dict[str, np.ndarray]:
        size = size or self.camera_size
        return {
            camera: self.world.sim.render(width=size, height=size, camera_name=camera)[::-1].copy()
            for camera in (cameras or self.camera_names)
        }

    # ------------------------------------------------------------------ reset

    @staticmethod
    def _seed_generator(seed: Optional[int]) -> Generator[int, None, None]:
        if seed is None:
            seed = random.randint(0, 2**30)
        yield from itertools.count(start=seed)

    def _park_objects(self) -> None:
        for i, obj in enumerate(self.movable_objects()):
            obj.set_pose(Pose.from_yaw(np.array([2.0 + 0.5 * i, 2.0, 0.5]), 0.0))

    def _sample_scene(self, state: List[predicates.Predicate]) -> bool:
        self.world.reset()
        self.world.robots[0].controller.reset_goal()
        self.robot.gripper_closed = False
        self._park_objects()
        placement = [prop for prop in state if not isinstance(prop, predicates.Inhand)]
        for prop in placement:
            if not prop.sample(self, state):
                return self._reject(f"sampling {prop}")
        if not self.robot._move_to_random_start():
            return self._reject("robot start pose")
        self._wait_until_stable()
        placed = {prop.args[0] for prop in state if isinstance(prop, (predicates.On, predicates.Inhand))}
        for obj in self.movable_objects():
            if obj.name in placed and predicates.is_below_table(obj):
                return self._reject(f"{obj} fell off the table")
        for prop in state:
            if not prop.value(self, state):
                return self._reject(f"{prop} does not hold after settling")
        return True

    def _reject(self, reason: str) -> bool:
        self.rejections[reason] += 1
        return False

    def reset(self, seed: Optional[int] = None, max_samples_per_variant: int = 100) -> int:
        """Samples a scene; seeds whose scene is invalid are skipped. Returns the seed of the scene."""
        for attempt, attempt_seed in enumerate(self._seed_generator(seed)):
            random.seed(attempt_seed)
            np.random.seed(attempt_seed)
            if attempt % max_samples_per_variant == 0:
                self._variant = self._variants[
                    int(np.random.choice(len(self._variants), p=self._probabilities))
                ]
            self.symbols = {}
            self.symbols_registered = False
            if self._sample_scene(list(self._variant.initial_state)):
                break
        for prop in self._variant.initial_state:
            if isinstance(prop, predicates.Pos):
                self.symbols[prop.args[1]] = self.objects[prop.args[0]].pose()
        self.symbols_registered = True
        self.seed = attempt_seed
        return attempt_seed

    def is_goal(self) -> bool:
        return all(pred.value(self, self._variant.initial_state) for pred in self._variant.goal)

    def _wait_until_stable(self, min_steps: int = 2, max_steps: int = 40, threshold: float = 0.01) -> int:
        for step in range(max_steps):
            self.robot._hold(1)
            speeds = [np.abs(obj.velocity()).max() for obj in self.movable_objects()]
            if step + 1 >= min_steps and (not speeds or max(speeds) < threshold):
                return step + 1
        return max_steps

    def iter_objects(self) -> Iterator[SceneObject]:
        return iter(self.objects.values())

    def close(self) -> None:
        world = getattr(self, "world", None)
        if world is not None:
            world.close()
