# Use an official Python runtime as a parent image
FROM python:3.11-slim

# Set the working directory in the container
WORKDIR /app

# Copy requirements (if you have a requirements.txt)
COPY requirements.txt ./

# Install dependencies
RUN pip install --no-cache-dir torch --index-url https://download.pytorch.org/whl/cpu
RUN pip install --no-cache-dir -r requirements.txt

# Copy the rest of the application code
COPY . .
    
# Expose the port your FastAPI app runs on
EXPOSE 8003

# Set environment variables (optional, for production best practices)
ENV PYTHONUNBUFFERED=1

# Command to run the FastAPI app with Uvicorn
CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "8003"]
