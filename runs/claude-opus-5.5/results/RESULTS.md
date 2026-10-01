# RESULTS

Scripted (no learning) solutions for the 9 RoboEnvs environments. They use only `make`, `reset`,
`get_state`, `get_goal`, `step` and `render`, with `control="absolute"`: each action is a target
gripper pose plus a gripper command.

## How to run

```bash
cd /workspace/claude
python solutions/<EnvName>.py --seed 1 [--video out.gif]   # one episode, e.g. solutions/PackRack-v2.py
python evaluate.py                    # 20 distinct scenes per env (--n 60 for the final table below)
python make_videos.py                 # 5 random seeds per env -> videos/<env>_seed<seed>.gif
python summarize.py results/final.json   # prints the table below
```

**Seeds.** `reset(seed)` silently skips invalid scenes, so seeds 0–19 contain duplicate scenes (for
example, seeds 1–16 of RedBoxToBlueSpot-v0 all give scene 16). Which seeds are skipped also depends
on the simulator's history. `evaluate.py` therefore uses the first N seeds that a freshly created
environment maps to themselves (`info["scene_seed"] == seed`); they are listed in
`results/scene_seeds.json`. Every evaluated episode is a distinct, reproducible scene. Success means
the episode ended with `terminated=True` before the environment's default time limit.

## Success rates (final code)

60 distinct scenes per environment, 540 episodes in total. Results for the seven environments whose
code did not change after cycle 10 come from cycle 10 (`results/final_iter10_all60.json`). The two
BlueSpot environments come from cycle 11 (`results/final_iter11_bluespot60.json`), after the fix
described below. The merged file is `results/final.json`.

| environment | first 20 seeds | seeds 21-40 | seeds 41-60 | all | mean steps (min-max) of successes | time limit | failed seeds |
|---|---|---|---|---|---|---|---|
| LiftRedBox-v0 | 20/20 | 20/20 | 20/20 | **60/60** | 472 (443-515) | 1500 | - |
| RedBoxOnRack-v0 | 20/20 | 20/20 | 20/20 | **60/60** | 573 (529-622) | 1800 | - |
| RedBoxUnderRack-v0 | 20/20 | 20/20 | 20/20 | **60/60** | 532 (400-732) | 1300 | - |
| RedBoxUnderRack-v1 | 20/20 | 20/20 | 20/20 | **60/60** | 953 (811-1285) | 2500 | - |
| RedBoxToBlueSpot-v0 | 20/20 | 20/20 | 20/20 | **60/60** | 395 (1-482) | 1000 | - |
| RedBoxToBlueSpot-v1 | 20/20 | 20/20 | 20/20 | **60/60** | 820 (749-1047) | 2400 | - |
| PackRack-v0 | 20/20 | 20/20 | 20/20 | **60/60** | 401 (325-469) | 1000 | - |
| PackRack-v1 | 20/20 | 20/20 | 20/20 | **60/60** | 626 (567-691) | 1600 | - |
| PackRack-v2 | 20/20 | 20/20 | 20/20 | **60/60** | 836 (749-908) | 2000 | - |

Total: 540/540

The first 20 seeds and seeds 21–40 were used while developing. **Seeds 41–60 had never been run
before cycle 10** (held-out). Cycle 10 scored 178/180 on them: one failure each in
RedBoxToBlueSpot-v0 (seed 224) and RedBoxToBlueSpot-v1 (seed 120), both in the search for a free
spot for the blue box. The fix (a wider, step-by-step relaxed spot search) changes only
`bluespot_common.py`, so cycle 11 re-ran both BlueSpot environments on all 60 seeds: 120/120. The
exact evaluated code is in `results/final_iter10_all60_solutions/` and
`results/final_iter11_bluespot60_solutions/` (identical except `bluespot_common.py`). Earlier cycles'
logs, JSON files and code snapshots are also in `results/`.

## Videos

