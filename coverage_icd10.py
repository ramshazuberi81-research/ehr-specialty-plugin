"""Stage 1 evaluation: how much of ICD-10-CM does the specialty table cover?

    python scripts/coverage_icd10.py                      # uses data/icd10cm_billable.csv
    python scripts/coverage_icd10.py path/to/codes.csv    # any CSV with a 'code' column

Writes data/coverage_by_chapter.csv and data/general_blocks.csv, and prints a summary.

Reading the numbers: ICD-10-CM is dominated by injury (S/T) and external-cause (V-Y) codes, so the
raw "% general" is misleading. Three views are printed:
  ALL                every billable code
  EXCL. CH.20        drops external-cause codes (V00-Y99), which are not used as the primary diagnosis
  DISEASE CHAPTERS   chapters 1-18 only (diseases, symptoms, pregnancy, perinatal, congenital)
'general' means the table has no specialty for the code; it is a gap to review, not necessarily an error.
"""
import csv
import os
import sys
from collections import Counter, defaultdict

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
os.environ.setdefault("FHIR_BASE", "http://fhir.test/fhir")
from app.filing import specialties_for  # noqa: E402


def chapter_no(label: str) -> int:
    try:
        return int(label.split()[0])
    except (ValueError, IndexError):
        return 0


def pct(n, d):
    return f"{(100 * n / d):.1f}%" if d else "n/a"


def view(name, rows):
    n = len(rows)
    g = sum(1 for r in rows if r["pred"] == ["general"])
    d = sum(1 for r in rows if len(r["pred"]) > 1)
    print(f"{name:18} codes={n:>6}   routed to general: {g:>6} ({pct(g, n)})   dual-filed: {d:>5} ({pct(d, n)})")


def main(path):
    rows = list(csv.DictReader(open(path, newline="", encoding="utf-8")))
    for r in rows:
        r["pred"] = specialties_for(r["code"])
        r["ch"] = chapter_no(r.get("chapter", ""))
    print(f"Source: {path}   ({len(rows)} codes)\n")
    view("ALL", rows)
    view("EXCL. CH.20", [r for r in rows if r["ch"] != 20])
    view("DISEASE CHAPTERS", [r for r in rows if 1 <= r["ch"] <= 18])

    by_ch = defaultdict(lambda: [0, 0, ""])
    for r in rows:
        c = by_ch[r["ch"]]
        c[0] += 1
        c[1] += r["pred"] == ["general"]
        c[2] = r.get("chapter", "")
    out = os.path.join(ROOT, "data", "coverage_by_chapter.csv")
    with open(out, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["chapter", "codes", "general", "pct_general"])
        for k in sorted(by_ch):
            n, g, lab = by_ch[k]
            w.writerow([lab, n, g, f"{100 * g / n:.1f}"])
    print("\nCHAPTERS WITH THE BIGGEST GAPS (codes routed to general)")
    for k, (n, g, lab) in sorted(by_ch.items(), key=lambda kv: -kv[1][1])[:8]:
        print(f"  {g:>6}/{n:<6} {pct(g, n):>6}  {lab[:70]}")

    spec = Counter(s for r in rows for s in r["pred"])
    print("\nCODES PER SPECIALTY (dual-filed codes count once per specialty)")
    for s, n in spec.most_common():
        print(f"  {s:22}{n:>7}")

    blocks = Counter((r["ch"], r.get("block", "")) for r in rows if r["pred"] == ["general"] and 1 <= r["ch"] <= 18)
    out2 = os.path.join(ROOT, "data", "general_blocks.csv")
    with open(out2, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["chapter_no", "block", "codes_in_general"])
        for (c, b), n in blocks.most_common():
            w.writerow([c, b, n])
    print("\nTOP DISEASE-CHAPTER BLOCKS STILL IN general (fix these first; full list in data/general_blocks.csv)")
    for (c, b), n in blocks.most_common(12):
        print(f"  ch{c:<2} {b:10} {n:>5} codes")
    print(f"\nWrote {out}\nWrote {out2}")


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else os.path.join(ROOT, "data", "icd10cm_billable.csv"))
