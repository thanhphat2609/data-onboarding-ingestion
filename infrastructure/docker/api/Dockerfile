# Ingestion API (FastAPI). Build context is the repository root (see /.dockerignore).
# pymssql wheels bundle FreeTDS, so no ODBC driver or system packages are needed.

FROM python:3.12.15-slim-bookworm

ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1 PIP_DISABLE_PIP_VERSION_CHECK=1
WORKDIR /app

COPY code/control-plane/pyproject.toml code/control-plane/
COPY code/control-plane/src/ code/control-plane/src/
RUN pip install ./code/control-plane && rm -rf code

# uid 1000 = the Codespaces user, so the YAML working copy written to the bind-mounted pipelines/ stays editable.
RUN useradd --uid 1000 --create-home ingestion
USER ingestion

ENV INGESTION_PIPELINES_DIR=/workspace/pipelines INGESTION_TEMPLATES_DIR=/workspace/code/templates
EXPOSE 8000
HEALTHCHECK --interval=15s --timeout=5s --start-period=10s --retries=5 \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/api/health', timeout=4)"
CMD ["uvicorn", "ingestion.api:create_app", "--factory", "--host", "0.0.0.0", "--port", "8000", "--proxy-headers"]
