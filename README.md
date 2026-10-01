# RoboEnvs × coding agents

Can a coding agent write robot controllers from scratch? This repository holds a small manipulation benchmark,
**RoboEnvs**, and two complete runs of coding agents solving it:

| agent | model | effort | time | evaluation | success |
|---|---|---|---|---|---|
| Claude Code 2.1.285 | Opus 5.5 | medium | 9 h 44 min | 60 scenes × 9 tasks | **540/540** |
| Codex CLI 0.159.2 | GPT-6-Astra | medium | 1 h 44 min | 20 seeds × 9 tasks | **166/180** (92.2%) |

Both agents worked in the same sandbox, with the same task: write Python code that solves all nine environments,
with no training, learned models or GPU, using only the environments' public interface.

**→ Open [`docs/index.html`](docs/index.html)** in a browser for the full story: the benchmark, the exact prompt,
results, every evaluation run each agent made (what it observed, what it changed, the code diff and the success
rate before and after), the conversation logs, all the code, and an interactive explorer for 90 recorded episodes
with a synchronized top-down map, height and gripper charts and auto-detected events. The page is static (no
server, no build step); GitHub Pages can serve it from `/docs`.

## Repository layout

```
RoboEnvs/      the benchmark: 9 tabletop tasks for a Franka Panda in robosuite/MuJoCo (pip-installable)
docker/        the sandbox both agents ran in: read-only RoboEnvs, Claude Code + Codex, tmux
prompts/       PROMPT.md (the task as one prompt) and the prompts as each agent actually received them
runs/          per agent: final code, evaluation results, its own write-ups, key conversation log
docs/          the website (index.html, app.js, data/, media/)
tools/         scripts that built runs/ and docs/data/ from the raw runs
```

## Try the environments

```bash
pip install -e RoboEnvs        # Python 3.8+, mujoco 2.3.7, robosuite 1.4.1
export MUJOCO_GL=egl           # or osmesa on a machine without a GPU
python - <<'EOF'
import roboenvs
env = roboenvs.make("roboenvs/RedBoxOnRack-v0")
obs, info = env.reset(seed=1)
print(env.get_goal()["text"])
for _ in range(100):
    obs, reward, terminated, truncated, info = env.step(env.action_space.sample())
env.close()
EOF
```

`RoboEnvs/README.md` documents the nine tasks, the interface (`reset`, `get_state`, `get_goal`, `step`), the
action and observation spaces, the state layout and the goal format.

Run an agent's solution, e.g. Claude's:

```bash
cd runs/claude-opus-5.5/code && python solutions/RedBoxUnderRack-v1.py --seed 1
```

## Run your own agent in the same sandbox

```bash
docker build -t roboenvs -f docker/Dockerfile .   # Python 3.8, MuJoCo, robosuite, CPU rendering, Node, claude, codex, tmux
docker/run.sh                                     # persistent container, attach to tmux; log in to claude/codex once
docker/run.sh claude                              # tmux session running Claude Code without permission prompts
docker/run.sh codex                               # tmux session running Codex without approvals
```

Inside the container RoboEnvs is at `/opt/RoboEnvs` (root-owned, read-only), the agent runs as the non-root user
`agent`, and `/workspace` (a host folder, default `~/roboenvs_workspace`) is the only writable place. Give the agent
[`prompts/PROMPT.md`](prompts/PROMPT.md). Logins persist in Docker volumes; tmux sessions survive closing the
terminal (`docker/run.sh --stop` removes the container).

## Caveats

- **Privileged state.** Both agents control from `get_state()` — the simulator's exact object poses — not from
  camera images.
- **Different evaluation sizes.** Codex evaluated 20 seeds per task, Claude 60 distinct scenes (20 of them held out
  until its tenth cycle).
- **Seeds.** `reset(seed)` skips seeds whose scene is invalid, and within one environment instance which seeds are
  skipped can depend on earlier episodes. A fresh environment always maps a seed to the same scene.
- **Self-reported tables, independently replayed videos.** Success tables come from the agents' own evaluation
  files. The 90 video episodes were re-run with state logging for the website and reproduced the recordings step
  for step.
- **A process mistake** during the Codex run: a second, unintended Codex process also wrote to `/workspace` for
  its first ~1.7 hours before it was stopped. The final evaluation ran after it stopped.
- The raw transcripts (with tool outputs and model reasoning) are not included; `runs/*/log.md` has the prompts,
  the agents' narration and the commands they ran.
