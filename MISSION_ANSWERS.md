# Day 12 Lab - Mission Answers

## Part 1: Localhost vs Production

### Exercise 1.1: Anti-patterns found

1. API key is hardcoded in `01-localhost-vs-production/develop/app.py`.
2. Database URL and password are hardcoded.
3. Secrets are printed to logs.
4. Port `8000` is hardcoded instead of reading `PORT` from environment.
5. Host is bound to `localhost`, so the app is not reachable inside containers/cloud.
6. Debug reload is enabled for the runtime command.
7. There is no `/health` endpoint for platform liveness checks.
8. There is no `/ready` endpoint for readiness checks.
9. Logging uses `print()` instead of structured logs.
10. There is no graceful shutdown or lifecycle cleanup.

### Exercise 1.2: Basic version

Expected local run:

```bash
cd 01-localhost-vs-production/develop
pip install -r requirements.txt
python app.py
curl http://localhost:8000/ask -X POST \
  -H "Content-Type: application/json" \
  -d '{"question":"Hello"}'
```

Observation: the app can answer locally, but it is not production-ready because config, secrets, logs, health checks, networking, and shutdown are not cloud-safe.

### Exercise 1.3: Comparison table

| Feature | Develop | Production | Why Important? |
|---|---|---|---|
| Config | Hardcoded values | Environment variables | Same image can run in dev, staging, and prod without code changes. |
| Secrets | API key and DB password in source | Read from env | Prevents leaking secrets to GitHub and logs. |
| Host/port | `localhost:8000` | `0.0.0.0` and `PORT` | Required for Docker and cloud platforms. |
| Health check | Missing | `/health` | Lets the platform restart unhealthy containers. |
| Readiness | Missing | `/ready` | Keeps traffic away until dependencies are ready. |
| Logging | `print()` | JSON structured logs | Easier to search, alert, and aggregate. |
| Shutdown | Abrupt | FastAPI lifespan plus graceful Uvicorn timeout | Lets in-flight requests finish before the container exits. |
| CORS | Not configured | Env-driven allowlist | Safer browser/API access control. |

## Part 2: Docker

### Exercise 2.1: Dockerfile questions

1. Base image: `python:3.11` in the basic Dockerfile.
2. Working directory: `/app`.
3. `COPY requirements.txt` comes before source code so Docker can cache dependency installation when only app code changes.
4. `CMD` is the default command and can be overridden at runtime. `ENTRYPOINT` defines the executable pattern and is harder to override.

### Exercise 2.2: Build and run

Expected commands:

```bash
docker build -f 02-docker/develop/Dockerfile -t my-agent:develop .
docker run -p 8000:8000 my-agent:develop
curl http://localhost:8000/ask -X POST \
  -H "Content-Type: application/json" \
  -d '{"question":"What is Docker?"}'
docker images my-agent:develop
```

Measured on this laptop after installing Docker Desktop:

```text
my-agent:develop -> 1.66GB
```

### Exercise 2.3: Multi-stage build

Stage 1 installs build tools and Python dependencies. Stage 2 copies only the installed packages and app source into a slim runtime image.

Why smaller: compilers, package cache, apt metadata, and build-only files stay out of the final image.

Expected commands:

```bash
cd 02-docker/production
docker build -t my-agent:advanced .
docker images my-agent:advanced
```

Measured comparison:

| Image | Expected size | Notes |
|---|---:|---|
| Develop | 1.66 GB | Full Python base image. |
| Production | 236 MB | Slim base, multi-stage, no build cache. |
| Reduction | About 85.8 percent | Multi-stage build removes the large full base/build context from runtime. |

### Exercise 2.4: Docker Compose stack

Services:

1. `nginx`: public reverse proxy and load balancer on port 80.
2. `agent`: FastAPI app on internal port 8000.
3. `redis`: shared storage for sessions/rate limit/budget.
4. In section 2 production example, `qdrant` is also included as a vector database.

Architecture:

```text
Client -> Nginx :80 -> Agent :8000 -> Redis :6379
```

## Part 3: Cloud Deployment

### Exercise 3.1: Railway deployment

Status: code and `railway.toml` are ready, but actual deployment requires the owner's Railway account login.

Commands to run after login:

