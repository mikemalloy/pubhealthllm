"""
AWS Lambda entry point for the pubHealthLLM FastAPI backend.

Mangum wraps the existing FastAPI app object — no changes to server.py needed.
Lambda invokes handler(event, context) on each request.

lifespan="off": FastAPI startup/shutdown hooks (validate_model_config,
check_aurora_db, check_vector_store) are NOT run by Mangum. This is intentional:
with lifespan="auto", Mangum runs the startup lifecycle on every invocation —
including warm ones — which blocks each request for 5-30s while Aurora resumes
from auto-pause. With a 60-second Clerk JWT, this causes token expiry → 403.

Health/config errors now surface at the tool level on first use rather than at
startup. The /health endpoint triggers the same checks on demand. If a true
fail-fast on Lambda init is needed, implement it as a module-level call here
(runs once per container, not per request).
"""

from mangum import Mangum

from server import app

handler = Mangum(app, lifespan="off")
