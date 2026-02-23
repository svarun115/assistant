FROM python:3.11-slim

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends curl \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY src/ ./src/

# Non-root user
# token.json and credentials.json are mounted as volumes (not baked in — they're gitignored)
RUN useradd -m -u 1000 wsuser && chown -R wsuser:wsuser /app
USER wsuser

EXPOSE 3000

HEALTHCHECK --interval=30s --timeout=10s --start-period=15s --retries=3 \
    CMD curl -sf http://localhost:3000/health || exit 1

CMD ["python", "src/server.py", "--http", "--port", "3000"]
