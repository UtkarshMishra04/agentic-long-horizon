# Claude Code: prompt as given (one message). Time UTC.

[20:56 UTC]
Write Python code that solves the 9 robot manipulation environments in /opt/RoboEnvs.

Environments
- Code and documentation: /opt/RoboEnvs (read-only). Read /opt/RoboEnvs/README.md first; the package source is in /opt/RoboEnvs/roboenvs.
- Python: /usr/local/bin/python (3.8), with roboenvs importable (PYTHONPATH=/opt/RoboEnvs). Rendering is headless with MUJOCO_GL=osmesa (already set). 10 CPU cores, no GPU.
- The environments are listed in roboenvs.ENV_IDS. Each has reset(seed), get_state(), get_goal(), step(action), render() and close(). The reward is 1.0 when the goal is reached.

Rules
- No approach that requires training or a GPU: no learning from data, no neural networks, no reinforcement learning, no fitting models to rollouts. Plain Python code you write (numpy is fine).
- Your solutions may interact with an environment only through its public interface: reset, get_state, get_goal, step, render, and the action_space / observation_space attributes. You may read the source to understand the environments, but do not call private members (names starting with _) or the simulator directly.
- Work only in /workspace/claude/; create it and put all code, videos, notes and results there. Do not read /home/agent/.codex/ or anything outside /opt/RoboEnvs and /workspace/claude/ that relates to other agents.

Deliverables
1. Code: for each environment, a Python solution /workspace/claude/solutions/<env_name>.py that creates the environment and, from what reset/get_state/get_goal return, computes the actions and sends them with step() until the goal is reached. Each must run with one command.
2. Evaluation: a script that runs every solution on at least 20 seeds per environment and reports the success rate (episodes that end with terminated=True before the time limit).
3. Videos: for every environment, rendered videos of 5 random seeds (45 in total), from env.render() frames, saved as /workspace/claude/videos/<env_name>_seed<seed>.gif (or .mp4). Each video covers the whole episode and shows whether it succeeded (in the file name or an overlay).
4. /workspace/claude/RESULTS.md: per-environment success rates, how each solution works, the seeds used for the videos, and the remaining failure cases. Aim for every environment to be solved on every seed; if some are not, explain why and what you tried.
5. /workspace/claude/REPORT.md: a compact report of how you got there: how many iterations it took (count each revise-and-re-evaluate cycle, overall and per environment); what you discovered about the environments along the way (what made each task hard, what failed and why); how each discovery changed your solution, with the success rate before and after. Keep it to about one page: a short iteration table (iteration, what changed, success rates) followed by bullet points.

Work autonomously until all deliverables are complete.
