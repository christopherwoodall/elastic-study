# =============================================================================
# Dockerfile — Multi-Agent Coding Sandbox (Ubuntu Edition)
# =============================================================================
#
# AGENTS:
#   claude    Anthropic Claude Code  https://github.com/anthropics/claude-code
#   codex     OpenAI Codex CLI       https://github.com/openai/codex
#   gemini    Google Gemini CLI      https://github.com/google-gemini/gemini-cli
#   opencode  OpenCode (anomalyco)   https://github.com/anomalyco/opencode
#   amp       Sourcegraph Amp        https://ampcode.com/manual
#   aider     Aider-AI               https://github.com/Aider-AI/aider
#   pi        Pi Mono                https://github.com/badlogic/pi-mono
#
# BUILD:
#   docker build -t agent-zoo .
#
# RUN (programmatic — CMD is fully overridden):
#    echo "Waiting for Elasticsearch to be healthy..."
#    until [ "$(docker inspect -f '{{.State.Health.Status}}' elasticsearch)" == "healthy" ]; do
#        sleep 2
#    done
#
#    docker run --rm -it \
#      --user $(id -u):$(id -g) \
#      --hostname opencode-agent-001 \
#      --network agent_sandbox_net \
#      --add-host=host.docker.internal:host-gateway \
#      --env-file .env \
#      -v $(pwd)/workspace:/workspace \
#      -v $(pwd)/opencode.jsonc:/workspace/opencode.jsonc \
#      -v $(pwd)/configs/filebeat.yml:/etc/filebeat/filebeat.yml:ro \
#      agent-zoo \
#      bash -c "service rsyslog start && service filebeat start && opencode run --dir /workspace --model openrouter-audit/moonshotai/kimi-k2.5 'Create a simple game called game.py where the player has to guess a number between 1 and 10. The game should provide feedback on whether the guess is too high, too low, or correct.'"
# =============================================================================

FROM ubuntu:24.04

# -----------------------------------------------------------------------------
# 1. BUILD ENVIRONMENT
# -----------------------------------------------------------------------------
ENV DEBIAN_FRONTEND=noninteractive
ENV TZ=Etc/UTC

# Set npm global prefix to avoid root permission warnings
ENV NPM_CONFIG_PREFIX=/usr/local

# -----------------------------------------------------------------------------
# 2. SYSTEM DEPENDENCIES & RUNTIMES
# -----------------------------------------------------------------------------
# Install baseline fetch utilities
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl wget gnupg ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# Add NodeSource PPA for Node.js 22 LTS (Required for Claude Code on Ubuntu)
RUN mkdir -p /etc/apt/keyrings && \
    curl -fsSL https://deb.nodesource.com/gpgkey/nodesource-repo.gpg.key | gpg --dearmor -o /etc/apt/keyrings/nodesource.gpg && \
    echo "deb [signed-by=/etc/apt/keyrings/nodesource.gpg] https://deb.nodesource.com/node_22.x nodistro main" > /etc/apt/sources.list.d/nodesource.list

