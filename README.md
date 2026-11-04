# EHR Specialty Filing Plugin

> **Prototype for demonstration only. Synthetic data only. Not for clinical use.** Not security-reviewed, not regulatory-reviewed, never used with real patient data.

**Live demo (runs in your browser, fake patients):** https://ramshazuberi81-research.github.io/ehr-specialty-plugin/

A doctor saves **one** diagnosis form. The plugin files it under the right specialty, tells the right
colleague, and has a one-screen, source-linked summary ready before the patient sits down.

Built on **FHIR R4**. The project has two parts:

| Part | What it is | Where |
| ---- | ---------- | ----- |
| **Plugin (backend)** | Specialty filing, pre-visit summary, observation normalizer. Python / FastAPI against a FHIR server. | `app/`, `tests/`, `scripts/` |
| **Ask the Chart (front-end demo)** | A privacy-consent gate plus a plain-language "ask or tell" assistant for doctors and patients. One static HTML page, no server. | `index.html` |

---

## Ask the Chart (v2 demo)

A single-page demo of how a patient-consented, auditable assistant could sit on top of the chart.
Everything runs in the page. **The sign-in is simulated and protects nothing**; real protection must be enforced on a server.

### Step 1: Privacy consent (the gate)

You cannot reach the assistant until consent is active.

- **Simulated sign-in** as the patient (Jane Doe, fake), the doctor (Dr. A, fake), or "someone else". "Someone else" is denied and the attempt is logged.
- **The patient chooses** what is allowed, and can withdraw at any time:
  - share records with treating specialists (filing and pre-visit summaries)
  - let the system notify the care team when a diagnosis is filed
  - allow the plain-language assistant
  - allow voice input (the browser's speech service may send audio to its vendor)
- **Two signatures:** the patient signs by typing their full name; the doctor then reviews and countersigns. The doctor **cannot change** the patient's choices.
- **FHIR `Consent` record** (illustrative) shown to the patient and doctor only.
- **Access log:** every open, sign, withdraw and refused attempt is recorded.

### Step 2: Ask or tell

Switch between **Doctor view** and **Patient view**, then type (or speak) a command.

| Try | What happens |
| --- | ------------ |
| `Show Ahmed Khan's medications` | Opens the chart; every block cites its source. Gaps say "not recorded". |
| `Draft hydralazine 25 mg twice daily for Ahmed Siddiqui` | Saved as a **pending draft, not active**. A named clinician must confirm it on screen. Look-alike warning shown (hydralazine / hydroxyzine). |
| `Note for Sara Noor: <text>` | Saved as a pending draft note until a clinician confirms. |
| `Remind me to check blood pressure tomorrow` | Creates a reminder only. No orders, no chart changes. |
| `Remind the patient to use eye drops in 3 days` | Clinician only, and only if the patient consented to reminders. |
| `What does metformin do?` / `Why was lisinopril started?` | Plain-language explanation plus the chart reason, with source. Information only, not advice. |
| `Next appointment for Sara Noor` | Reads the schedule. |
| `Which results are unacknowledged?` | Clinician only. Lists unfiled diagnoses and unacknowledged results for assigned patients. |

### Safety behaviour built into the demo

- **Never guesses between people.** Two patients named Ahmed? It asks for the full name instead of picking one.
- **Least access.** Doctors see only their assigned patients; patients see only their own record. Anything else is refused and logged.
- **Consent is checked per action.** No voice consent means voice commands are refused; no reminder consent means no reminders.
- **Never acts alone on clinical changes.** Medicine and note drafts stay inactive until a named clinician confirms.
- **Never invents.** Missing data is shown as "not recorded"; unknown drug names are flagged.
- **Never places orders.** The assistant reads the chart and sets reminders only.
- **Everything is logged,** labelled `blocked`, `needs approval`, `approved by clinician` or `agent did alone` (expand "Agent and access log").
- The command parser is rule-based. **No AI model is called** in this demo, and typed text never leaves the device.

### What a real version needs

- Real login for patient and doctor (for example SMART on FHIR), plus a second identifier for the patient.
- Authorization checked **on the server** for every read and write, so "only these two people" is enforced, not just hidden.
- Consent stored as a FHIR `Consent` resource in the FHIR server, encrypted in transit and at rest, with an audit trail.
- Every other part of the system must read that consent before sharing anything.
- Review by the site's privacy, legal and clinical-safety teams before any pilot.

---

## Plugin features

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

**Front-end demo:** open `index.html` in a browser, or use the live link above.

**Plugin:**

```
pip install -r requirements-dev.txt
python scripts/demo_local.py     # runs the 4-diagnosis story, prints the ophthalmology summary
pytest -q                        # 23 tests
```

## Run it against a local FHIR server

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

## Safety choices (plugin)

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
- **The consent gate, sign-in, access log and assistant in `index.html` are browser-only simulations.**
  They are not connected to the plugin or to a FHIR server, and the backend does not yet read the `Consent` resource.

## Roadmap

1. Externalize the code table to a reviewable CSV/JSON; add clinician sign-off.
2. Connect Ask the Chart to the plugin API and a FHIR server (real `Consent`, `Provenance` and `AuditEvent` resources) so consent is enforced server-side.
3. CDS Hooks service (`patient-view`) so the summary appears natively in EHRs.
4. Pagination, observation tagging, retry/dead-letter handling.
5. Cite DailyMed or RxNorm for medicine information instead of the demo reference list.
6. Shadow-mode pilot beside a real chart at a partner clinic, under that site's governance. Measure
   time saved and filing errors.
7. Threat model, privacy review, and applicable regulatory assessment (HIPAA/GDPR/local law, medical-device rules).

## Project layout

```
index.html  Ask the Chart demo (consent gate + assistant), served via GitHub Pages
app/        auth.py  config.py  normalize.py  filing.py  main.py
tests/      pytest suite (offline, fake FHIR client)
scripts/    demo_local.py  gen_keys.py
```

## Production-style auth

`python scripts/gen_keys.py`, register `jwks.json` with your FHIR server, then set `SMART_CLIENT_ID`.
Never commit `private_key.pem`.

## License

MIT (see `LICENSE`, replace `<YOUR NAME>`). Contributions welcome. Please keep all test data synthetic.
