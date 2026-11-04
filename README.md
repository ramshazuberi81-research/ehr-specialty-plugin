# EHR Specialty Filing Plugin

> **Prototype for demonstration only. Synthetic data only. Not for clinical use.** Not security-reviewed, not regulatory-reviewed, never used with real patient data.

A doctor saves **one** diagnosis form. The plugin files it under the right specialty, tells the right
colleague, and has a one-screen, source-linked summary ready before the patient sits down.

**Live demo page (fake patients, runs in your browser):** https://ramshazuberi81-research.github.io/ehr-specialty-plugin/

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

```
pip install -r requirements-dev.txt
python scripts/demo_local.py     # runs the 4-diagnosis story, prints the ophthalmology summary
pytest -q                        # 23 tests
```

## Run it against a local FHIR server (Docker)

```
cp .env.example .env             # set WEBHOOK_SECRET to a long random string
docker compose up --build        # HAPI FHIR on :8080, plugin on :8000
```

API docs at <http://localhost:8000/docs>. Point FHIR `Subscription`s (rest-hook) at:

| Endpoint                                             | Purpose                   |
| ---------------------------------------------------- | ------------------------- |
| `POST /webhook/condition`                            | files a saved Condition   |
| `POST /webhook/observation`                          | normalizes an Observation |
| `GET /previsit/{patient_id}?specialty=ophthalmology` | builds the summary        |
| `GET /health`                                        | liveness                  |

All but `/health` require the `X-Webhook-Secret` header. The server **fails closed** if `WEBHOOK_SECRET` is unset.

## Demo page: Ask the Chart (v2)

Live at https://ramshazuberi81-research.github.io/ehr-specialty-plugin/ (source: `index.html`, no server needed).
Everything runs in the page. **The sign-in is simulated and protects nothing**; real protection must be enforced on a server.

**1. Privacy consent (gate).** Simulated sign-in as patient (Jane Doe, fake), doctor (Dr. A, fake) or "someone else" (denied and logged).
The patient chooses what is allowed (share records, notify care team, plain-language assistant, voice input) and can withdraw any time.
The patient signs by typing their name; the doctor countersigns but cannot change the patient's choices.
An illustrative FHIR `Consent` record and an access log (every open, sign, withdraw and refused attempt) are shown.

**2. Ask or tell.** Doctor view and Patient view with a typed or spoken command box:

| Try | What happens |
| --- | ------------ |
| `Show Ahmed Khan's medications` | Opens the chart; every block cites its source, gaps say "not recorded". |
| `Draft hydralazine 25 mg twice daily for Ahmed Siddiqui` | Saved as a **pending draft, not active** until a named clinician confirms. Look-alike warning (hydralazine / hydroxyzine). |
| `Note for Sara Noor: <text>` | Pending draft note until a clinician confirms. |
| `Remind me to check blood pressure tomorrow` | Reminder only; no orders, no chart changes. |
| `What does metformin do?` | Plain-language explanation with source. Information only, not advice. |
| `Which results are unacknowledged?` | Clinician only; lists unfiled diagnoses and unacknowledged results. |

**Built-in safety behaviour:** never guesses between same-name patients; doctors see only assigned patients and patients only their own record;
consent is checked per action (voice, reminders); drafts never become active without a clinician; the assistant never places orders;
every action is logged as `blocked`, `needs approval`, `approved by clinician` or `agent did alone`.
The command parser is rule-based, so **no AI model is called**, and typed text never leaves the device.

**A real version needs:** real login (e.g. SMART on FHIR) plus a second patient identifier; server-side authorization on every read and write;
consent stored as a FHIR `Consent` resource, encrypted in transit and at rest, with an audit trail that the rest of the system must read before sharing;
and review by the site's privacy, legal and clinical-safety teams.

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
- The backend has no PHI handling, encryption-at-rest, access logging, or consent logic.
- The consent gate, sign-in, access log and assistant on the demo page are browser-only simulations, not connected to the plugin or a FHIR server.

## Roadmap

1. Externalize the code table to a reviewable CSV/JSON; add clinician sign-off.
2. Connect the demo page to the plugin API and a FHIR server (real `Consent`, `Provenance`, `AuditEvent`) so consent is enforced server-side.
3. CDS Hooks service (`patient-view`) so the summary appears natively in EHRs.
4. Pagination, observation tagging, retry/dead-letter handling.
5. Shadow-mode pilot beside a real chart at a partner clinic, under that site's governance. Measure
   time saved and filing errors.
6. Threat model, privacy review, and applicable regulatory assessment (HIPAA/GDPR/local law, medical-device rules).

## Project layout

```
index.html  demo page (Ask the Chart), served by GitHub Pages
app/        auth.py  config.py  normalize.py  filing.py  main.py
tests/      pytest suite (offline, fake FHIR client)
scripts/    demo_local.py  gen_keys.py
```

## Production-style auth

`python scripts/gen_keys.py`, register `jwks.json` with your FHIR server, then set `SMART_CLIENT_ID`.
Never commit `private_key.pem`.


