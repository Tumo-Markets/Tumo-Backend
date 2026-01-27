# ============================================================================
# Sui Transaction Service - Dockerfile (with Bun)
# ============================================================================

FROM oven/bun:1 AS base

WORKDIR /app

# Install dependencies
COPY package.json bun.lockb* ./
RUN bun install --frozen-lockfile

# Copy source
COPY . .

# ============================================================================
# Production
# ============================================================================

FROM oven/bun:1-slim

WORKDIR /app

# Copy node_modules and source from base
COPY --from=base /app/node_modules ./node_modules
COPY --from=base /app/src ./src
COPY --from=base /app/package.json ./

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
  CMD wget --spider -q http://localhost:3001/health || exit 1

# Expose port
EXPOSE 3001

# Run with Bun
CMD ["bun", "run", "src/index.ts"]