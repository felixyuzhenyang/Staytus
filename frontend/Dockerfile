# Build from the repository root: docker build -f frontend/Dockerfile .
FROM node:22-bookworm-slim AS dependencies
WORKDIR /app
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci

FROM dependencies AS builder
ENV NEXT_TELEMETRY_DISABLED=1
COPY frontend/ ./
RUN mkdir -p public && npm run build

FROM node:22-bookworm-slim AS runtime
ENV NODE_ENV=production NEXT_TELEMETRY_DISABLED=1 PORT=3000 HOSTNAME=0.0.0.0
WORKDIR /app
RUN groupadd --gid 10001 staytus && useradd --uid 10001 --gid staytus --create-home staytus
COPY --from=builder --chown=staytus:staytus /app/.next/standalone ./
COPY --from=builder --chown=staytus:staytus /app/.next/static ./.next/static
COPY --from=builder --chown=staytus:staytus /app/public ./public
USER staytus
EXPOSE 3000
CMD ["node", "server.js"]
