"""Propositions over scene objects.

Every predicate can *sample* a geometric arrangement of its arguments when a scene is reset (the
initial state of a task) and *evaluate* whether it currently holds (initial-state validation and
the goal check). Geometry is computed from object poses and bounding boxes in the table frame; the
only physical query is the finger contact used by ``inhand``.
"""

from __future__ import annotations

import random
from typing import TYPE_CHECKING, Any, Dict, List, Optional, Sequence, Tuple, Type

import numpy as np
from shapely.geometry import LineString, Polygon

from longhorizontamp import geometry
from longhorizontamp.geometry import (
    EPSILONS,
    INTERSECTION_THRESHOLD,
    LIFT_HEIGHT,
    TABLE_CONSTRAINTS,
    Pose,
    parse_proposition,
)
from longhorizontamp.objects import object_state_range

if TYPE_CHECKING:
    from longhorizontamp.objects import SceneObject
    from longhorizontamp.scene import TabletopScene as TableEnv


PLACEMENT_CLEARANCE = 0.005
"""Gap between a sampled object and its support; objects settle onto the support during ``reset``."""

WORKSPACE: Dict[str, float] = {
    **TABLE_CONSTRAINTS,
    "workspace_radius": 0.80,
    "workspace_radius_padding": 0.10,
}
"""Workspace zones: ``inworkspace`` means closer than 0.75 m to the robot base (and ``x >= 0.4``),
``beyondworkspace`` at least 0.85 m away."""


# ---------------------------------------------------------------------- geometry


def footprint_polygons(obj: SceneObject) -> List[Polygon]:
    return [Polygon(hull) for hull in obj.footprints() if len(hull) >= 3]


def bbox_footprint(obj: Any) -> np.ndarray:
    """Convex x-y hull of the object's bounding box in the table frame (one hull for every object)."""
    pose = obj.pose()
    corners = np.array([pose.apply(c) for c in geometry.bbox_corners(obj.bbox)])
    return geometry.convex_hull_2d(corners[:, :2])


def is_above(obj_a: SceneObject, obj_b: SceneObject) -> bool:
    """True if the bottom of ``obj_a`` is (almost) above the top of ``obj_b``."""
    return bool(obj_a.aabb()[0, 2] > obj_b.aabb()[1, 2] - EPSILONS["aabb"])


def is_intersecting(obj_a: SceneObject, obj_b: SceneObject) -> bool:
    return any(pa.intersects(pb) for pa in footprint_polygons(obj_a) for pb in footprint_polygons(obj_b))


def footprint_area(obj: SceneObject) -> float:
    return float(sum(poly.area for poly in footprint_polygons(obj)))


def footprint_intersection_area(obj_a: SceneObject, obj_b: SceneObject) -> float:
    return float(
        sum(pa.intersection(pb).area for pa in footprint_polygons(obj_a) for pb in footprint_polygons(obj_b))
    )


def footprint_distance(obj_a: SceneObject, obj_b: SceneObject) -> float:
    """Smallest x-y distance between the footprints of two objects."""
    return float(min(pa.distance(pb) for pa in footprint_polygons(obj_a) for pb in footprint_polygons(obj_b)))


def is_under(obj_a: SceneObject, obj_b: SceneObject) -> bool:
    """True if ``obj_a`` lies underneath the rack ``obj_b`` (any overlap)."""
    if obj_b.kind != "rack" or "table" in (obj_a.kind, obj_b.kind):
        return False
    return not is_above(obj_a, obj_b) and is_intersecting(obj_a, obj_b)


def is_under_with_intersection(obj_a: SceneObject, obj_b: SceneObject) -> bool:
    """True if at least ``INTERSECTION_THRESHOLD`` of ``obj_a``'s footprint lies under the rack."""
    if obj_b.kind != "rack" or "table" in (obj_a.kind, obj_b.kind):
        return False
    if is_above(obj_a, obj_b) or not is_intersecting(obj_a, obj_b):
        return False
    return footprint_intersection_area(obj_a, obj_b) / footprint_area(obj_a) >= INTERSECTION_THRESHOLD


def is_lifted(obj: SceneObject) -> bool:
    """True if the object's center is higher than ``LIFT_HEIGHT`` minus half the object's height."""
    return bool(obj.pose().pos[2] > LIFT_HEIGHT - 0.5 * obj.size[2])


def is_on(obj_a: SceneObject, obj_b: SceneObject, on_distance: float = 0.04) -> bool:
    """True if ``obj_a`` rests on top of ``obj_b``."""
    return bool(
        is_above(obj_a, obj_b)
        and is_intersecting(obj_a, obj_b)
        and not is_lifted(obj_a)
        and abs(obj_a.aabb()[0, 2] - obj_b.aabb()[1, 2]) < on_distance
    )


