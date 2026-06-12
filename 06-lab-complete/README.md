# Lab 12 Complete Production Agent

This project combines all Day 12 deployment requirements into one production-ready FastAPI agent.

## Features

- REST API: `POST /ask`
- Optional streaming: `POST /ask/stream`
- Conversation history in Redis
- API key authentication
- Optional JWT authentication
- Redis sliding-window rate limiting, default `10 req/min/user`
- Redis monthly cost guard, default `$10/month/user`
- `/health` liveness and `/ready` readiness checks
- Structured JSON logging
- Graceful shutdown through FastAPI lifespan and Uvicorn
- Multi-stage Dockerfile, non-root runtime user
- Docker Compose stack with agent, Redis, and Nginx load balancer
- Railway and Render deployment config

## Structure

```text
06-lab-complete/
├── app/
│   ├── main.py
│   ├── config.py
│   ├── auth.py
│   ├── rate_limiter.py
│   ├── cost_guard.py
│   └── redis_client.py
├── utils/
│   └── mock_llm.py
├── Dockerfile
├── docker-compose.yml
├── nginx.conf
├── railway.toml
├── render.yaml
├── .env.example
├── .dockerignore
└── requirements.txt
```

## Run Locally With Docker

Docker Desktop must be installed and running.

```bash
cd 06-lab-complete
docker compose up --build
```

Scale to three agent replicas:

```bash
docker compose up --build --scale agent=3
```

## Test

```bash
curl http://localhost/health
curl http://localhost/ready
```

Authenticated request:

```bash
curl -X POST http://localhost/ask \
  -H "X-API-Key: dev-key-change-me" \
  -H "Content-Type: application/json" \
  -d '{"user_id":"test","question":"What is Docker?"}'
```

Conversation history:

```bash
curl -X POST http://localhost/ask \
  -H "X-API-Key: dev-key-change-me" \
  -H "Content-Type: application/json" \
  -d '{"user_id":"alice","question":"My name is Alice"}'

curl -X POST http://localhost/ask \
  -H "X-API-Key: dev-key-change-me" \
  -H "Content-Type: application/json" \
  -d '{"user_id":"alice","question":"What is my name?"}'
```

Rate limit:

```bash
for i in {1..15}; do
  curl -s -o /dev/null -w "%{http_code}\n" -X POST http://localhost/ask \
    -H "X-API-Key: dev-key-change-me" \
    -H "Content-Type: application/json" \
    -d "{\"user_id\":\"rate-test\",\"question\":\"test $i\"}"
done
```

## Run Without Docker For Syntax/Smoke Checks

This starts the app, but `/ready` and authenticated `/ask` require Redis.

```bash
python -m venv .venv
.\.venv\Scripts\python -m pip install -r requirements.txt
.\.venv\Scripts\python -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

## Production Readiness Check

```bash
python check_production_ready.py
```

On Windows consoles that cannot print emoji:

```powershell
$env:PYTHONIOENCODING='utf-8'
python check_production_ready.py
```

## Deploy

Railway:

```bash
railway login
railway init
railway add redis
railway variables set ENVIRONMENT=production
railway variables set AGENT_API_KEY=<strong-secret>
railway variables set JWT_SECRET=<strong-secret>
railway variables set RATE_LIMIT_PER_MINUTE=10
railway variables set MONTHLY_BUDGET_USD=10.0
railway up
railway domain
```

Render:

1. Push the repository to GitHub.
2. Create a new Blueprint on Render.
3. Select this repo and the `06-lab-complete/render.yaml` blueprint.
4. Confirm generated secrets and Redis connection.
5. Deploy and test `/health`, `/ready`, and `/ask`.
