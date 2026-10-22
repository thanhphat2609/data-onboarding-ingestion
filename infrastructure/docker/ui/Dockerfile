# Web UI: static build served by nginx. Build context is the repository root (see /.dockerignore).

FROM node:24.19.0-alpine AS build
WORKDIR /repo/code/ui
COPY code/ui/package.json code/ui/package-lock.json ./
RUN npm ci --no-audit --no-fund
COPY code/ui/ ./
# The UI reads source and sink templates from the repository at build time.
COPY code/templates/ /repo/code/templates/
RUN npm run build

FROM nginx:1.30.6-alpine
COPY infrastructure/docker/ui/nginx.conf /etc/nginx/conf.d/default.conf
COPY --chmod=755 infrastructure/docker/ui/40-app-config.sh /docker-entrypoint.d/40-app-config.sh
COPY --from=build /repo/code/ui/dist /usr/share/nginx/html
EXPOSE 80
