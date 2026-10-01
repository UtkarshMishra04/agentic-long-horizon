# LongHorizonTAMP controller results

All nine solutions are hand-written Python state-feedback controllers. They use only public reset/state/goal/step data for control, with no training, learned models, rollout fitting, GPU, simulator access, or private environment members. NumPy, SciPy rotation utilities, and Shapely geometry are used for deterministic calculations.

## Evaluation

The authoritative run uses requested seeds **0, 1000, …, 19000**, the environment’s default episode limits, and CPU-only rendering. A success is the environment returning `terminated=True`; the controller does not substitute its own goal test. Requested and actual scene seeds are retained because reset can skip invalid scenes. Diagnostic batches are excluded.

| Environment | Successes | Rate | Distinct actual scenes | Default step limit |
|---|---:|---:|---:|---:|
| LiftRedBox-v0 | 20/20 | 100.0% | 20 | 1500 |
| RedBoxOnRack-v0 | 20/20 | 100.0% | 20 | 1800 |
| RedBoxUnderRack-v0 | 20/20 | 100.0% | 20 | 1300 |
| RedBoxUnderRack-v1 | 11/20 | 55.0% | 20 | 2500 |
| RedBoxToBlueSpot-v0 | 20/20 | 100.0% | 20 | 1000 |
| RedBoxToBlueSpot-v1 | 17/20 | 85.0% | 20 | 2400 |
| PackRack-v0 | 20/20 | 100.0% | 20 | 1000 |
| PackRack-v1 | 20/20 | 100.0% | 20 | 1600 |
| PackRack-v2 | 18/20 | 90.0% | 20 | 2000 |

**Overall:** 166/180 successful episodes (92.2%).

Raw results: [results.jsonl](results.jsonl); aggregate rates: [results.jsonl.summary.json](results.jsonl.summary.json).

Final controller SHA-256: `f85bb334e22fa648952ddfb7726ac57f63358e3f587e37a7c69b0a0eb6df3319`.
Validation was staged: the final correction adds collision-checked hook headings and lateral offsets only for under-rack tasks. Both under-rack variants were re-evaluated after the correction; other completed episodes exercise unchanged code paths. `revision_compat.py` verifies the exact source difference, and every raw record retains its actual source hash. The evaluator can also run the complete final version from scratch.
Tool-servo SHA-256: `0e0eec396df612a047941397b7a39b5ef92b89e40599fe65bd25db9a58c30bcb`.

## How the controllers work

The shared controller decodes the documented flat state layout, sends absolute end-effector targets at 20 Hz, and advances bounded Cartesian waypoints. Box symmetries help choose a reachable wrist yaw. Before each box grasp and placement, the arm moves upward and inward while preserving its measured orientation, reducing wrist-limit stalls. The held object’s measured offset and a final position-feedback phase guide placement. Tool manipulation uses bounded rigid-body pose errors and lever-arm compensation. All success decisions remain with the environment.

| Environment | Strategy |
|---|---|
| LiftRedBox-v0 | Grasp the red box. Use an angled wrist for distant direct grasps; beyond 0.84 m radial distance, first hook the box inward with the L-stick, park the stick, then grasp. |
| RedBoxOnRack-v0 | Retrieve the red box with the same direct/tool strategy, move through a high central pose, level it, and lower it to the rack center. |
| RedBoxUnderRack-v0 | Place the box in front of the rack, grasp the L-stick near its short bar, then use pose feedback to push the upright box through the opening. |
| RedBoxUnderRack-v1 | Retrieve the initially distant red box when needed. Search hook headings and lateral offsets for rack clearance and gripper reach, preserving a clear radial pull and otherwise preferring an axis-aligned heading; then use the same staging and tool-pushing strategy as v0. |
| RedBoxToBlueSpot-v0 | Search the goal’s 15 cm position-tolerance region for a landing point clear of blue and the stick. Usually only red moves, preserving the stick’s initial position; relocate blue to a clear in-workspace patch if necessary. |
| RedBoxToBlueSpot-v1 | Retrieve distant red when needed, park the stick clear of the boxes, and use the same collision-clear landing-point search. Blue can be relocated if there is no suitable point. |
| PackRack-v0 | Keep the initially elevated cyan box, then place yellow and red in rack-frame corner slots selected to maximize separation from occupied slots. |
| PackRack-v1 | Pick and place blue, yellow, and cyan into separated rack-frame slots, checking object height between attempts. |
| PackRack-v2 | Use the same four-slot packing strategy for blue, yellow, red, and cyan. |

## Failures and attempted improvements

The following are failed requested seeds and evidence from their final public states. Full per-episode details are in [failure_analysis.json](failure_analysis.json).

| Environment | Failed requested seeds | Final-state evidence |
|---|---|---|
| RedBoxUnderRack-v1 | 0, 5000, 7000, 8000, 9000, 10000, 12000, 13000, 17000 | rack fell off the table; red_box rack overlap 0.0% is below 50.0%; rack is overturned or tilted; lstick fell off the table; red_box rack overlap 6.1% is below 50.0%; red_box is tipped; red_box is not at the required support height |
| RedBoxToBlueSpot-v1 | 7000, 17000, 19000 | blue_box is outside the required workspace; blue_box is tipped; red_box position error 0.409 m exceeds 0.150 m; red_box is tipped; red_box is too close to lstick; lstick is tipped; lstick is too close to red_box; lstick is outside the required workspace; blue_box is too close to lstick; lstick is too close to blue_box |
| PackRack-v2 | 12000, 13000 | cyan_box fell off the table; cyan_box is tipped; cyan_box is not at the required support height; cyan_box is outside the rack footprint; red_box is not at the required support height; red_box is outside the rack footprint |

