"""Scene objects: boxes, an L-shaped stick, a rack and the table.

Every object exposes its pose, size, bounding box and x-y footprint in the table frame, and one
row of the object-state matrix (position, axis-angle orientation, shape features).
"""

from __future__ import annotations

import inspect
from typing import Any, Dict, List, Optional, Sequence, Tuple

import numpy as np
from robosuite.models.objects import BoxObject, CompositeObject, MujocoObject

from longhorizontamp import geometry
from longhorizontamp.geometry import TABLE_CONSTRAINTS, Pose, TableFrame, quat_wxyz_to_xyzw, quat_xyzw_to_wxyz

OBJECT_STATE_DIM = 12

OBJECT_STATE_RANGES: Dict[str, Tuple[float, float]] = {
    "x": (-0.3, 0.9),
    "y": (-0.5, 0.5),
    "z": (-0.1, 0.5),
    "wx": (-np.pi, np.pi),
    "wy": (-np.pi, np.pi),
    "wz": (-np.pi, np.pi),
    "size_x": (0.0, 0.4),
    "size_y": (0.0, 0.4),
    "size_z": (0.0, 0.2),
    "short_length": (0.0, 0.3),
    "long_length": (0.0, 0.5),
    "short_offset": (-1.0, 1.0),
}
"""Ranges of the 12 features of an object's state row (the first two bound where objects are placed)."""


def object_state_range() -> np.ndarray:
    """``[2, 12]`` lower and upper bounds of the state-row features."""
    return np.array(list(OBJECT_STATE_RANGES.values()), dtype=np.float32).T


_COMPOSITE_SUPPORTS_CENTER = (
    "locations_relative_to_center" in inspect.signature(CompositeObject.__init__).parameters
)


def make_composite(
    name: str,
    total_half_size: np.ndarray,
    geom_types: Sequence[str],
    geom_sizes: Sequence[Sequence[float]],
    geom_centers: Sequence[Sequence[float]],
    geom_names: Sequence[str],
    density: float,
    rgba: Optional[Sequence[float]] = None,
    geom_rgbas: Optional[Sequence[Sequence[float]]] = None,
    geom_condims: Optional[Sequence[int]] = None,
    geom_frictions: Optional[Sequence[Sequence[float]]] = None,
) -> CompositeObject:
    """Creates a robosuite ``CompositeObject`` from geoms positioned relative to the body center."""
    kwargs: Dict[str, Any] = dict(
        name=name,
        total_size=[float(v) for v in total_half_size],
        geom_types=list(geom_types),
        geom_sizes=[[float(v) for v in size] for size in geom_sizes],
        geom_names=list(geom_names),
        density=float(density),
        joints="default",
    )
    if rgba is not None:
        kwargs["rgba"] = [float(v) for v in rgba]
    if geom_rgbas is not None:
        kwargs["geom_rgbas"] = [[float(v) for v in c] for c in geom_rgbas]
    if geom_condims is not None:
        kwargs["geom_condims"] = [int(c) for c in geom_condims]
    if geom_frictions is not None:
        kwargs["geom_frictions"] = [[float(v) for v in f] for f in geom_frictions]
    centers = np.asarray(geom_centers, dtype=np.float64)
    if _COMPOSITE_SUPPORTS_CENTER:
        kwargs["geom_locations"] = centers.tolist()
        kwargs["locations_relative_to_center"] = True
    else:  # Older robosuite: locations are relative to the lower corner of the total box.
        kwargs["geom_locations"] = (centers + np.asarray(total_half_size)).tolist()
    return CompositeObject(**kwargs)


