#!/bin/bash
# Threads 交友軟體貼文爬蟲
# 使用 Apify logical_scrapers~threads-post-scraper
# 每次執行會累積新資料到 data/raw/

set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
RAW_DIR="$PROJECT_DIR/data/raw"

# Apify token from env or .env file
if [ -z "${APIFY_TOKEN:-}" ]; then
  if [ -f "$PROJECT_DIR/.env" ]; then
    source "$PROJECT_DIR/.env"
  fi
fi

if [ -z "${APIFY_TOKEN:-}" ]; then
  echo "ERROR: APIFY_TOKEN not set. Either:"
  echo "  export APIFY_TOKEN=your_token"
  echo "  or create .env in project root with: APIFY_TOKEN=your_token"
  exit 1
fi

ACTOR="logical_scrapers~threads-post-scraper"
API_URL="https://api.apify.com/v2/acts/${ACTOR}/run-sync-get-dataset-items"
TIMEOUT=300
MAX_POSTS="${MAX_POSTS:-100}"
TIMESTAMP=$(date +%Y-%m-%d_%H%M%S)
OUTPUT_FILE="$RAW_DIR/apify_${TIMESTAMP}.json"

# Search queries - add more as needed
QUERIES=(
  "交友軟體"
  "交友app"
  "交友軟體推薦"
  "交友軟體詐騙"
  "交友軟體脫單"
  "交友軟體約會"
  "tinder探探"
  "bumble配對"
)

echo "=== Threads 交友軟體爬蟲 ==="
echo "Time: $(date)"
echo "Max posts: $MAX_POSTS"
echo "Queries: ${#QUERIES[@]}"
echo ""

# Build startUrls JSON array
START_URLS=""
for q in "${QUERIES[@]}"; do
  ENCODED=$(python3 -c "import urllib.parse; print(urllib.parse.quote('$q'))")
  if [ -n "$START_URLS" ]; then
    START_URLS="$START_URLS,"
  fi
  START_URLS="${START_URLS}{\"url\":\"https://www.threads.com/search?q=${ENCODED}&serp_type=default\"}"
done

PAYLOAD="{\"startUrls\":[${START_URLS}],\"maxPosts\":${MAX_POSTS}}"

echo "Calling Apify..."
HTTP_CODE=$(curl -s -w "%{http_code}" -o "$OUTPUT_FILE" \
  -X POST "${API_URL}?token=${APIFY_TOKEN}&timeout=${TIMEOUT}" \
  -H "Content-Type: application/json" \
  -d "$PAYLOAD")

if [ "$HTTP_CODE" != "200" ] && [ "$HTTP_CODE" != "201" ]; then
  echo "ERROR: HTTP $HTTP_CODE"
  cat "$OUTPUT_FILE"
  rm -f "$OUTPUT_FILE"
  exit 1
fi

# Validate JSON and count results
RESULT=$(python3 -c "
import json
with open('$OUTPUT_FILE') as f:
    data = json.load(f)
if isinstance(data, list):
    threads = len(data)
    replies = sum(len(item.get('replies', [])) for item in data)
    print(f'{threads} threads, {replies} replies')
else:
    print('ERROR: unexpected format')
")

echo "Result: $RESULT"
echo "Saved: $OUTPUT_FILE"
echo ""
echo "Next: run 'python3 scripts/analyze.py' to generate the report"
