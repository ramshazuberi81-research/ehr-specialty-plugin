# EHR Specialty Filing Plugin

[![tests](https://github.com/ramshazuberi81-research/ehr-specialty-plugin/actions/workflows/ci.yml/badge.svg)](https://github.com/ramshazuberi81-research/ehr-specialty-plugin/actions)
[![docker-e2e](https://github.com/ramshazuberi81-research/ehr-specialty-plugin/actions/workflows/docker.yml/badge.svg)](https://github.com/ramshazuberi81-research/ehr-specialty-plugin/actions)
[![Open in Colab](https://colab.research.google.com/assets/colab-badge.svg)](https://colab.research.google.com/github/ramshazuberi81-research/ehr-specialty-plugin/blob/main/notebooks/ehr_plugin_colab_demo.ipynb)

> **Research prototype. Synthetic and public data only. Not for clinical use.**
> Not security-reviewed, not regulatory-reviewed, never used with real patient data.

A doctor saves **one** diagnosis form. The plugin files it under the right specialty, tells the right
colleague, and has a one-screen, source-linked summary ready before the patient sits down.

Built on **FHIR R4**. It is rule-based (no machine learning), and it is designed to fail safe rather than guess.

## What it does

1. **Specialty filing** (`app/filing.py`): maps an ICD-10 code to one or more specialties, tags the
   `Condition` in place (one record, no copies), writes a `Provenance` audit record, and creates `Task`s
   for specialists who should know. Free-text diagnoses get a *suggested* code that a doctor must confirm.
   Unknown codes go to a `general` section instead of being dropped.
2. **Pre-visit summary** (`/previsit/{patient}?specialty=...`): alerts (allergies), active/past problems,
   linked medications, results, recent visits, open items. Every line cites its source resource;
   gaps are stated as "not recorded", never invented.
3. **CDS Hooks service** (`app/cds_hooks.py`): a `patient-view` hook that returns the pre-visit summary as a
   card for the viewing doctor's specialty (taken from their `PractitionerRole`, never guessed). If the
   specialty is unknown or nothing is recorded, it returns no card.
4. **Observation normalizer** (`app/normalize.py`): converts units (HbA1c mmol/mol to %, glucose
   mmol/L to mg/dL) and flags implausible values for human review instead of "fixing" them.

## Try it in 30 seconds (no server, no network)

```bash
pip install -r requirements-dev.txt
python scripts/demo_local.py     # files 4 synthetic diagnoses, prints the ophthalmology summary
pytest -q                        # 30 tests
```

Or run it in the browser: click the **Open in Colab** badge above.

## Evidence: audit of the specialty table

The ICD-10-CM to specialty table is the core of the tool, so I audited it against every billable code
(74,714 codes, ICD-10-CM April 2026 release).

| View | Codes | Routed to `general` (no specialty yet) |
|---|---|---|
| All billable codes | 74,714 | 74.4% |
| Excluding external-cause codes (chapter 20) | 67,253 | 71.6% |
| Disease chapters only (chapters 1-18) | 24,698 | **22.7%** |

Injury (chapter 19) and external-cause codes make up most of ICD-10-CM, so the disease-chapter figure is
the meaningful one. Gaps found so far: thyroid disorders (E00-E07), secondary diabetes (E08, E09),
obesity and lipid disorders, and all pregnancy (O) codes. These fall to `general`, which is safe (nothing
is dropped), but they have no specialty routing yet. Full tables are in `data/coverage_by_chapter.csv`
and `data/general_blocks.csv`. The table has **not** been clinically reviewed; see `EVALUATION.md` for the
planned clinician-labelled accuracy study.

Reproduce the audit:

```bash
pip install simple-icd-10-cm
python scripts/build_icd10_dataset.py   # builds data/icd10cm_billable.csv (not committed, about 12 MB)
python scripts/coverage_icd10.py
```

## Run it against a local FHIR server

```bash
cp .env.example .env             # set WEBHOOK_SECRET to a long random string
docker compose up --build        # HAPI FHIR on :8080, plugin on :8000
```

The Docker Compose setup is verified end-to-end in CI: the `docker-e2e` workflow (`scripts/e2e_docker.sh`) starts HAPI FHIR R4
and the plugin, files a diagnosis, builds the summary and the CDS card, and checks that a wrong secret is rejected.
The Python tests also run offline against a fake FHIR client. API docs: http://localhost:8000/docs.

| Endpoint | Purpose |
|---|---|
| `POST /webhook/condition` | files a saved Condition |
| `POST /webhook/observation` | normalizes an Observation |
| `GET /previsit/{patient_id}?specialty=ophthalmology` | builds the summary |
| `GET /cds-services` | CDS Hooks discovery (open, per spec) |
| `POST /cds-services/ehr-previsit` | CDS Hooks `patient-view`: returns the summary card |
| `GET /health` | liveness |

All but `/health` and `/cds-services` require the `X-Webhook-Secret` header. The server **fails closed** if
`WEBHOOK_SECRET` is unset.

## Safety choices

- Never guesses silently: free text gives a suggested code, a `needs-coding-review` tag and a confirm task.
- Never drops data: unknown codes go to `general`.
- Never auto-corrects: implausible lab values become an urgent review task.
- Every write is one atomic FHIR transaction with a `Provenance` record.
- Idempotent: already-tagged records are skipped (this also prevents webhook loops).
- Shows nothing rather than something wrong: no card when the specialty is unknown or nothing is recorded.
- Unknown clinical status is shown in its own "status not recorded" section and counted on the CDS card, never assumed to be a past problem.

## Known limitations

- The ICD-10 to specialty table needs clinical review before any pilot (see the audit above).
- Search results use the first page only (`_count=200`); no paging.
- Normalized Observations are not yet specialty-tagged, so they don't appear in summaries.
- Auth is a shared secret, fine for a sandbox, not for production. The CDS Hooks endpoint must verify the
  EHR's signed JWT, and users should authenticate via SMART on FHIR, before any pilot.
- The CDS Hooks service is tested against a fake FHIR client and a local HAPI server, not yet in the official CDS Hooks sandbox or a real EHR.
- Docker Compose passes on a GitHub Actions runner. In one GitHub Codespace the plugin container timed out connecting to HAPI; this was not diagnosed and looks environment-specific.
- No PHI handling, encryption at rest, access logging, or consent logic.

## Roadmap

1. Run the accuracy study in `EVALUATION.md` and fill the gaps found in the audit, with clinician sign-off.
2. Verify the EHR's JWT in the CDS Hooks service and test it in the CDS Hooks sandbox.
3. Add sample FHIR `Subscription` resources so the FHIR server calls the plugin automatically.
4. Pagination, observation tagging, retry and dead-letter handling.
5. Shadow-mode pilot beside a real chart at a partner clinic, under that site's governance. Measure
   filing errors and time saved.
6. Threat model, privacy review, and applicable regulatory assessment (HIPAA/GDPR/local law, medical-device rules).

## Project layout

```
app/        main.py  filing.py  cds_hooks.py  normalize.py  auth.py  config.py
tests/      pytest suite (offline, fake FHIR client)
scripts/    demo_local.py  evaluate_filing.py  build_icd10_dataset.py  coverage_icd10.py  e2e_docker.sh  gen_keys.py
data/       coverage_by_chapter.csv  general_blocks.csv  gold_template.csv
notebooks/  ehr_plugin_colab_demo.ipynb
EVALUATION.md   four-stage evaluation plan
```

## Production-style auth

`python scripts/gen_keys.py`, register `jwks.json` with your FHIR server, then set `SMART_CLIENT_ID`.
Never commit `private_key.pem`.

## Feedback welcome

The most useful feedback right now: clinicians willing to review the specialty table, and FHIR / CDS Hooks
engineers who can critique the design. Please keep all test data synthetic.

## Author

Ramsha Zuberi, Clinical AI Researcher (oral oncology focus). Developed with AI assistance; design, clinical framing, testing and review by the author.
[ORCID 0009-0004-9272-0343](https://orcid.org/0009-0004-9272-0343) · [GitHub](https://github.com/ramshazuberi81-research)

## License

MIT (see `LICENSE`).
