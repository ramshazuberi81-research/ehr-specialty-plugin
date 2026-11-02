# Clinical safety case and ethics (draft hazard log)

Status: **draft starter for clinician review.** It was drafted from reading the code and data files on
2 Nov 2026. Every row needs a named clinical owner to confirm, change or reject it before any pilot.
Nothing here means the software is safe for clinical use; it is **not**.

## Principles

1. **A human stays accountable.** The software suggests and files; a clinician confirms anything uncertain.
2. **Never guess silently.** Uncertain input becomes a visible suggestion with a review flag.
3. **Never drop or "fix" data silently.** Unknown goes to `general`; implausible values go to review.
4. **Show the source.** Every summary line cites the resource it came from; gaps say "not recorded".
5. **Synthetic data only** until a site's own governance, privacy and regulatory review says otherwise.
6. **Be honest about limits** in the README, in demos and in this file.

## Hazard log

| ID | Hazard | Possible harm | Controls in place | Residual risk / next step | Owner |
|---|---|---|---|---|---|
| H1 | Wrong ICD-10 to specialty mapping | Patient or colleague notified in the wrong specialty; delayed care | Table is documented as needing clinical review; unknown codes go to `general`; free text needs confirmation | Clinician sign-off per specialty; version the table with reviewer and date; measure against a gold set (`EVALUATION.md`) | TBD |
| H2 | Diagnoses stuck in `general` and never seen | Specialist never learns of a relevant condition | `general` section exists; coverage report shows how much falls there | `data/coverage_by_chapter.csv` shows whole chapters mostly or entirely unrouted (for example chapter 3, D50-D89, is 100% `general` and chapter 4 is about 73%). Prioritise these chapters for clinical review | TBD |
| H3 | Alert fatigue from too many `Task`s | Important tasks ignored | Idempotent filing avoids duplicates | Decide who needs notification per specialty; measure task volume per clinician in a pilot | TBD |
| H4 | Over-trust in the pre-visit summary (automation bias) | Clinician skips the chart and misses something | Every line is source-linked | State clearly in the UI that the summary is an aid, not a record; test with clinicians | TBD |
| H5 | "Not recorded" read as "absent" | Missed allergy or history | Gaps are written as "not recorded"; unknown clinical status gets its own section | Usability check with clinicians on the wording | TBD |
| H6 | Wrong patient selected in `/ask` | Wrong chart shown | Two matching names return candidates, never a guess | A typed or spoken name is not identity. Add real login and a second identifier before any pilot | TBD |
| H7 | Lab value auto-"corrected" | Wrong decision on a wrong number | Implausible values are flagged for urgent human review, never changed | Review plausibility ranges and unit conversions with a clinician (HbA1c and glucose are covered by `tests/test_normalize.py`) | TBD |
| H8 | Model misreads or invents content from a note | False diagnosis drafted | Model only interprets text; output is validated; drafts are unconfirmed; nothing is written by `/nlp/extract-note`; negations kept apart | Add adversarial and negation test cases; evaluate on a labelled synthetic set; never auto-confirm | TBD |
| H9 | Real patient data used by mistake | Privacy breach | Synthetic-only banners in README, demo and code | Add a config guard that makes sandbox mode explicit; training for contributors | TBD |
| H10 | Terminology mismatch with the target setting | Mappings wrong for local practice | None yet | The dataset script builds an ICD-10-CM list (US clinical modification). Check which ICD version and local concept dictionary the target Bahmni/OpenMRS sites actually use, and map accordingly | TBD |
| H11 | Unequal performance (language, names, local disease burden) | Some patients routed or found less reliably | None yet | Test name matching and free-text coding on non-English and transliterated names and on local terms; involve local clinicians | TBD |
| H12 | Duplicate or looping writes from webhooks | Duplicated or conflicting records | Already-tagged records are skipped; each write is one atomic transaction with `Provenance` | Retry and dead-letter handling (see roadmap) | TBD |

## Before any pilot (minimum)

- Named clinical safety officer and written sign-off of the mapping table.
- Site governance approval, privacy review, and a check of local data-protection and medical-device rules.
- Real user authentication and authorization, audit logging, consent handling.
- Shadow mode only first: the tool runs beside the real chart and changes nothing.
- A way to report errors and a rule for when to stop the pilot.

## Review log

| Date | Reviewer | What was reviewed | Outcome |
|---|---|---|---|
| | | | |
