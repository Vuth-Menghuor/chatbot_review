# GDCE Trade Query Service

A FastAPI-based microservice that translates natural language questions about Cambodia trade data into structured Data Access Layer (DAL) queries, retrieves corresponding statistics, and generates conversational natural language responses (NLG) along with structured charts and tables.

---

## 🚀 Getting Started

### Prerequisites
- Python 3.10+
- Google Gemini API Key

### Local Installation & Run
1. Copy the example environment file and configure your API keys:
   ```bash
   cp .env.example .env
   ```
2. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```
3. Run the service:
   ```bash
   python main.py
   ```
   Or run using Uvicorn directly:
   ```bash
   uvicorn app.main:app --host 127.0.0.1 --port 8004
   ```

### Run via Docker
1. Build the Docker image:
   ```bash
   docker build -t trade-service .
   ```
2. Run the container:
   ```bash
   docker run -p 8004:8004 --env-file .env trade-service
   ```
   Or run via Docker Compose:
   ```bash
   docker compose up --build
   ```

---

## 🛣️ API Endpoints

All endpoints are hosted at the root path:

### 1. `GET /health`
- **Purpose**: Service health check.
- **Response**:
  ```json
  {
    "status": "ok",
    "version": "1.0.0"
  }
  ```

### 2. `POST /query`
- **Purpose**: Full Stage 1 to 6 natural language query execution.
- **Request Body**:
  ```json
  {
    "question": "Top 10 export countries in 2025"
  }
  ```
- **Response**: A standard trade statistics envelope with normalised records, summary metadata, chart visualization specs, table data, and natural language summary message.

### 3. `POST /extract-params`
- **Purpose**: Debug endpoint to view parameter extraction & intent recognition outputs without hitting the live DAL database.
- **Request Body**:
  ```json
  {
    "question": "Top 10 export countries in 2025"
  }
  ```
- **Response**: The structured parameter representation extracted by the Gemini LLM.
