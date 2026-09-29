# Base images are pinned by digest; .github/dependabot.yml proposes updates.
FROM python:3.14-slim@sha256:51dafde81dbdb6ebde285137a295cf18a47ca95234fe388a343719cb97305b3d
COPY --from=ghcr.io/astral-sh/uv:0.12.15@sha256:62f8c047d0a0e9ece6b53fc63df902585a67a47a7f318ddec4a37db586edc8e3 /uv /usr/local/bin/uv
WORKDIR /app
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-install-project --extra yahoo
COPY axiom ./axiom
COPY alembic ./alembic
COPY alembic.ini ./
COPY scripts ./scripts
RUN uv sync --frozen --extra yahoo && useradd --uid 10001 --create-home axiom && mkdir -p data reports && chown -R axiom:axiom /app
USER axiom
# The slim image has no git, so experiment provenance reads the commit from here.
ARG GIT_COMMIT=unavailable
ENV PATH="/app/.venv/bin:$PATH" GIT_COMMIT=$GIT_COMMIT
EXPOSE 8820
# 0.0.0.0 here is required so the dashboard container can reach this one over
# the Compose bridge network (apps/dashboard's AXIOM_API_URL=http://api:8820
# is not loopback traffic). The real security boundary is the HOST port
# mapping in compose.yaml ("127.0.0.1:8820:8820"), not this bind address.
CMD ["uvicorn","axiom.api:create_app","--factory","--host","0.0.0.0","--port","8820"]
