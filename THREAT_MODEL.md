# Threat model (draft)

Status: **draft starter**, written from reading the code on 2 Nov 2026. It needs review by someone with
security experience before any pilot. Scope: synthetic-data sandbox only.

## Assets

| Asset | Why it matters |
|---|---|
| FHIR resources (Patient, Condition, Observation, ...) | Would be PHI in a real deployment |
| Specialty tags, `Task`s, `Provenance` written by the plugin | Wrong or forged writes could misroute care |
| `WEBHOOK_SECRET`, SMART private key, `ANTHROPIC_API_KEY` | Compromise lets an attacker act as the plugin or spend the API quota |
| Logs | Must never contain clinical content |

## Entry points

| Endpoint | Auth today |
|---|---|
| `POST /webhook/condition`, `POST /webhook/observation` | `X-Webhook-Secret` |
| `GET /previsit/{patient}` | `X-Webhook-Secret` |
| `GET /cds-services` (discovery) | open, per CDS Hooks spec |
| `POST /cds-services/ehr-previsit` | EHR-signed JWT when `CDS_JWT_ISSUERS` is set, otherwise `X-Webhook-Secret` |
| `POST /nlp/suggest-code`, `/nlp/extract-note`, `/ask` | `X-Webhook-Secret`; need `ANTHROPIC_API_KEY` |
| `GET /ask-page`, `GET /health` | open |

## Threats, current controls, gaps

| # | Threat | Current control | Gap / next step |
|---|---|---|---|
| T1 | Forged webhook writes tags or tasks | Shared secret, constant-time compare, fails closed if unset | No body signature or timestamp, so a captured request can be replayed. Move to HMAC over the body + timestamp, or SMART/OAuth |
| T2 | Forged CDS Hooks request | JWT checked: RS384/ES384 only, `iss`/`aud`/`exp`/`iat`/`jti` required, key URL must be pre-configured, lifetime <= 10 min, one-time `jti` | `jti` cache is in-process; use a shared store if more than one instance |
| T3 | Brute-forcing the shared secret | Long random secret recommended in `.env.example` | No rate limiting or lockout. Add a reverse-proxy limit or middleware |
| T4 | Clinical text sent to a third-party model | NLP endpoints are off unless `ANTHROPIC_API_KEY` is set; `/ask` sends only the request text, not the chart | `/nlp/extract-note` sends whole notes, and `/ask` requests contain patient names. Real data would need a DPA/BAA and de-identification. Keep synthetic-only |
| T5 | Prompt injection through a note or request | Model only interprets text; deterministic code decides; output validated; `/nlp/extract-note` writes nothing and its drafts are unconfirmed; a code suggested while filing free text is tagged `needs-coding-review` and needs a doctor's confirmation | Add adversarial-note tests (instructions hidden in a note, fake "confirmed" statuses) |
| T6 | Wrong-patient lookup via `/ask` | Two matching names return candidates, never a guess | A spoken or typed name is not authentication. Needs real user login before any pilot |
| T7 | Secrets committed to git | `.gitignore` covers `.env`, `*.pem`, `jwks.json`; no key material found in history when checked on 2 Nov 2026 | Add a secret scanner (e.g. gitleaks) to CI |
| T8 | Vulnerable dependencies | `pip-audit` and `bandit` run in CI (`.github/workflows/security.yml`) | `hapiproject/hapi:latest` is unpinned; pin a version and scan the image |
| T9 | Exposed test FHIR server | Compose binds HAPI and the plugin to `127.0.0.1` | Never deploy the compose file as-is to a public host |
| T10 | PHI in logs | No request or clinical payloads are logged today | Keep it that way; add a test or lint rule |
| T11 | Denial of service | Search uses a single page (`_count=200`) | No request-size limit or rate limit. Add both |
| T12 | Real patient data entered by mistake | Banners and README state synthetic-only | Add a startup guard / config flag that makes the mode explicit, and refuse to start against a non-sandbox FHIR base unless set |
| T13 | Browser voice input | The demo page states that the browser's speech service may send audio to its vendor | Make typing the default; never use voice with real data |
| T14 | No audit trail of reads | `Provenance` is written for filings | Write FHIR `AuditEvent` records for reads and summary views |

## Not covered yet

Encryption at rest, backup and recovery, consent (`Consent` resource), user-level authorization (who may
see which patient), incident response, and a formal privacy review. See the roadmap in `README.md`.
