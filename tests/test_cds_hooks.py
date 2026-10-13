import asyncio

import pytest
from fastapi import HTTPException

from app.cds_hooks import build_cards, discovery, specialties_of_user


class FakeResp:
    """Minimal stand-in for an httpx response (defined here so this file has no cross-test imports)."""
    def __init__(self, body, status=200):
        self._b, self.status_code, self.text = body, status, str(body)

    def json(self):
        return self._b

    def raise_for_status(self):
        pass


class Router:
    """Tiny fake FHIR server: returns canned resources by resource type."""
    def __init__(self, data):
        self.data = data

    async def get(self, url, params=None, headers=None):
        tail = url.rsplit("/fhir/", 1)[1]
        if tail.startswith("Patient/"):
            return FakeResp(self.data.get("Patient", {}))
        return FakeResp({"entry": [{"resource": r} for r in self.data.get(tail, [])]})


ROLE = {"resourceType": "PractitionerRole", "specialty": [{"text": "Ophthalmology"}]}
COND = {"resourceType": "Condition", "id": "c1", "clinicalStatus": {"coding": [{"code": "active"}]},
        "code": {"text": "Glaucoma", "coding": [{"system": "http://hl7.org/fhir/sid/icd-10-cm", "code": "H40.9"}]}}
ALLERGY = {"resourceType": "AllergyIntolerance", "id": "a1", "code": {"text": "Penicillin"}, "criticality": "high"}


def run(c):
    return asyncio.run(c)


def test_discovery_declares_patient_view():
    assert discovery()["services"][0]["hook"] == "patient-view"


def test_specialty_comes_from_practitioner_role():
    assert run(specialties_of_user(Router({"PractitionerRole": [ROLE]}), "Practitioner/eye")) == ["ophthalmology"]


def test_card_has_summary_under_140_chars_and_warns_on_allergy():
    r = Router({"PractitionerRole": [ROLE], "Condition": [COND], "AllergyIntolerance": [ALLERGY]})
    out = run(build_cards(r, {"hook": "patient-view", "context": {"userId": "Practitioner/eye", "patientId": "p1"}}))
    card = out["cards"][0]
    assert len(card["summary"]) <= 140 and card["indicator"] == "warning"
    assert "Condition/c1" in card["detail"]  # source-linked


def test_unknown_specialty_returns_no_cards_never_guesses():
    out = run(build_cards(Router({"PractitionerRole": []}),
                          {"hook": "patient-view", "context": {"userId": "x", "patientId": "p1"}}))
    assert out == {"cards": []}


def test_nothing_recorded_returns_no_cards():
    out = run(build_cards(Router({"PractitionerRole": [ROLE]}),
                          {"hook": "patient-view", "context": {"userId": "x", "patientId": "p1"}}))
    assert out == {"cards": []}


def test_bad_request_rejected():
    with pytest.raises(HTTPException):
        run(build_cards(Router({}), {"hook": "order-sign", "context": {}}))


def test_unknown_status_is_not_called_past_and_is_counted_on_card():
    no_status = {k: v for k, v in COND.items() if k != "clinicalStatus"}
    r = Router({"PractitionerRole": [ROLE], "Condition": [no_status]})
    card = run(build_cards(r, {"hook": "patient-view", "context": {"userId": "x", "patientId": "p1"}}))["cards"][0]
    assert "1 with status not recorded" in card["summary"] and card["indicator"] == "warning"
    assert "STATUS NOT RECORDED" in card["detail"] and "PAST PROBLEMS" not in card["detail"]
