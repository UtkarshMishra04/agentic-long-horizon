#!/bin/bash
# Persistent roboenvs container: it keeps running in the background, so tmux sessions inside it survive
# closing the terminal. Every call attaches to (or creates) the tmux session "main".
#   docker/run.sh              # attach to tmux session "main" (detach: Ctrl-b d)
#   docker/run.sh claude       # attach to tmux session "claude" running Claude Code
#   docker/run.sh codex        # attach to tmux session "codex" running Codex
#   docker/run.sh <command>    # run a command in the container instead
#   docker/run.sh --stop       # stop and remove the container (tmux sessions end)
# Both CLIs run without permission prompts (--dangerously-skip-permissions /
# --dangerously-bypass-approvals-and-sandbox; Codex also --no-daemon): the container is the sandbox.
# WORKSPACE (default ~/roboenvs_workspace) is mounted read-write at /workspace. Claude Code and Codex
# logins persist in the named volumes roboenvs-claude and roboenvs-codex.
NAME=roboenvs
WORKSPACE="${WORKSPACE:-$HOME/roboenvs_workspace}"

if [ "$1" = "--stop" ]; then
  docker rm -f "$NAME" >/dev/null && echo "stopped $NAME"
  exit 0
fi

if [ -z "$(docker ps -q -f name="^${NAME}$")" ]; then
  docker rm -f "$NAME" >/dev/null 2>&1  # a stopped container with the same name
  mkdir -p "$WORKSPACE"
  docker run -d --name "$NAME" --init \
    -v "$WORKSPACE":/workspace \
    -v roboenvs-claude:/home/agent/.claude \
    -v roboenvs-codex:/home/agent/.codex \
    roboenvs sleep infinity >/dev/null
fi

if [ $# -eq 0 ]; then
  exec docker exec -it "$NAME" tmux new-session -A -s main
fi
case "$1" in
  claude) exec docker exec -it "$NAME" tmux new-session -A -s claude "claude --dangerously-skip-permissions; bash" ;;
  codex) exec docker exec -it "$NAME" tmux new-session -A -s codex "codex --dangerously-bypass-approvals-and-sandbox --no-daemon; bash" ;;
esac
exec docker exec -it "$NAME" "$@"
