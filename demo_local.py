"""Offline demo: no server needed. Runs the 4-diagnosis story from the demo brief against an
in-memory fake FHIR store (synthetic data) and prints the ophthalmology pre-visit summary.

    python scripts/demo_local.py
"""
import asyncio
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("FHIR_BASE", "http://fhir.test/fhir")

from app.filing import SPEC_SYS, file_diagnosis, previsit_summary, render_text  # noqa: E402


class R:
    def __init__(self, body, status=200):
        self._b, self.status_code, self.text = body, status, str(body)[:200]

    def json(self):
        return self._b

    def raise_for_status(self):
        pass


class FakeFhir:
    """Tiny in-memory FHIR server: just enough GET/search/transaction for the demo."""

    def __init__(self):
        self.db = {}

    def put(self, res):
        self.db[f"{res['resourceType']}/{res['id']}"] = res

    async def get(self, url, params=None, headers=None):
        path = url.split("/fhir/", 1)[1]
        if "/" in path:
            return R(self.db[path]) if path in self.db else R({}, 404)
        rtype, p = path, params or {}
        out = [r for k, r in self.db.items() if k.startswith(rtype + "/")]
        if "patient" in p:
            out = [r for r in out if p["patient"] in (r.get("subject", {}).get("reference"),
                                                       r.get("patient", {}).get("reference"))]
        if "_tag" in p:
            sys_, code = p["_tag"].split("|")
            out = [r for r in out if {"system": sys_, "code": code} in r.get("meta", {}).get("tag", [])]
        if "_id" in p:
            ids = p["_id"].split(",")
            out = [r for r in out if r["id"] in ids]
        return R({"entry": [{"resource": r} for r in out]})

    async def post(self, url, json=None, headers=None):
        for i, e in enumerate(json["entry"]):
            res = e["resource"]
            if e["request"]["method"] == "PUT":
                self.put(res)
            else:
                res["id"] = f"{res['resourceType'].lower()}-{len(self.db)}-{i}"
                self.put(res)
        return R({})


def icd(code):
    return {"coding": [{"system": "http://hl7.org/fhir/sid/icd-10-cm", "code": code}]}


async def main():
    f = FakeFhir()
    f.put({"resourceType": "Patient", "id": "p1", "name": [{"text": "Amina (synthetic)"}], "birthDate": "1960-01-01"})
    f.put({"resourceType": "AllergyIntolerance", "id": "a1", "patient": {"reference": "Patient/p1"},
           "code": {"text": "Penicillin"}, "criticality": "high",
           "clinicalStatus": {"coding": [{"code": "active"}]}})
    for pid, spec in [("eye", "Ophthalmology"), ("endo", "Endocrinology"), ("cardio", "Cardiology")]:
        f.put({"resourceType": "PractitionerRole", "id": f"r-{pid}", "practitioner": {"reference": f"Practitioner/{pid}"},
               "specialty": [{"text": spec}]})

    forms = [("c1", "Glaucoma", icd("H40.9"), "eye"), ("c2", "Pink eye", None, "eye"),
             ("c3", "Diabetic retinopathy", icd("E11.319"), "endo"), ("c4", "Hypertension", icd("I10"), "endo")]
    for cid, text, coding, author in forms:
        cond = {"resourceType": "Condition", "id": cid, "subject": {"reference": "Patient/p1"},
                "recorder": {"reference": f"Practitioner/{author}"},
                "clinicalStatus": {"coding": [{"code": "active"}]}, "recordedDate": "2026-09-01",
                "code": {"text": text, **(coding or {})}}
        f.put(cond)
        out = await file_diagnosis(f, cond)
        print(f"saved {text!r:28} -> {out['filed_under']}  review={out['needs_coding_review']}")

    print("\n" + render_text(await previsit_summary(f, "p1", "ophthalmology")))


if __name__ == "__main__":
    asyncio.run(main())
