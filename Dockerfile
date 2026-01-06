# Dockerfile for Ping.pub Block Explorer - Aura Blockchain
# Multi-stage build for optimized production image

FROM node:20-alpine AS builder

# Install build dependencies
RUN apk add --no-cache git python3 make g++

WORKDIR /app

# Copy explorer source
COPY ping-pub-explorer/package.json ping-pub-explorer/yarn.lock ./
RUN yarn install --frozen-lockfile --ignore-engines --network-timeout 100000

# Copy all source files
COPY ping-pub-explorer/ ./

# Build production bundle
RUN yarn build

# Production stage
FROM nginx:alpine

# Copy custom nginx config
COPY nginx.conf /etc/nginx/conf.d/default.conf

# Copy built files from builder
COPY --from=builder /app/dist /usr/share/nginx/html

# Add health check
HEALTHCHECK --interval=30s --timeout=3s --start-period=5s --retries=3 \
  CMD wget --no-verbose --tries=1 --spider http://localhost/ || exit 1

EXPOSE 80

CMD ["nginx", "-g", "daemon off;"]
