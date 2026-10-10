"""Feature 2: file a saved Condition under specialty section(s) and build pre-visit summaries.

A doctor saves ONE diagnosis form. This module tags the Condition in place
(no copies), writes a Provenance record, creates tasks for other specialists,
and can build a source-linked pre-visit summary for any specialty.
"""
import copy
from datetime import datetime, timezone

from .auth import auth_headers
from .config import fhir_base

SPEC_SYS = "urn:ehr-plugin:specialty"   # tag: which specialty section(s) an entry belongs to
FLAG_SYS = "urn:ehr-plugin:flag"        # tag: e.g. needs-coding-review


# =====================================================================
# 1. Diagnosis code -> specialty
# =====================================================================
# Overrides win over ranges (longest prefix first). Dots are ignored when matching.
OVERRIDES = [
    ("B30",  ["ophthalmology"]),                       # viral conjunctivitis sits in the infections chapter
    ("E103", ["endocrinology", "ophthalmology"]),      # diabetic eye complications (type 1)
    ("E113", ["endocrinology", "ophthalmology"]),      # (type 2)
    ("E133", ["endocrinology", "ophthalmology"]),      # (other specified diabetes)
    ("J30",  ["ent"]),                                 # allergic rhinitis
]
RANGES = [  # (first 3 chars low, high, specialty)
    ("A00", "B99", "infectious-disease"), ("C00", "D49", "oncology"),
    ("E10", "E14", "endocrinology"),      ("F00", "F99", "psychiatry"),
    ("G00", "G99", "neurology"),          ("H00", "H59", "ophthalmology"),
    ("H60", "H95", "ent"),                ("I00", "I99", "cardiology"),
    ("J00", "J99", "pulmonology"),        ("K00", "K95", "gastroenterology"),
    ("L00", "L99", "dermatology"),        ("M00", "M99", "musculoskeletal"),
    ("N00", "N99", "urology-nephrology"),
]
# How a specialty is written on a PractitionerRole (used to find doctors)
ALIASES = {"ent": ["ent", "otolaryngology"], "urology-nephrology": ["urolog", "nephrolog"],
           "musculoskeletal": ["orthop", "rheumat"], "psychiatry": ["psychiat"]}

# Free-text fallback. These are SUGGESTIONS only; the doctor must confirm the code.
TEXT_TO_ICD = {
    "diabetic retinopathy": ("E11.319", "Type 2 diabetes with diabetic retinopathy"),
    "pink eye":     ("H10.9", "Conjunctivitis, unspecified"),
    "conjunctivitis": ("H10.9", "Conjunctivitis, unspecified"),
    "glaucoma":     ("H40.9", "Glaucoma, unspecified"),
    "cataract":     ("H26.9", "Cataract, unspecified"),
    "type 2 diabetes": ("E11.9", "Type 2 diabetes mellitus"),
    "hypertension": ("I10", "Essential hypertension"),
}


def _norm(code: str) -> str:
    return code.upper().replace(".", "").strip()


def specialties_for(icd10: str) -> list:
    c = _norm(icd10)
    for prefix, specs in sorted(OVERRIDES, key=lambda x: -len(x[0])):
        if c.startswith(prefix):
            return list(specs)
    for lo, hi, spec in RANGES:
        if lo <= c[:3] <= hi:
            return [spec]
    return ["general"]            # unknown code: never drop it, never guess


def _icd_from(cond: dict):
    for c in cond.get("code", {}).get("coding", []):
        if "icd-10" in c.get("system", "").lower() and c.get("code"):
            return c["code"]
    return None


def _label(cond: dict) -> str:
    code = cond.get("code", {})
    return code.get("text") or next((c.get("display") for c in code.get("coding", []) if c.get("display")), "diagnosis")


def plan_filing(cond: dict) -> dict:
    """Decide which specialty section(s) a Condition belongs to."""
    code = _icd_from(cond)
    if code:
        return {"code": code, "specialties": specialties_for(code), "suggested": False}
    text = (cond.get("code", {}).get("text", "") + " " + _label(cond)).lower()
    for key in sorted(TEXT_TO_ICD, key=len, reverse=True):
        if key in text:
            icd, disp = TEXT_TO_ICD[key]
            return {"code": icd, "display": disp, "specialties": specialties_for(icd), "suggested": True}
    return {"code": None, "specialties": ["general"], "suggested": True}


# =====================================================================
# 2. File the diagnosis (tag in place + provenance + tasks, one transaction)
# =====================================================================
def _has_tag(res, system):
    return any(t.get("system") == system for t in res.get("meta", {}).get("tag", []))


def _author_ref(cond):
    for k in ("recorder", "asserter"):
        ref = cond.get(k, {}).get("reference", "")
        if ref.startswith("Practitioner/"):
            return ref
    return None


def _role_text(role):
    parts = []
    for s in role.get("specialty", []):
        parts.append(s.get("text", ""))
        parts += [c.get("display", "") + " " + c.get("code", "") for c in s.get("coding", [])]
    return " ".join(parts).lower()


