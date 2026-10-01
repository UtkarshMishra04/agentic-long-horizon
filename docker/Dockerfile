# Container with the RoboEnvs simulation environments and the Claude Code / Codex CLIs.
#
# RoboEnvs is copied to /opt/RoboEnvs, owned by root and read-only; the container runs as the
# non-root user `agent`, whose only writable locations are /workspace (a host folder) and its home.
#
#   docker build -t roboenvs -f docker/Dockerfile .
#   docker/run.sh                  # interactive shell as `agent` (claude, codex available)
FROM python:3.8-slim-bookworm AS base

ENV DEBIAN_FRONTEND=noninteractive \
    PIP_NO_CACHE_DIR=1 \
    MUJOCO_GL=osmesa \
    PYOPENGL_PLATFORM=osmesa

RUN apt-get update && apt-get install -y --no-install-recommends \
        build-essential linux-libc-dev libosmesa6 libgl1 libglib2.0-0 ffmpeg \
        curl ca-certificates git gnupg \
    && rm -rf /var/lib/apt/lists/*

COPY docker/requirements.txt /tmp/requirements.txt
RUN pip install --upgrade pip \
    && pip install torch==2.2.2 --index-url https://download.pytorch.org/whl/cpu \
    && pip install -r /tmp/requirements.txt

RUN curl -fsSL https://deb.nodesource.com/setup_22.x | bash - \
    && apt-get install -y --no-install-recommends nodejs \
    && rm -rf /var/lib/apt/lists/* \
    && npm install -g @anthropic-ai/claude-code @openai/codex \
    && npm cache clean --force

RUN useradd --create-home --shell /bin/bash agent \
    && mkdir -p /workspace /home/agent/.claude /home/agent/.codex \
    && chown -R agent:agent /workspace /home/agent

FROM base
RUN apt-get update && apt-get install -y --no-install-recommends tmux \
    && rm -rf /var/lib/apt/lists/*
COPY RoboEnvs /opt/RoboEnvs
RUN chown -R root:root /opt/RoboEnvs \
    && find /opt/RoboEnvs -type d -exec chmod 555 {} + \
    && find /opt/RoboEnvs -type f -exec chmod 444 {} +
# In this container both CLIs run without permission prompts (it is the sandbox: non-root, read-only
# RoboEnvs, /workspace the only writable host folder).
RUN printf '%s\n' \
      "alias claude='claude --dangerously-skip-permissions'" \
      "alias codex='codex --dangerously-bypass-approvals-and-sandbox --no-daemon'" \
      >> /home/agent/.bashrc
ENV PYTHONPATH=/opt/RoboEnvs \
    CLAUDE_CONFIG_DIR=/home/agent/.claude \
    CODEX_HOME=/home/agent/.codex
USER agent
WORKDIR /workspace
CMD ["bash"]
