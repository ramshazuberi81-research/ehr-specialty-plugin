# Security policy

**This is a prototype. Synthetic data only. Not for clinical use.** It has not been security-reviewed or
regulatory-reviewed and must never be pointed at real patient data.

## Reporting a vulnerability

Please use GitHub's private reporting: **Security tab > Report a vulnerability** on this repository.
Do not open a public issue for a security problem, and do not include real patient data in any report.

I will acknowledge a report as soon as I can. This is a volunteer research project, so there is no
guaranteed response time and no bug bounty.

## Scope

In scope: the code in this repository (`app/`, `scripts/`, Docker files, workflows).
Out of scope: the HAPI FHIR test server image, third-party model APIs, and anything involving real patient data.

## Supported versions

Only the `main` branch.

## What is already in place

- Shared-secret webhooks fail closed when `WEBHOOK_SECRET` is unset; comparison is constant-time.
- Optional SMART Backend Services auth towards the FHIR server (signed JWT, RS384).
- Optional verification of the EHR's signed JWT on the CDS Hooks endpoint (`app/cds_auth.py`).
- CI runs `pip-audit` (known-vulnerable dependencies) and `bandit` (common Python security issues).
- Docker Compose publishes ports on localhost only.

See `THREAT_MODEL.md` for known gaps and `SAFETY_CASE.md` for clinical-safety hazards.

## Rules for contributors

- Never commit `.env`, `*.pem`, `jwks.json`, API keys or any real patient data. If a secret is ever
  committed, treat it as compromised and rotate it; deleting the file is not enough.
- Keep all test data synthetic.
- Do not log request bodies or clinical content.
