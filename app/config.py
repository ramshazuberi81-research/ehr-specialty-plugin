"""All configuration comes from environment variables (see .env.example)."""
import os


def fhir_base() -> str:
    return os.environ.get("FHIR_BASE", "http://localhost:8080/fhir").rstrip("/")


def webhook_secret() -> str:
    return os.environ.get("WEBHOOK_SECRET", "")


def anthropic_key() -> str:
    return os.environ.get("ANTHROPIC_API_KEY", "")


def nlp_model() -> str:
    return os.environ.get("NLP_MODEL", "claude-sonnet-5-5")