`videos/<env>_seed<seed>.gif`: 45 GIFs, 5 per environment. Each shows the whole episode, one frame
every 4 control steps plus the last frame, from `env.render()`. A banner on every frame shows the
result: green SUCCESS or red FAILURE. Seeds were drawn with a fixed RNG from each environment's first
20 evaluation seeds:

| environment | video seeds (result, steps) |
|---|---|
| LiftRedBox-v0 | 1 (success, 473), 24 (success, 471), 39 (success, 445), 53 (success, 490), 54 (success, 480) |
| RedBoxOnRack-v0 | 1 (success, 577), 19 (success, 541), 35 (success, 586), 39 (success, 531), 45 (success, 568) |
| RedBoxUnderRack-v0 | 242 (success, 469), 283 (success, 694), 292 (success, 494), 368 (success, 514), 650 (success, 476) |
| RedBoxUnderRack-v1 | 1 (success, 940), 7 (success, 811), 24 (success, 929), 32 (success, 894), 35 (success, 954) |
| RedBoxToBlueSpot-v0 | 0 (success, 466), 4 (success, 454), 30 (success, 471), 62 (success, 440), 69 (success, 1) |
| RedBoxToBlueSpot-v1 | 18 (success, 794), 22 (success, 1034), 29 (success, 838), 30 (success, 816), 46 (success, 756) |
| PackRack-v0 | 6 (success, 377), 8 (success, 467), 11 (success, 407), 18 (success, 436), 20 (success, 380) |
| PackRack-v1 | 1 (success, 648), 2 (success, 615), 12 (success, 671), 15 (success, 663), 20 (success, 616) |
| PackRack-v2 | 0 (success, 749), 6 (success, 812), 10 (success, 899), 20 (success, 813), 21 (success, 792) |

All 45/45 recorded episodes succeed (list in `results/videos.json`). The camera is the environment's fixed `agentview` camera: in PackRack the rack sits in the top-left corner of the image and is only partly visible, and in RedBoxUnderRack a box under the rack is hidden by the rack top. The banner gives the result. RedBoxToBlueSpot-v0 seed 69 is a scene that already satisfies the goal at reset: the episode ends after one step and its GIF is just that step.

## How the solutions work

All code is in `solutions/`.

**Shared controller (`common.py`).**
- **Motion.** The gripper is kept pointing down with a chosen yaw. Moves are straight lines of at most 3 cm per step, followed by a settle phase. All object poses are re-read from `get_state()` before every sub-move, so the control is closed-loop.
- **Arm safety, from reach experiments.** Right after `reset` the gripper goes to a home pose (0.5, 0, 0.3). The commanded height is capped as a function of distance r from the base (0.45 m at r=0.66, 0.25 m at 0.72, 0.14 m at 0.76, 0.08 m at 0.80). The radius is clipped to [0.40, 0.80] m. Far boxes are approached low from the inside. These rules prevent the elbow from locking at its joint limit, which the OSC cannot recover from.
- **Wrist model.** q7 ≈ q7₀ − Δyaw + Δazimuth. It is used to choose among symmetric grasp yaws (90° for boxes; 0°/180° and the 2π unwrap for the stick) so the wrist stays in range.
- **Pick and place.** The grasp yaw is aligned with the box faces. Optionally the finger axis is chosen to keep the fingers away from an obstacle. Placement corrects the offset between box and gripper measured while carrying.
- **Stick skills.**
  - Wrist-aware grasp of the long bar.
  - Closed-loop placement of the held stick, using the stick's measured pose and grasp offset; droop compensation; slow turns.
  - *Hook pull*: the short bar is placed behind the box and the stick is pulled along its long bar.
  - *Post pull*: the stick is rolled 90° so the short bar hangs down as a post, then pulled.
  - *Park*: search for a stick pose that clears the boxes and the rack, stays on the table, is reachable, and respects keep-out zones.
  - An upside-down (mirror-image) stick is handled by negating stick-frame y.

