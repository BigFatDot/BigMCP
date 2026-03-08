#!/bin/sh
set -e

# Fix permissions on bind-mounted directories.
# Needed when files are copied from Windows (wrong UID) or when
# host directories are owned by root instead of the container user.
if [ "$(id -u)" = "0" ]; then
    chown -R bigmcp:bigmcp \
        /app/conf \
        /app/data \
        /app/logs \
        /app/embeddings_cache \
        /app/mcp_servers 2>/dev/null || true
    chmod 775 /app/conf 2>/dev/null || true
    exec gosu bigmcp "$@"
fi

exec "$@"
