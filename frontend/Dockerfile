# syntax=docker/dockerfile:1
# Frontend production image: build with Vite, serve the static files with nginx.
# The build context is the repo root (see infra/docker-compose.yml), so the
# root .dockerignore applies.

# --- Build Stage ---
# The bundle is plain static files, so this stage runs on the build machine's own
# platform even when the image targets another: the release workflow builds the
# arm64 image on an amd64 runner without emulating Node.
FROM --platform=$BUILDPLATFORM node:22-alpine AS build

# Mirror the repo layout (/app/frontend next to /app/data) so the '@data'
# alias in vite.config.ts resolves to the shared airport dataset.
WORKDIR /app/frontend

COPY frontend/package.json frontend/package-lock.json ./

# The cache mount keeps npm's download cache between builds without baking it
# into a layer, so a lockfile change re-installs from local tarballs.
RUN --mount=type=cache,target=/root/.npm \
    npm ci --no-audit --no-fund

COPY frontend/ .
COPY data/ /app/data/

# CI runs `npm run build` (tsc -b, then vite build) on every push; the image only needs the bundle.
# There is no .env.production: API and WebSocket URLs are same-origin, so one image works anywhere.
RUN npx vite build

# --- Serve Stage ---
# The config needs NGINX_ENTRYPOINT_LOCAL_RESOLVERS, which the nginx image has had since 1.25.3.
# The stable tag guarantees it, even where an old nginx:alpine is cached.
FROM nginx:stable-alpine

# The server config: static files, plus /api/, /healthz and /readyz proxied to BACKEND_URL
# (scheme://host:port, no path), so self-hosters need no nginx of their own.
# NGINX_ENTRYPOINT_LOCAL_RESOLVERS makes the image's entrypoint export the container's
# nameservers, which the config resolves the backend with.
ENV BACKEND_URL=http://backend:8000 \
    NGINX_ENTRYPOINT_LOCAL_RESOLVERS=1
COPY frontend/nginx/default.conf.template /etc/nginx/templates/default.conf.template
COPY --chmod=755 frontend/nginx/25-drop-ipv6-listen.sh /docker-entrypoint.d/25-drop-ipv6-listen.sh

COPY --from=build /app/frontend/dist /usr/share/nginx/html

EXPOSE 80

CMD ["nginx", "-g", "daemon off;"]