def is_inworkspace(xy: np.ndarray) -> bool:
    radius = WORKSPACE["workspace_radius"] - WORKSPACE["workspace_radius_padding"] / 2
    return bool(WORKSPACE["workspace_x_min"] <= xy[0] and np.linalg.norm(xy) < radius)


def is_beyondworkspace(xy: np.ndarray) -> bool:
    radius = WORKSPACE["workspace_radius"] + WORKSPACE["workspace_radius_padding"] / 2
    return bool(np.linalg.norm(xy) >= radius)


def is_entirely_inworkspace(obj: SceneObject) -> bool:
    return all(is_inworkspace(point) for hull in obj.footprints() for point in hull)


def is_below_table(obj: SceneObject) -> bool:
    return bool(obj.pose().pos[2] < TABLE_CONSTRAINTS["table_z_max"])


# ---------------------------------------------------------------------- base class


class Predicate:
    """A proposition over object names that can be sampled and evaluated in a scene."""

    def __init__(self, args: Sequence[str]):
        self.args: List[str] = list(args)

    @classmethod
    def create(cls, proposition: str) -> Predicate:
        name, args = parse_proposition(proposition)
        try:
            return PREDICATE_CLASSES[name](args)
        except KeyError as e:
            raise ValueError(f"Unknown predicate {name!r}.") from e

    def objects(self, env: TableEnv) -> List[SceneObject]:
        return [env.objects[arg] for arg in self.args]

    def sample(self, env: TableEnv, state: Sequence[Predicate]) -> bool:
        """Generates a geometric grounding; returns False if none was found."""
        return True

    def value(self, env: TableEnv, state: Optional[Sequence[Predicate]] = None) -> bool:
        """True if the predicate currently holds."""
        return True

    def __str__(self) -> str:
        return f"{type(self).__name__.lower()}({', '.join(self.args)})"

    def __repr__(self) -> str:
        return str(self)

    def __eq__(self, other: object) -> bool:
        return str(self) == str(other)

    def __hash__(self) -> int:
        return hash(str(self))


class NotInCenter(Predicate):
    def value(self, env: TableEnv, state: Optional[Sequence[Predicate]] = None) -> bool:
        obj = self.objects(env)[0]
        if obj.kind != "box":
            return True
        y = obj.pose().pos[1]
        return bool(y < -0.2 or y > 0.2)


class Free(Predicate):
    """No object rests on top of the argument and neighbors keep a minimum distance."""

    DISTANCE_MIN: Dict[Tuple[str, str], float] = {
        ("box", "box"): 0.05,
        ("box", "lstick"): 0.05,
        ("box", "rack"): 0.1,
        ("lstick", "rack"): 0.1,
    }

    def value(self, env: TableEnv, state: Optional[Sequence[Predicate]] = None) -> bool:
        state = state or []
        child = self.objects(env)[0]
        for obj in env.objects.values():
            if obj is child or obj.kind == "table" or f"inhand({obj})" in state:
                continue
            if is_under(child, obj):
                return False
            pair = tuple(sorted((child.kind, obj.kind)))
            min_distance = Free.DISTANCE_MIN.get(pair)  # type: ignore[arg-type]
            if min_distance is None:
                continue
            if obj.kind == "rack" and f"beyondworkspace({obj})" in state:
                min_distance = 0.04
            if footprint_distance(child, obj) < min_distance and not is_above(child, obj):
                return False
        return True


# ---------------------------------------------------------------------- table zones


