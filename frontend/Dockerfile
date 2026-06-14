# ---------------------------------------------------------------------------
# Stage 1 — deps: install node_modules so the runner stage has them cached
# ---------------------------------------------------------------------------
FROM node:20-alpine AS deps

WORKDIR /app

COPY package.json package-lock.json ./
RUN npm ci

# ---------------------------------------------------------------------------
# Stage 2 — runner: lightweight image that can run both dev and production
# ---------------------------------------------------------------------------
FROM node:20-alpine AS runner

WORKDIR /app

# Non-root user
RUN addgroup -S appgroup && adduser -S appuser -G appgroup

# Config files needed by Next.js at startup
COPY --chown=appuser:appgroup package.json package-lock.json ./
COPY --chown=appuser:appgroup next.config.ts tsconfig.json postcss.config.mjs ./
COPY --chown=appuser:appgroup components.json ./

# node_modules from the deps stage
COPY --from=deps --chown=appuser:appgroup /app/node_modules ./node_modules

# Application source (shadowed by volume mount in dev; used in production)
COPY --chown=appuser:appgroup public/ ./public/
COPY --chown=appuser:appgroup src/ ./src/

# Give the non-root user ownership of the entire workdir so Next.js can write
# next-env.d.ts, .next/, etc.  Do this last so it covers all COPY layers.
RUN chown -R appuser:appgroup /app

USER appuser
EXPOSE 3000

HEALTHCHECK --interval=10s --timeout=5s --start-period=60s --retries=5 \
    CMD wget -qO- http://localhost:3000 > /dev/null 2>&1 || exit 1

# Default: dev server with hot-reload. Override CMD for production:
#   CMD ["npm", "run", "start"]
CMD ["npm", "run", "dev"]
