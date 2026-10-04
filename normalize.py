"""Feature 1: normalize incoming lab/vital Observations (units, codes, plausibility)."""
import uuid
from datetime import datetime, timezone
from typing import Optional

import httpx

from .auth import auth_headers
from .config import fhir_base

# canonical LOINC code -> section, unit, plausible range, unit converters
CATALOG = {
    "4548-4": dict(name="HbA1c", section="laboratory", unit="%", rng=(3, 20),
                   conv={"mmol/mol": lambda v: v / 10.929 + 2.15}),
    "2339-0": dict(name="Glucose", section="laboratory", unit="mg/dL", rng=(20, 1000),
                   conv={"mmol/L": lambda v: v * 18.016}),
    "8480-6": dict(name="Systolic BP", section="vital-signs", unit="mm[Hg]", rng=(40, 300),
                   conv={"mmHg": lambda v: v}),
}
ALIASES = {"HBA1C": "4548-4", "A1C": "4548-4", "GLU": "2339-0", "SBP": "8480-6"}


def get_code(obs: dict) -> Optional[str]:
    for c in obs.get("code", {}).get("coding", []):
        if c.get("code") in CATALOG:
            return c["code"]
        if c.get("code", "").upper() in ALIASES:
            return ALIASES[c["code"].upper()]
    return None


def normalize(obs: dict) -> dict:
    """Return {"ok": bool, "issues": [...], ...}. Implausible values are flagged, never corrected."""
    issues, code = [], get_code(obs)
    if not code:
        return {"ok": False, "issues": ["unmapped code"], "code": None}
    spec, q = CATALOG[code], obs.get("valueQuantity")
    if not q or "value" not in q:
        return {"ok": False, "issues": ["no numeric value"], "code": code}
    value, unit = float(q["value"]), q.get("unit") or q.get("code")
    if unit != spec["unit"]:
        if unit in spec["conv"]:
            value = spec["conv"][unit](value)
            issues.append(f"converted {q['value']} {unit} -> {round(value, 2)} {spec['unit']}")
        else:
            return {"ok": False, "issues": [f"unknown unit '{unit}'"], "code": code}
    lo, hi = spec["rng"]
    if not (lo <= value <= hi):
        return {"ok": False, "issues": [f"implausible value {round(value, 2)} (expected {lo}-{hi})"],
                "code": code}
    return {"ok": True, "code": code, "value": round(value, 2), "spec": spec, "issues": issues}


async def resolve_doctor(client: httpx.AsyncClient, obs: dict) -> Optional[str]:
    """Encounter participant first, then the patient's general practitioner."""
    h = await auth_headers(client)
    enc = obs.get("encounter", {}).get("reference")
    if enc:
        r = await client.get(f"{fhir_base()}/{enc}", headers=h)
        if r.status_code == 200:
            for p in r.json().get("participant", []):
                ref = p.get("individual", {}).get("reference", "")
                if ref.startswith("Practitioner/"):
                    return ref
    r = await client.get(f"{fhir_base()}/{obs['subject']['reference']}", headers=h)
    if r.status_code == 200:
        for gp in r.json().get("generalPractitioner", []):
            if gp.get("reference", "").startswith("Practitioner/"):
                return gp["reference"]
    return None


def build_bundle(orig: dict, n: dict, doctor: Optional[str]) -> dict:
    """One atomic transaction: derived Observation + Provenance + review Task."""
    now = datetime.now(timezone.utc).isoformat()
    orig_ref = f"Observation/{orig['id']}"
    obs_id, prov_id, task_id = (f"urn:uuid:{uuid.uuid4()}" for _ in range(3))
    entries = []

    if n["ok"]:
        spec = n["spec"]
        entries.append({"fullUrl": obs_id, "request": {"method": "POST", "url": "Observation"},
            "resource": {
                "resourceType": "Observation", "status": "preliminary",
                "category": [{"coding": [{"system": "http://terminology.hl7.org/CodeSystem/observation-category",
                                          "code": spec["section"]}]}],
                "code": {"coding": [{"system": "http://loinc.org", "code": n["code"], "display": spec["name"]}]},
                "subject": orig["subject"], "encounter": orig.get("encounter"),
                "effectiveDateTime": orig.get("effectiveDateTime", now),
                "valueQuantity": {"value": n["value"], "unit": spec["unit"],
                                  "system": "http://unitsofmeasure.org"},
                "derivedFrom": [{"reference": orig_ref}],
                "note": [{"text": "Auto-normalized: " + ("; ".join(n["issues"]) or "no changes")}]}})
        entries.append({"fullUrl": prov_id, "request": {"method": "POST", "url": "Provenance"},
            "resource": {"resourceType": "Provenance", "target": [{"reference": obs_id}],
                "recorded": now, "activity": {"text": "automated normalization"},
                "agent": [{"type": {"text": "assembler"}, "who": {"display": "EHR Normalize Plugin"}}],
                "entity": [{"role": "source", "what": {"reference": orig_ref}}]}})

    task = {"resourceType": "Task", "status": "requested", "intent": "order",
            "priority": "routine" if n["ok"] else "urgent",
            "description": ("Review auto-normalized result and sign off" if n["ok"]
                            else "Data quality issue, manual review needed: " + "; ".join(n["issues"])),
            "for": orig["subject"], "authoredOn": now,
            "focus": {"reference": obs_id if n["ok"] else orig_ref}}
    if doctor:
        task["owner"] = {"reference": doctor}
    else:
        task["note"] = [{"text": "No responsible practitioner found: assign manually"}]
    entries.append({"fullUrl": task_id, "request": {"method": "POST", "url": "Task"}, "resource": task})
    return {"resourceType": "Bundle", "type": "transaction", "entry": entries}
