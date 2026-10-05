"""All configuration comes from environment variables (see .env.example)."""
import os


def fhir_base() -> str:
    return os.environ.get("FHIR_BASE", "http://localhost:8080/fhir").rstrip("/")


def webhook_secret() -> str:
    return os.environ.get("WEBHOOK_SECRET", "")
