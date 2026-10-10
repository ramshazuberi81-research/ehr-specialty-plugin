"""FastAPI app: webhooks for Observations and Conditions, plus the pre-visit summary endpoint.

Run:  uvicorn app.main:app --port 8000
"""
import hmac

import httpx
from pathlib import Path

from fastapi import FastAPI, Header, HTTPException, Request
from fastapi.responses import FileResponse, HTMLResponse

from .auth import auth_headers
from .cds_hooks import SERVICE_ID, build_cards, discovery
from .cds_hooks import KNOWN_SPECIALTIES
from .config import anthropic_key, fhir_base, webhook_secret
from .filing import file_diagnosis, previsit_summary, render_text
from .lookup import answer_ask
from .nlp import NLPUnavailable, claude_llm, draft_conditions, extract_note, interpret_ask, suggest_codes
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
        suggester = None
        if anthropic_key():       # NLP fallback for free text the table cannot match (suggestion only)
            llm = claude_llm(client)
            suggester = lambda text: suggest_codes(llm, text)
        try:
            return await file_diagnosis(client, cond, suggester)
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


# ---------------------------------------------------------------- NLP (optional, needs ANTHROPIC_API_KEY)
def _llm(client):
    try:
        return claude_llm(client)
    except NLPUnavailable as e:
        raise HTTPException(503, str(e))


async def _guarded(coro):
    try:
        return await coro
    except NLPUnavailable as e:
        raise HTTPException(502, str(e))


@app.post("/nlp/suggest-code")
async def nlp_suggest_code(req: Request, x_webhook_secret: str = Header(None)):
    """Free-text diagnosis -> ranked ICD-10 candidates. Suggestions only; a doctor confirms."""
    check_secret(x_webhook_secret)
    body = await req.json()
    async with make_client() as client:
        return {"candidates": await _guarded(suggest_codes(_llm(client), body.get("text", ""))),
                "needs_doctor_confirmation": True}


@app.post("/nlp/extract-note")
async def nlp_extract_note(req: Request, x_webhook_secret: str = Header(None)):
    """Clinical note -> DRAFT findings and unconfirmed Condition drafts. Nothing is written to the chart."""
    check_secret(x_webhook_secret)
    body = await req.json()
    async with make_client() as client:
        found = await _guarded(extract_note(_llm(client), body.get("note", "")))
    pid = body.get("patient_id")
    return {**found, "condition_drafts": draft_conditions(found, f"Patient/{pid}") if pid else []}


@app.post("/ask")
async def ask(req: Request, x_webhook_secret: str = Header(None)):
    """Plain language in ('show records for Jane Doe'), records out. The model only reads the request,
    never the chart; the lookup is deterministic and never guesses between several matching names."""
    check_secret(x_webhook_secret)
    body = await req.json()
    async with make_client() as client:
        parsed = await _guarded(interpret_ask(_llm(client), body.get("text", ""), KNOWN_SPECIALTIES))
        result = await answer_ask(client, parsed)
    for S in result.get("summaries", []):
        S["text"] = render_text(S)
    return {"understood": parsed, **result}


@app.get("/ask-page", response_class=HTMLResponse)
async def ask_page():
    return (Path(__file__).parent / "static" / "ask.html").read_text()


# ---------------------------------------------------------------- installable web app (PWA) files
_STATIC = Path(__file__).parent / "static"
_PWA = {"/manifest.webmanifest": ("manifest.webmanifest", "application/manifest+json"),
        "/sw.js": ("sw.js", "application/javascript"),
        "/icon-192.png": ("icon-192.png", "image/png"),
        "/icon-512.png": ("icon-512.png", "image/png")}


def _pwa_route(path, fname, mime):
    async def serve():
        return FileResponse(_STATIC / fname, media_type=mime, headers={"Cache-Control": "no-cache"})
    app.add_api_route(path, serve, methods=["GET"], include_in_schema=False)


for _p, (_f, _m) in _PWA.items():
    _pwa_route(_p, _f, _m)