Development trials included straight-down distant grasps, angled grasps, direct pushes under the rack, angled insertion while holding the box, and grasping/moving the rack. Direct insertion often tipped boxes or collided with the roof; rack grasps were unstable. The final design uses the stick for insertion and long-distance retrieval. A grasp closer to the stick’s short bar fixed near-base reach stalls during pushing. Preserving the stick heading when parking avoided large wrist rotations. Moving through a high central pose with the measured wrist orientation fixed tested grasp/placement stalls where a fixed upright home pose did not. For under-rack retrieval, radial pulls sometimes struck the roof; always pulling along x regressed other scenes. The final planner checks sampled tool footprints along candidate pulls and preserves a clear radial pull and otherwise prefers a clear axis-aligned heading. A central recovery before the push did not cure one diagnostic wrist stall and was not retained. A longer tool pull helped one trial but still missed insertion on another and was not retained. Lowering the angled-grasp threshold for the failed packing video seed 71097 improved retrieval but still missed placement and the time limit, so it was not retained either. These are hand-written geometric/control changes, not fitted models.

Remaining general limitations are contact-induced tipping, tool slippage, constrained arm reach, and collisions during crowded placements. The under-rack planner checks sampled tool footprints in two dimensions; it does not guarantee collision-free motion of the entire arm or gripper, and tool contact can be lost during a pull. Objects knocked off the table cannot generally be recovered through the bounded Cartesian action interface. The controller retries task phases within the default horizon; there is no mid-episode reset, teleport, or extension of the time limit. See [NOTES.md](NOTES.md) for the development record.

## Rendered videos

[Watch the combined 45-episode video](solutions_demo.mp4), with one seekable chapter per episode. Individual clips and the complete seed/outcome index are in [videos/INDEX.md](videos/INDEX.md).

Five seeds per task were selected without success screening using `numpy.random.RandomState(20260930)` over `[0, 1000000)`. They are independent of the evaluation grid. Every control step is rendered at 20 fps, followed by a 1.5-second final-frame hold. Clips use a 384-pixel display with a label banner; later recordings render at 256 pixels and scale to that display size to reduce CPU rendering time. Failed attempts, if any, are included and labeled rather than omitted.

| Environment | Successful recorded runs |
|---|---:|
| LiftRedBox-v0 | 5/5 |
| RedBoxOnRack-v0 | 5/5 |
| RedBoxUnderRack-v0 | 5/5 |
| RedBoxUnderRack-v1 | 2/5 |
| RedBoxToBlueSpot-v0 | 5/5 |
| RedBoxToBlueSpot-v1 | 5/5 |
| PackRack-v0 | 4/5 |
| PackRack-v1 | 5/5 |
| PackRack-v2 | 5/5 |

**Video outcomes:** 41/45 successful runs. The remaining clips show complete failed attempts, not successful solutions.

Failed video seeds: RedBoxUnderRack-v1: 904620, 859916, 417674; PackRack-v0: 71097.

## Run the solutions

From `/workspace`:

```bash
PYTHONPATH=/opt/LongHorizonTAMP /usr/local/bin/python solutions/LiftRedBox-v0.py --seed 0
PYTHONPATH=/opt/LongHorizonTAMP /usr/local/bin/python solutions/RedBoxOnRack-v0.py --seed 0
PYTHONPATH=/opt/LongHorizonTAMP /usr/local/bin/python solutions/RedBoxUnderRack-v0.py --seed 0
PYTHONPATH=/opt/LongHorizonTAMP /usr/local/bin/python solutions/RedBoxUnderRack-v1.py --seed 1000
PYTHONPATH=/opt/LongHorizonTAMP /usr/local/bin/python solutions/RedBoxToBlueSpot-v0.py --seed 0
PYTHONPATH=/opt/LongHorizonTAMP /usr/local/bin/python solutions/RedBoxToBlueSpot-v1.py --seed 0
PYTHONPATH=/opt/LongHorizonTAMP /usr/local/bin/python solutions/PackRack-v0.py --seed 0
PYTHONPATH=/opt/LongHorizonTAMP /usr/local/bin/python solutions/PackRack-v1.py --seed 0
PYTHONPATH=/opt/LongHorizonTAMP /usr/local/bin/python solutions/PackRack-v2.py --seed 0
```

Reproduce evaluation and videos:

```bash
PYTHONPATH=/opt/LongHorizonTAMP /usr/local/bin/python evaluate.py --workers 6 --output /workspace/results.jsonl
PYTHONPATH=/opt/LongHorizonTAMP /usr/local/bin/python record_videos.py --workers 2
PYTHONPATH=/opt/LongHorizonTAMP /usr/local/bin/python assemble_videos.py
```

Validation: Python compilation; static audit of environment attribute access; full episode evaluation; and ffprobe checks of all 45 video resolutions/frame counts plus the combined frame total and 45 chapter markers; and a full decode of the combined video with no errors. Environment source under `/opt/LongHorizonTAMP` was read, not modified.
