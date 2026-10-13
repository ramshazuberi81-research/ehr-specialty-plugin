# Evaluation plan: does the specialty table file diagnoses correctly?

**Question:** For real diagnosis codes, does the plugin file each one under the specialty (or specialties) a clinician would choose?
**Primary metrics:** exact-match accuracy, per-specialty precision/recall, share routed to `general` (coverage gap).

## Stage 1: Coverage (public data, no restrictions)
```bash
pip install simple-icd-10-cm
python scripts/build_icd10_dataset.py     # -> data/icd10cm_billable.csv (74,714 billable codes, April 2026 release)
python scripts/coverage_icd10.py          # -> summary + data/coverage_by_chapter.csv + data/general_blocks.csv
```
Report the % landing in `general` in three views (all codes, excluding external causes, disease chapters only),
because injury and external-cause codes make up over half of ICD-10-CM and dominate the raw number.
Goal: show where the table is thin and fix those blocks first.

## Stage 2: Clinician-labelled accuracy (the headline result)
1. Build a gold file of ~200 codes, stratified by specialty, with extra weight on frequently used codes.
   For frequency, use local counts only, and check your data use agreement before sharing any derived counts.
2. Two clinicians label independently: `code, gold_specialties` (use `|` for dual filing).
3. Report inter-rater agreement (Cohen's kappa). Resolve disagreements by discussion. Final labels become the gold file.
4. `python scripts/evaluate_filing.py data/gold.csv`
5. Fix the table where the plugin is wrong, then re-run on a **fresh held-out set** so you don't grade on what you tuned.

## Stage 3: Free-text suggestions
Take ~100 realistic free-text diagnoses ("pink eye", "sugar problem"). Measure:
(a) % where the suggested code is correct, (b) % correctly left unmatched, (c) **% wrongly suggested**.
Item (c) is the safety metric. The design promise is that a doctor confirms, so report how often they'd have to correct.

## Stage 4 (later): Shadow-mode pilot
Under a partner site's governance. Run beside the real chart without writing back. Compare plugin filing with what staff did.
Measure filing errors and time saved. Needs ethics/IRB approval and a privacy review first.

## What to report honestly
Sample size, who labelled, kappa, confidence intervals (bootstrap over codes), and that Stage 2 labels reflect
two clinicians' judgement, not a universal truth.
