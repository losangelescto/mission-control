#!/usr/bin/env bash
# Seed representative POC data via the running API (no direct DB credentials required).
# Prereq: API up, Postgres reachable, USE_FIXTURE_MAILBOX=true (default).
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
API_URL="${API_URL:-http://localhost:8000}"
FIXTURES="$(cd "$SCRIPT_DIR/../fixtures/poc" && pwd)"

echo "==> Health"
curl -sS -o /dev/null -w "%{http_code}" "$API_URL/ready" | grep -q 200 || {
  echo "API not ready at $API_URL — start the server first." >&2
  exit 1
}

echo "==> Active canon snapshot (text stand-in for DOCX)"
CANON_JSON=$(curl -sS -X POST "$API_URL/sources/upload" \
  -F "source_type=canon_doc" \
  -F "canonical_doc_id=poc_canon" \
  -F "version_label=active_snapshot" \
  -F "is_active_canon_version=true" \
  -F "file=@$FIXTURES/active_canon.txt")
echo "$CANON_JSON" | python3 -c "import json,sys; print(json.load(sys.stdin)['source_document']['id'])" 2>/dev/null || true

echo "==> Thread source (text stand-in for PDF export)"
curl -sS -X POST "$API_URL/sources/upload" \
  -F "source_type=thread_export" \
  -F "file=@$FIXTURES/thread_export.txt" >/dev/null

echo "==> Board seed"
curl -sS -X POST "$API_URL/sources/upload" \
  -F "source_type=board_seed" \
  -F "file=@$FIXTURES/board_seed.txt" >/dev/null

echo "==> Mailbox fixtures (fixture connector)"
MAIL_JSON=$(curl -sS -X POST "$API_URL/mail/sync-fixture" \
  -H "Content-Type: application/json" \
  -d "{\"mailbox_owner\":\"poc-owner@example.com\",\"folder_name\":\"Inbox\"}")
echo "$MAIL_JSON"

echo "==> Call artifact (transcript stand-in)"
CALL_JSON=$(curl -sS -X POST "$API_URL/calls/upload-artifact" \
  -F "artifact_type=transcript" \
  -F "title=POC planning call" \
  -F "file=@$FIXTURES/call_transcript.txt")
echo "$CALL_JSON" | python3 -c "import json,sys; print(json.load(sys.stdin)['call_artifact']['id'])" 2>/dev/null || true

echo "==> Representative tasks"
curl -sS -X POST "$API_URL/tasks" -H "Content-Type: application/json" -d '{
  "title":"POC — Daily operations checkpoint",
  "description":"Run daily checkpoint across active priorities",
  "objective":"Maintain execution consistency",
  "standard":"Daily review completed before noon",
  "status":"in_progress",
  "priority":"high",
  "owner_name":"Alex",
  "assigner_name":"Jordan",
  "due_at":null,
  "source_confidence":0.8
}' >/dev/null

curl -sS -X POST "$API_URL/tasks" -H "Content-Type: application/json" -d '{
  "title":"POC — Vendor dependency",
  "description":"Follow up on dependency blocking delivery",
  "objective":"Unblock release task stream",
  "standard":"Dependency resolved with written confirmation",
  "status":"blocked",
  "priority":"high",
  "owner_name":"Taylor",
  "assigner_name":"Jordan",
  "due_at":null,
  "source_confidence":0.7
}' >/dev/null

curl -sS -X POST "$API_URL/tasks" -H "Content-Type: application/json" -d '{
  "title":"POC — Backlog hygiene",
  "description":"Triage stale items",
  "objective":"Keep backlog accurate",
  "standard":"Stale items reviewed weekly",
  "status":"backlog",
  "priority":"medium",
  "owner_name":"Sam",
  "assigner_name":"Jordan",
  "due_at":null,
  "source_confidence":0.6
}' >/dev/null

echo "==> Recurrence template"
curl -sS -X POST "$API_URL/recurrence-templates" -H "Content-Type: application/json" -d '{
  "title":"Weekly review",
  "description":"Review weekly task health and blockers",
  "cadence":"weekly",
  "default_owner_name":"Alex",
  "default_assigner_name":"Jordan",
  "default_due_window_days":3,
  "is_active":true
}' >/dev/null

echo ""
echo "POC seed complete. Next: see docs/runbook.md (End-to-end POC test flow)."
