FROM python:3.12-slim AS builder
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv
WORKDIR /app
COPY pyproject.toml uv.lock ./
RUN uv venv /app/.venv && \
    uv pip install --python /app/.venv/bin/python -e . --no-cache-dir
COPY feed_reader/ ./feed_reader/

FROM python:3.12-slim AS runtime
RUN groupadd --gid 1000 appuser && \
    useradd --uid 1000 --gid 1000 --create-home appuser
WORKDIR /app
COPY --from=builder /app/.venv /app/.venv
COPY --from=builder /app/feed_reader /app/feed_reader
COPY --from=builder /app/pyproject.toml /app/pyproject.toml
RUN mkdir -p /home/appuser/.feed_reader \
             /home/appuser/.config/feed_reader \
             /home/appuser/.local/share/feed_reader && \
    chown -R appuser:appuser /home/appuser /app
USER appuser
ENV PATH="/app/.venv/bin:$PATH" PYTHONPATH="/app" HOME="/home/appuser"
ENV LOG_LEVEL="INFO" PORT="3001"
EXPOSE 3001
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD python -c "import socket; s = socket.socket(); s.settimeout(5); s.connect(('127.0.0.1', 3001)); s.close()"
CMD ["python", "-m", "feed_reader", "--transport", "streamable-http", "--host", "0.0.0.0", "--port", "3001"]
