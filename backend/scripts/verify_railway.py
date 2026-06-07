"""
verify_railway.py — Live D3 end-to-end verification against the deployed Railway API.

Usage (from backend/ with venv active and .env present):
    python scripts/verify_railway.py

What it does:
  1. Loads CLERK_SECRET_KEY from .env
  2. Finds a test user (TEST_USER_EMAIL env var, or first user in the instance)
  3. Creates a Clerk session + mints a JWT via the backend API
  4. Calls GET {RAILWAY_URL}/measures and POST {RAILWAY_URL}/ask with the token
  5. Prints status + body for each call

Do NOT commit printed tokens or secrets — this script reads from env only.

Costs: one real LLM call on Railway (Anthropic API spend).
"""

import json
import os
import sys
from pathlib import Path

import httpx
from dotenv import load_dotenv

# Load .env from backend/
load_dotenv(Path(__file__).parents[1] / ".env")

RAILWAY_URL = "https://pubhealthllm-production.up.railway.app"
TEST_QUESTION = "What is the diabetes rate in Travis County, TX?"


def _clerk_sdk():
    """Return an initialised Clerk SDK or exit with a helpful message."""
    try:
        import clerk_backend_api as clerk
    except ImportError:
        sys.exit(
            "clerk-backend-api not installed. Run:\n"
            "  pip install clerk-backend-api"
        )

    secret_key = os.getenv("CLERK_SECRET_KEY")
    if not secret_key:
        sys.exit(
            "CLERK_SECRET_KEY not set. Add it to backend/.env:\n"
            "  CLERK_SECRET_KEY=sk_test_..."
        )

    return clerk.Clerk(bearer_auth=secret_key)


def _find_user(sdk) -> str:
    """Return a user_id to mint a token for, or exit if none exist."""
    target_email = os.getenv("TEST_USER_EMAIL")

    import clerk_backend_api as clerk
    result = sdk.users.list(request=clerk.models.GetUserListRequest(limit=50))
    users = result if isinstance(result, list) else []

    if not users:
        sys.exit(
            "No users found in your Clerk instance.\n"
            "Create a test user at https://dashboard.clerk.com → Users → Create user,\n"
            "then re-run this script (or set TEST_USER_EMAIL in .env)."
        )

    if target_email:
        matches = [
            u for u in users
            if any(
                getattr(e, "email_address", None) == target_email
                for e in (u.email_addresses or [])
            )
        ]
        if not matches:
            sys.exit(
                f"No user found with email {target_email!r}.\n"
                "Check TEST_USER_EMAIL in .env or create the user in the Clerk dashboard."
            )
        user = matches[0]
    else:
        user = users[0]

    email = next(
        (getattr(e, "email_address", "?") for e in (user.email_addresses or [])),
        "<no email>",
    )
    print(f"[clerk] Using user: {email!r}  id={user.id}")
    return user.id


def _mint_token(sdk, user_id: str) -> str:
    """Create a Clerk session and return a short-lived JWT."""
    import clerk_backend_api as clerk

    session = sdk.sessions.create(
        request=clerk.models.CreateSessionRequestBody(user_id=user_id)
    )
    session_id = session.id
    print(f"[clerk] Session created: {session_id}")

    token_resp = sdk.sessions.create_token(session_id=session_id)
    jwt = token_resp.jwt
    # Print first/last 10 chars only — do not log full token
    preview = f"{jwt[:10]}...{jwt[-10:]}" if len(jwt) > 25 else "***"
    print(f"[clerk] Token minted: {preview}")
    return jwt


def _call(method: str, path: str, jwt: str, body: dict | None = None) -> None:
    """Make an authenticated HTTP call and pretty-print the result."""
    url = f"{RAILWAY_URL}{path}"
    headers = {
        "Authorization": f"Bearer {jwt}",
        "Content-Type": "application/json",
    }
    print(f"\n{'='*70}")
    print(f"{method} {url}")
    print("─" * 70)

    with httpx.Client(timeout=120.0) as client:
        if method == "GET":
            resp = client.get(url, headers=headers)
        else:
            resp = client.post(url, headers=headers, json=body)

    print(f"HTTP {resp.status_code}")
    try:
        data = resp.json()
        print(json.dumps(data, indent=2, default=str))
    except Exception:
        print(resp.text)


def main() -> None:
    print("=== D3 Railway Verification ===\n")

    sdk = _clerk_sdk()
    user_id = _find_user(sdk)
    jwt = _mint_token(sdk, user_id)

    # GET /measures
    _call("GET", "/measures", jwt)

    # POST /ask — a data question that should return mode=artifact
    _call("POST", "/ask", jwt, body={"question": TEST_QUESTION})

    print(f"\n{'='*70}")
    print("Done.")


if __name__ == "__main__":
    main()
