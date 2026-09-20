# syntax=docker/dockerfile:1.7
#
# Mission Control web application (Next.js, standalone output).
# Build with:  docker build -f infra/docker/web.Dockerfile .
#
# Behind a TLS-intercepting corporate proxy, pass the CA bundle as a BuildKit secret:
#   docker build --secret id=extra_ca,src=/path/to/ca.pem ...

ARG NODE_IMAGE=node:22-bookworm-slim@sha256:48e4b67d85f87bd551df43704e24d252f56cc5f8e9718841aace50f19948f0f9

# ---------------------------------------------------------------- deps
FROM ${NODE_IMAGE} AS deps
ENV PNPM_HOME=/pnpm \
    PATH=/pnpm:$PATH \
    COREPACK_ENABLE_DOWNLOAD_PROMPT=0 \
    NEXT_TELEMETRY_DISABLED=1
WORKDIR /repo
RUN --mount=type=secret,id=extra_ca \
    sh -c 'if [ -f /run/secrets/extra_ca ]; then export NODE_EXTRA_CA_CERTS=/run/secrets/extra_ca; fi; \
           corepack enable && corepack prepare pnpm@10.28.0 --activate'
COPY package.json pnpm-lock.yaml pnpm-workspace.yaml .npmrc ./
COPY apps/web/package.json apps/web/
COPY packages/client/package.json packages/client/
RUN --mount=type=cache,id=pnpm-store,target=/pnpm/store \
    --mount=type=secret,id=extra_ca \
    sh -c 'if [ -f /run/secrets/extra_ca ]; then export NODE_EXTRA_CA_CERTS=/run/secrets/extra_ca; fi; \
           pnpm install --frozen-lockfile --filter @reslab/web... --filter @reslab/api-client...'

# ---------------------------------------------------------------- build
FROM deps AS build
ARG VERSION=0.1.0
ARG GIT_COMMIT=unknown
ENV NEXT_PUBLIC_APP_VERSION=${VERSION} \
    NEXT_PUBLIC_GIT_COMMIT=${GIT_COMMIT}
COPY packages/client ./packages/client
COPY apps/web ./apps/web
RUN pnpm --filter @reslab/web build

# ---------------------------------------------------------------- runtime
FROM ${NODE_IMAGE} AS runtime
ARG VERSION=0.1.0
ARG GIT_COMMIT=unknown
LABEL org.opencontainers.image.title="resilient-uas-lab-web" \
      org.opencontainers.image.description="Resilient UAS Lab Mission Control web application" \
      org.opencontainers.image.version="${VERSION}" \
      org.opencontainers.image.revision="${GIT_COMMIT}" \
      org.opencontainers.image.licenses="Apache-2.0"
ENV NODE_ENV=production \
    NEXT_TELEMETRY_DISABLED=1 \
    PORT=3000 \
    HOSTNAME=0.0.0.0
# The standalone server needs only the node binary: remove the bundled package
# managers so their dependency trees are not part of the attack surface.
RUN groupadd --system --gid 10001 reslab \
    && useradd --system --uid 10001 --gid reslab --home-dir /app --shell /usr/sbin/nologin reslab \
    && rm -rf /usr/local/lib/node_modules /usr/local/bin/npm /usr/local/bin/npx /usr/local/bin/corepack \
    && rm -rf /opt/yarn-* /usr/local/bin/yarn /usr/local/bin/yarnpkg
WORKDIR /app
COPY --from=build --chown=reslab:reslab /repo/apps/web/.next/standalone ./
COPY --from=build --chown=reslab:reslab /repo/apps/web/.next/static ./apps/web/.next/static
COPY --from=build --chown=reslab:reslab /repo/apps/web/public ./apps/web/public
USER reslab:reslab
EXPOSE 3000
HEALTHCHECK --interval=15s --timeout=5s --start-period=20s --retries=4 \
    CMD ["node", "-e", "fetch('http://127.0.0.1:3000/').then(r=>process.exit(r.ok?0:1)).catch(()=>process.exit(1))"]
CMD ["node", "apps/web/server.js"]
