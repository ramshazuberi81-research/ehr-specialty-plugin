"""Deterministic patient lookup for the natural-language 'ask' feature. No model involved here.

A spoken or typed name is NOT authentication. This only resolves a name to ONE patient or returns
candidates; it never guesses between several matches.
"""
from .filing import SPEC_SYS, _search, previsit_summary


def _display(p: dict) -> str:
    n = (p.get("name") or [{}])[0]
    return n.get("text") or " ".join(n.get("given", []) + [n.get("family", "")]).strip() or f"Patient/{p.get('id')}"


async def find_patients(client, name: str, birth_date: str = "") -> list:
    """Search Patients by name (and DOB if given). Every query token must appear in the patient's name."""
    tokens = [t for t in name.lower().replace(",", " ").split() if t]
    if not tokens:
        return []
    params = {"name": tokens[0]}
    if birth_date:
        params["birthdate"] = birth_date
    found = await _search(client, "Patient", **params)
    return [p for p in found if all(t in _display(p).lower() for t in tokens)]


async def specialties_on_file(client, patient_id: str) -> list:
    conds = await _search(client, "Condition", patient=f"Patient/{patient_id}")
    return sorted({t["code"] for c in conds for t in c.get("meta", {}).get("tag", [])
                   if t.get("system") == SPEC_SYS and t.get("code")})


async def answer_ask(client, parsed: dict) -> dict:
    """Resolve a parsed request to records. Returns one of: needs_name / not_found / ambiguous / records."""
    if parsed["intent"] != "records" or not parsed["name"]:
        return {"status": "needs_name", "message": "Say or type a name, e.g. 'show records for Jane Doe'."}
    matches = await find_patients(client, parsed["name"], parsed["birth_date"])
    if not matches:
        return {"status": "not_found", "message": "No patient matched that name."}
    if len(matches) > 1:
        return {"status": "ambiguous", "message": "More than one patient matched. Add a date of birth.",
                "candidates": [{"id": p["id"], "name": _display(p), "birthDate": p.get("birthDate")} for p in matches[:10]]}
    pid = matches[0]["id"]
    specs = [parsed["specialty"]] if parsed["specialty"] else await specialties_on_file(client, pid)
    return {"status": "records", "patient_id": pid,
            "summaries": [await previsit_summary(client, pid, s) for s in specs]}
