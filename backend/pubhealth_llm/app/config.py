"""
Model configuration for pubHealthLLM.

Single source of truth for model selection. Reads PUBHEALTH_MODEL from the
environment; falls back to the default Bedrock Nova Pro model.
"""

import os

ALLOWED_PROVIDERS = {"anthropic", "openai", "bedrock"}
DEFAULT_MODEL = "bedrock:us.amazon.nova-pro-v1:0"

# Providers that authenticate with API keys (bedrock uses IAM — no key needed)
_API_KEY_MAP = {
    "anthropic": "ANTHROPIC_API_KEY",
    "openai": "OPENAI_API_KEY",
}


def get_model() -> str:
    """Return the configured model string (provider:model-id).

    Reads PUBHEALTH_MODEL env var; falls back to DEFAULT_MODEL.
    """
    return os.getenv("PUBHEALTH_MODEL", DEFAULT_MODEL)


def validate_model_config(model: str | None = None) -> None:
    """Validate provider is allowed and required API key is present.

    Bedrock uses IAM authentication — no API key check is performed.

    Args:
        model: Provider:model-id string to validate. Defaults to get_model().

    Raises:
        ValueError: If the provider is not in ALLOWED_PROVIDERS.
        EnvironmentError: If the required API key env var is not set
                          (for key-based providers only).
    """
    target = model if model is not None else get_model()
    parts = target.split(":", 1)
    provider = parts[0] if len(parts) == 2 else target

    if provider not in ALLOWED_PROVIDERS:
        raise ValueError(
            f"Provider {provider!r} is not supported. "
            f"Allowed providers: {sorted(ALLOWED_PROVIDERS)}. "
            f"Set PUBHEALTH_MODEL to 'bedrock:<model-id>', "
            f"'anthropic:<model>', or 'openai:<model>'."
        )

    # Bedrock uses IAM auth — no API key required
    if provider == "bedrock":
        return

    key_name = _API_KEY_MAP[provider]
    if not os.getenv(key_name):
        raise EnvironmentError(
            f"{key_name} is not set. "
            f"Add it to your .env file to use provider {provider!r}."
        )