def role_matches(role, spec):
    return any(a in _role_text(role) for a in ALIASES.get(spec, [spec]))


async def _search(client, rtype, **params):
    r = await client.get(f"{fhir_base()}/{rtype}", params={**params, "_count": 200}, headers=await auth_headers(client))
    r.raise_for_status()
    return [e["resource"] for e in r.json().get("entry", [])]   # NOTE: first page only (prototype)


async def file_diagnosis(client, cond: dict, suggester=None) -> dict:
    """`suggester` (optional async fn text -> [{code, display}]) is the NLP fallback for free text that the
    built-in table cannot match. Its answer is still only a SUGGESTION: the record is flagged for review."""
    if cond.get("resourceType") != "Condition" or not cond.get("id"):
        return {"skipped": "not a saved Condition"}
    if _has_tag(cond, SPEC_SYS):
        return {"skipped": "already filed"}               # idempotent, also stops webhook loops

    plan, author = plan_filing(cond), _author_ref(cond)
    if plan["code"] is None and suggester:
        try:
            cands = await suggester(_label(cond))
        except Exception:                                   # NLP is optional: any failure keeps the safe default
            cands = []
        if cands:
            top = cands[0]
            plan = {"code": top["code"], "display": top.get("display"), "suggested": True,
                    "specialties": specialties_for(top["code"]), "nlp": True}
    now = datetime.now(timezone.utc).isoformat()
    ref = f"Condition/{cond['id']}"
    roles = await _search(client, "PractitionerRole")
    author_roles = [r for r in roles if author and r.get("practitioner", {}).get("reference") == author]

    updated = copy.deepcopy(cond)
    tags = updated.setdefault("meta", {}).setdefault("tag", [])
    for s in plan["specialties"]:
        tags.append({"system": SPEC_SYS, "code": s})
    if plan["suggested"]:
        tags.append({"system": FLAG_SYS, "code": "needs-coding-review"})

    entries = [{"request": {"method": "PUT", "url": ref}, "resource": updated},
               {"request": {"method": "POST", "url": "Provenance"}, "resource": {
                   "resourceType": "Provenance", "target": [{"reference": ref}], "recorded": now,
                   "activity": {"text": "automated specialty filing"},
                   "agent": [{"type": {"text": "assembler"}, "who": {"display": "EHR Specialty Filing Plugin"}}]
                            + ([{"type": {"text": "author"}, "who": {"reference": author}}] if author else [])}}]
    tasks = []

    def add_task(desc, owner, spec=None, priority="routine"):
        t = {"resourceType": "Task", "status": "requested", "intent": "order", "priority": priority,
             "description": desc, "for": cond.get("subject"), "authoredOn": now, "focus": {"reference": ref}}
        if spec:
            t["performerType"] = [{"text": spec}]
        if owner:
            t["owner"] = {"reference": owner}
        else:
            t["note"] = [{"text": "No matching practitioner found: assign manually"}]
        entries.append({"request": {"method": "POST", "url": "Task"}, "resource": t})
        tasks.append({"description": desc, "owner": owner})

    if plan["suggested"]:   # code was guessed from text (or unknown): doctor must confirm
        sug = f"suggested {plan['code']} ({plan.get('display')})" if plan["code"] else "no code could be suggested"
        add_task(f"Confirm diagnosis code for '{_label(cond)}': {sug}", author)

    for s in plan["specialties"]:       # FYI to specialists who are not the author
        if s == "general" or any(role_matches(r, s) for r in author_roles):
            continue
        spec_role = next((r for r in roles if role_matches(r, s)), None)
        owner = spec_role["practitioner"]["reference"] if spec_role else None
        add_task(f"FYI: new diagnosis '{_label(cond)}' filed under {s} for this patient", owner, spec=s)

    r = await client.post(fhir_base(), json={"resourceType": "Bundle", "type": "transaction", "entry": entries},
                          headers=await auth_headers(client))
    if r.status_code >= 300:
        raise RuntimeError(f"FHIR write failed: {r.status_code} {r.text[:300]}")
    return {"filed_under": plan["specialties"], "code": plan["code"],
            "needs_coding_review": plan["suggested"], "tasks": tasks}


# =====================================================================
# 3. Pre-visit summary (built only from what is in the chart, every line has a source)
# =====================================================================
ACTIVE = {"active", "recurrence", "relapse"}
OPEN_TASK = {"draft", "requested", "received", "accepted", "ready", "in-progress"}


def _first_coding_text(cc, default="(unnamed)"):
    cc = cc or {}
    return cc.get("text") or next((c.get("display") or c.get("code") for c in cc.get("coding", [])), default)


def _status(res, field="clinicalStatus"):
    return next((c.get("code") for c in res.get(field, {}).get("coding", [])), None)


def _date(res):
    for k in ("onsetDateTime", "recordedDate", "effectiveDateTime", "authoredOn"):
        if res.get(k):
            return res[k][:10]
    return ""


def _item(res, text, **extra):
    return {"text": text, "source": f"{res['resourceType']}/{res['id']}", **extra}


