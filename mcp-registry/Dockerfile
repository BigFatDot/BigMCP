# MCPHub Gateway - Dockerfile
FROM python:3.11-slim

# Set working directory
WORKDIR /app

# Install system dependencies including Node.js for MCP servers
RUN apt-get update && apt-get install -y \
    gcc \
    g++ \
    curl \
    git \
    ca-certificates \
    gnupg \
    && mkdir -p /etc/apt/keyrings \
    && curl -fsSL https://deb.nodesource.com/gpgkey/nodesource-repo.gpg.key | gpg --dearmor -o /etc/apt/keyrings/nodesource.gpg \
    && echo "deb [signed-by=/etc/apt/keyrings/nodesource.gpg] https://deb.nodesource.com/node_20.x nodistro main" | tee /etc/apt/sources.list.d/nodesource.list \
    && apt-get update \
    && apt-get install -y nodejs \
    && rm -rf /var/lib/apt/lists/*

# Install gosu for privilege dropping in entrypoint
# (fixes bind-mount ownership issues when conf/ files come from Windows)
RUN set -eux; \
    GOSU_VERSION=1.17; \
    ARCH=$(dpkg --print-architecture); \
    curl -fsSL "https://github.com/tianon/gosu/releases/download/${GOSU_VERSION}/gosu-${ARCH}" -o /usr/local/bin/gosu; \
    chmod +x /usr/local/bin/gosu; \
    gosu nobody true

# Install uv (Python package manager) for uvx support (MCP servers using uvx)
RUN curl -LsSf https://astral.sh/uv/install.sh | sh \
    && cp /root/.local/bin/uv /usr/local/bin/uv \
    && cp /root/.local/bin/uvx /usr/local/bin/uvx \
    && chmod +x /usr/local/bin/uv /usr/local/bin/uvx

# Pre-install MCP npm packages and apply Zod v4 compatibility patches.
# Runs as root at build time → installs to /usr/lib/node_modules/ (root-only).
# npx at runtime finds these global installs and uses them without re-downloading.
# Patches fix two Zod v4 breaking changes in @modelcontextprotocol/server-gitlab:
#   1. zodToJsonSchema (zod-to-json-schema v3) returns empty schema with Zod v4
#      → replaced with z.toJSONSchema() (built-in Zod v4 method)
#   2. ZodError.errors was renamed to ZodError.issues in Zod v4
#      → error.errors.map → (error.issues || []).map
RUN npm install -g @modelcontextprotocol/server-gitlab \
    && GITLAB_JS="$(npm root -g)/@modelcontextprotocol/server-gitlab/dist/index.js" \
    && sed -i "s|import { zodToJsonSchema } from 'zod-to-json-schema';|// zod-to-json-schema removed: using z.toJSONSchema() (Zod v4 built-in)|" "$GITLAB_JS" \
    && sed -i 's/zodToJsonSchema(/z.toJSONSchema(/g' "$GITLAB_JS" \
    && sed -i 's/error\.errors\.map/(error.issues || []).map/g' "$GITLAB_JS" \
    && echo "GitLab MCP Zod v4 patch applied OK"

# Copy requirements first for better caching
# Use locked requirements for reproducible builds (DSI audit requirement)
COPY requirements-lock.txt .
COPY requirements.txt .

# Install Python dependencies from locked file
# To update dependencies: uv pip compile requirements.txt -o requirements-lock.txt
RUN pip install --no-cache-dir -r requirements-lock.txt

# Copy application code
COPY app/ ./app/
COPY conf/ ./conf/
COPY templates/ ./templates/

# Copy Alembic configuration and migrations
COPY alembic.ini .
COPY alembic/ ./alembic/

# Create necessary directories
RUN mkdir -p /app/data /app/logs /app/embeddings_cache /app/mcp_servers

# Create non-root user and set permissions
RUN groupadd -r bigmcp && useradd -r -g bigmcp -d /app -s /sbin/nologin bigmcp \
    && chown -R bigmcp:bigmcp /app

# Copy entrypoint (runs as root, fixes bind-mount perms, drops to bigmcp)
COPY entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

# Expose port
EXPOSE 8001

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=40s --retries=3 \
    CMD curl -f http://localhost:8001/mcp/health || exit 1

# Entrypoint fixes permissions on bind-mounted dirs, then drops to bigmcp
ENTRYPOINT ["/entrypoint.sh"]
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8001", "--proxy-headers", "--forwarded-allow-ips", "*"]
