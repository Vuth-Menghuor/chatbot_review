FROM python:3.11-slim

# Set working directory
WORKDIR /app

# Set environment variables
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements
COPY requirements.txt .

# Install dependencies
RUN pip install --upgrade pip && \
    pip install -r requirements.txt

# Copy application code
COPY . .

# Create non-root user
RUN useradd -m -u 1000 appuser && chown -R appuser:appuser /app
USER appuser

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=40s --retries=3 \
    CMD curl -f http://localhost:${ORCHESTRATOR_PORT:-8001}/health || exit 1

# Expose port
EXPOSE ${ORCHESTRATOR_PORT:-8001}

# Run application
CMD ["python", "main.py"]

# Build: docker build -t orchestrator:v2 .
# Run:   docker run -p 8001:8001 \
#        -e ORCHESTRATOR_HOST=0.0.0.0 \
#        -e ORCHESTRATOR_PORT=8001 \
#        -e RETRIEVAL_SERVICE_URL=http://retrieval:8000 \
#        orchestrator:v2
