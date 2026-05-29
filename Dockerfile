# Container image for deploying this project (e.g. to Railway).
#
# Uses the official uv image (Python 3.12 + uv). Dependencies install in their own
# layer so rebuilds are fast. Secrets are NOT baked in — set them as environment
# variables on your host (Railway dashboard); .env is gitignored AND dockerignored.

FROM ghcr.io/astral-sh/uv:python3.12-bookworm-slim

WORKDIR /app

# 1) Install dependencies first (cached unless pyproject.toml / uv.lock change).
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project

# 2) Copy the source and install the project itself.
COPY . .
RUN uv sync --frozen --no-dev

# Run everything from the project's virtualenv.
ENV PATH="/app/.venv/bin:$PATH"

# `fastapi run` serves on 0.0.0.0 and reads the PORT env var (Railway injects it;
# defaults to 8000 locally). We don't hardcode --port so the same image works anywhere.
EXPOSE 8000

# Default: serve the project's own web app. To deploy a different entrypoint (e.g.
# an example, a Telegram bot, or a CLI worker), override the start command on your host
# (see railway.toml for how this demo points at examples/agent_idea_web/app.py).
CMD ["fastapi", "run", "src/agent/web.py"]
