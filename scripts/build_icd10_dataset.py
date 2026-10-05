"""Build data/icd10cm_billable.csv (code, description, chapter, block) from the CMS ICD-10-CM
release bundled in the PyPI package `simple-icd-10-cm` (April 2026 release when this was written).

    pip install simple-icd-10-cm
    python scripts/build_icd10_dataset.py

For anything you publish, you can cross-check the code count against the official CMS download
(cms.gov, 'ICD-10 Clinical Modifications'), and rebuild if CMS has a newer release.
"""
import csv
import os

import simple_icd_10_cm as cm

OUT = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "icd10cm_billable.csv")


def main():
    rows = []
    for code in cm.get_all_codes(with_dots=True):
        if not cm.is_leaf(code) or cm.is_block(code) or cm.is_chapter(code):
            continue  # keep only billable (leaf) codes
        anc = cm.get_ancestors(code)
        chapter = next((a for a in anc if cm.is_chapter(a)), "")
        block = next((a for a in anc if cm.is_block(a)), "")
        rows.append({"code": code, "description": cm.get_description(code),
                     "chapter": f"{chapter} {cm.get_description(chapter)}" if chapter else "",
                     "block": block})
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with open(OUT, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=["code", "description", "chapter", "block"])
        w.writeheader()
        w.writerows(rows)
    print(f"wrote {len(rows)} billable codes -> {OUT}")


if __name__ == "__main__":
    main()
