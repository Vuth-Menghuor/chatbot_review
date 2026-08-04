FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /app

RUN addgroup --system api && adduser --system --ingroup api api
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
RUN chown -R api:api /app
USER api

EXPOSE 8000
# The API container only starts the web process; migrations run in the api-migrate service.
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
