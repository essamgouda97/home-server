FROM python:3.12-slim@sha256:2f17fc044b579bab302c2e8054d3a686e2cb9a83de48e70534b94cd8ebbe06a9
WORKDIR /app
COPY requirements.lock wheels.sha256.json ./
COPY wheelhouse /wheels
RUN python -c "import hashlib,json,pathlib; assert all(hashlib.sha256((pathlib.Path('/wheels')/n).read_bytes()).hexdigest()==h for n,h in json.load(open('wheels.sha256.json')).items())" && pip install --no-cache-dir --no-index --find-links=/wheels -r requirements.lock

COPY . .
USER 1000:1000
CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "8080", "--no-access-log", "--no-proxy-headers", "--limit-concurrency", "12", "--timeout-keep-alive", "5"]
