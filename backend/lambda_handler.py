"""
AWS Lambda entry point for the pubHealthLLM FastAPI backend.

Mangum wraps the existing FastAPI app object — no changes to server.py needed.
Lambda invokes handler(event, context) on each request.

Lifespan "auto": Mangum calls FastAPI startup/shutdown hooks on Lambda
init/destruction, so validate_model_config + Aurora/vector store warmup
run on cold start (fail-fast on misconfiguration, warm on first request).
"""

from mangum import Mangum

from server import app

handler = Mangum(app, lifespan="auto")
