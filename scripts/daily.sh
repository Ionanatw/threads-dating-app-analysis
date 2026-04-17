#!/bin/bash
# Threads 每日熱榜 — 36 小時內最熱門
#
# 用法：
#   bash scripts/daily.sh                # 爬 + 分析 + AI 點評 + 出 HTML
#   bash scripts/daily.sh skip-scrape    # 只用現有 raw 重算
#   bash scripts/daily.sh no-ai          # 爬 + 分析，不跑 AI 點評

set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
cd "$PROJECT_DIR"

MODE="${1:-full}"

echo "════════════════════════════════════════"
echo "  Threads 每日熱榜 — $(date '+%Y-%m-%d %H:%M')"
echo "  動漫 × 交友 × Cosplay · 36h window"
echo "════════════════════════════════════════"

# Step 1: 爬取（除非 skip-scrape）
if [ "$MODE" != "skip-scrape" ]; then
  echo ""
  echo "▶ Step 1/3: 爬取三主題（Playwright · scroll=4）"
  python3 scripts/scrape_playwright_topics.py --scroll 4
fi

# Step 2: 分析（--days 2 ≈ 48h 涵蓋 36h 窗口）
echo ""
echo "▶ Step 2/3: 分析（近 2 天）"
python3 scripts/analyze_by_topic.py --all --days 2

# Step 3: 渲染 daily HTML（含 AI 或不含）
echo ""
if [ "$MODE" = "no-ai" ] || [ "$MODE" = "skip-scrape" ]; then
  echo "▶ Step 3/3: 渲染每日版 HTML（不含 AI 點評）"
  python3 scripts/render_daily.py
else
  echo "▶ Step 3/3: 渲染每日版 HTML + AI 點評"
  python3 scripts/render_daily.py --with-ai
fi

echo ""
echo "✅ 完成 — daily/index.html"
echo "   本機預覽：open daily/index.html"
echo "   部署請執行：bash scripts/deploy.sh"
