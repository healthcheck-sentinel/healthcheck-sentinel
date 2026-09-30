# services/payment_service/Dockerfile
FROM python:3.11-slim

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends curl && rm -rf /var/lib/apt/lists/*

# Install dependencies
COPY services/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy service source
COPY services/payment_service/ ./services/payment_service/

EXPOSE 8001

CMD ["uvicorn", "services.payment_service.main:app", "--loop", "asyncio", "--host", "0.0.0.0", "--port", "8001"]

COPY services/health_resources.py services/probe_pool.py ./services/
