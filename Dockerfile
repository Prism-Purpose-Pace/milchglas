# Option B image (spec section 9, D-9): one image, two Compose services (`web`, `refresher`).
# Both bases are pinned by tag and digest; Dependabot proposes new digests and holds the
# 3.12 minor (.github/dependabot.yml). No pip: uv installs only what uv.lock pins.

FROM docker.io/astral/uv:0.12.24@sha256:3af4716e991d6956a41e573eab705d0ee08500cd829ed30293eb8472f372c65a AS uv

FROM docker.io/library/python:3.12-slim@sha256:b18b261e1b4974b4f321451ad5251ded85abb22c2b8b262da527dda1d031ab30 AS build
COPY --from=uv /uv /usr/local/bin/uv
ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=never \
    UV_PROJECT_ENVIRONMENT=/app/.venv
WORKDIR /src
# Runtime dependencies first, so a source change does not rebuild them.
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project
COPY README.md LICENSE ./
COPY src ./src
RUN uv sync --frozen --no-dev --no-editable

FROM docker.io/library/python:3.12-slim@sha256:b18b261e1b4974b4f321451ad5251ded85abb22c2b8b262da527dda1d031ab30
# A fixed non-root user; the state directory exists and belongs to it, because a non-root
# process can write an empty named volume only when the image already owns the mount point.
RUN groupadd --system --gid 10001 milchglas \
    && useradd --system --uid 10001 --gid 10001 --no-create-home --home-dir /nonexistent \
        --shell /usr/sbin/nologin milchglas \
    && mkdir -p /var/lib/milchglas /etc/milchglas \
    && chown 10001:10001 /var/lib/milchglas \
    && chmod 0700 /var/lib/milchglas
COPY --from=build /app/.venv /app/.venv
# PYTHONTZPATH empty: the tzdata package pinned in uv.lock decides every DST rule, not the
# base image's zone database (FR-6, GATE-7).
ENV PATH=/app/.venv/bin:$PATH \
    PYTHONTZPATH= \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    MILCHGLAS_VAR_DIR=/var/lib/milchglas \
    MILCHGLAS_CONFIG=/etc/milchglas/config.json
USER 10001:10001
WORKDIR /nonexistent
EXPOSE 8000
# Liveness only: 200 or 503 from /healthz passes, silence fails (WEB-17, D-7d).
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD ["python", "-m", "milchglas.web.liveness"]
# `web`. The refresher's command is set in compose.yaml. The config module only filters
# gunicorn's error log, which would otherwise quote request lines (WEB-21, NFR-S5).
CMD ["gunicorn", "--config", "python:milchglas.web.gunicorn_conf", \
     "--bind", "0.0.0.0:8000", "--workers", "2", "--timeout", "30", \
     "--no-control-socket", "--worker-tmp-dir", "/tmp", "milchglas.web.wsgi:create()"]
