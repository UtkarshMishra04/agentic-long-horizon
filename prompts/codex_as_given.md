# Codex: prompts as given (a /goal, then three follow-ups typed during the run). Times UTC.

[17:52 UTC]
/goal Write controllers that solve the 9 robot manipulation environments in /opt/LongHorizonTAMP (read-only; read /opt/LongHorizonTAMP/README.md first, source in /opt/LongHorizonTAMP/longhorizontamp). Python: /usr/local/bin/python (3.8), longhorizontamp importable via PYTHONPATH=/opt/LongHorizonTAMP, headless rendering with MUJOCO_GL=osmesa already set; 10 CPU cores, no GPU. Environments are listed in longhorizontamp.ENV_IDS; each has reset(seed), get_state(), get_goal(), step(action), render(), close(), and reward 1.0 when the goal is reached. Do not use any approach that requires training or a GPU: no learning from data, no neural networks, no reinforcement learning, no fitting models to rollouts. Controllers may only use the public interface (reset, get_state, get_goal, step, action_space, observation_space); you may read the source to understand the environments but must not call private members (names starting with _) or the simulator directly. Put all code, notes and results in /workspace. Deliverables: a controller for every environment runnable with one command each; an evaluation script running each controller on at least 20 seeds per environment and reporting success rates; /workspace/RESULTS.md with per-environment success rates, how each controller works, and remaining failure cases. Aim for every environment solved on every seed; if not, explain why and what you tried. Work autonomously until done.

[17:57 UTC]
Clarification of the goal: the deliverable is Python code that solves the tasks. For each of the 9 environments, write a Python solution (e.g. /workspace/solutions/<env_name>.py) that creates the environment, and given only what reset/get_state/get_goal return, computes and sends the actions with step() until the goal is reached. Everything must be plain Python code you write (numpy is fine); no training, no learned models, no GPU. Keep the evaluation script and RESULTS.md as described.

[17:59 UTC]
final deliverable also included a rendered video file showing the full solution for 5 random seeds for each task

[19:36 UTC]
summarize your findings with how many iterations did it take you, what did you disciover and how did you improve on it as a compact report
