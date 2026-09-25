FROM python:3.12-slim@sha256:2f17fc044b579bab302c2e8054d3a686e2cb9a83de48e70534b94cd8ebbe06a9
COPY requirements.lock wheels.sha256.json /build/
COPY wheelhouse /wheels
RUN python -c "import hashlib,json,pathlib; assert all(hashlib.sha256((pathlib.Path('/wheels')/n).read_bytes()).hexdigest()==h for n,h in json.load(open('/build/wheels.sha256.json')).items())" && pip install --no-cache-dir --no-index --find-links=/wheels -r /build/requirements.lock
USER 65532:65532
WORKDIR /tmp
ENV PYTHONDONTWRITEBYTECODE=1
CMD ["python", "-I", "/inputs/script.py"]
