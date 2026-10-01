"""Build RESULTS.md only after complete evaluation and video manifests exist."""
import collections
import hashlib
import json
from pathlib import Path
from controllers import ORDERS
from analyze_results import reasons
from revision_compat import compatible

root=Path(__file__).resolve().parent
records=[json.loads(line) for line in (root/'results.jsonl').read_text().splitlines()]
clips=[json.loads(line) for line in (root/'videos/results.jsonl').read_text().splitlines()]
digest=hashlib.sha256((root/'controllers.py').read_bytes()).hexdigest()
helper_digest=hashlib.sha256((root/'tool_control.py').read_bytes()).hexdigest()
assert len(records)>=180 and len(clips)==45
assert all(compatible(r['env'],r['controller_sha256']) and r['tool_control_sha256']==helper_digest for r in records)
assert all(compatible(r['env'],r['controller_sha256']) for r in clips)
assert (root/'solutions_demo.mp4').is_file()
methods={
 'LiftRedBox-v0':'Grasp the red box. Use an angled wrist for distant direct grasps; beyond 0.84 m radial distance, first hook the box inward with the L-stick, park the stick, then grasp.',
 'RedBoxOnRack-v0':'Retrieve the red box with the same direct/tool strategy, move through a high central pose, level it, and lower it to the rack center.',
 'RedBoxUnderRack-v0':'Place the box in front of the rack, grasp the L-stick near its short bar, then use pose feedback to push the upright box through the opening.',
 'RedBoxUnderRack-v1':'Retrieve the initially distant red box when needed. Search hook headings and lateral offsets for rack clearance and gripper reach, preserving a clear radial pull and otherwise preferring an axis-aligned heading; then use the same staging and tool-pushing strategy as v0.',
 'RedBoxToBlueSpot-v0':'Search the goal’s 15 cm position-tolerance region for a landing point clear of blue and the stick. Usually only red moves, preserving the stick’s initial position; relocate blue to a clear in-workspace patch if necessary.',
 'RedBoxToBlueSpot-v1':'Retrieve distant red when needed, park the stick clear of the boxes, and use the same collision-clear landing-point search. Blue can be relocated if there is no suitable point.',
 'PackRack-v0':'Keep the initially elevated cyan box, then place yellow and red in rack-frame corner slots selected to maximize separation from occupied slots.',
 'PackRack-v1':'Pick and place blue, yellow, and cyan into separated rack-frame slots, checking object height between attempts.',
 'PackRack-v2':'Use the same four-slot packing strategy for blue, yellow, red, and cyan.'}
limits=[1500,1800,1300,2500,1000,2400,1000,1600,2000]
lines=['# LongHorizonTAMP controller results','',
       'All nine solutions are hand-written Python state-feedback controllers. They use only public reset/state/goal/step data for control, with no training, learned models, rollout fitting, GPU, simulator access, or private environment members. NumPy, SciPy rotation utilities, and Shapely geometry are used for deterministic calculations.','',
       '## Evaluation','',
       'The authoritative run uses requested seeds **0, 1000, …, 19000**, the environment’s default episode limits, and CPU-only rendering. A success is the environment returning `terminated=True`; the controller does not substitute its own goal test. Requested and actual scene seeds are retained because reset can skip invalid scenes. Diagnostic batches are excluded.','',
       '| Environment | Successes | Rate | Distinct actual scenes | Default step limit |','|---|---:|---:|---:|---:|']
for name,limit in zip(ORDERS,limits):
    group=[r for r in records if r['env']=='LongHorizonTAMP/'+name]
    assert len(group)>=20 and len({r['seed'] for r in group})>=20
    assert len({r['scene_seed'] for r in group})>=20
    successes=sum(r['success'] for r in group)
    lines.append('| %s | %d/%d | %.1f%% | %d | %d |'%(name,successes,len(group),100*successes/len(group),len({r['scene_seed'] for r in group}),limit))
lines+=['', '**Overall:** %d/%d successful episodes (%.1f%%).'%(sum(r['success'] for r in records),len(records),100*sum(r['success'] for r in records)/len(records)),
        '', 'Raw results: [results.jsonl](results.jsonl); aggregate rates: [results.jsonl.summary.json](results.jsonl.summary.json).',
        '', 'Final controller SHA-256: `%s`.'%digest, 'Validation was staged: the final correction adds collision-checked hook headings and lateral offsets only for under-rack tasks. Both under-rack variants were re-evaluated after the correction; other completed episodes exercise unchanged code paths. `revision_compat.py` verifies the exact source difference, and every raw record retains its actual source hash. The evaluator can also run the complete final version from scratch.', 'Tool-servo SHA-256: `%s`.'%helper_digest,'',
        '## How the controllers work','',
        'The shared controller decodes the documented flat state layout, sends absolute end-effector targets at 20 Hz, and advances bounded Cartesian waypoints. Box symmetries help choose a reachable wrist yaw. Before each box grasp and placement, the arm moves upward and inward while preserving its measured orientation, reducing wrist-limit stalls. The held object’s measured offset and a final position-feedback phase guide placement. Tool manipulation uses bounded rigid-body pose errors and lever-arm compensation. All success decisions remain with the environment.','',
        '| Environment | Strategy |','|---|---|']