class TableBounds:
    """Mixin for predicates that restrict where on the table an object may be placed."""

    def bounds_and_margin(
        self, child: SceneObject, table: SceneObject, state: Sequence[Predicate], theta: float
    ) -> Tuple[np.ndarray, np.ndarray, float]:
        """Returns ``([xy_min, xy_max], margin, theta)`` for sampling ``child`` on the table."""
        zone = type(self).__name__.lower()
        theta = self._zone_angle(child, state, zone, theta)
        margin = geometry.rotated_footprint_margins(child.bbox, theta)
        poslimit = TableBounds.get_poslimit(child, state)
        if poslimit is not None:
            pos_bounds = poslimit.bounds(child)
            if zone not in pos_bounds:
                zone = random.choice(sorted(pos_bounds))
                theta = self._zone_angle(child, state, zone, theta)
            return pos_bounds[zone], margin, theta
        bounds = self.table_bounds(table)
        bounds = self.restrict(bounds)
        bounds[0] += margin
        bounds[1] -= margin
        return bounds, margin, theta

    @staticmethod
    def _zone_angle(child: SceneObject, state: Sequence[Predicate], zone: str, theta: float) -> float:
        if f"aligned({child})" in state:
            return Aligned.sample_angle(child, zone=zone)
        return theta

    @staticmethod
    def table_bounds(table: SceneObject) -> np.ndarray:
        """Placement bounds on the table: its top, clipped to the object-state position range."""
        bounds = table.aabb()[:, :2].copy()
        low, high = object_state_range()
        bounds[0] = np.maximum(bounds[0], low[:2])
        bounds[1] = np.minimum(bounds[1], high[:2])
        bounds[0, 0] = TABLE_CONSTRAINTS["table_x_min"]
        return bounds

    def restrict(self, bounds: np.ndarray) -> np.ndarray:
        """Zone-specific restriction of the table bounds (identity for the whole table)."""
        return bounds

    @staticmethod
    def get_poslimit(obj: SceneObject, state: Sequence[Predicate]) -> Optional[PosLimit]:
        for prop in state:
            if isinstance(prop, PosLimit) and prop.args[0] == obj.name:
                return prop
        return None

    @staticmethod
    def get_zone(obj: SceneObject, state: Sequence[Predicate]) -> Optional[TableBounds]:
        zones = [prop for prop in state if isinstance(prop, TableBounds) and prop.args[0] == obj.name]  # type: ignore[attr-defined]
        if len(zones) > 1:
            raise ValueError(f"{obj} cannot be in multiple zones: {zones}")
        if zones:
            return zones[0]
        if f"on({obj}, table)" in state:
            return TableBounds()
        return None


class Aligned(Predicate):
    """The object's yaw is close to a zone-specific canonical angle."""

    ANGLE_EPS = 0.002
    ANGLE_STD = 0.05
    ANGLE_ABS = 0.1
    ZONE_ANGLES: Dict[Tuple[str, Optional[str]], float] = {
        ("rack", "inworkspace"): 0.5 * np.pi,
        ("rack", "beyondworkspace"): 0.0,
    }

    @staticmethod
    def sample_angle(obj: SceneObject, zone: Optional[str] = None) -> float:
        angle = 0.0
        while abs(angle) < Aligned.ANGLE_EPS:
            angle = float(np.random.randn() * Aligned.ANGLE_STD)
        mean = Aligned.ZONE_ANGLES.get((obj.kind, zone), 0.0)
        angle = float(np.clip(angle + mean, mean - Aligned.ANGLE_ABS, mean + Aligned.ANGLE_ABS))
        return (angle + np.pi) % (2 * np.pi) - np.pi


class PosLimit(Predicate):
    """The object sits at one of a few canonical positions of its zone."""

    POS_EPS: Dict[str, float] = {"rack": 0.01, "box": 0.01}
    """Half width of the sampling box around the canonical positions."""
    VALUE_EPS = 0.02
    """Tolerance when checking the predicate (objects slide slightly while settling in MuJoCo)."""
    POS_SPEC: Dict[str, Dict[str, np.ndarray]] = {
        "rack": {"inworkspace": np.array([0.44, -0.33]), "beyondworkspace": np.array([0.86, 0.0])},
        "box": {"inworkspace": np.array([0.6, 0.0])},
    }

    def value(self, env: TableEnv, state: Optional[Sequence[Predicate]] = None) -> bool:
        obj = self.objects(env)[0]
        if obj.kind not in PosLimit.POS_SPEC or state is None:
            return True
        zone = next(
            (
                type(p).__name__.lower()
                for p in state
                if isinstance(p, (InWorkspace, BeyondWorkspace)) and p.args[0] == obj.name
            ),
            None,
        )
        if zone is None or zone not in PosLimit.POS_SPEC[obj.kind]:
            return True
        distance = np.linalg.norm(obj.pose().pos[:2] - PosLimit.POS_SPEC[obj.kind][zone])
        return bool(distance <= PosLimit.VALUE_EPS)

    def bounds(self, obj: SceneObject) -> Dict[str, np.ndarray]:
        if obj.kind not in PosLimit.POS_SPEC:
            raise ValueError(f"No position limits specified for {obj.kind!r} objects.")
        eps = PosLimit.POS_EPS[obj.kind]
        return {zone: np.array([xy - eps, xy + eps]) for zone, xy in PosLimit.POS_SPEC[obj.kind].items()}


