# LongHorizonTAMP

Long-horizon task and motion planning (TAMP) environments with a Franka Panda arm in robosuite (MuJoCo).
Each environment samples a scene of objects on a table and defines a goal on the final arrangement of the
objects.

## Install

```bash
pip install -e .            # numpy<2, gym 0.26.2, mujoco 2.3.7, robosuite 1.4.1, shapely, pyyaml, pillow, imageio
export MUJOCO_GL=egl        # headless rendering on a GPU; MUJOCO_GL=osmesa on CPU-only machines
```

## Environments

| id | goal |
|---|---|
| `LongHorizonTAMP/LiftRedBox-v0` | the red box is held by the gripper or raised above the table |
| `LongHorizonTAMP/RedBoxOnRack-v0` | the red box rests upright on the rack |
| `LongHorizonTAMP/RedBoxUnderRack-v0` | the red box is under the rack, resting on the table |
| `LongHorizonTAMP/RedBoxUnderRack-v1` | the same goal in a different scene distribution |
| `LongHorizonTAMP/RedBoxToBlueSpot-v0` | the red box is at the blue box's starting position, the L-shaped stick is back at its own starting position, the blue box and the stick rest on the table inside the workspace, and nothing rests on any of them |
| `LongHorizonTAMP/RedBoxToBlueSpot-v1` | the red box is at the blue box's starting position, the blue box and the L-shaped stick rest on the table inside the workspace, and nothing rests on any of them |
| `LongHorizonTAMP/PackRack-v0` | the yellow, red and cyan boxes rest upright on the rack |
| `LongHorizonTAMP/PackRack-v1` | the yellow, cyan and blue boxes rest upright on the rack |
| `LongHorizonTAMP/PackRack-v2` | the red, yellow, cyan and blue boxes rest upright on the rack |

The exact conditions, with their numeric parameters, are returned by `env.get_goal()`.

## Interface

```python
import numpy as np
import longhorizontamp

env = longhorizontamp.make("LongHorizonTAMP/RedBoxOnRack-v0", control="delta")
observation, info = env.reset(seed=1)
state = env.get_state()          # flat float32 array, layout below
goal = env.get_goal()            # {"text": str, "conditions": [dict, ...]}
for _ in range(100):
    observation, reward, terminated, truncated, info = env.step(env.action_space.sample())
    if terminated or truncated:
        break
frame = env.render()             # [256, 256, 3] uint8
env.close()
```

`longhorizontamp.make(env_id, control="delta", max_episode_steps=None, image_size=84,
cameras=("agentview", "robot0_eye_in_hand"), render_size=256)`; `longhorizontamp.ENV_IDS` lists the ids.

* `reset(seed=None) -> (observation, info)` samples a new scene. A seed whose scene is invalid is
  skipped; `info["scene_seed"]` is the seed of the scene actually used. A freshly created
  environment always maps a seed to the same scene, but within one environment instance which
  seeds are skipped can depend on earlier episodes. For reproducible evaluation, create a fresh
  environment per episode, or use seeds that a fresh environment maps to themselves
  (`info["scene_seed"] == seed`).
* `get_state() -> np.ndarray` returns the simulator state (see *State*).
* `get_goal() -> dict` returns the goal of the current episode (see *Goal*). Goals that refer to
  positions from the start of the episode change with every reset.
* `step(action) -> (observation, reward, terminated, truncated, info)`.
* `render()`, `close()`, `action_space`, `observation_space`.

### Actions

The controller runs at 20 Hz. `control="delta"` (default): `[dx, dy, dz, drx, dry, drz, gripper]` in
`[-1, 1]`, a translation of up to 5 cm and a rotation of up to 0.25 rad (axis-angle, world frame)
of the end-effector per step. `control="absolute"`: the target end-effector position (m) and
orientation (axis-angle, rad), then the gripper. The gripper closes when its entry is `> 0`. Target
positions are clipped to x in [0.1, 0.95], y in [-0.5, 0.5], z in [0, 0.6] m.

### Observations

A dict: `agentview_image` and `robot0_eye_in_hand_image` (`[84, 84, 3]` uint8 by default),
`robot0_joint_pos` (7), `robot0_joint_vel` (7), `robot0_eef_pos` (3), `robot0_eef_quat` (4, x-y-z-w),
`robot0_gripper_qpos` (gripper joints), `robot0_gripper_opening` (1, 0 = closed, 1 = open).

### State

`get_state()` concatenates, in this order: arm joint positions (7), arm joint velocities (7),
gripper joint positions (`G`, the size of `robot0_gripper_qpos`), end-effector position (3) and
orientation quaternion (4, x-y-z-w), then for every movable object its position (3) and orientation
quaternion (4, x-y-z-w). Positions are in meters in a frame whose origin is at the robot base, with
x pointing away from the robot and z up (the same frame as the goal targets).

| id | objects in `get_state()` order (each 7 values: position, quaternion) |
|---|---|
| `LongHorizonTAMP/LiftRedBox-v0` | rack, lstick, red_box |
| `LongHorizonTAMP/RedBoxOnRack-v0` | rack, lstick, red_box |
| `LongHorizonTAMP/RedBoxUnderRack-v0` | rack, lstick, red_box |
| `LongHorizonTAMP/RedBoxUnderRack-v1` | rack, lstick, red_box |
| `LongHorizonTAMP/RedBoxToBlueSpot-v0` | lstick, red_box, blue_box |
| `LongHorizonTAMP/RedBoxToBlueSpot-v1` | lstick, red_box, blue_box |
| `LongHorizonTAMP/PackRack-v0` | rack, yellow_box, red_box, cyan_box |
| `LongHorizonTAMP/PackRack-v1` | rack, blue_box, yellow_box, cyan_box |
| `LongHorizonTAMP/PackRack-v2` | rack, blue_box, yellow_box, red_box, cyan_box |

The gripper has `G = 6` joints, so the object part starts at index 27 (e.g. 48 values for three objects).

### Goal

`get_goal()` returns `{"text": ..., "conditions": [...]}`. Every condition has `type`, `objects`, a
readable `text`, and its numeric parameters:

| type | holds when | parameters |
|---|---|---|
| `on` | the object rests upright on the other object (or the table) | |
| `under` | the object's x-y footprint overlaps the other's by at least `min_fraction`, below its top | `min_fraction` |
| `inhand` | the object is between the gripper fingers or its center is above `min_height` | `min_height` |
| `pos` | the object's x-y position is within `tolerance` of `target_xy` | `target_xy`, `tolerance` |
| `free` | nothing rests on the object and it is at least `min_distance` from the listed objects | `min_distance` |
| `inworkspace` | the object's center has x ≥ `x_min` and lies within `radius` of the robot base | `x_min`, `radius` |

### Reward and episode end

The reward is `1.0` on the step at which all goal conditions hold and `0.0` otherwise. Reaching the
goal sets `terminated=True`. Otherwise the episode is `truncated` after the time limit
(`max_episode_steps`; defaults: LiftRedBox 1500, RedBoxOnRack 1800, RedBoxUnderRack 1300 / 2500,
RedBoxToBlueSpot 1000 / 2400, PackRack 1000 / 1600 / 2000 steps). `info` holds `success`, `step`,
`scene_seed` and the goal `text`.
