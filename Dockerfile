# syntax=docker/dockerfile:1

# Stage 1: install dependencies into a copyable user directory.
FROM python:3.11-slim AS builder

WORKDIR /build

RUN apt-get update \
    && apt-get install -y --no-install-recommends gcc \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir --user -r requirements.txt


# Stage 2: small non-root runtime image.
FROM python:3.11-slim AS runtime

RUN groupadd -r agent && useradd -r -g agent -d /app agent

WORKDIR /app

COPY --from=builder /root/.local /home/agent/.local
COPY app/ ./app/
COPY utils/ ./utils/

RUN chown -R agent:agent /app

USER agent

ENV PATH=/home/agent/.local/bin:$PATH
ENV HOME=/home/agent
ENV PYTHONPATH=/app:/home/agent/.local/lib/python3.11/site-packages
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV PORT=8000
ENV WEB_CONCURRENCY=2

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=10s --start-period=15s --retries=3 \
    CMD python -c "import os,urllib.request; urllib.request.urlopen('http://127.0.0.1:%s/health' % os.getenv('PORT','8000'))" || exit 1

CMD ["sh", "-c", "python -m uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000} --workers ${WEB_CONCURRENCY:-2} --timeout-graceful-shutdown 30"]
