"""
Smoke tests for the Mangum Lambda adapter.
Verifies the handler is a Mangum instance and that core routes exist.
No actual Lambda invocation — pure import-level checks.
"""


def test_handler_is_mangum_instance():
    """handler must be a Mangum object wrapping our FastAPI app."""
    from mangum import Mangum
    import lambda_handler
    assert isinstance(lambda_handler.handler, Mangum), (
        f"Expected Mangum instance, got {type(lambda_handler.handler)}"
    )


def test_handler_wraps_fastapi_app():
    """handler.app must be the same FastAPI app object from server.py."""
    import lambda_handler
    from server import app
    assert lambda_handler.handler.app is app


def test_health_route_exists():
    """FastAPI app must expose GET /health (sanity check routes are registered)."""
    from server import app
    routes = {r.path for r in app.routes}
    assert "/health" in routes, f"GET /health missing from routes: {routes}"


def test_ask_route_exists():
    """FastAPI app must expose POST /ask."""
    from server import app
    routes = {r.path for r in app.routes}
    assert "/ask" in routes, f"POST /ask missing from routes: {routes}"
