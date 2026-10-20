FROM node:22-bookworm

RUN apt-get update && apt-get install -y git curl jq python3 python3-pip && rm -rf /var/lib/apt/lists/*

# GitHub CLI
RUN curl -fsSL https://cli.github.com/packages/githubcli-archive-keyring.gpg \
    | dd of=/usr/share/keyrings/githubcli-archive-keyring.gpg \
  && chmod go+r /usr/share/keyrings/githubcli-archive-keyring.gpg \
  && echo "deb [arch=$(dpkg --print-architecture) signed-by=/usr/share/keyrings/githubcli-archive-keyring.gpg] https://cli.github.com/packages stable main" \
    > /etc/apt/sources.list.d/github-cli.list \
  && apt-get update && apt-get install -y gh && rm -rf /var/lib/apt/lists/*

# Security tools available to the security reviewer
RUN pip3 install --break-system-packages --no-cache-dir semgrep==1.* \
  && curl -fsSL https://github.com/gitleaks/gitleaks/releases/latest/download/gitleaks_$(uname -s | tr A-Z a-z)_$(uname -m | sed 's/x86_64/x64/;s/aarch64/arm64/').tar.gz \
    | tar -xz -C /usr/local/bin gitleaks || true

# ---- add your project's toolchain here (e.g. python, go, playwright) ----

ARG AGENT_UID=1000
ARG AGENT_GID=1000
RUN groupmod -o -g $AGENT_GID node && usermod -o -u $AGENT_UID -g $AGENT_GID -d /home/agent -m -l agent node
USER ${AGENT_UID}:${AGENT_GID}

RUN curl -fsSL https://claude.ai/install.sh | bash
ENV PATH="/home/agent/.local/bin:$PATH"
WORKDIR /home/agent
ENTRYPOINT ["sleep", "infinity"]
