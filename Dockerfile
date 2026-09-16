FROM python:3.12-slim
COPY --from=ghcr.io/astral-sh/uv:0.12.15 /uv /usr/local/bin/uv
WORKDIR /app
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-install-project --extra yahoo
COPY axiom ./axiom
COPY alembic ./alembic
COPY alembic.ini ./
COPY scripts ./scripts
RUN uv sync --frozen --extra yahoo && useradd --uid 10001 --create-home axiom && mkdir -p data reports && chown -R axiom:axiom /app
USER axiom
ENV PATH="/app/.venv/bin:$PATH"
EXPOSE 8820
CMD ["uvicorn","axiom.api:create_app","--factory","--host","0.0.0.0","--port","8820"]
