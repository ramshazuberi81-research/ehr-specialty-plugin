#!/usr/bin/env bash
# End-to-end test of the Docker Compose setup: HAPI FHIR + plugin, synthetic data only.
# Run from anywhere:  bash scripts/e2e_docker.sh      (needs Docker with the compose plugin)
set -euo pipefail
cd "$(dirname "$0")/.."

SECRET=$(openssl rand -hex 24)
printf 'WEBHOOK_SECRET=%s\nFHIR_BASE=http://fhir:8080/fhir\n' "$SECRET" > .env
trap 'echo "--- compose logs (tail)"; docker compose logs --tail 60 || true; docker compose down -v || true; rm -f .env' EXIT

docker compose up -d --build

echo "Waiting for HAPI FHIR..."
for i in $(seq 1 90); do
  curl -sf localhost:8080/fhir/metadata > /dev/null && break
  sleep 5
done
curl -sf localhost:8080/fhir/metadata > /dev/null || { echo "FAIL: HAPI never became ready"; exit 1; }
curl -sf localhost:8000/health > /dev/null || { echo "FAIL: plugin /health not answering"; exit 1; }
echo "OK: HAPI and plugin are up"

F=localhost:8080/fhir
H='Content-Type: application/fhir+json'
put() { curl -sf -X PUT -H "$H" -d "$2" "$F/$1" > /dev/null || { echo "FAIL: PUT $1"; exit 1; }; }
put Patient/p1 '{"resourceType":"Patient","id":"p1"}'
put Practitioner/eye '{"resourceType":"Practitioner","id":"eye"}'
put Practitioner/endo '{"resourceType":"Practitioner","id":"endo"}'
put PractitionerRole/r-eye '{"resourceType":"PractitionerRole","id":"r-eye","practitioner":{"reference":"Practitioner/eye"},"specialty":[{"text":"Ophthalmology"}]}'
put PractitionerRole/r-endo '{"resourceType":"PractitionerRole","id":"r-endo","practitioner":{"reference":"Practitioner/endo"},"specialty":[{"text":"Endocrinology"}]}'

COND='{"resourceType":"Condition","id":"c1","subject":{"reference":"Patient/p1"},"recorder":{"reference":"Practitioner/endo"},"code":{"coding":[{"system":"http://hl7.org/fhir/sid/icd-10-cm","code":"E11.319"}],"text":"Diabetic retinopathy"}}'
CDS='{"hook":"patient-view","hookInstance":"t1","context":{"userId":"Practitioner/eye","patientId":"p1"}}'

echo "1. File a diagnosis"
OUT=$(curl -sf -X POST -H "X-Webhook-Secret: $SECRET" -H 'Content-Type: application/json' -d "$COND" localhost:8000/webhook/condition)
echo "$OUT"
python3 - "$OUT" <<'PY'
import json, sys
d = json.loads(sys.argv[1])
assert set(d["filed_under"]) == {"endocrinology", "ophthalmology"}, d
assert [t["owner"] for t in d["tasks"]] == ["Practitioner/eye"], d
print("PASS: filed under both specialties, only the other specialist notified")
PY

echo "2. Pre-visit summary"
SUM=$(curl -sf -H "X-Webhook-Secret: $SECRET" "localhost:8000/previsit/p1?specialty=ophthalmology")
python3 - "$SUM" <<'PY'
import json, sys
d = json.loads(sys.argv[1])
assert "Condition/c1" in d["text"] and "Diabetic retinopathy" in d["text"], d["text"]
print("PASS: summary lists the problem with its source")
PY

echo "3. CDS Hooks card"
CARD=$(curl -sf -X POST -H "X-Webhook-Secret: $SECRET" -H 'Content-Type: application/json' -d "$CDS" localhost:8000/cds-services/ehr-previsit)
python3 - "$CARD" <<'PY'
import json, sys
c = json.loads(sys.argv[1])["cards"]
assert c and c[0]["summary"].startswith("Ophthalmology pre-visit"), c
print("PASS: CDS card returned:", c[0]["summary"])
PY

echo "4. Wrong secret is rejected"
CODE=$(curl -s -o /dev/null -w '%{http_code}' -X POST -H "X-Webhook-Secret: wrong" -H 'Content-Type: application/json' -d '{}' localhost:8000/webhook/condition)
[ "$CODE" = "401" ] || { echo "FAIL: expected 401, got $CODE"; exit 1; }
echo "PASS: 401"

echo "DOCKER END-TO-END OK"
