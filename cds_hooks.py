"""CDS Hooks service: shows the specialty pre-visit summary natively in an EHR when a chart opens.

Hook: patient-view.  Spec: https://cds-hooks.hl7.org
  GET  /cds-services                    discovery (unauthenticated, per spec)
  POST /cds-services/ehr-previsit       returns {"cards": [...]}

The specialty comes from the logged-in doctor's PractitionerRole, never guessed. If it cannot be
determined, or there is nothing to show, the service returns NO cards (silence beats noise).

PROTOTYPE AUTH: shared secret header. Real CDS Hooks clients send a signed JWT (Bearer) that the
service must verify against the EHR's JWKS. That is required before any pilot.
"""
from fastapi import APIRouter, Header, HTTPException, Request

from .filing import ALIASES, OVERRIDES, RANGES, _search, previsit_summary, render_text, role_matches

SERVICE_ID = "ehr-previsit"
router = APIRouter()

KNOWN_SPECIALTIES = sorted({s for _, _, s in RANGES} | set(ALIASES) | {s for _, specs in OVERRIDES for s in specs})


def discovery() -> dict:
    return {"services": [{
        "hook": "patient-view",
        "id": SERVICE_ID,
        "title": "Specialty pre-visit summary (prototype)",
        "description": "One-screen, source-linked summary of this patient's problems for the viewing doctor's specialty.",
        "prefetch": {"patient": "Patient/{{context.patientId}}"},
    }]}


async def specialties_of_user(client, user_id: str) -> list:
    ref = user_id if "/" in user_id else f"Practitioner/{user_id}"
    roles = await _search(client, "PractitionerRole", practitioner=ref)
    return [s for s in KNOWN_SPECIALTIES if any(role_matches(r, s) for r in roles)]


def card_from_summary(S: dict) -> dict | None:
    if not (S["active"] or S["past"] or S["alerts"]):
        return None  # nothing recorded for this specialty: no card
    n_review = sum(1 for i in S["active"] + S["past"] if i.get("needs_review"))
    bits = [f"{len(S['active'])} active problem(s)"]
    if S["alerts"]:
        bits.append(f"{len(S['alerts'])} allergy alert(s)")
    if n_review:
        bits.append(f"{n_review} code(s) awaiting confirmation")
    summary = f"{S['specialty'].title()} pre-visit: " + ", ".join(bits)
    return {
        "summary": summary[:140],
        "indicator": "warning" if (S["alerts"] or n_review) else "info",
        "source": {"label": "EHR Specialty Filing Plugin (synthetic-data prototype)"},
        "detail": "```\n" + render_text(S) + "\n```",
    }


async def build_cards(client, body: dict) -> dict:
    ctx = body.get("context", {})
    patient_id, user_id = ctx.get("patientId"), ctx.get("userId")
    if body.get("hook") != "patient-view" or not patient_id or not user_id:
        raise HTTPException(422, "patient-view request needs context.patientId and context.userId")
    cards = []
    for spec in (await specialties_of_user(client, user_id))[:2]:
        card = card_from_summary(await previsit_summary(client, patient_id, spec))
        if card:
            cards.append(card)
    return {"cards": cards}
