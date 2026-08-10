# syntax=docker/dockerfile:1

FROM python:3.12-slim

# Pin this to a version once the build works. :latest is convenient, not
# reproducible.
COPY --from=ghcr.io/astral-sh/uv:latest /uv /bin/uv

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PROJECT_ENVIRONMENT=/app/.venv \
    PATH="/app/.venv/bin:$PATH"

WORKDIR /app

# Dependencies get their own layer, so editing a template doesn't reinstall
# Django. Only pyproject.toml / uv.lock changes invalidate this.
COPY pyproject.toml uv.lock ./
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --locked --no-install-project --no-dev

COPY src/ ./src/
COPY docker-entrypoint.sh /usr/local/bin/

# This MUST happen at build time. CompressedManifestStaticFilesStorage raises
# on a missing manifest entry, so running it at boot is already too late -- the
# first request 500s. The key here only exists so settings.py can be imported;
# it never reaches a running container.
RUN SECRET_KEY=build-only-not-a-real-secret \
    python src/manage.py collectstatic --noinput

# Run as a non-root user. /app/data is the mount point for the SQLite volume,
# created here so the volume inherits the right ownership.
RUN useradd --create-home --uid 10001 lucid \
    && mkdir -p /app/data \
    && chmod +x /usr/local/bin/docker-entrypoint.sh \
    && chown -R lucid:lucid /app
USER lucid

EXPOSE 8000

ENTRYPOINT ["docker-entrypoint.sh"]
CMD ["gunicorn", "config.wsgi:application", \
     "--chdir", "src", \
     "--bind", "0.0.0.0:8000", \
     "--workers", "2", \
     "--access-logfile", "-", \
     "--error-logfile", "-"]
