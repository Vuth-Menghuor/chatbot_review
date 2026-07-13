FROM python:3.11-slim

WORKDIR /app

# Install system deps for psycopg2
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc libpq-dev \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy the restructured calculator package into a 'calculator' subdir
# so Python can import it as a module (calculator.main:app)
COPY . /app/calculator/

ENV PYTHONPATH=/app
ENV PYTHONUNBUFFERED=1

EXPOSE 8002

CMD ["uvicorn", "calculator.main:app", "--host", "0.0.0.0", "--port", "8002"]