| environment | solution |
|---|---|
| LiftRedBox-v0 | The red box starts 0.85–0.95 m from the base, beyond reach. Plan a hook pull: search pull direction, grasp point on the long bar and hook offset so the gripper stays at 0.45–0.72 m, the wrist stays feasible, and the stick stays on the table and clear of the rack. Grasp the stick, place the hook behind the box, pull the box to about 0.62 m, lift the stick, park it, then pick the red box and lift it. The goal holds as soon as both pads grip the box. |
| RedBoxOnRack-v0 | Same fetch, then place the red box on the centre of the rack top, aligned with the rack. |
| RedBoxUnderRack-v0 | The rack stands beyond reach with its open side toward the robot. The gripper cannot get under its top, so the box is staged 7.5 cm in front of the rack (aligned) by pick and place. The stick is moved first if it lies in the push lane. The stick's short bar is laid behind the box, and the box is pushed to the rack centre (the stick is 4 cm tall, the opening 15 cm). |
| RedBoxUnderRack-v1 | Box and rack both beyond reach. Fetch the box with a hook pull. If no collision-free flat hook pose exists (box within a few cm of the rack's side), use a post pull instead: roll the stick at z=0.42 so the short bar hangs down behind the box, with the long bar above the rack. Then stage and push as in v0. |
| RedBoxToBlueSpot-v0 | The stick must stay within 1 cm of its start, so it is never touched, and every grasp/placement uses the finger axis that keeps the fingers clear of it. The blue box goes to a free workspace spot (≥0.12 m from the stick, ≥0.17 m from the target and the red box). The red box is placed exactly at the blue box's start. |
| RedBoxToBlueSpot-v1 | Red box beyond reach; the stick may move. Boxes resting on the stick are moved first. Fetch the red box (hook or post pull). Park the stick in the workspace, away from the boxes and (hard constraint) from the target. Then as v0, also re-placing the blue box or re-parking the stick if one is not `free` of the other. |
| PackRack-v0/v1/v2 | Nearest box first. Each goal box not yet on the rack is picked and placed on a free slot: candidates on a 5×7 grid of the rack top, ≥9.5 cm from boxes already there, corners preferred. Boxes are carried at z=0.34 so they clear boxes already on the rack. In v0 the cyan box starts on the rack and is left in place. |

## Remaining failure cases

**None in the final evaluation:** 540/540 across 60 distinct scenes per environment, including 20
held-out scenes per environment.

Failures seen in earlier cycles and how each was removed (details in `REPORT.md`):

| failure | environments | fixed in cycle |
|---|---|---|
| Elbow locks at its joint limit when the arm is far and high (start pose, descents at r ≥ 0.74 m) | all, mostly tool envs | 3–7 |
| Wrist (q7, then q5/q6) winds into its limits during large stick turns or near the base | Lift, OnRack, UR1, BS1 | 5, 6, 10 |
| Stick carried too low drags the rack; drooping stick sweeps a box away | UR1, BS1 | 5, 8 |
| No flat hook pose for a far box beside the rack (L-stick handedness) | UR1 (≈10 % of scenes) | 8–9 |
| Box resting on the stick at reset; stick parked too close to the target | BS1 | 8, 9 |
| No free spot for the blue box when the stick lies across the workspace | BS0, BS1 | 11 |

Known fragile spots (none failed in the final run):
- **Post pull (rolled stick).** It is used for far boxes beside the rack, roughly 10 % of UnderRack-v1 scenes. It relies on the arm realizing a large wrist roll; the roll is closed-loop and verified, and a failed roll is undone and retried, but this path was debugged on only a handful of scenes (5 during development).
- **Tilted-gripper direct grasp.** The last-resort fallback when neither pull is possible. It was checked in isolation (3/3 far boxes grasped) but not at scale.
- **Timing.** The slowest success used 56 % of its time limit (RedBoxUnderRack-v0: 732 of 1300 steps); all others stayed at or below about 51 %. A scene that needs several retries could still run out of time.
