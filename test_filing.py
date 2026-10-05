import asyncio

from app import filing
from app.filing import FLAG_SYS, SPEC_SYS, file_diagnosis, plan_filing, specialties_for


def cond(code=None, text=None, author="Practitioner/eye", cid="c1"):
    c = {"resourceType": "Condition", "id": cid, "subject": {"reference": "Patient/p1"},
         "recorder": {"reference": author}, "code": {}}
    if code:
        c["code"]["coding"] = [{"system": "http://hl7.org/fhir/sid/icd-10-cm", "code": code}]
    if text:
        c["code"]["text"] = text
    return c


def test_code_to_specialty():
    assert specialties_for("H40.9") == ["ophthalmology"]
    assert specialties_for("I10") == ["cardiology"]
    assert specialties_for("E11.319") == ["endocrinology", "ophthalmology"]  # dual filing
    assert specialties_for("B30.9") == ["ophthalmology"]                     # override beats range
    assert specialties_for("J30.1") == ["ent"]


def test_unknown_code_goes_to_general_never_dropped():
    assert specialties_for("Z99.9") == ["general"]


def test_free_text_is_suggestion_only():
    p = plan_filing(cond(text="Pink eye"))
    assert p["suggested"] and p["code"] == "H10.9"
    assert plan_filing(cond(code="H40.9"))["suggested"] is False


def test_unmatched_text_has_no_code():
    p = plan_filing(cond(text="mystery ailment"))
    assert p["code"] is None and p["specialties"] == ["general"] and p["suggested"]


class FakeResp:
    def __init__(self, body, status=200):
        self._b, self.status_code, self.text = body, status, str(body)

    def json(self):
        return self._b

    def raise_for_status(self):
        pass


class FakeClient:
    def __init__(self, roles):
        self.roles, self.posted = roles, []

    async def get(self, url, params=None, headers=None):
        return FakeResp({"entry": [{"resource": r} for r in self.roles]})

    async def post(self, url, json=None, headers=None):
        self.posted.append(json)
        return FakeResp({})


ROLES = [
    {"resourceType": "PractitionerRole", "practitioner": {"reference": "Practitioner/eye"},
     "specialty": [{"text": "Ophthalmology"}]},
    {"resourceType": "PractitionerRole", "practitioner": {"reference": "Practitioner/endo"},
     "specialty": [{"text": "Endocrinology"}]},
]


def run(coro):
    return asyncio.run(coro)


def test_dual_filing_creates_fyi_task_for_other_specialist():
    c = FakeClient(ROLES)
    out = run(file_diagnosis(c, cond(code="E11.319", author="Practitioner/endo")))
    assert set(out["filed_under"]) == {"endocrinology", "ophthalmology"}
    owners = [t["owner"] for t in out["tasks"]]
    assert owners == ["Practitioner/eye"]              # author (endo) is not notified
    entries = c.posted[0]["entry"]
    assert entries[0]["request"]["method"] == "PUT"    # tagged in place, no copy
    assert any(e["request"]["url"] == "Provenance" for e in entries)  # audit record


def test_free_text_gets_review_flag_and_confirm_task():
    c = FakeClient(ROLES)
    out = run(file_diagnosis(c, cond(text="pink eye", author="Practitioner/eye")))
    assert out["needs_coding_review"]
    assert any("Confirm diagnosis code" in t["description"] for t in out["tasks"])
    tags = c.posted[0]["entry"][0]["resource"]["meta"]["tag"]
    assert {"system": FLAG_SYS, "code": "needs-coding-review"} in tags


def test_already_filed_is_skipped_idempotent():
    c = FakeClient(ROLES)
    done = cond(code="H40.9")
    done["meta"] = {"tag": [{"system": SPEC_SYS, "code": "ophthalmology"}]}
    assert run(file_diagnosis(c, done)) == {"skipped": "already filed"}
    assert c.posted == []


def test_no_matching_specialist_is_flagged_for_manual_assignment():
    c = FakeClient([])  # nobody on file
    out = run(file_diagnosis(c, cond(code="I10")))
    task = c.posted[0]["entry"][-1]["resource"]
    assert out["tasks"][0]["owner"] is None and "assign manually" in task["note"][0]["text"]
