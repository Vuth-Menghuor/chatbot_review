# Use an official Python runtime as a parent image
FROM python:3.13-slim

WORKDIR /app

COPY requirements.txt ./

RUN pip install --no-cache-dir torch --index-url https://download.pytorch.org/whl/cpu
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

EXPOSE 8003

ENV PYTHONUNBUFFERED=1

CMD ["uvicorn", "app.app:app", "--host", "0.0.0.0", "--port", "8003"]