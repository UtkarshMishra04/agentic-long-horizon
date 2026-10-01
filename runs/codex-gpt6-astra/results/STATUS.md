# Completed deliverables

All nine public-interface Python controllers, individual entrypoints, evaluation tooling, videos, and the final report are delivered.

- Evaluation: 166/180 successes (92.2%), with 20 distinct requested and actual scene seeds per environment. Six environments scored 20/20; BlueSpot-v1 scored 17/20, PackRack-v2 18/20, and UnderRack-v1 11/20.
- Videos: 45 complete episodes, five preselected random seeds per environment; 41 successes and four explicitly labeled failed attempts. No failed seed was omitted or replaced.
- Combined video: solutions_demo.mp4, 38,177 frames at 20 fps, 45 chapters, 1,908.85 seconds, 10,718,006 bytes.
- Main report: RESULTS.md. Commands: README.md. Raw evaluation: results.jsonl. Video index: videos/INDEX.md. Validation facts: validation.json.

Checks passed: all nine environment IDs and entrypoints; Python compilation; static public-environment-interface audit; 20 distinct actual evaluation scenes per environment; original random video seed selection; source revision compatibility; every action frame retained; all individual and combined video frame counts; 45 chapter markers; full combined-video decode with exit code 0 and no errors.

The outcome is not 100% success. Remaining failures, their seeds, final-state evidence, and attempted improvements are documented in RESULTS.md, failure_analysis.json, and NOTES.md. In particular, the four failed video episodes are full attempts rather than successful solutions. No training, learned models, rollout fitting, GPU, private environment members, or direct simulator control was used.

The final controller SHA-256 is f85bb334e22fa648952ddfb7726ac57f63358e3f587e37a7c69b0a0eb6df3319. Evaluation was staged across an exactly verified under-rack-only change; original hashes remain in all raw records. Development artifacts are retained under development/. No simulation or recording job remains running.
