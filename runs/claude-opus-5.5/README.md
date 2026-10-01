# Claude Code (Opus 5.5, medium effort)

> **Naming.** Environment identifiers in this agent's code and log were updated to the release names (package `longhorizontamp`, ids `LongHorizonTAMP/<Task>`); nothing else was changed.

Claude Code 2.1.285 with `--dangerously-skip-permissions`, in the container from `docker/`. Given the task as one
message (see `prompts/claude_as_given.md`). Worked 9 h 44 min (2026-09-30 20:56 – 2026-10-01 06:40 UTC), 256 tool
calls, 823k output tokens.

**Result:** 540/540 episodes on 60 distinct scenes per environment (seeds 41–60 held out until cycle 10, where it
scored 178/180; the two failures were fixed in cycle 11). 45/45 recorded video episodes succeed.

- `code/`: the final solution. `python solutions/<Env>.py --seed N [--video out.gif]` runs one episode;
  `solutions/common.py` holds the controller library, `tool_common.py` the stick handling,
  `bluespot_common.py` and `packrack_common.py` task-family logic; `evaluate.py`, `make_videos.py`, `summarize.py`.
- `results/`: `RESULTS.md` and `REPORT.md` (Claude's write-ups, including the 11-cycle iteration table),
  `final.json` (every evaluation episode), `scene_seeds.json` (the evaluated seeds), `videos.json`.
- `log.md`: key conversation log — the prompt, Claude's own narration and every command it ran (outputs omitted).

Claude controls from `get_state()` (exact object poses), not from images.
