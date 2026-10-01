# Development notes

All control is deterministic task planning and pose feedback. No training, model fitting, neural networks, simulator access, or private environment members are used. Geometry constants come from the documented environment source. Public `get_state` contains all object poses and arm/gripper state. The nine scripts under `solutions/` share `controllers.py`.

Initial observations and changes:
- Distant boxes cannot reliably be reached by a vertical gripper. An approximately 49-degree inward wrist tilt extends reach. The closing axis must remain perpendicular to the radial direction: the other orientation lifts one finger and pushes the box away.
- Advancing Cartesian waypoints from the previous target, rather than only 2.5 cm ahead of the measured pose, improves convergence speed.
- A grasped distant box is brought inward before lifting farther, then leveled for placement.
- Blue-spot goals allow a 15 cm position tolerance. A geometric search finds a nearby empty landing point, often leaving both the blue box and stick untouched. If none is available, blue is moved to an empty patch first.
- Under-rack tasks need a low angled push: moving a vertical closed gripper underneath catches the roof and tips the box.
- An empty camera tuple renders both default cameras in this implementation; one 8-pixel camera is faster for evaluation. Mesa and BLAS thread counts are limited to one per worker. Rendering is CPU-only.

Evaluation uses default environment episode limits and reward/termination returned by `step`. Reset can skip invalid scene seeds; both requested and actual seeds are saved. Final evaluation seeds are spaced by 1000 to improve scene diversity.

Further findings:
- Closing the gripper across the radial direction during an angled grasp can sweep a far box off the table. The tool hook is now used earlier, above 0.84 m radial distance.
- Stick hooking needs clearance before descent: the short bar starts 8 cm beyond the box center, then follows object-pose feedback at table height. This retrieved the previously unreachable seed-1700 scene upright.
- Returning the stick to its old position can hit the retrieved box. Tool parking now searches collision-free poses from current object footprints.
- Direct under-rack pushing tipped boxes; carrying with a pitched gripper also collided with the rack. Grasping/moving the rack was tried and rejected after unstable grasps. The successful strategy uses the short bar of the L-stick to push a staged upright box, with the tool elevated slightly to keep the robot fingers clear of the table.
- Moving to a central high pose before manipulation fixed a near-box grasp failure caused by the initial arm configuration.
- Evaluation and video batches are kept to roughly eight simultaneous processes; a diagnostic batch was interrupted by a worker process termination when more workers overlapped. Partial diagnostic files are not final evaluation results.

The tool controller is an analytic rigid-body servo: it compares a requested tool pose with `get_state()`, applies a bounded Cartesian correction, and compensates the gripper-to-tool lever arm while rotating. All geometry and controller gains are hand-written; there is no parameter estimation, rollout fitting, or learning. A later under-rack test showed that grasping the long bar 5 cm past its center (toward the short bar) keeps the wrist away from the robot's near-base reach limit. This fixed the two failing diagnostic scenes (requested seeds 700 and 1400).

Under-rack hook-path trials exposed an additional geometric issue: a radial hook can sweep through the rack footprint, whereas always pulling along x regressed other scenes. The next controller revision explicitly checks candidate hook headings and lateral offsets against the rack footprint along the low pulling path, and rejects gripper targets outside its usable reach. This is deterministic geometric collision checking, not rollout fitting. The geometry-controlled diagnostic succeeded on UnderRack-v1 requested seed0 after the fixed-x strategy failed there.

A high central recovery immediately before under-rack tool grasp did not fix the stalled seed-3000 push: the wrist remained in an unfavorable configuration after the angled retrieval. The next geometric candidate ranking prefers axis-aligned tool headings when collision-free, minimizing the rotation needed for the eventual insertion. The original fixed-axis trial solved this scene, but must be collision-checked to avoid regressions elsewhere.

The independent video sample exposed PackRack-v0 seed 71097 despite 20/20 on the evaluation grid. A replay showed a near-extended-arm grasp followed by a stalled return/placement. A diagnostic lowered the angled-grasp threshold from 0.77 m to 0.72 m for packing tasks; retrieval improved but yellow was placed back on the table and the default horizon expired. That change was not retained. The full failed video is included, not replaced with a successful seed.

A longer 0.35 m under-rack hook pull with the earlier angular ranking was tested on seeds 3000 and 0. Seed 0 succeeded, but seed 3000 still ran out of time with too little footprint overlap; the tool lost effective contact during the pull and the push stalled. The current geometric policy remains unchanged. The 40-episode under-rack evaluation process ended with 38 completed records; only the two missing seeds 17000 and 19000 were resumed, preserving every completed success/failure.
