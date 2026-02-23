FROM python:3.11-slim

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy all application code (handlers/, services/, tools/, etc.)
COPY . .
RUN pip install --no-cache-dir -e . --no-deps

# Non-root user
RUN useradd -m -u 1000 journaluser && chown -R journaluser:journaluser /app
USER journaluser

EXPOSE 3333

HEALTHCHECK --interval=30s --timeout=10s --start-period=15s --retries=3 \
    CMD curl -sf http://localhost:3333/health || exit 1

CMD ["python", "server.py", "--http", "--port", "3333"]