class InWorkspace(Predicate, TableBounds):
    def value(self, env: TableEnv, state: Optional[Sequence[Predicate]] = None) -> bool:
        obj = self.objects(env)[0]
        if obj.kind == "rack":  # The rack is in the workspace by construction.
            return True
        return is_inworkspace(obj.pose().pos[:2])

    def restrict(self, bounds: np.ndarray) -> np.ndarray:
        bounds[0, 0] = WORKSPACE["workspace_x_min"]
        bounds[1, 0] = WORKSPACE["workspace_radius"]
        return bounds


class EntirelyInWorkspace(Predicate, TableBounds):
    def value(self, env: TableEnv, state: Optional[Sequence[Predicate]] = None) -> bool:
        return is_entirely_inworkspace(self.objects(env)[0])

    def restrict(self, bounds: np.ndarray) -> np.ndarray:
        bounds[0, 0] = WORKSPACE["workspace_x_min"]
        bounds[1, 0] = WORKSPACE["workspace_radius"]
        return bounds


class BeyondWorkspace(Predicate, TableBounds):
    def value(self, env: TableEnv, state: Optional[Sequence[Predicate]] = None) -> bool:
        return is_beyondworkspace(self.objects(env)[0].pose().pos[:2])

    def restrict(self, bounds: np.ndarray) -> np.ndarray:
        radius = WORKSPACE["workspace_radius"]
        half_width = 0.5 * (bounds[1, 1] - bounds[0, 1])
        bounds[0, 0] = radius * np.cos(np.arcsin(min(half_width / radius, 1.0)))
        return bounds


class Inhand(Predicate):
    """The object is held by the gripper, or lifted to ``LIFT_HEIGHT``."""

    def value(self, env: TableEnv, state: Optional[Sequence[Predicate]] = None) -> bool:
        obj = self.objects(env)[0]
        return is_lifted(obj) or env.robot.is_holding(obj)


class Under(Predicate):
    def value(self, env: TableEnv, state: Optional[Sequence[Predicate]] = None) -> bool:
        child, parent = self.objects(env)
        return is_under_with_intersection(child, parent)


class NonBlocking(Predicate):
    """The second object does not block the straight path from the robot to the first."""

    MARGIN: Dict[Tuple[str, str], Dict[Optional[str], float]] = {
        ("box", "rack"): {"inworkspace": 3.0, "beyondworkspace": 1.5},
        ("box", "box"): {"inworkspace": 3.0, "beyondworkspace": 3.0},
        ("rack", "lstick"): {"inworkspace": 0.25, "beyondworkspace": 0.25},
    }

    def value(self, env: TableEnv, state: Optional[Sequence[Predicate]] = None) -> bool:
        target, blocker = self.objects(env)
        line = LineString([[0.0, 0.0], target.pose().pos[:2].tolist()])
        # The blocker's footprint is approximated by its bounding box (single hull).
        vertices = bbox_footprint(blocker).astype(np.float64)
        margins = NonBlocking.MARGIN.get((target.kind, blocker.kind))
        if margins is not None:
            xy = blocker.pose().pos[:2]
            zone = (
                "inworkspace" if is_inworkspace(xy) else "beyondworkspace" if is_beyondworkspace(xy) else None
            )
            scale = margins.get(zone, 1.0)
            margin = scale * float(target.size[:2].max())
            center = vertices.mean(axis=0)
            vertices = vertices + np.sign(vertices - center) * margin
        return not Polygon(vertices).intersects(line)


