# Use an official Python runtime as a parent image
FROM python:3.11-slim

# Set the working directory in the container
WORKDIR /app

# Copy requirements
COPY requirements.txt ./

# Install dependencies
RUN pip install --no-cache-dir torch --index-url https://download.pytorch.org/whl/cpu
RUN pip install --no-cache-dir -r requirements.txt

# Copy the rest of the application code inside the package structure
COPY . ./services_version2/orchestrator

# Expose the port this service runs on
EXPOSE 8001

# Set environment variables
ENV PYTHONUNBUFFERED=1

# Command to run the FastAPI app as a module
CMD ["python", "-m", "services_version2.orchestrator.main"]