class SceneObject:
    """An object of the scene with its geometry and MuJoCo bindings.

    Attributes:
        name: Object name used in propositions.
        kind: ``box``, ``lstick``, ``rack`` or ``table``.
        size: Full extents of the bounding box in the object frame.
        bbox: ``[[min], [max]]`` bounding box in the object frame.
        is_static: Static objects (the table) have no free joint.
    """

    kind: str = "object"

    def __init__(self, name: str, size: np.ndarray, bbox: np.ndarray, mujoco_object: Optional[MujocoObject]):
        self.name = name
        self.size = np.asarray(size, dtype=np.float64)
        self.bbox = np.asarray(bbox, dtype=np.float64)
        self.mujoco_object = mujoco_object
        self.is_static = mujoco_object is None
        self._sim: Any = None
        self._frame: Optional[TableFrame] = None
        self._body_id: Optional[int] = None

    # ------------------------------------------------------------------ bindings

    def bind(self, sim: Any, frame: TableFrame) -> None:
        """Binds the object to a MuJoCo simulation after the model was loaded."""
        self._sim = sim
        self._frame = frame
        if self.mujoco_object is not None:
            self._body_id = sim.model.body_name2id(self.mujoco_object.root_body)

    @property
    def frame(self) -> TableFrame:
        assert self._frame is not None, "Object is not bound to a simulation."
        return self._frame

    @property
    def joint_name(self) -> str:
        assert self.mujoco_object is not None
        return self.mujoco_object.joints[0]

    @property
    def contact_geoms(self) -> List[str]:
        return [] if self.mujoco_object is None else list(self.mujoco_object.contact_geoms)

    # ------------------------------------------------------------------ geometry

    def pose(self) -> Pose:
        """Pose of the object frame in the table frame."""
        assert self._sim is not None and self._body_id is not None
        pos = self.frame.to_table(self._sim.data.body_xpos[self._body_id])
        quat = quat_wxyz_to_xyzw(self._sim.data.body_xquat[self._body_id])
        return Pose(pos, quat)

    def set_pose(self, pose: Pose) -> None:
        """Teleports the object (and zeroes its velocity)."""
        assert self._sim is not None
        qpos = np.concatenate([self.frame.to_world(pose.pos), quat_xyzw_to_wxyz(pose.quat)])
        self._sim.data.set_joint_qpos(self.joint_name, qpos)
        self._sim.data.set_joint_qvel(self.joint_name, np.zeros(6))
        self._sim.forward()

    def velocity(self) -> np.ndarray:
        """Linear and angular velocity, shape ``[6]``."""
        assert self._sim is not None
        return np.asarray(self._sim.data.get_joint_qvel(self.joint_name))

    def aabb(self) -> np.ndarray:
        """World-aligned bounding box ``[[min], [max]]`` in the table frame."""
        pose = self.pose()
        corners = np.array([pose.apply(c) for c in geometry.bbox_corners(self.bbox)])
        return np.array([corners.min(axis=0), corners.max(axis=0)])

    def footprints(self) -> List[np.ndarray]:
        """Convex x-y footprints (one per part) in the table frame."""
        pose = self.pose()
        corners = np.array([pose.apply(c) for c in geometry.bbox_corners(self.bbox)])
        return [geometry.convex_hull_2d(corners[:, :2])]

    def is_upright(self, tolerance: float = 0.99) -> bool:
        return bool(abs(self.pose().z_axis()[2]) >= tolerance)

    # ------------------------------------------------------------------ observation

    def static_features(self) -> np.ndarray:
        """``size_x, size_y, size_z, short_length, long_length, short_offset`` features of the state row."""
        return np.concatenate([self.size, [0.0, 0.0, 0.0]])

    def state_row(self) -> np.ndarray:
        """State row: position, axis-angle orientation and shape features."""
        pose = self.pose()
        return np.concatenate([pose.pos, pose.axis_angle(), self.static_features()]).astype(np.float32)

    def __str__(self) -> str:
        return self.name

    def __repr__(self) -> str:
        return f"{type(self).__name__}({self.name})"


class Table(SceneObject):
    """The table top (part of the robosuite arena)."""

    kind = "table"

    def __init__(self, name: str, full_size: Sequence[float], center_x: float):
        size = np.asarray(full_size, dtype=np.float64)
        bbox = np.array([[-size[0] / 2, -size[1] / 2, -size[2]], [size[0] / 2, size[1] / 2, 0.0]])
        super().__init__(name, size, bbox, mujoco_object=None)
        self._center = np.array([center_x, 0.0, TABLE_CONSTRAINTS["table_z_max"]])

    def pose(self) -> Pose:
        return Pose(self._center.copy(), np.array([0.0, 0.0, 0.0, 1.0]))

    def set_pose(self, pose: Pose) -> None:
        raise RuntimeError("The table is static.")

    def velocity(self) -> np.ndarray:
        return np.zeros(6)


class Box(SceneObject):
    kind = "box"

    def __init__(self, name: str, size: Sequence[float], color: Sequence[float], mass: float = 0.1):
        size_arr = np.asarray(size, dtype=np.float64)
        density = mass / float(np.prod(size_arr))
        mujoco_object = BoxObject(
            name=name, size=(size_arr / 2).tolist(), rgba=[float(c) for c in color], density=float(density)
        )
        super().__init__(name, size_arr, np.array([-size_arr / 2, size_arr / 2]), mujoco_object)


