# EHR Specialty Filing Plugin

> **Prototype for demonstration only. Synthetic data only. Not for clinical use.**
> Not security-reviewed, not regulatory-reviewed, never used with real patient data.

A doctor saves **one** diagnosis form. The plugin files it under the right specialty, tells the right
colleague, and has a one-screen, source-linked summary ready before the patient sits down.

Built on **FHIR R4**. Two features:

1. **Specialty filing** (`app/filing.py`): maps an ICD-10 code to one or more specialties, tags the
   `Condition` in place (one record, no copies), writes a `Provenance` audit record, and creates `Task`s
   for specialists who should know. Free-text diagnoses get a *suggested* code that a doctor must confirm.
   Unknown codes go to a `general` section instead of being dropped.
2. **Pre-visit summary** (`/previsit/{patient}?specialty=...`): alerts (allergies), active/past problems,
   linked medications, results, recent visits, open items. Every line cites its source resource;
   gaps are stated as "not recorded", never invented.

Bonus: **Observation normalizer** (`app/normalize.py`): converts units (HbA1c mmol/mol → %, glucose
mmol/L → mg/dL), flags implausible values for human review instead of "fixing" them.

## Try it in 30 seconds (no server, no network)

```bash
pip install -r requirements-dev.txt
python scripts/demo_local.py     # runs the 4-diagnosis story, prints the ophthalmology summary
pytest -q                        # 29 tests
```

## Run it against a local FHIR server

```bash
cp .env.example .env             # set WEBHOOK_SECRET to a long random string
docker compose up --build        # HAPI FHIR on :8080, plugin on :8000
```

API docs at http://localhost:8000/docs. Point FHIR `Subscription`s (rest-hook) at:

| Endpoint | Purpose |
|---|---|
| `POST /webhook/condition` | files a saved Condition |
| `POST /webhook/observation` | normalizes an Observation |
| `GET /previsit/{patient_id}?specialty=ophthalmology` | builds the summary |
| `GET /cds-services` | CDS Hooks discovery (open, per spec) |
| `POST /cds-services/ehr-previsit` | CDS Hooks `patient-view`: returns the pre-visit summary card for the viewing doctor's specialty |
| `GET /health` | liveness |

All but `/health` require the `X-Webhook-Secret` header. The server **fails closed** if `WEBHOOK_SECRET` is unset.

## Safety choices

- Never guesses silently: free-text → suggested code + `needs-coding-review` tag + confirm task.
- Never drops data: unknown codes → `general`.
- Never auto-corrects: implausible lab values become an urgent review task.
- Every write is one atomic FHIR transaction with a `Provenance` record.
- Idempotent: already-tagged records are skipped (also prevents webhook loops).

## Known limitations (be honest about these in any demo)

- The ICD-10 → specialty table (`app/filing.py`) covers chapters broadly with a few overrides; it needs
  clinical review before any pilot.
- Search results use the first page only (`_count=200`); no paging.
- Normalized Observations are not yet specialty-tagged, so they don't appear in summaries.
- Webhook secret is shared-secret auth, fine for a sandbox, not for production. Use SMART/OAuth user auth.
- No PHI handling, encryption-at-rest, access logging, or consent logic.

## Roadmap

1. Run the accuracy study in `EVALUATION.md` (`scripts/evaluate_filing.py`), then externalize the code table to a reviewable CSV/JSON; add clinician sign-off.
2. ~~CDS Hooks service~~ prototype done (`app/cds_hooks.py`). Still needed: verify the EHR's signed JWT, test in the CDS Hooks sandbox.
3. Pagination, observation tagging, retry/dead-letter handling.
4. Shadow-mode pilot beside a real chart at a partner clinic, under that site's governance. Measure
   time saved and filing errors.
5. Threat model, privacy review, and applicable regulatory assessment (HIPAA/GDPR/local law, medical-device rules).

## Project layout

```
app/        auth.py  config.py  normalize.py  filing.py  cds_hooks.py  main.py
tests/      pytest suite (offline, fake FHIR client)
scripts/    demo_local.py  gen_keys.py  evaluate_filing.py  build_icd10_dataset.py  coverage_icd10.py
data/       gold_template.csv  icd10cm_billable.csv  coverage_by_chapter.csv  general_blocks.csv
```

## Production-style auth

`python scripts/gen_keys.py`, register `jwks.json` with your FHIR server, then set `SMART_CLIENT_ID`.
Never commit `private_key.pem`.

## License

MIT (see `LICENSE`, owner: Ramsha Zuberi). Contributions welcome. Please keep all test data synthetic.
