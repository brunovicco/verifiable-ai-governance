FROM node:22-alpine AS dependencies
WORKDIR /workspace
COPY package.json package-lock.json ./
COPY apps/web/package.json apps/web/package.json
RUN npm ci

FROM node:22-alpine AS builder
WORKDIR /workspace
ARG NEXT_PUBLIC_API_URL=http://localhost:8000
ARG NEXT_PUBLIC_AUTH_MODE=local
ARG NEXT_PUBLIC_ENTRA_CLIENT_ID=
ARG NEXT_PUBLIC_ENTRA_TENANT_ID=
ARG NEXT_PUBLIC_ENTRA_API_SCOPE=
ARG NEXT_PUBLIC_DEMO_READ_ONLY=false
ARG NEXT_PUBLIC_DEPLOYMENT_LABEL=Ambiente local
ARG NEXT_PUBLIC_GIT_SHA=
ENV NEXT_PUBLIC_API_URL=$NEXT_PUBLIC_API_URL \
    NEXT_PUBLIC_AUTH_MODE=$NEXT_PUBLIC_AUTH_MODE \
    NEXT_PUBLIC_ENTRA_CLIENT_ID=$NEXT_PUBLIC_ENTRA_CLIENT_ID \
    NEXT_PUBLIC_ENTRA_TENANT_ID=$NEXT_PUBLIC_ENTRA_TENANT_ID \
    NEXT_PUBLIC_ENTRA_API_SCOPE=$NEXT_PUBLIC_ENTRA_API_SCOPE \
    NEXT_PUBLIC_DEMO_READ_ONLY=$NEXT_PUBLIC_DEMO_READ_ONLY \
    NEXT_PUBLIC_DEPLOYMENT_LABEL=$NEXT_PUBLIC_DEPLOYMENT_LABEL \
    NEXT_PUBLIC_GIT_SHA=$NEXT_PUBLIC_GIT_SHA
COPY --from=dependencies /workspace/node_modules ./node_modules
COPY --from=dependencies /workspace/apps/web/node_modules ./apps/web/node_modules
COPY package.json ./
COPY packages/document-templates ./packages/document-templates
COPY apps/web ./apps/web
RUN npm run build:web

FROM node:22-alpine AS runner
WORKDIR /app
ENV NODE_ENV=production \
    PORT=3000 \
    HOSTNAME=0.0.0.0
# The standalone server only needs the `node` binary; npm/npx/yarn/corepack are
# never invoked here, so drop them rather than carry their bundled dependencies
# (e.g. tar, sigstore) as unused, unpatched attack surface in the runtime image.
RUN rm -rf /usr/local/lib/node_modules/npm /usr/local/bin/npm /usr/local/bin/npx \
    /usr/local/lib/node_modules/corepack /usr/local/bin/corepack /opt/yarn-v*
COPY --from=builder --chown=node:node /workspace/apps/web/.next/standalone ./
COPY --from=builder --chown=node:node /workspace/apps/web/.next/static ./apps/web/.next/static
COPY --from=builder --chown=node:node /workspace/packages/document-templates ./packages/document-templates
USER node
EXPOSE 3000
CMD ["node", "apps/web/server.js"]
