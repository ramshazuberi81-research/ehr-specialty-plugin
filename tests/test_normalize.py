import pytest
from app.normalize import normalize


def obs(code, value, unit):
    return {"code": {"coding": [{"code": code}]}, "valueQuantity": {"value": value, "unit": unit}}


def test_hba1c_ifcc_to_ngsp():
    n = normalize(obs("4548-4", 64, "mmol/mol"))
    assert n["ok"] and n["value"] == pytest.approx(8.01, abs=0.01)
    n = normalize(obs("4548-4", 48, "mmol/mol"))
    assert n["ok"] and n["value"] == pytest.approx(6.54, abs=0.01)


def test_already_canonical_unit_unchanged():
    n = normalize(obs("4548-4", 6.5, "%"))
    assert n["ok"] and n["value"] == 6.5 and not n["issues"]
    n = normalize(obs("2339-0", 100, "mg/dL"))
    assert n["ok"] and n["value"] == 100


def test_glucose_mmol_to_mgdl():
    n = normalize(obs("2339-0", 5.5, "mmol/L"))
    assert n["ok"] and n["value"] == pytest.approx(99.09, abs=0.1)


def test_alias_maps_to_loinc():
    assert normalize(obs("A1C", 7.0, "%"))["code"] == "4548-4"


@pytest.mark.parametrize("o,msg", [
    (obs("4548-4", 85, "%"), "implausible"),
    (obs("2339-0", -5, "mg/dL"), "implausible"),
    (obs("4548-4", 7, "furlongs"), "unknown unit"),
    (obs("9999-9", 7, "%"), "unmapped code"),
    ({"code": {"coding": [{"code": "4548-4"}]}}, "no numeric value"),
    (obs("4548-4", 20.01, "%"), "implausible"),
])
def test_bad_input_is_flagged_not_corrected(o, msg):
    n = normalize(o)
    assert not n["ok"] and msg in n["issues"][0]


def test_lower_bound_inclusive():
    assert normalize(obs("4548-4", 3, "%"))["ok"]
