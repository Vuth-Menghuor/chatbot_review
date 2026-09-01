# Database and Redis Setup Guide

This guide provides instructions for spinning up Redis and PostgreSQL on your local machine using Docker to test session management and conversation transcripts.

---

## Prerequisites
- [Docker Desktop](https://www.docker.com/products/docker-desktop/) installed and running on Windows.

---

## 1. Start PostgreSQL (Archive Database)
Run this command in PowerShell or Command Prompt to start a PostgreSQL container:

```powershell
docker run -d `
  --name gdce-postgres `
  -p 5432:5432 `
  -e POSTGRES_USER=postgres `
  -e POSTGRES_PASSWORD=postgres `
  -e POSTGRES_DB=gdce_chat_history `
  postgres
```

### What this does:
- Runs a container named `gdce-postgres`.
- Exposes port `5432` on your localhost.
- Automatically creates the database named `gdce_chat_history` with username `postgres` and password `postgres` (matching the configuration in your `.env` file).

---

## 2. Start Redis (Live Session Cache)
Run this command in PowerShell or Command Prompt to start a Redis container:

```powershell
docker run -d `
  --name gdce-redis `
  -p 6379:6379 `
  redis `
  redis-server --requirepass gdce_redis
```

### What this does:
- Runs a container named `gdce-redis`.
- Exposes port `6379` on your localhost.
- Configures Redis-server with password authentication using the password `gdce_redis` (matching the configuration in your `.env` file).

---

## 3. Verify Containers Are Running
To verify that both database servers are active, run:

```powershell
docker ps
```

You should see both `gdce-postgres` and `gdce-redis` listed as running.

---

## 4. Managing Containers

### Stopping Containers
To stop the databases when you are done testing:
```powershell
docker stop gdce-postgres gdce-redis
```

### Restarting Containers
To start them back up later:
```powershell
docker start gdce-postgres gdce-redis
```

### Removing Containers (Fresh Start)
To remove the containers entirely (your data will be deleted):
```powershell
docker rm -f gdce-postgres gdce-redis
```
