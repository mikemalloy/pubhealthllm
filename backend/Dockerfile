# backend/Dockerfile
# Build context must be the project root:
#   docker build -f backend/Dockerfile .
# Used by AWS App Runner via Terraform (see terraform/).
# For Railway use backend/Dockerfile.railway instead.

FROM python:3.11-slim

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

COPY backend/requirements.txt /tmp/requirements.txt
RUN pip install --no-cache-dir \
    --extra-index-url https://download.pytorch.org/whl/cpu \
    -r /tmp/requirements.txt

COPY backend/server.py /app/
COPY backend/pubhealth_llm/ /app/pubhealth_llm/
COPY backend/data/ /app/data/

EXPOSE 8000

CMD ["uvicorn", "server:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1"]