```bash
cd 06-lab-complete
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

Public URL: `PENDING_USER_DEPLOYMENT`

### Exercise 3.2: Render deployment and config comparison

`railway.toml` is concise and mostly describes how to build/start one service. Environment variables and Redis are commonly configured through Railway CLI/dashboard.

`render.yaml` is a blueprint: it can define the web service, Redis service, region, plan, generated secrets, and environment variable wiring in one file.

### Exercise 3.3: Optional GCP Cloud Run

`cloudbuild.yaml` describes a CI/CD pipeline:

1. Install dependencies and run tests.
2. Build the Docker image.
3. Push the image to Google Container Registry/Artifact Registry.
4. Deploy the image to Cloud Run.

`service.yaml` describes runtime infrastructure:

1. Public ingress.
2. Min/max autoscaling.
3. Container concurrency and timeout.
4. CPU/memory limits.
5. Secret Manager references.
6. Liveness/startup probes.

## Part 4: API Security

### Exercise 4.1: API key authentication

The API key is checked in the authentication dependency. In the completed final app this is `app/auth.py::verify_auth`.

If the key is missing or invalid, the API returns `401 Unauthorized`.

Rotate key by changing `AGENT_API_KEY` in the environment or cloud dashboard, then restarting/redeploying the service. Do not change source code.

### Exercise 4.2: JWT authentication

JWT flow:

1. Client sends username/password to `/auth/token`.
2. Server verifies credentials from environment-backed demo config.
3. Server signs a JWT with `sub`, `role`, `iat`, and `exp`.
4. Client calls protected endpoints with `Authorization: Bearer <token>`.
5. Server verifies signature and expiry on each request.

In the final app, JWT is optional bonus support in addition to API key auth.

### Exercise 4.3: Rate limiting

Algorithm: Redis-backed sliding window using a sorted set per user.

Limit: `10 requests/minute/user` by default. Admin JWT role gets `100 requests/minute` by default.

Admin bypass or higher quota: use the JWT `role=admin` claim and a separate env var `ADMIN_RATE_LIMIT_PER_MINUTE`.

### Exercise 4.4: Cost guard implementation

Implemented in `06-lab-complete/app/cost_guard.py`.

Approach:

1. Estimate tokens from input/output text.
2. Convert estimated tokens to USD with model price env vars.
3. Store usage in Redis key `budget:{user_id}:{YYYY-MM}`.
4. Use `INCRBYFLOAT` to record usage.
5. Set TTL to 32 days so old month keys expire.
6. Return `402 Payment Required` when the next request would exceed `$10/month/user`.

## Part 5: Scaling and Reliability

### Exercise 5.1: Health checks

Implemented:

```text
GET /health -> liveness, returns 200 when process is alive
GET /ready  -> readiness, returns 200 only when Redis is reachable
```

Local test on this laptop without Redis:

```text
/health -> 200
/ready  -> 503
```

That is expected because Redis is required for readiness.

### Exercise 5.2: Graceful shutdown

The final app uses FastAPI lifespan cleanup and Uvicorn `--timeout-graceful-shutdown 30`. Uvicorn handles SIGTERM from Docker/cloud orchestrators, while the app logs `graceful_shutdown` during lifespan shutdown.

### Exercise 5.3: Stateless design

User state is not stored in Python memory. The final app stores:

1. Conversation history in Redis list keys `history:{user_id}`.
2. Rate limit windows in Redis sorted set keys `rate:{user_id}`.
3. Monthly cost usage in Redis keys `budget:{user_id}:{YYYY-MM}`.

This allows multiple agent containers to serve the same user without losing context.

### Exercise 5.4: Load balancing

Final architecture in `06-lab-complete/docker-compose.yml`:

```text
Client -> Nginx -> agent replicas -> Redis
```

Run:

```bash
cd 06-lab-complete
docker compose up --scale agent=3
```

Nginx routes requests to the Docker Compose service name `agent`, which resolves to replicas.

### Exercise 5.5: Test stateless

Manual test plan:

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

Expected second response mentions `Alice`, even if a different replica serves the request, because history is in Redis.

## Part 6: Final Project

Completed in `06-lab-complete` and mirrored at the repository root for graders that expect `app/`, `Dockerfile`, and `docker-compose.yml` at top level.

Implemented requirements:

1. REST API agent via `POST /ask`.
2. Conversation history via Redis.
3. Optional streaming via `POST /ask/stream`.
4. Multi-stage Dockerfile.
5. Env-driven config.
6. API key auth.
7. Optional JWT auth.
8. Redis sliding-window rate limiting.
9. Redis monthly cost guard.
10. `/health` and `/ready`.
11. Graceful shutdown.
12. Stateless design.
13. JSON structured logs.
14. Nginx load-balanced Docker Compose stack.
15. Railway and Render config.

Verification completed on this laptop:

```text
python -m compileall 06-lab-complete\app 06-lab-complete\utils -> passed
python 06-lab-complete\check_production_ready.py -> 20/20 passed
Docker Desktop 4.77.0 installed -> docker run hello-world passed
docker compose up --build -d -> agent, redis, nginx healthy
final production image size -> 247 MB
local uvicorn /health -> 200
local uvicorn /ask without auth -> 401
local uvicorn /ask with auth but without Redis -> 503
local uvicorn /ready without Redis -> 503
Docker Compose /health -> 200
Docker Compose /ready -> 200
Docker Compose /ask without auth -> 401
Docker Compose /ask with auth -> 200
Conversation history test -> second response mentions Alice
Rate limit test -> first 10 requests 200, following requests 429
```

Remaining user-owned items:

1. Deploy to Railway or Render using your account.
2. Fill the real public URL in `DEPLOYMENT.md`.
3. Add screenshots from the cloud dashboard and API test.
