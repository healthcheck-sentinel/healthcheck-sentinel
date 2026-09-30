# services/order_service/Dockerfile
FROM python:3.11-slim

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends curl && rm -rf /var/lib/apt/lists/*

# Install dependencies
COPY services/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy service source
COPY services/order_service/ ./services/order_service/

EXPOSE 8002

CMD ["uvicorn", "services.order_service.main:app", "--host", "0.0.0.0", "--port", "8002"]