# Install runtimes (Node, Python), compiler basics, and debug tools
RUN apt-get update && apt-get install -y --no-install-recommends \
    nodejs \
    python3 \
    python3-pip \
    python3-venv \
    git \
    build-essential \
    ripgrep \
    jq \
    sqlite3 \
    tree \
    procps \
    unzip \
    gdb \
    strace \
    rsyslog \
    && rm -rf /var/lib/apt/lists/*

# -----------------------------------------------------------------------------
# 3. GIT IDENTITY (System-Wide)
# -----------------------------------------------------------------------------
# Using --system writes to /etc/gitconfig. This ensures non-root UIDs mapped
# at runtime still have access to a valid git author configuration.
RUN git config --system user.email "agent@docker.local" \
    && git config --system user.name "Coding Agent" \
    && git config --system init.defaultBranch main

ENV GIT_AUTHOR_NAME="Coding Agent"
ENV GIT_AUTHOR_EMAIL="agent@docker.local"
ENV GIT_COMMITTER_NAME="Coding Agent"
ENV GIT_COMMITTER_EMAIL="agent@docker.local"

# -----------------------------------------------------------------------------
# 4. API KEY & AGENT BEHAVIOR STUBS
# -----------------------------------------------------------------------------
ENV ANTHROPIC_API_KEY=""
ENV OPENAI_API_KEY=""
ENV GOOGLE_API_KEY=""
ENV GEMINI_API_KEY=""
ENV AMP_API_KEY=""
ENV OPENROUTER_API_KEY=""
ENV GROQ_API_KEY=""
ENV DEEPSEEK_API_KEY=""
ENV AIDER_MODEL=""

# CI/CD Stability Flags
ENV DISABLE_AUTOUPDATER=1
ENV CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC=1

# -----------------------------------------------------------------------------
# 5. INSTALL CODING AGENTS (Single Layers & Cache Clearing)
# -----------------------------------------------------------------------------
RUN npm install -g \
    @anthropic-ai/claude-code \
    @openai/codex \
    @google/gemini-cli \
    opencode-ai@latest \
    @sourcegraph/amp \
    @mariozechner/pi-coding-agent \
    && npm cache clean --force

# Python 3.11+ in Ubuntu 24.04 enforces PEP 668.
# --break-system-packages is safe/required here as this is a dedicated container.
RUN pip3 install --break-system-packages aider-chat \
    && rm -rf /root/.cache/pip

# -----------------------------------------------------------------------------
# 6. LOG FORWARDING (Filebeat)
# -----------------------------------------------------------------------------
# Download from https://www.elastic.co/downloads/beats/filebeat
RUN curl -L -O https://artifacts.elastic.co/downloads/beats/filebeat/filebeat-9.4.1-amd64.deb && \
    dpkg -i filebeat-9.4.1-amd64.deb && \
    rm filebeat-9.4.1-amd64.deb

# -----------------------------------------------------------------------------
# 7. HELP DOCUMENTATION
# -----------------------------------------------------------------------------
RUN cat > /etc/agent-help.txt << 'EOF'
=============================================================================
 AGENT ZOO -- Multi-Agent Coding Sandbox (Ubuntu)
=============================================================================
 Available agents and their headless invocation patterns:

 CLAUDE CODE (Anthropic)  |  Requires: ANTHROPIC_API_KEY
   claude -p "prompt" --dangerously-skip-permissions

 CODEX CLI (OpenAI)       |  Requires: OPENAI_API_KEY
   codex exec --full-auto "prompt"

 GEMINI CLI (Google)      |  Requires: GOOGLE_API_KEY
   gemini -p "prompt"

 OPENCODE (anomalyco)     |  Requires: any supported provider key
   opencode -p "prompt" -q

 AMP (Sourcegraph)        |  Requires: AMP_API_KEY OR ANTHROPIC_API_KEY + --isolated
   amp -x "prompt" --dangerously-allow-all [--isolated]

 AIDER (Aider-AI)         |  Requires: model-specific key (ANTHROPIC/OPENAI/etc.)
   aider --message "prompt" --yes-always --model sonnet
   aider --message "prompt" --yes-always --model gpt-4o

 EXAMPLE (programmatic, overrides CMD entirely):
   docker run --rm -v $(pwd):/workspace -e ANTHROPIC_API_KEY="..." \
     agent-zoo claude -p "Write tests for all public functions" \
     --dangerously-skip-permissions
=============================================================================
EOF

# -----------------------------------------------------------------------------
# 8. WORKSPACE & DEFAULT COMMAND
# -----------------------------------------------------------------------------
WORKDIR /workspace

# Patch skill directories
RUN mkdir -p .agents/skills .claude/skills && \
    ln -s .agents/skills/ .claude/skills/

CMD ["/bin/bash", "-c", "cat /etc/agent-help.txt && exec /bin/bash"]