class LStick(SceneObject):
    """L-shaped stick: a long bar along ``x`` joined at a right angle to a short bar along ``y``."""

    kind = "lstick"

    def __init__(
        self,
        name: str,
        short_length: float,
        long_length: float,
        short_offset: float,
        color: Sequence[float],
        radius: float = 0.02,
        mass: float = 0.1,
    ):
        self.short_length, self.long_length, self.short_offset, self.radius = (
            short_length,
            long_length,
            short_offset,
            radius,
        )
        pos_long, pos_short, pos_corner = geometry.lstick_link_positions(
            short_length, long_length, short_offset, radius
        )
        size = geometry.lstick_size(short_length, long_length, short_offset, radius)
        volume = (long_length + short_length) * (2 * radius) ** 2 + 4 / 3 * np.pi * radius**3
        mujoco_object = make_composite(
            name=name,
            total_half_size=size / 2,
            geom_types=["box", "box", "sphere"],
            geom_sizes=[[long_length / 2, radius, radius], [radius, short_length / 2, radius], [radius]],
            geom_centers=[pos_long, pos_short, pos_corner],
            geom_names=["long", "short", "corner"],
            density=mass / volume,
            rgba=color,
            geom_condims=[4, 4, 4],
            geom_frictions=[[1.0, 0.05, 0.0001]] * 3,
        )
        super().__init__(name, size, np.array([-size / 2, size / 2]), mujoco_object)
        self._pos_long, self._pos_short = pos_long, pos_short

    def footprints(self) -> List[np.ndarray]:
        """Footprints of the long and the short bar (two rectangles)."""
        pose = self.pose()
        half_sizes = np.array(
            [[self.size[0] / 2, self.radius, self.radius], [self.radius, self.size[1] / 2, self.radius]]
        )
        centers = np.array([[0.0, self._pos_long[1], 0.0], [self._pos_short[0], 0.0, 0.0]])
        hulls = []
        for center, half in zip(centers, half_sizes):
            bbox = np.array([center - half, center + half])
            corners = np.array([pose.apply(c) for c in geometry.bbox_corners(bbox)])
            hulls.append(geometry.convex_hull_2d(corners[:, :2]))
        return hulls

    def static_features(self) -> np.ndarray:
        return np.concatenate([self.size, [self.short_length, self.long_length, self.short_offset]])


class Rack(SceneObject):
    kind = "rack"
    TOP_THICKNESS = 0.01
    LEG_THICKNESS = 0.01

    def __init__(self, name: str, size: Sequence[float], color: Sequence[float], mass: float = 1.0):
        size_arr = np.asarray(size, dtype=np.float64)
        sx, sy, height = size_arr
        top, leg = Rack.TOP_THICKNESS, Rack.LEG_THICKNESS
        xy_legs = np.array([(x, y) for x in (-1, 1) for y in (-1, 1)]) * ((size_arr[:2] - leg) / 2)
        leg_height = height - top - leg
        geom_sizes = [[sx / 2, sy / 2, top / 2]]
        geom_locations = [[0.0, 0.0, -top / 2]]
        geom_rgbas = [list(color)]
        for x, y in xy_legs:
            geom_sizes.append([leg / 2, leg / 2, leg_height / 2])
            geom_locations.append([x, y, -(height + top - leg) / 2])
            geom_rgbas.append([0.0, 0.0, 0.0, 1.0])
        for y in xy_legs[:2, 1]:
            geom_sizes.append([sx / 2, leg / 2, leg / 2])
            geom_locations.append([0.0, y, -height + leg / 2])
            geom_rgbas.append([0.0, 0.0, 0.0, 1.0])
        volume = sum(8 * np.prod(s) for s in geom_sizes)
        mujoco_object = make_composite(
            name=name,
            total_half_size=np.array([sx / 2, sy / 2, height / 2]),
            geom_types=["box"] * len(geom_sizes),
            geom_sizes=geom_sizes,
            geom_centers=geom_locations,
            geom_names=["top"] + [f"leg{i}" for i in range(4)] + ["stabilizer0", "stabilizer1"],
            density=mass / volume,
            geom_rgbas=geom_rgbas,
        )
        # The object frame sits at the center of the top surface.
        bbox = np.array([[-sx / 2, -sy / 2, -height], [sx / 2, sy / 2, 0.0]])
        super().__init__(name, size_arr, bbox, mujoco_object)


OBJECT_CLASSES: Dict[str, type] = {"Box": Box, "LStick": LStick, "Rack": Rack}


def create_object(object_type: str, object_kwargs: Dict[str, Any]) -> SceneObject:
    """Instantiates a scene object from an environment config entry."""
    try:
        cls = OBJECT_CLASSES[object_type]
    except KeyError as e:
        raise ValueError(f"Unknown object type {object_type!r}.") from e
    return cls(**object_kwargs)
