"""SMART Backend Services auth (client_credentials + signed JWT, RS384).

If SMART_CLIENT_ID is unset the plugin runs in dev mode: no auth, or a static
FHIR_TOKEN. Never use dev mode against a real system.
"""
import asyncio
import os
import time
import uuid

import httpx
import jwt

from .config import fhir_base

DEFAULT_SCOPE = " ".join([
    "system/Patient.read", "system/Encounter.read", "system/Observation.read",
    "system/Observation.write", "system/Condition.read", "system/Condition.write",
    "system/AllergyIntolerance.read", "system/MedicationRequest.read",
    "system/PractitionerRole.read", "system/Provenance.write", "system/Task.read",
    "system/Task.write",
])

_tok = {"value": None, "exp": 0.0}
_token_endpoint = None
_lock = asyncio.Lock()


async def _discover(client: httpx.AsyncClient) -> str:
    global _token_endpoint
    if not _token_endpoint:
        r = await client.get(f"{fhir_base()}/.well-known/smart-configuration",
                             headers={"Accept": "application/json"})
        r.raise_for_status()
        _token_endpoint = r.json()["token_endpoint"]
    return _token_endpoint


def _assertion(aud: str) -> str:
    client_id = os.environ["SMART_CLIENT_ID"]
    now = int(time.time())
    claims = {"iss": client_id, "sub": client_id, "aud": aud,
              "jti": uuid.uuid4().hex, "exp": now + 240}  # spec max is 5 minutes
    with open(os.environ.get("SMART_PRIVATE_KEY", "private_key.pem"), "rb") as f:
        return jwt.encode(claims, f.read(), algorithm="RS384",
                          headers={"kid": os.environ.get("SMART_KID", "plugin-key-1"), "typ": "JWT"})


async def auth_headers(client: httpx.AsyncClient) -> dict:
    base = {"Content-Type": "application/fhir+json", "Accept": "application/fhir+json"}
    if not os.environ.get("SMART_CLIENT_ID"):  # dev / sandbox only
        tok = os.environ.get("FHIR_TOKEN", "")
        return {**base, **({"Authorization": f"Bearer {tok}"} if tok else {})}
    async with _lock:
        if time.time() > _tok["exp"] - 60:
            endpoint = await _discover(client)
            r = await client.post(endpoint, data={
                "grant_type": "client_credentials",
                "scope": os.environ.get("SMART_SCOPE", DEFAULT_SCOPE),
                "client_assertion_type": "urn:ietf:params:oauth:client-assertion-type:jwt-bearer",
                "client_assertion": _assertion(endpoint)})
            r.raise_for_status()
            j = r.json()
            _tok.update(value=j["access_token"], exp=time.time() + int(j.get("expires_in", 300)))
    return {**base, "Authorization": f"Bearer {_tok['value']}"}
