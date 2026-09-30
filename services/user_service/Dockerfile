# services/user_service/Dockerfile
FROM python:3.11-slim

WORKDIR /app

# Install dependencies
COPY services/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy service source
COPY services/user_service/ ./services/user_service/

EXPOSE 8003

CMD ["uvicorn", "services.user_service.main:app", "--host", "0.0.0.0", "--port", "8003"]
