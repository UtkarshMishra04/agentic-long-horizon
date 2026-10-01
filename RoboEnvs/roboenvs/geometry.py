"""Poses, coordinate frames and scene geometry.

All positions are meters in the *table frame*: origin at the robot base projected onto the table
surface, ``x`` pointing away from the robot, ``y`` to its left, ``z`` up (the table surface is at
``z = 0``). Quaternions are ``(x, y, z, w)``; MuJoCo's ``(w, x, y, z)`` is converted at the boundary.
"""

from __future__ import annotations

import dataclasses
import math
import re
from typing import List, Optional, Tuple

import numpy as np

# Rotation matrix of a gripper pointing straight down (robosuite's default OSC orientation).
TOP_DOWN_ROTATION = np.array([[0.0, 1.0, 0.0], [1.0, 0.0, 0.0], [0.0, 0.0, -1.0]])


def quat2mat(quat: np.ndarray) -> np.ndarray:
    """Rotation matrix of an ``(x, y, z, w)`` quaternion."""
    x, y, z, w = (float(v) for v in np.asarray(quat, dtype=np.float64) / np.linalg.norm(quat))
    return np.array(
        [
            [1 - 2 * (y * y + z * z), 2 * (x * y - z * w), 2 * (x * z + y * w)],
            [2 * (x * y + z * w), 1 - 2 * (x * x + z * z), 2 * (y * z - x * w)],
            [2 * (x * z - y * w), 2 * (y * z + x * w), 1 - 2 * (x * x + y * y)],
        ]
    )


def mat2quat(rotation: np.ndarray) -> np.ndarray:
    """``(x, y, z, w)`` quaternion of a rotation matrix, with ``w >= 0`` (robosuite's convention)."""
    m = np.asarray(rotation, dtype=np.float64)[:3, :3]
    k = (
        np.array(
            [
                [m[0, 0] - m[1, 1] - m[2, 2], 0.0, 0.0, 0.0],
                [m[0, 1] + m[1, 0], m[1, 1] - m[0, 0] - m[2, 2], 0.0, 0.0],
                [m[0, 2] + m[2, 0], m[1, 2] + m[2, 1], m[2, 2] - m[0, 0] - m[1, 1], 0.0],
                [m[2, 1] - m[1, 2], m[0, 2] - m[2, 0], m[1, 0] - m[0, 1], m[0, 0] + m[1, 1] + m[2, 2]],
            ]
        )
        / 3.0
    )
    eigenvalues, eigenvectors = np.linalg.eigh(k)
    q = eigenvectors[[3, 0, 1, 2], np.argmax(eigenvalues)]  # (w, x, y, z)
    if q[0] < 0.0:
        q = -q
    return q[[1, 2, 3, 0]]


def pose2mat(pos: np.ndarray, quat: np.ndarray) -> np.ndarray:
    matrix = np.eye(4)
    matrix[:3, :3] = quat2mat(quat)
    matrix[:3, 3] = np.asarray(pos, dtype=np.float64)
    return matrix


