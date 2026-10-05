"""FastAPI app: webhooks for Observations and Conditions, plus the pre-visit summary endpoint.

Run:  uvicorn app.main:app --port 8000
"""
import hmac

import httpx
from fastapi import FastAPI, Header, HTTPException, Request

from .auth import auth_headers
from .cds_hooks import SERVICE_ID, build_cards, discovery
from .config import fhir_base, webhook_secret
from .filing import file_diagnosis, previsit_summary, render_text
from .normalize import build_bundle, normalize, resolve_doctor

app = FastAPI(title="EHR Specialty Filing & Normalization Plugin", version="0.1.0")


def make_client() -> httpx.AsyncClient:
    return httpx.AsyncClient(timeout=15)


def check_secret(provided) -> None:
    expected = webhook_secret()
    if not expected:
        raise HTTPException(503, "WEBHOOK_SECRET is not configured")
    if not provided or not hmac.compare_digest(provided, expected):
        raise HTTPException(401, "unauthorized")


@app.get("/health")
async def health():
    return {"status": "ok"}


@app.post("/webhook/observation")
async def on_observation(req: Request, x_webhook_secret: str = Header(None)):
    check_secret(x_webhook_secret)
    obs = await req.json()
    if obs.get("resourceType") != "Observation" or obs.get("status") == "preliminary":
        return {"skipped": True}  # skip our own derived records (prevents infinite loops)
    n = normalize(obs)
    async with make_client() as client:
        doctor = await resolve_doctor(client, obs)
        r = await client.post(fhir_base(), json=build_bundle(obs, n, doctor),
                              headers=await auth_headers(client))
        if r.status_code >= 300:
            raise HTTPException(502, f"FHIR write failed: {r.text[:300]}")
    return {"normalized": n["ok"], "issues": n["issues"], "assigned_to": doctor}


@app.post("/webhook/condition")
async def on_condition(req: Request, x_webhook_secret: str = Header(None)):
    check_secret(x_webhook_secret)
    cond = await req.json()
    async with make_client() as client:
        try:
            return await file_diagnosis(client, cond)
        except RuntimeError as e:
            raise HTTPException(502, str(e))


@app.get("/previsit/{patient_id}")
async def previsit(patient_id: str, specialty: str, x_webhook_secret: str = Header(None)):
    check_secret(x_webhook_secret)  # prototype auth only: use real user auth in production
    async with make_client() as client:
        S = await previsit_summary(client, patient_id, specialty.lower())
    return {**S, "text": render_text(S)}


@app.get("/cds-services")
async def cds_discovery():
    return discovery()  # unauthenticated by spec


@app.post(f"/cds-services/{SERVICE_ID}")
async def cds_patient_view(req: Request, x_webhook_secret: str = Header(None)):
    check_secret(x_webhook_secret)  # prototype only: real CDS Hooks uses a signed JWT from the EHR
    body = await req.json()
    async with make_client() as client:
        return await build_cards(client, body)
