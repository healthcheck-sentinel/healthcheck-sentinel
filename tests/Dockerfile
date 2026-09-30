FROM healthcheck-sentinel-monitoring-agent
COPY services/requirements-dev.txt /tmp/requirements-dev.txt
COPY services/requirements.txt /tmp/requirements.txt
RUN pip install --no-cache-dir -r /tmp/requirements-dev.txt
WORKDIR /app
CMD ["python", "-m", "pytest", "-q"]
