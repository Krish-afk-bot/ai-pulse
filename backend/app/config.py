import os
import secrets

# Load .env if present (very small loader, no extra dependency)
_env_path = os.path.join(os.path.dirname(__file__), "..", ".env")
if os.path.exists(_env_path):
    for line in open(_env_path):
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, v = line.split("=", 1)
            os.environ.setdefault(k.strip(), v.strip())

# No hard-coded fallback: if no secret is configured we generate a random one
# per process, so a leaked/committed secret can never be used to forge tokens.
SECRET_KEY = os.getenv("SECRET_KEY") or secrets.token_urlsafe(48)
DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./aipulse.db")
LLM_API_URL = os.getenv("LLM_API_URL", "")
LLM_API_KEY = os.getenv("LLM_API_KEY", "")
LLM_MODEL = os.getenv("LLM_MODEL", "")
TOKEN_HOURS = 12


def validate_ai_config(mode, api_url="", api_key="", model=""):
    """Fail fast on an unusable AI configuration, and return the validated mode."""
    if mode not in ("mock", "live"):
        raise ValueError(f"AI_MODE must be 'mock' or 'live', got {mode!r}")
    if mode == "live":
        missing = [
            name for name, value in (
                ("LLM_API_URL", api_url),
                ("LLM_API_KEY", api_key),
                ("LLM_MODEL", model),
            ) if not value
        ]
        if missing:
            raise ValueError(
                "AI_MODE is 'live' but these are not set: " + ", ".join(missing)
            )
    return mode


# Runs on import, i.e. at startup, so a bad AI_MODE or an incomplete live
# configuration stops the app instead of failing later on the first assessment.
AI_MODE = validate_ai_config(
    os.getenv("AI_MODE", "mock"), LLM_API_URL, LLM_API_KEY, LLM_MODEL
)
