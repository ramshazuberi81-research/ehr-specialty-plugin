"""Run the WHOLE app locally with fake synthetic data. No Docker, no FHIR server, no API key.

    pip install -r requirements.txt
    python scripts/demo_app.py          # then open http://localhost:8000/ask-page

Secret to type on the page: demo
A keyword-based stand-in replaces the language model (so wording must be simple, e.g.
"show records for Jane Doe"). With a real ANTHROPIC_API_KEY set, the real model is used instead.
"""
import json
import os
import re
import sys

os.environ.setdefault("FHIR_BASE", "http://fhir.demo/fhir")
os.environ.setdefault("WEBHOOK_SECRET", "demo")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import httpx  # noqa: E402
import uvicorn  # noqa: E402

from app import main, nlp  # noqa: E402
from app.filing import SPEC_SYS, TEXT_TO_ICD  # noqa: E402

ICD = "http://hl7.org/fhir/sid/icd-10-cm"


def cond(i, pid, text, code, spec, status="active"):
    return {"resourceType": "Condition", "id": i, "subject": {"reference": f"Patient/{pid}"},
            "clinicalStatus": {"coding": [{"code": status}]}, "onsetDateTime": "2024-03-01",
            "code": {"text": text, "coding": [{"system": ICD, "code": code}]},
            "meta": {"tag": [{"system": SPEC_SYS, "code": s} for s in spec]}}


def pat(i, given, family, dob):
    return {"resourceType": "Patient", "id": i, "name": [{"given": [given], "family": family}], "birthDate": dob}


DB = {
    "Patient": [pat("p1", "Jane", "Doe", "1980-02-03"), pat("p2", "John", "Smith", "1965-11-20"),
                pat("p3", "Sam", "Lee", "1990-05-05"), pat("p4", "Sam", "Lee", "1972-09-09")],
    "Condition": [cond("c1", "p1", "Type 2 diabetes with retinopathy", "E11.319", ["endocrinology", "ophthalmology"]),
                  cond("c2", "p1", "Hypertension", "I10", ["cardiology"]),
                  cond("c3", "p2", "Glaucoma", "H40.9", ["ophthalmology"]),
                  cond("c4", "p2", "Cataract", "H26.9", ["ophthalmology"], "resolved"),
                  cond("c5", "p3", "Migraine", "G43.9", ["neurology"])],
    "AllergyIntolerance": [{"resourceType": "AllergyIntolerance", "id": "a1", "patient": {"reference": "Patient/p1"},
                            "code": {"text": "Penicillin"}, "criticality": "high"}],
    "PractitionerRole": [{"resourceType": "PractitionerRole", "id": "r1", "practitioner": {"reference": "Practitioner/eye"},
                          "specialty": [{"text": "Ophthalmology"}]}],
    "Observation": [], "MedicationRequest": [], "Task": [], "Encounter": [],
}


def ref(r):
    for k in ("subject", "patient"):
        if k in r:
            return r[k].get("reference")


def fake_fhir(request: httpx.Request) -> httpx.Response:
    parts = request.url.path.split("/fhir")[-1].strip("/").split("/")
    q = dict(request.url.params)
    if request.method == "POST":                      # transaction: store posted resources
        for e in json.loads(request.content).get("entry", []):
            res = e["resource"]
            rows = DB.setdefault(res["resourceType"], [])
            res.setdefault("id", f"n{len(rows) + 1}")
            rows[:] = [r for r in rows if r.get("id") != res["id"]] + [res]
        return httpx.Response(200, json={"resourceType": "Bundle"})
    if len(parts) == 2:                               # read one resource
        hit = next((r for r in DB.get(parts[0], []) if r["id"] == parts[1]), None)
        return httpx.Response(200 if hit else 404, json=hit or {})
    rows = DB.get(parts[0], [])
    if "name" in q:
        rows = [r for r in rows if q["name"].lower() in json.dumps(r["name"]).lower()]
    if "birthdate" in q:
        rows = [r for r in rows if r.get("birthDate") == q["birthdate"]]
    if "patient" in q:
        rows = [r for r in rows if ref(r) == q["patient"]]
    if "_tag" in q:
        s, c = q["_tag"].split("|")
        rows = [r for r in rows if any(t["system"] == s and t["code"] == c for t in r.get("meta", {}).get("tag", []))]
    if "practitioner" in q:
        rows = [r for r in rows if r.get("practitioner", {}).get("reference") == q["practitioner"]]
    return httpx.Response(200, json={"entry": [{"resource": r} for r in rows]})


FILLER = {"show", "me", "my", "the", "records", "record", "for", "of", "chart", "pull", "up", "open", "get", "i", "am",
          "is", "name", "patient", "please", "born", "dob", "on", "birthday", "date", "of", "birth", "and", "a", "an", "to"}


async def stand_in_llm(system: str, user: str) -> dict:
    """Keyword stand-in for the model. Understands only simple phrasing."""
    text = re.search(r"<input>(.*)</input>", user, re.S).group(1)
    low = text.lower()
    if "Schema: {\"candidates\"" in system:
        hits = [v for k, v in sorted(TEXT_TO_ICD.items(), key=lambda kv: -len(kv[0])) if k in low]
        return {"candidates": [{"code": c, "display": d, "confidence": 0.6} for c, d in hits]}
    if "\"negated\"" in system:
        neg = [w for w in ("diabetes", "glaucoma", "hypertension") if re.search(rf"\b(no|denies|without)\b[^.]*{w}", low)]
        pos = [w for w in ("diabetes", "glaucoma", "hypertension") if w in low and w not in neg]
        return {"diagnoses": [{"text": w, "status": "active", "evidence": text[:80]} for w in pos],
                "negated": [{"text": w, "evidence": text[:80]} for w in neg], "medications": [], "allergies": []}
    dob = re.search(r"\d{4}-\d{2}-\d{2}", text)
    words = [w for w in re.findall(r"[A-Za-z']+", re.sub(r"\d{4}-\d{2}-\d{2}", " ", text)) if w.lower() not in FILLER]
    spec = next((s for s in ("ophthalmology", "cardiology", "endocrinology", "neurology") if s in low), "")
    words = [w for w in words if w.lower() != spec]
    return {"intent": "records" if words else "unknown", "name": " ".join(words[:3]),
            "birth_date": dob.group(0) if dob else "", "specialty": spec}


main.make_client = lambda: httpx.AsyncClient(transport=httpx.MockTransport(fake_fhir))
if not os.environ.get("ANTHROPIC_API_KEY"):
    main._llm = lambda client: stand_in_llm

if __name__ == "__main__":
    print("\nOpen http://localhost:8000/ask-page   (secret: demo)")
    print("Try: show records for Jane Doe | Sam Lee | Sam Lee born 1990-05-05 | John Smith ophthalmology\n")
    uvicorn.run(main.app, host="127.0.0.1", port=8000)