async def previsit_summary(client, patient_id: str, specialty: str) -> dict:
    pref = f"Patient/{patient_id}"
    h = await auth_headers(client)
    pr = await client.get(f"{fhir_base()}/{pref}", headers=h)
    pat = pr.json() if pr.status_code == 200 else {}
    nm = (pat.get("name") or [{}])[0]
    name = nm.get("text") or " ".join(nm.get("given", []) + [nm.get("family", "")]).strip() or pref

    tag = f"{SPEC_SYS}|{specialty}"
    conds = await _search(client, "Condition", patient=pref, _tag=tag)
    allergies = await _search(client, "AllergyIntolerance", patient=pref)
    obs = await _search(client, "Observation", patient=pref, _tag=tag)
    meds = await _search(client, "MedicationRequest", patient=pref)
    tasks = await _search(client, "Task", patient=pref)
    cond_refs = {f"Condition/{c['id']}" for c in conds}
    enc_ids = sorted({c["encounter"]["reference"].split("/")[-1] for c in conds
                      if c.get("encounter", {}).get("reference")})
    encs = await _search(client, "Encounter", _id=",".join(enc_ids)) if enc_ids else []

    S = {"patient": {"id": patient_id, "name": name, "birthDate": pat.get("birthDate")},
         "specialty": specialty, "generated": datetime.now(timezone.utc).isoformat(),
         "alerts": [], "active": [], "unknown": [], "past": [], "medications": [], "results": [],
         "visits": [], "open_items": [], "gaps": []}

    for a in allergies:
        if _status(a) in ("inactive", "resolved"):
            continue
        crit = f", criticality: {a['criticality']}" if a.get("criticality") else ""
        S["alerts"].append(_item(a, f"ALLERGY: {_first_coding_text(a.get('code'))}{crit}"))

    for c in sorted(conds, key=_date, reverse=True):
        st = _status(c) or "status not recorded"
        review = _has_tag(c, FLAG_SYS)
        code = _icd_from(c)
        txt = f"{_label(c)}{f' ({code})' if code else ''} - {st}" + (f", {_date(c)}" if _date(c) else "")
        if review:
            txt += "  [code awaiting doctor confirmation]"
        # Unknown status is never silently treated as "past": it gets its own bucket, shown to the doctor.
        bucket = "active" if st in ACTIVE else ("unknown" if st == "status not recorded" else "past")
        S[bucket].append(_item(c, txt, needs_review=review))

    for m in meds:
        linked = [r.get("reference") for r in m.get("reasonReference", [])]
        if cond_refs.intersection(linked):
            dose = (m.get("dosageInstruction") or [{}])[0].get("text", "")
            S["medications"].append(_item(m, f"{_first_coding_text(m.get('medicationCodeableConcept'))}"
                                             f"{' - ' + dose if dose else ''} ({m.get('status', 'status not recorded')})"))

    for o in sorted(obs, key=_date, reverse=True):
        q = o.get("valueQuantity", {})
        val = f"{q.get('value')} {q.get('unit', '')}".strip() if "value" in q else o.get("valueString", "(no value)")
        S["results"].append(_item(o, f"{_first_coding_text(o.get('code'))}: {val} ({_date(o)})"))

    for e in sorted(encs, key=lambda e: e.get("period", {}).get("start", ""), reverse=True)[:3]:
        S["visits"].append(_item(e, f"Visit {e.get('period', {}).get('start', '')[:10] or '(date not recorded)'}"
                                    f" - {_first_coding_text((e.get('type') or [{}])[0], 'type not recorded')}"))

    for t in tasks:
        if t.get("status") in OPEN_TASK and t.get("focus", {}).get("reference") in cond_refs:
            S["open_items"].append(_item(t, f"OPEN: {t.get('description', '')}"))

    if not allergies:
        S["gaps"].append("No allergy information recorded (this is NOT the same as 'no known allergies').")
    if not conds:
        S["gaps"].append(f"No {specialty} history recorded for this patient.")
    elif not S["medications"]:
        S["gaps"].append(f"No medications linked to the {specialty} conditions.")
    if conds and not obs:
        S["gaps"].append(f"No {specialty} test results on file.")
    return S


def render_text(S: dict) -> str:
    out = [f"PRE-VISIT SUMMARY - {S['specialty'].upper()}",
           f"Patient: {S['patient']['name']}" + (f" (DOB {S['patient']['birthDate']})" if S['patient']['birthDate'] else "")]
    for title, key in [("ALERTS", "alerts"), ("ACTIVE PROBLEMS", "active"), ("STATUS NOT RECORDED (confirm active or past)", "unknown"), ("PAST PROBLEMS", "past"),
                       ("MEDICATIONS", "medications"), ("RESULTS", "results"),
                       ("RECENT VISITS", "visits"), ("OPEN ITEMS", "open_items")]:
        if S[key]:
            out += ["", title] + [f"  - {i['text']}   [{i['source']}]" for i in S[key]]
    if S["gaps"]:
        out += ["", "NOT RECORDED / GAPS"] + [f"  - {g}" for g in S["gaps"]]
    return "\n".join(out)
