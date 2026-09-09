# A pinned environment for reproducing the table, for anyone who does not want to
# take the manifest's word for what produced it.
#
#   docker build -t injection-eval .
#   docker run --rm -v "$PWD/results:/app/results" injection-eval
#
# The default command regenerates every number and fails if any of them moved.
FROM python:3.12-slim-bookworm

# git is needed because the manifest records the harness commit sha, and a build
# without it silently reports "unknown" for the one field that ties a result to
# the code that made it.
RUN apt-get update \
 && apt-get install -y --no-install-recommends git ca-certificates \
 && rm -rf /var/lib/apt/lists/*

COPY --from=ghcr.io/astral-sh/uv:0.5.14 /uv /usr/local/bin/uv

WORKDIR /app

# Dependency layer first so that editing source does not re-resolve the world.
COPY pyproject.toml ./
COPY scripts/setup_worktree.py scripts/
RUN uv venv --python 3.12 .venv

COPY . .
RUN uv pip install --python .venv/bin/python -e ".[dev]"

# Model weights land here. Mount it to reuse them across runs:
#   -v "$HOME/.cache/huggingface:/root/.cache/huggingface"
ENV HF_HOME=/root/.cache/huggingface

CMD [".venv/bin/python", "scripts/check_determinism.py", "--regenerate", "--twice"]
