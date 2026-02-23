FROM python:3.11-slim

WORKDIR /app

# System deps (postgres client for future PG health checks)
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Install Python dependencies first (better layer caching)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code (exclude skills/ and data/ — mounted as volumes at runtime)
COPY *.py ./
COPY graph/ ./graph/
COPY migrations/ ./migrations/
COPY static/ ./static/
# system-agents/ is filesystem-backed (AgentLoader reads at startup)
# agents/ templates are seeded into the DB via AgentSeeder on first run
COPY agents/ ./agents/
COPY system-agents/ ./system-agents/

# Non-root user
RUN useradd -m -u 1000 assistant && chown -R assistant:assistant /app
USER assistant

# skills/ and data/ are mounted at runtime via docker-compose volumes:
#   /app/skills  ← ~/.claude/skills  (read-only)
#   /app/data    ← ~/.claude/data    (read-only)
# The SkillsLoader and profile factory resolve these paths from env / defaults.

EXPOSE 8080

HEALTHCHECK --interval=30s --timeout=10s --start-period=15s --retries=3 \
    CMD curl -sf http://localhost:8080/api/health || exit 1

CMD ["uvicorn", "web_server:app", "--host", "0.0.0.0", "--port", "8080"]
