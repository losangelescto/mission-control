#!/usr/bin/env bash
set -euo pipefail

API_URL="${API_URL:-http://localhost:8000}"
CANON_ZIP="${CANON_ZIP:-/home/gkey/Downloads/The Uncommon Pursuit - Active.zip}"
THREAD_PDF_1="${THREAD_PDF_1:-/home/gkey/Downloads/Heather Moots.pdf}"
THREAD_PDF_2="${THREAD_PDF_2:-/home/gkey/Downloads/Denise, Heather & Andrea.pdf}"
BOARD_SEED_TXT="${BOARD_SEED_TXT:-/tmp/board_seed_manual.txt}"
TMP_DIR="${TMP_DIR:-/tmp/mission-control-seed}"

mkdir -p "$TMP_DIR/canon"
unzip -o "$CANON_ZIP" -d "$TMP_DIR/canon" >/dev/null
DOCX_DIR="$TMP_DIR/canon/The Uncommon Pursuit - Active"

echo "Seeding canon DOCX files from: $DOCX_DIR"
for f in "$DOCX_DIR"/*.docx; do
  curl -sS -X POST "$API_URL/sources/upload" \
    -F "source_type=canon_doc" \
    -F "version_label=active_snapshot" \
    -F "is_active_canon_version=true" \
    -F "file=@$f" >/dev/null
  echo "  uploaded $(basename "$f")"
done

echo "Seeding thread PDFs"
curl -sS -X POST "$API_URL/sources/upload" \
  -F "source_type=thread_export" \
  -F "file=@$THREAD_PDF_1" >/dev/null
echo "  uploaded $(basename "$THREAD_PDF_1")"

cp "$THREAD_PDF_2" "$TMP_DIR/thread_2.pdf"
curl -sS -X POST "$API_URL/sources/upload" \
  -F "source_type=thread_export" \
  -F "file=@$TMP_DIR/thread_2.pdf" >/dev/null
echo "  uploaded $(basename "$THREAD_PDF_2")"

if [[ ! -f "$BOARD_SEED_TXT" ]]; then
cat > "$BOARD_SEED_TXT" <<'EOF'
Board seed captured manually from local screenshot.
- Backlog
- Up Next
- In progress
- Blocked
- Completed
EOF
fi

curl -sS -X POST "$API_URL/sources/upload" \
  -F "source_type=board_seed" \
  -F "file=@$BOARD_SEED_TXT" >/dev/null
echo "  uploaded board seed text"

echo "Done."
