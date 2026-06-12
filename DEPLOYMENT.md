# Deployment Information

## Public URL

`https://ai-agent-production-ga3j.onrender.com`

Deployed successfully on Render from commit `8e6af2a`.

## Platform

Render Blueprint.

Blueprint:

```bash
day12-agent-deployment
```

## Environment Variables

Set these in the cloud dashboard:

```text
ENVIRONMENT=production
PORT=<platform-provided>
REDIS_URL=<redis-connection-string>
AGENT_API_KEY=<strong-secret>
JWT_SECRET=<strong-secret>
RATE_LIMIT_PER_MINUTE=10
MONTHLY_BUDGET_USD=10.0
ALLOWED_ORIGINS=*
```

## Railway Commands

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

## Render Deployment

1. Repository: `diepnbno1/day12_ha-tang-cloud_va_deployment`
2. Branch: `main`
3. Blueprint file: `render.yaml`
4. Services created:
   - `ai-agent-production` web service
   - `ai-agent-redis` key value store
5. Deploy status: live

## Test Commands

Replace `BASE_URL` and `API_KEY` after deployment.

```bash
BASE_URL=https://ai-agent-production-ga3j.onrender.com
API_KEY=<your-agent-api-key>
```

### Health Check

```bash
curl "$BASE_URL/health"
```

Expected:

```json
{"status":"ok"}
```

### Readiness Check

```bash
curl "$BASE_URL/ready"
```

Expected: `200` when Redis is connected.

### Authentication Required

```bash
curl -i -X POST "$BASE_URL/ask" \
  -H "Content-Type: application/json" \
  -d '{"question":"Hello"}'
```

Expected: `401 Unauthorized`.

### API Test

```bash
curl -X POST "$BASE_URL/ask" \
  -H "X-API-Key: $API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"user_id":"test","question":"Hello"}'
```

Expected: `200 OK` with an `answer`.

## Cloud Verification

```text
GET /health -> 200 OK
GET /ready -> 200 OK
GET /metrics without API key -> 401 Unauthorized
POST /ask without API key -> 401 Unauthorized
```

Health response:

```json
{"status":"ok","version":"1.0.0","environment":"production"}
```

Readiness response:

```json
{"ready":true,"storage":"redis"}
```

### Conversation History Test

```bash
curl -X POST "$BASE_URL/ask" \
  -H "X-API-Key: $API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"user_id":"alice","question":"My name is Alice"}'

curl -X POST "$BASE_URL/ask" \
  -H "X-API-Key: $API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"user_id":"alice","question":"What is my name?"}'
```

Expected second answer mentions `Alice`.

### Rate Limiting

```bash
for i in {1..15}; do
  curl -s -o /dev/null -w "%{http_code}\n" -X POST "$BASE_URL/ask" \
    -H "X-API-Key: $API_KEY" \
    -H "Content-Type: application/json" \
    -d "{\"user_id\":\"rate-test\",\"question\":\"test $i\"}"
done
```

Expected: first 10 are `200`, later requests return `429`.

## Local Verification Already Completed

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

## Screenshots

Screenshots can be added from the Render dashboard:

```text
screenshots/dashboard.png
screenshots/running.png
screenshots/test.png
```
