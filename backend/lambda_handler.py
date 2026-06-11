"""
AWS Lambda entry point for the pubHealthLLM FastAPI backend.

Mangum wraps the existing FastAPI app object — no changes to server.py needed.
Lambda invokes handler(event, context) on each request.

Lifespan "auto": Mangum calls FastAPI startup/shutdown hooks on every Lambda
invocation, so validate_model_config + Aurora/vector store warmup run on
every Lambda invocation — fail-fast on misconfiguration, warm DB on each
request. If startup checks prove expensive, switch to lifespan="off" and use a
Lambda init module for one-time setup.
"""

from mangum import Mangum

from server import app

handler = Mangum(app, lifespan="auto")
