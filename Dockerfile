FROM ghcr.io/astral-sh/uv:0.11.4 AS uv
FROM python:3.11.15-slim
COPY --from=uv /uv /bin/uv
WORKDIR /suite
ENV UV_PYTHON_DOWNLOADS=never UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy
COPY pyproject.toml uv.lock ./
RUN uv sync --locked --no-dev
COPY app app
COPY data/docs data/docs
RUN useradd --no-create-home --uid 10001 suite
USER 10001
EXPOSE 8000
CMD ["/suite/.venv/bin/python", "-m", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--no-access-log"]
