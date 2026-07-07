FROM python:3.12-slim

WORKDIR /app

# Install system dependencies
RUN apt-get update && \
    apt-get install -y --no-install-recommends gcc libpq-dev && \
    rm -rf /var/lib/apt/lists/*

# Copy and install dependencies first (layer cache)
COPY pyproject.toml .
RUN pip install --no-cache-dir .

# Copy application code
COPY . .

# Make scripts executable
RUN chmod +x scripts/start.sh

# Expose port
EXPOSE 8000

# Default command: just run uvicorn (migrations handled separately or via start.sh)
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