def mat2pose(matrix: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    return np.array(matrix[:3, 3], dtype=np.float64), mat2quat(matrix[:3, :3])


def pose_inv(matrix: np.ndarray) -> np.ndarray:
    inverse = np.eye(4)
    inverse[:3, :3] = matrix[:3, :3].T
    inverse[:3, 3] = -inverse[:3, :3] @ matrix[:3, 3]
    return inverse


def axisangle2quat(axis_angle: np.ndarray) -> np.ndarray:
    """``(x, y, z, w)`` quaternion of a rotation vector (unit axis scaled by the angle)."""
    vector = np.asarray(axis_angle, dtype=np.float64)
    angle = float(np.linalg.norm(vector))
    if math.isclose(angle, 0.0, abs_tol=1e-12):
        return np.array([0.0, 0.0, 0.0, 1.0])
    axis = vector / angle
    return np.concatenate([axis * math.sin(angle / 2.0), [math.cos(angle / 2.0)]])


def quat2axisangle(quat: np.ndarray) -> np.ndarray:
    """Rotation vector (unit axis scaled by the angle) of an ``(x, y, z, w)`` quaternion."""
    q = np.asarray(quat, dtype=np.float64) / np.linalg.norm(quat)
    w = float(np.clip(q[3], -1.0, 1.0))
    den = math.sqrt(max(0.0, 1.0 - w * w))
    if math.isclose(den, 0.0, abs_tol=1e-12):
        return np.zeros(3)
    return q[:3] * (2.0 * math.acos(w)) / den


def quat_multiply(quat_a: np.ndarray, quat_b: np.ndarray) -> np.ndarray:
    """Quaternion product ``a * b`` (both ``(x, y, z, w)``)."""
    return mat2quat(quat2mat(quat_a) @ quat2mat(quat_b))


def quat_wxyz_to_xyzw(quat: np.ndarray) -> np.ndarray:
    q = np.asarray(quat, dtype=np.float64)
    return q[[1, 2, 3, 0]]


def quat_xyzw_to_wxyz(quat: np.ndarray) -> np.ndarray:
    q = np.asarray(quat, dtype=np.float64)
    return q[[3, 0, 1, 2]]


@dataclasses.dataclass(frozen=True)
class Pose:
    """Rigid transform with position ``pos`` and quaternion ``quat`` (x, y, z, w)."""

    pos: np.ndarray
    quat: np.ndarray

    @staticmethod
    def identity() -> Pose:
        return Pose(np.zeros(3), np.array([0.0, 0.0, 0.0, 1.0]))

    @staticmethod
    def from_matrix(matrix: np.ndarray) -> Pose:
        pos, quat = mat2pose(matrix)
        return Pose(pos, quat)

    @staticmethod
    def from_yaw(pos: np.ndarray, theta: float) -> Pose:
        return Pose(np.asarray(pos, dtype=np.float64), yaw_quat(theta))

    def matrix(self) -> np.ndarray:
        return pose2mat(self.pos, self.quat)

    def rotation(self) -> np.ndarray:
        return quat2mat(self.quat)

    def inverse(self) -> Pose:
        return Pose.from_matrix(pose_inv(self.matrix()))

    def compose(self, other: Pose) -> Pose:
        """``self * other``: applies ``other`` first, then ``self``."""
        return Pose.from_matrix(self.matrix() @ other.matrix())

    def apply(self, point: np.ndarray) -> np.ndarray:
        """Transforms a point from this frame to the parent frame."""
        return self.rotation() @ np.asarray(point, dtype=np.float64) + self.pos

    def axis_angle(self) -> np.ndarray:
        return quat2axisangle(self.quat)

    def yaw(self) -> float:
        return rotation_yaw(self.rotation())

    def z_axis(self) -> np.ndarray:
        return self.rotation()[:, 2]


def rotation_yaw(rotation: np.ndarray) -> float:
    """Yaw (z rotation of the ``sxyz`` Euler decomposition) of a rotation matrix."""
    cy = math.hypot(float(rotation[0, 0]), float(rotation[1, 0]))
    if cy > 1e-8:
        return math.atan2(float(rotation[1, 0]), float(rotation[0, 0]))
    return 0.0  # Gimbal lock: the yaw is folded into the roll (as in transforms3d).


def yaw_quat(theta: float) -> np.ndarray:
    return axisangle2quat(np.array([0.0, 0.0, float(theta)]))


def top_down_orientation(theta: float, base_quat: Optional[np.ndarray] = None) -> np.ndarray:
    """Gripper orientation (x, y, z, w) pointing down, yawed by ``theta`` in ``base_quat``'s frame."""
    rotation = quat2mat(yaw_quat(theta)) @ TOP_DOWN_ROTATION
    if base_quat is not None:
        rotation = quat2mat(base_quat) @ rotation
    return mat2quat(rotation)


def top_down_yaw(quat: np.ndarray) -> float:
    """Yaw of a (roughly) top-down gripper orientation relative to :data:`TOP_DOWN_ROTATION`."""
    rotation = quat2mat(quat) @ TOP_DOWN_ROTATION.T
    return float(np.arctan2(rotation[1, 0], rotation[0, 0]))


def wrap_angle(angle: float) -> float:
    return float((angle + np.pi) % (2 * np.pi) - np.pi)


def orientation_error(quat_a: np.ndarray, quat_b: np.ndarray) -> float:
    """Angle in radians between two orientations (quaternion sign ambiguity handled)."""
    dot = abs(
        float(
            np.dot(np.asarray(quat_a) / np.linalg.norm(quat_a), np.asarray(quat_b) / np.linalg.norm(quat_b))
        )
    )
    return float(2.0 * np.arccos(min(1.0, dot)))


@dataclasses.dataclass(frozen=True)
class TableFrame:
    """Translation between a simulator's world frame and the table frame."""

    origin: np.ndarray
    """World position of the table-frame origin (robot base x-y at table height)."""

    def to_world(self, pos: np.ndarray) -> np.ndarray:
        return np.asarray(pos, dtype=np.float64) + self.origin

    def to_table(self, pos: np.ndarray) -> np.ndarray:
        return np.asarray(pos, dtype=np.float64) - self.origin


# ---------------------------------------------------------------------- shapes


def lstick_link_positions(
    short_length: float, long_length: float, short_offset: float, radius: float
) -> Tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Centers of the L-stick's long bar, short bar and corner in the object frame.

    The long bar runs along ``x`` and the short bar along ``y``; ``short_offset`` in ``[-1, 1]``
    sets where the long bar meets the short bar (``-1`` = one end, ``0`` = middle, ``1`` = other end).
    """
    dy = 0.5 * np.sign(short_offset) * max(0.0, (abs(short_offset) - 1.0) * short_length / 2 + radius)
    pos_long = np.array([-radius / 2, short_offset * short_length / 2 - dy, 0.0])
    pos_short = np.array([(long_length - radius) / 2, -dy, 0.0])
    pos_corner = np.array([(long_length - radius) / 2, short_offset * short_length / 2 - dy, 0.0])
    return pos_long, pos_short, pos_corner


def lstick_size(short_length: float, long_length: float, short_offset: float, radius: float) -> np.ndarray:
    """Full extents ``(x, y, z)`` of the L-stick's bounding box."""
    _, pos_short, _ = lstick_link_positions(short_length, long_length, short_offset, radius)
    return np.array([long_length + radius, short_length + 2 * abs(pos_short[1]), 2 * radius])


def yaw_rotation(theta: float) -> np.ndarray:
    """2x2 rotation matrix for a yaw angle."""
    c, s = np.cos(theta), np.sin(theta)
    return np.array([[c, -s], [s, c]])


def rotated_footprint_margins(bbox: np.ndarray, theta: float) -> np.ndarray:
    """Half extents of a bounding box's x-y footprint after rotating it by ``theta`` about z."""
    corners = np.array([[x, y] for x in bbox[:, 0] for y in bbox[:, 1]])
    rotated = corners @ yaw_rotation(theta).T
    return 0.5 * (rotated.max(axis=0) - rotated.min(axis=0))


def bbox_corners(bbox: np.ndarray) -> np.ndarray:
    """The 8 corners of an axis-aligned box given as ``[[min], [max]]``."""
    return np.array([[x, y, z] for x in bbox[:, 0] for y in bbox[:, 1] for z in bbox[:, 2]])


def convex_hull_2d(points: np.ndarray) -> np.ndarray:
    """Counter-clockwise convex hull of 2D points (Andrew's monotone chain)."""
    pts = sorted({(float(p[0]), float(p[1])) for p in points})
    if len(pts) <= 2:
        return np.array(pts)

    def cross(o, a, b):
        return (a[0] - o[0]) * (b[1] - o[1]) - (a[1] - o[1]) * (b[0] - o[0])

    lower: list = []
    for p in pts:
        while len(lower) >= 2 and cross(lower[-2], lower[-1], p) <= 0:
            lower.pop()
        lower.append(p)
    upper: list = []
    for p in reversed(pts):
        while len(upper) >= 2 and cross(upper[-2], upper[-1], p) <= 0:
            upper.pop()
        upper.append(p)
    return np.array(lower[:-1] + upper[:-1])


# ---------------------------------------------------------------------- scene constants

TABLE_CONSTRAINTS = {
    "table_z_max": 0.00,
    "table_x_min": 0.28,
    "table_y_min": -0.45,
    "table_y_max": 0.45,
    "workspace_x_min": 0.40,
}
"""Table extents used when sampling scenes (table frame, meters)."""

START_POSE = {"height": 0.4, "radius": 0.7}
"""The gripper starts every episode at this height, at most this far from the robot base."""

LIFT_HEIGHT = 0.4
"""An object whose center is within half its height of this height counts as lifted."""

EPSILONS = {"aabb": 0.05, "align": 0.99}

INTERSECTION_THRESHOLD = 0.5
"""Fraction of a box's footprint that must lie below the rack for ``under``."""

_PROPOSITION_PATTERN = re.compile(r"^\s*([A-Za-z_][\w]*)\s*\((.*)\)\s*$")


def parse_proposition(proposition: str) -> Tuple[str, List[str]]:
    """Parses ``"name(arg1, arg2)"`` into ``("name", ["arg1", "arg2"])``."""
    match = _PROPOSITION_PATTERN.match(proposition)
    if match is None:
        raise ValueError(f"Cannot parse proposition {proposition!r}.")
    name, args = match.group(1), match.group(2).strip()
    if not args:
        return name, []
    return name, [arg.strip() for arg in args.split(",")]
