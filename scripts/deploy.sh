#!/bin/bash
# 部署報告到 Cloudflare Pages
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"

echo "=== 部署到 Cloudflare Pages ==="
npx wrangler pages deploy "$PROJECT_DIR" \
  --project-name threads-analytics-report \
  --commit-dirty=true

echo ""
echo "Live: https://threads-analytics-report.pages.dev"
