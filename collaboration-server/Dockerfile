# Copyright (c) 2026 Trustedwear Tech Private Limited (https://citra-ai.com)
# Author: Rohit Kumar Chandan
# SPDX-License-Identifier: Apache-2.0
#
# Licensed under the Apache License, Version 2.0 (the "License"); you may not
# use this file except in compliance with the License. You may obtain a copy of
# the License at http://www.apache.org/licenses/LICENSE-2.0

# Dockerfile for Collaboration Service
FROM node:20-alpine

# Build-time argument to mark environment (prod/test)
ARG APP_ENV=prod

ENV NODE_ENV=production \
    PORT=1234 \
    TZ=America/New_York \
    APP_ENV=${APP_ENV}

WORKDIR /app

# Install dumb-init for proper signal handling
RUN apk add --no-cache dumb-init curl moreutils

# Copy package files first for better caching
COPY package*.json ./

# Install dependencies. --only=production was removed in newer npm
# (this build errored on it, printing npm's usage/help text instead of
# installing) — --omit=dev is the current equivalent.
RUN npm ci --omit=dev

# Copy application files
COPY . .

# Create directories for LevelDB persistence and logs
RUN mkdir -p /app/y-leveldb-storage /app/logs && \
    chown -R node:node /app

# Switch to non-root user
USER node

# Expose WebSocket port
EXPOSE 1234

# Health check
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD curl -f http://127.0.0.1:1234/health || exit 1

# Use dumb-init to handle signals properly
ENTRYPOINT ["/usr/bin/dumb-init", "--"]

# Start the collaboration service
CMD ["node", "server.js"]
