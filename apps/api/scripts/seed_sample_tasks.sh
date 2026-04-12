#!/usr/bin/env bash
set -euo pipefail

API_URL="${API_URL:-http://localhost:8000}"

echo "Seeding sample tasks"
curl -sS -X POST "$API_URL/tasks" -H "Content-Type: application/json" -d '{
  "title":"Daily operations checkpoint",
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
  "title":"Resolve vendor dependency",
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

echo "Seeding recurrence template"
curl -sS -X POST "$API_URL/recurrence-templates" -H "Content-Type: application/json" -d '{
  "title":"Weekly review",
  "description":"Review weekly task health and blockers",
  "cadence":"weekly",
  "default_owner_name":"Alex",
  "default_assigner_name":"Jordan",
  "default_due_window_days":3,
  "is_active":true
}' >/dev/null

echo "Done."
