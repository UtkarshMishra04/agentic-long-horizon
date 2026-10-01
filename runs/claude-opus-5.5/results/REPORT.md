# REPORT: how the solutions were developed

Eleven revise-and-re-evaluate cycles in total. Every cycle ran `evaluate.py` (the first two on PackRack
only). From cycle 5 on, each run used a frozen copy of the code (`results/<run>_solutions/`). Scores
are episodes that ended with `terminated=True` before the default time limit.

| # | What changed (main discovery behind it) | Seeds per env | Result |
|---|---|---|---|
| 1 | First PackRack solution: nearest box first, pick, place on a free rack slot, carried at z=0.28 | PackRack, seeds 0-19 | v0 17/20, v1 18/20, v2 18/20 |
| 2 | Carry at z=0.34: a carried box clipped boxes already on the rack | same | v0 20/20, v1 18/20, v2 17/20 |
| 3 | All 9 envs. Stick tool (hook pull + park). Move away from the random start pose at once (**elbow lock**) | 20 (130/180 episodes finished: OOM) | Lift 19/19, OnRack 16/16, UR0 13/17, UR1 9/12, BS0 13/13, BS1 9/10, PR 11/11, 14/15, 17/17 |
| 4 | Reach envelope measured, height capped by radius. Pull planner searches pull direction and grasp point; stick may overhang the table edge; radial clip 0.80 m. Seeds that a fresh env maps to themselves | 20 (123 episodes, stopped: code changed mid-run) | Lift 18/20, OnRack 18/20, UR0 19/20, UR1 13/20, BS0 20/20, BS1 18/19 |
| 5 | **Wrist (q7) model** for stick grasp and yaw unwrapping. Stick carried at z=0.20 (it had dragged the 0.16 m rack). Hook offsets near the rack. Park margins | 20 | **177/180** (UR1 18, BS1 19) |
| 6 | Pulls keep the gripper ≥0.45 m from the base (arm folded into q5/q6 limits). Stick grasped away from boxes. Blue box re-placed if not `free` | 20 | 178/180 (UR1 18) |
| 7 | Far boxes approached low from inside. A pulled box must end ≤0.68 m away | 20 + 20 held-out | 179/180; held-out 176/180 |
| 8 | **Rolled-stick post pull** for boxes beside the rack. Droop compensation. Park relaxation. Boxes resting on the stick moved first. Tilted-gripper fallback | 40 | 357/360 (UR1 38, BS1 39) |
| 9 | Closed-loop roll at z=0.42. Upside-down (mirror-image) stick handled. Stick set down if not flat. Hard keep-out and re-park in BlueSpot-v1 | 40 | 359/360 (BS1 39) |
| 10 | Minimum gripper radius 0.40 m (a park pose next to the base wound the wrist) | 60 (20 never used before) | 538/540; held-out seeds 178/180 (BS0, BS1 one each) |
| 11 | Free-spot search for the blue box relaxes step by step (the stick lay across the middle of the workspace) | 60, BlueSpot only | 120/120 → **final 540/540** |

Cycles per environment, counting only those that changed the environment's behaviour:
- **PackRack v0/v1/v2:** 3 cycles (2, 3, 4). 100 % from cycle 5.
- **LiftRedBox, RedBoxOnRack:** 3 cycles (3, 4, 5). 100 % from cycle 5.
- **RedBoxUnderRack-v0:** 2 cycles (4, 5). 100 % from cycle 5.
- **RedBoxToBlueSpot-v0:** 1 targeted cycle (11). 100 % in every full run until the held-out seeds of cycle 10.
- **RedBoxToBlueSpot-v1:** 7 cycles (4, 5, 6, 8, 9, 10, 11).
- **RedBoxUnderRack-v1:** 7 cycles (4 to 10). This was the hardest environment.

What I found, and how it changed the solution:
- **The arm locks up when it is high and far.** The OSC drives the elbow (q4) into its −0.07 rad limit when the target is far (r ≳ 0.74 m) and high. It also happens when the arm just holds some random start poses. At the limit the arm is singular in the radial direction and cannot recover; I tried several recovery motions and none worked. A grid of reach tests showed that gripper yaw does not matter, but the approach path does: coming in low from the inside reaches r≈0.79 m. Fixes: go to a home pose right after `reset`, cap the commanded height by radius, clip the radius to [0.40, 0.80] m, approach far boxes low. This took PackRack-v1 from 18/20 to 20/20, UnderRack-v0 from 13/17 to 20/20, and removed most tool-env failures (cycles 3→5).
- **Far boxes (0.85–0.95 m) need the L-stick.** Lifting the stick with fast turns made it roll in the grasp, so all stick turns are slow (0.035 rad per step). The hook pose is closed-loop: the stick's measured pose is fed back, which gives about 1 mm error. The pull is planned over direction × grasp point × hook offset. It has to keep the gripper within 0.45–0.72 m of the base and |y| ≤ 0.46 m, keep the stick ≥1.5 cm from the rack and 3 cm from boxes, and keep the wrist feasible.
- **Wrist winding.** q7 changes by −Δyaw + Δazimuth. Without that model a 2–3 rad stick turn hit the q7 limit. The OSC then twisted q5/q6 to their limits, tilting the gripper and leaving 5 cm position errors (Lift/OnRack 18/20 in cycle 4 → 20/20 in cycle 5). Poses close to the base fold the arm the same way (cycles 6 and 10).
- **The rack is light and the stick is long.** Carrying the stick at z=0.12 dragged and rotated the 0.16 m rack in many UnderRack-v1 scenes. Carrying at z=0.20 fixed it (UR1 13/20 → 18/20). A stick held far from its centre of mass also droops, so from cycle 8 the carry height is raised by the measured droop.
- **The stick's handedness matters.** With this L, a far box within 5–8 cm of the rack's side (4 of 40 UnderRack-v1 scenes, on either side of the rack) leaves no collision-free flat hook pose: the long bar or the hook would have to sit in the gap. A tilted-gripper direct grasp reached the box but hit the rack. The fix was to roll the held stick 90° so the short bar hangs as a vertical post behind the box. Rolling must happen high (z=0.42) so the bar clears the rack top, and it is closed-loop because the arm realizes only about 65° of a 90° roll command. A stick that has been set down may lie upside down; it is then the mirror-image L, so all stick geometry carries a handedness sign (UR1 38/40 → 40/40). The post pull also covers a BlueSpot-v1 scene where the blue box sat next to every usable grasp point for a flat pull.
- **Scene details that broke plans.** Some scenes start with a box resting on the stick, so that box is moved first. In BlueSpot-v0 the stick must stay within 1 cm, so the finger axis is chosen to keep the fingers away from it. One BlueSpot-v0 scene is already solved at reset (success at step 1).
- **Evaluation pitfalls.** `reset(seed)` skips invalid scenes, and which scenes it skips depends on the simulator's history, so seeds 0–19 contain duplicates. I evaluate on seeds that a fresh env maps to themselves. A forked pool deadlocked on OSMesa, so the pool uses spawn. Ten workers plus a debugging run used up the 8 GB of RAM and episodes were lost, so the pool now uses 8 workers and counts a lost episode as a failure. Editing code during a run mixes versions, so runs use snapshots.
