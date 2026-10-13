"""Evaluate the ICD-10 -> specialty table against clinician-labelled gold data.

    python scripts/evaluate_filing.py data/gold.csv

CSV columns:  code, gold_specialties      (gold = clinician-assigned, '|' separated)
Optional:     weight                      (e.g. how often the code occurs locally; default 1)

Reports exact-match accuracy, per-specialty precision/recall, the share routed to 'general',
and every disagreement, so the clinician reviewer can fix the table or the label.
Uses only code-level data (no patient records).
"""
import csv
import os
import sys
from collections import defaultdict

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("FHIR_BASE", "http://fhir.test/fhir")
from app.filing import specialties_for  # noqa: E402


def main(path):
    rows = list(csv.DictReader(open(path, newline="", encoding="utf-8")))
    tp, fp, fn = defaultdict(float), defaultdict(float), defaultdict(float)
    total = exact = general = 0.0
    errors = []
    for r in rows:
        w = float(r.get("weight") or 1)
        gold = set(filter(None, (r["gold_specialties"] or "").lower().split("|")))
        pred = set(specialties_for(r["code"]))
        total += w
        exact += w * (gold == pred)
        general += w * (pred == {"general"})
        for s in pred & gold: tp[s] += w
        for s in pred - gold: fp[s] += w
        for s in gold - pred: fn[s] += w
        if gold != pred:
            errors.append((r["code"], sorted(pred), sorted(gold)))
    print(f"codes: {len(rows)}  weighted n: {total:g}")
    print(f"exact match: {exact/total:.1%}   routed to 'general': {general/total:.1%}\n")
    print(f"{'specialty':22}{'precision':>10}{'recall':>9}{'support':>9}")
    for s in sorted(set(tp) | set(fp) | set(fn)):
        p = tp[s] / (tp[s] + fp[s]) if tp[s] + fp[s] else float("nan")
        rc = tp[s] / (tp[s] + fn[s]) if tp[s] + fn[s] else float("nan")
        print(f"{s:22}{p:>10.2f}{rc:>9.2f}{tp[s]+fn[s]:>9g}")
    print(f"\nDISAGREEMENTS ({len(errors)}): code | plugin | clinician")
    for c, p, g in errors:
        print(f"  {c:10} {p} vs {g}")


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "data/gold_template.csv")
