# ═══════════════════════════════════════════════════════════════
# TRADING BOT - Main Dockerfile
# ═══════════════════════════════════════════════════════════════
FROM python:3.12-slim

WORKDIR /app

# System dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    libpq-dev \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Application code
COPY src/ ./src/
COPY config/ ./config/
COPY main.py .
COPY run_backtest.py .
COPY check_sentiment.py .

# Create directories
RUN mkdir -p logs data/cache

# Health check endpoint
EXPOSE 8080

# Default command
CMD ["python", "main.py"]
