# syntax=docker/dockerfile:1.7
#
# Multi-stage image for the Python services (api, orchestrator, runner, migrate).
# Build with:  docker build -f infra/docker/python-service.Dockerfile --build-arg SERVICE=api .
#
# Behind a TLS-intercepting corporate proxy, pass the CA bundle as a BuildKit secret:
#   docker build --secret id=extra_ca,src=/path/to/ca.pem ...
# The secret is only mounted during dependency resolution and never stored in a layer.

ARG PYTHON_IMAGE=python:3.12-slim-bookworm@sha256:392307d22300de8b5986851a12d9176dfc0fc073e65bf6523ebd7dcbeb23564e
ARG UV_IMAGE=ghcr.io/astral-sh/uv:python3.12-bookworm-slim@sha256:e5b65587bce7de595f299855d7385fe7fca39b8a74baa261ba1b7147afa78e58

# ---------------------------------------------------------------- build
FROM ${UV_IMAGE} AS build
ARG SERVICE=api
# Workspace package installed for the service (the migrate job ships the platform package).
ARG PACKAGE=reslab-${SERVICE}
ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=never \
    UV_PROJECT_ENVIRONMENT=/app/.venv
WORKDIR /app

# Dependency layer: workspace manifests only, so it is cached across source changes.
COPY pyproject.toml uv.lock ./
COPY packages/core/pyproject.toml packages/core/README.md packages/core/
COPY packages/platform/pyproject.toml packages/platform/
COPY packages/cli/pyproject.toml packages/cli/
COPY adapters/mock/pyproject.toml adapters/mock/
COPY adapters/px4-gazebo/pyproject.toml adapters/px4-gazebo/
COPY adapters/replay/pyproject.toml adapters/replay/
COPY services/api/pyproject.toml services/api/
COPY services/orchestrator/pyproject.toml services/orchestrator/
COPY services/runner/pyproject.toml services/runner/
RUN --mount=type=cache,target=/root/.cache/uv \
    --mount=type=secret,id=extra_ca \
    sh -c 'if [ -f /run/secrets/extra_ca ]; then export SSL_CERT_FILE=/run/secrets/extra_ca; fi; \
           uv sync --frozen --no-dev --no-install-workspace --package ${PACKAGE}'

# Source layer.
COPY packages ./packages
COPY adapters ./adapters
COPY services ./services
RUN --mount=type=cache,target=/root/.cache/uv \
    --mount=type=secret,id=extra_ca \
    sh -c 'if [ -f /run/secrets/extra_ca ]; then export SSL_CERT_FILE=/run/secrets/extra_ca; fi; \
           uv sync --frozen --no-dev --no-editable --package ${PACKAGE}'

# ---------------------------------------------------------------- runtime
FROM ${PYTHON_IMAGE} AS runtime
ARG SERVICE=api
ARG VERSION=0.1.0
ARG GIT_COMMIT=unknown
LABEL org.opencontainers.image.title="resilient-uas-lab-${SERVICE}" \
      org.opencontainers.image.description="Resilient UAS Lab ${SERVICE} service" \
      org.opencontainers.image.version="${VERSION}" \
      org.opencontainers.image.revision="${GIT_COMMIT}" \
      org.opencontainers.image.licenses="Apache-2.0"
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PATH="/app/.venv/bin:${PATH}" \
    RESLAB_SERVICE=${SERVICE} \
    RESLAB_IMAGE_VERSION=${VERSION} \
    RESLAB_GIT_COMMIT=${GIT_COMMIT}
RUN groupadd --system --gid 10001 reslab \
    && useradd --system --uid 10001 --gid reslab --home-dir /app --shell /usr/sbin/nologin reslab \
    && mkdir -p /app && chown reslab:reslab /app
WORKDIR /app
COPY --from=build --chown=reslab:reslab /app/.venv /app/.venv
COPY --chown=reslab:reslab scenarios /app/scenarios
COPY --chown=reslab:reslab infra/docker/entrypoint.sh /app/entrypoint.sh
COPY --chown=reslab:reslab infra/docker/healthcheck.py /app/healthcheck.py
RUN chmod 0555 /app/entrypoint.sh
HEALTHCHECK --interval=15s --timeout=5s --start-period=30s --retries=4 \
    CMD ["python", "/app/healthcheck.py"]
USER reslab:reslab
ENTRYPOINT ["/app/entrypoint.sh"]
