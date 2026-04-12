#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Primary path: bundled fixtures under apps/api/fixtures/poc (no local PDF/ZIP paths).
"$SCRIPT_DIR/seed_poc_data.sh"

echo "Local POC seed completed."
