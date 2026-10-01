# LongHorizonTAMP × coding agents

Can a coding agent write robot controllers from scratch? This repository holds **LongHorizonTAMP**, a benchmark of nine
long-horizon task and motion planning (TAMP) problems for a Franka Panda arm, and two complete runs of coding agents
solving it:

| agent | model | effort | time | evaluation | success |
|---|---|---|---|---|---|
| Claude Code 2.1.285 | Opus 5.5 | medium | 9 h 44 min | 60 scenes × 9 tasks | **540/540** |
| Codex CLI 0.159.2 | GPT-6-Astra | medium | 1 h 44 min | 20 seeds × 9 tasks | **166/180** (92.2%) |

Both agents worked in the same sandbox, with the same task: write Python code that solves all nine environments,
with no training, learned models or GPU, using only the environments' public interface.

**→ Open [`docs/index.html`](docs/index.html)** in a browser: the benchmark, the prompt, results, a side-by-side
video explorer with a synchronized top-down map and auto-detected events, every evaluation run each agent made (what
it observed, what it changed, the code diff and the success rate before and after), and both agents' solutions. The
page is static (no server, no build step); GitHub Pages can serve it from `/docs`.

## Repository layout

```
LongHorizonTAMP/      the benchmark: 9 long-horizon TAMP tasks for a Franka Panda in robosuite/MuJoCo (pip-installable)
docker/        the sandbox both agents ran in: read-only LongHorizonTAMP, Claude Code + Codex, tmux
prompts/       PROMPT.md (the task as one prompt) and the prompts as each agent actually received them
runs/          per agent: final code, evaluation results, its own write-ups, key conversation log
docs/          the website (index.html, app.js, data/, media/)
tools/         scripts that built runs/ and docs/data/ from the raw runs
```

## Try the environments

```bash
pip install -e LongHorizonTAMP        # Python 3.8+, mujoco 2.3.7, robosuite 1.4.1
export MUJOCO_GL=egl           # or osmesa on a machine without a GPU
python - <<'EOF'
import longhorizontamp
env = longhorizontamp.make("LongHorizonTAMP/RedBoxOnRack-v0")
obs, info = env.reset(seed=1)
print(env.get_goal()["text"])
for _ in range(100):
    obs, reward, terminated, truncated, info = env.step(env.action_space.sample())
env.close()
EOF
```

`LongHorizonTAMP/README.md` documents the nine tasks, the interface (`reset`, `get_state`, `get_goal`, `step`), the
action and observation spaces, the state layout and the goal format.

Run an agent's solution, e.g. Claude's:

```bash
cd runs/claude-opus-5.5/code && python solutions/RedBoxUnderRack-v1.py --seed 1
```

## Run your own agent in the same sandbox

```bash
docker build -t longhorizontamp -f docker/Dockerfile .   # Python 3.8, MuJoCo, robosuite, CPU rendering, Node, claude, codex, tmux
docker/run.sh                                     # persistent container, attach to tmux; log in to claude/codex once
docker/run.sh claude                              # tmux session running Claude Code without permission prompts
docker/run.sh codex                               # tmux session running Codex without approvals
```

Inside the container LongHorizonTAMP is at `/opt/LongHorizonTAMP` (root-owned, read-only), the agent runs as the non-root user
`agent`, and `/workspace` (a host folder, default `~/longhorizontamp_workspace`) is the only writable place. Give the agent
[`prompts/PROMPT.md`](prompts/PROMPT.md). Logins persist in Docker volumes; tmux sessions survive closing the
terminal (`docker/run.sh --stop` removes the container).
