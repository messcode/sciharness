# Supply a reviewed, pinned CLI version at build time; no implicit latest.
FROM node:22-bookworm-slim
ARG CODEX_VERSION
RUN test -n "$CODEX_VERSION" \
    && apt-get update \
    && apt-get install -y --no-install-recommends git python3 ca-certificates \
    && rm -rf /var/lib/apt/lists/* \
    && npm install --global "@openai/codex@${CODEX_VERSION}" \
    && npm cache clean --force
COPY src/sciharness_loop/codex_runner.py /opt/sciharness/codex_runner.py
ENTRYPOINT ["codex"]