for name in ORDERS:lines.append('| %s | %s |'%(name,methods[name]))
lines+=['','## Failures and attempted improvements','']
failures=[r for r in records if not r['success']]
if not failures:lines+=['No failures occurred in the 180-episode evaluation. This is measured seed coverage, not a proof of success on every possible scene.']
else:
    lines+=['The following are failed requested seeds and evidence from their final public states. Full per-episode details are in [failure_analysis.json](failure_analysis.json).', '', '| Environment | Failed requested seeds | Final-state evidence |','|---|---|---|']
    for name in ORDERS:
        group=[r for r in failures if r['env']=='LongHorizonTAMP/'+name]
        if group:
            evidence=list(dict.fromkeys(message for r in group for message in reasons(r)))
            lines.append('| %s | %s | %s |'%(name,', '.join(str(r['seed']) for r in group),'; '.join(evidence)))
lines+=['',
 'Development trials included straight-down distant grasps, angled grasps, direct pushes under the rack, angled insertion while holding the box, and grasping/moving the rack. Direct insertion often tipped boxes or collided with the roof; rack grasps were unstable. The final design uses the stick for insertion and long-distance retrieval. A grasp closer to the stick’s short bar fixed near-base reach stalls during pushing. Preserving the stick heading when parking avoided large wrist rotations. Moving through a high central pose with the measured wrist orientation fixed tested grasp/placement stalls where a fixed upright home pose did not. For under-rack retrieval, radial pulls sometimes struck the roof; always pulling along x regressed other scenes. The final planner checks sampled tool footprints along candidate pulls and preserves a clear radial pull and otherwise prefers a clear axis-aligned heading. A central recovery before the push did not cure one diagnostic wrist stall and was not retained. A longer tool pull helped one trial but still missed insertion on another and was not retained. Lowering the angled-grasp threshold for the failed packing video seed 71097 improved retrieval but still missed placement and the time limit, so it was not retained either. These are hand-written geometric/control changes, not fitted models.',
 '', 'Remaining general limitations are contact-induced tipping, tool slippage, constrained arm reach, and collisions during crowded placements. The under-rack planner checks sampled tool footprints in two dimensions; it does not guarantee collision-free motion of the entire arm or gripper, and tool contact can be lost during a pull. Objects knocked off the table cannot generally be recovered through the bounded Cartesian action interface. The controller retries task phases within the default horizon; there is no mid-episode reset, teleport, or extension of the time limit. See [NOTES.md](NOTES.md) for the development record.',
 '', '## Rendered videos','',
 '[Watch the combined 45-episode video](solutions_demo.mp4), with one seekable chapter per episode. Individual clips and the complete seed/outcome index are in [videos/INDEX.md](videos/INDEX.md).',
 '', 'Five seeds per task were selected without success screening using `numpy.random.RandomState(20260930)` over `[0, 1000000)`. They are independent of the evaluation grid. Every control step is rendered at 20 fps, followed by a 1.5-second final-frame hold. Clips use a 384-pixel display with a label banner; later recordings render at 256 pixels and scale to that display size to reduce CPU rendering time. Failed attempts, if any, are included and labeled rather than omitted.',
 '', '| Environment | Successful recorded runs |','|---|---:|']
for name in ORDERS:
    group=[r for r in clips if r['env']==name]
    assert len(group)==5 and len({r['seed'] for r in group})==5
    lines.append('| %s | %d/5 |'%(name,sum(r['success'] for r in group)))
lines+=['', '**Video outcomes:** %d/45 successful runs. The remaining clips show complete failed attempts, not successful solutions.'%sum(r['success'] for r in clips)]
video_failures=[r for r in clips if not r['success']]
if video_failures:
    lines+=['', 'Failed video seeds: '+ '; '.join('%s: %s'%(name,', '.join(str(r['seed']) for r in video_failures if r['env']==name)) for name in ORDERS if any(r['env']==name for r in video_failures))+'.']
lines+=['','## Run the solutions','', 'From `/workspace`:', '', '```bash']
for name in ORDERS:lines.append('PYTHONPATH=/opt/LongHorizonTAMP /usr/local/bin/python solutions/%s.py --seed %d'%(name,1000 if name=='RedBoxUnderRack-v1' else 0))
lines+=['```','', 'Reproduce evaluation and videos:', '', '```bash',
 'PYTHONPATH=/opt/LongHorizonTAMP /usr/local/bin/python evaluate.py --workers 6 --output /workspace/results.jsonl',
 'PYTHONPATH=/opt/LongHorizonTAMP /usr/local/bin/python record_videos.py --workers 2',
 'PYTHONPATH=/opt/LongHorizonTAMP /usr/local/bin/python assemble_videos.py',
 '```','', 'Validation: Python compilation; static audit of environment attribute access; full episode evaluation; and ffprobe checks of all 45 video resolutions/frame counts plus the combined frame total and 45 chapter markers; and a full decode of the combined video with no errors. Environment source under `/opt/LongHorizonTAMP` was read, not modified.']
(root/'RESULTS.md').write_text('\n'.join(lines)+'\n')
print(root/'RESULTS.md')
