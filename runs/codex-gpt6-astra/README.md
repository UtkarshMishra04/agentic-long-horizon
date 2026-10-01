# Codex (GPT-6-Astra, medium effort)

Codex CLI 0.159.2 with `--dangerously-bypass-approvals-and-sandbox --no-daemon`, in the container from
`docker/`. Given the task as a `/goal` plus three follow-ups during the run (see `prompts/codex_as_given.md`).
Worked 1 h 44 min (2026-09-30, 17:52–19:37 UTC), 266 tool calls.

**Result:** 166/180 episodes (92.2%) on 20 seeds per environment; 6 environments 20/20,
RedBoxToBlueSpot-v1 17/20, PackRack-v2 18/20, RedBoxUnderRack-v1 11/20. 41/45 recorded video episodes succeed.

- `code/`: the final solution. `python solutions/<Env>.py --seed N` runs one episode; `controllers.py` holds the
  shared controller, `tool_control.py` the stick handling; `evaluate.py` runs the evaluation, `record_videos.py`
  the videos.
- `results/`: `RESULTS.md` (Codex's write-up), `results.jsonl` (every evaluation episode), failure analysis,
  `NOTES.md` / `STATUS.md` (its working notes).
- `log.md`: key conversation log — the prompts, Codex's own narration and every command it ran (outputs omitted).

Codex controls from `get_state()` (exact object poses), not from images. A second, unintended Codex process also
wrote to `/workspace` during the first ~1.7 hours; the final evaluation ran after it was stopped.

Run it: inside the container, copy `code/` to a writable folder and run e.g.
`python solutions/RedBoxOnRack-v0.py --seed 1`.
