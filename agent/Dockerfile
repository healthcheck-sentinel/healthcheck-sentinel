# agent/Dockerfile
FROM python:3.11-slim

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends curl && rm -rf /var/lib/apt/lists/*

# Install dependencies
COPY services/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy agent source
COPY agent/ ./agent/
COPY chatops/ ./chatops/

EXPOSE 9100

CMD ["python", "-m", "agent.main"]