class On(Predicate):
    """The first object rests on the second (table, rack or box)."""

    MAX_SAMPLE_ATTEMPTS = 10

    def sample(self, env: TableEnv, state: Sequence[Predicate]) -> bool:
        child, parent = self.objects(env)
        if child.is_static:
            return True
        parent_z = parent.aabb()[1, 2] + PLACEMENT_CLEARANCE

        validators: List[Predicate] = [
            prop for prop in state if isinstance(prop, (Free, TableBounds)) and prop.args[-1] == child.name
        ]
        fixed_pose: Optional[Pose] = None
        if env.symbols_registered:
            for prop in state:
                if isinstance(prop, Pos) and prop.args[0] == child.name:
                    validators.append(prop)
                    fixed_pose = prop.symbol_pose(env)

        for _ in range(On.MAX_SAMPLE_ATTEMPTS):
            if fixed_pose is not None:
                pose = fixed_pose
            else:
                # A fresh yaw per attempt: elongated objects only fit some zones in some orientations.
                if f"aligned({child})" in state:
                    theta = Aligned.sample_angle(child)
                else:
                    theta = float(np.random.uniform(-np.pi, np.pi))
                region = self._placement_region(child, parent, state, theta)
                if region is None:
                    continue
                bounds, theta, parent_pose = region
                low, high = np.minimum(bounds[0], bounds[1]), np.maximum(bounds[0], bounds[1])
                xy = np.random.uniform(low, high)
                position = np.array([xy[0], xy[1], 0.0])
                if parent_pose is not None:
                    position = parent_pose.apply(position)
                position[2] = parent_z + 0.5 * child.size[2]
                if child.kind == "rack":
                    position[2] += 0.5 * child.size[2]
                pose = Pose.from_yaw(position, theta)
            child.set_pose(pose)
            if all(prop.value(env, state) for prop in validators):
                return True
        return False

    @staticmethod
    def _placement_region(
        child: SceneObject,
        parent: SceneObject,
        state: Sequence[Predicate],
        theta: float,
    ) -> Optional[Tuple[np.ndarray, float, Optional[Pose]]]:
        """x-y bounds (and possibly adjusted yaw) for placing ``child`` on ``parent`` with yaw ``theta``.

        Returns ``(bounds, theta, parent_pose)``: ``parent_pose`` is None for the
        table (bounds in the planning frame) and the parent's pose otherwise
        (bounds in the parent frame). Returns None if the region is empty.
        """
        margin = geometry.rotated_footprint_margins(child.bbox, theta)
        if parent.kind == "table":
            zone = TableBounds.get_zone(child, state)
            if zone is None:
                bounds = TableBounds.table_bounds(parent)
                bounds[0] += margin
                bounds[1] -= margin
            else:
                bounds, margin, theta = zone.bounds_and_margin(child, parent, state, theta)
            return bounds, theta, None
        if parent.kind in ("rack", "box"):
            return np.array(On.stable_region(child, parent, theta)), theta, parent.pose()
        raise ValueError(f"Cannot place {child} on {parent}: parent must be a table, rack or box.")

    def value(self, env: TableEnv, state: Optional[Sequence[Predicate]] = None) -> bool:
        child, parent = self.objects(env)
        if not is_on(child, parent):
            return False
        if state is not None and not child.is_upright(EPSILONS["align"]):
            return False
        return True

    @staticmethod
    def stable_region(child: SceneObject, parent: SceneObject, theta: float) -> Tuple[np.ndarray, np.ndarray]:
        """x-y bounds (parent frame) where the child's footprint stays on the parent."""
        relative_yaw = theta - parent.pose().yaw()
        margin = geometry.rotated_footprint_margins(child.bbox, relative_yaw)
        xy_min = margin.copy()
        xy_max = parent.size[:2] - margin
        if np.any(xy_max - xy_min <= 0):
            ratio = 2 * margin / parent.size[:2]
            lo = np.minimum(0.25 * ratio, 0.45)
            hi = np.maximum(0.55, np.minimum(0.75 * ratio, 0.95))
            xy_min = parent.size[:2] * lo
            xy_max = parent.size[:2] * hi
        return xy_min - 0.5 * parent.size[:2], xy_max - 0.5 * parent.size[:2]


class Pos(Predicate):
    """The object is at the position bound to a symbolic variable (``pos(obj, x)``)."""

    POS_EPS: Dict[str, float] = {"rack": 0.01, "box": 0.15, "lstick": 0.01}

    def objects(self, env: TableEnv) -> List[SceneObject]:
        return [env.objects[self.args[0]]]

    def symbol_pose(self, env: TableEnv) -> Pose:
        try:
            return env.symbols[self.args[1]]
        except KeyError as e:
            raise ValueError(f"Position symbol {self.args[1]!r} is not registered.") from e

    def is_bound(self, env: TableEnv) -> bool:
        return self.args[1] in env.symbols

    def value(self, env: TableEnv, state: Optional[Sequence[Predicate]] = None) -> bool:
        if not self.is_bound(env):
            # An unbound symbol is defined by the object's current pose (see TabletopScene.reset).
            return True
        obj = self.objects(env)[0]
        distance = np.linalg.norm(obj.pose().pos[:2] - self.symbol_pose(env).pos[:2])
        return bool(distance <= Pos.POS_EPS.get(obj.kind, 0.01))


PREDICATE_CLASSES: Dict[str, Type[Predicate]] = {
    "free": Free,
    "aligned": Aligned,
    "poslimit": PosLimit,
    "pos": Pos,
    "inworkspace": InWorkspace,
    "entirelyinworkspace": EntirelyInWorkspace,
    "beyondworkspace": BeyondWorkspace,
    "inhand": Inhand,
    "notincenter": NotInCenter,
    "under": Under,
    "nonblocking": NonBlocking,
    "on": On,
}
