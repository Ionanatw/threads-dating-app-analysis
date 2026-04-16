#!/usr/bin/env python3
"""
掃 reports/archive/ 目錄底下所有 YYYY-Www 子資料夾，產出 archive 列表頁。
讓鴿王可以從 /reports/archive/ 點進過去任一週的歷史週報。
"""
import re, json, subprocess
from pathlib import Path
from datetime import datetime, timedelta

PROJECT_DIR = Path(__file__).resolve().parent.parent
ARCHIVE_DIR = PROJECT_DIR / "reports" / "archive"
OUTPUT = ARCHIVE_DIR / "index.html"
CF_PROJECT = "threads-analytics-report"

WEEK_PATTERN = re.compile(r"^(\d{4})-W(\d{2})$")

# 非週報的歷史 / 平行 Pages 專案（手動維護清單）
OTHER_REPORTS = [
    {
        "category": "早期獨立報告",
        "items": [
            {"title": "Threads 動漫主題貼文分析", "date": "2026-04-08",
             "url": "https://cosmate-threads-anime.pages.dev",
             "note": "四主題週報誕生前的動漫專項版"},
            {"title": "Threads 交友軟體深度洞察報告", "date": "2026-04-07",
             "url": "https://threads-dating-analysis.pages.dev",
             "note": "第一版 dating-only 報告（有手動填的 repost/share）"},
        ],
    },
    {
        "category": "互動 / 測驗專案",
        "items": [
            {"title": "交友軟體心理測驗 — 找回你的靈魂伴侶", "date": "2026-04-13",
             "url": "https://makefriends-quiz.pages.dev",
             "note": "行銷測驗頁"},
            {"title": "你的命定交友 App 是？", "date": "2026-04-09",
             "url": "https://008-makefriends.pages.dev",
             "note": "008 系列測驗"},
            {"title": "2026 交通通行證 — COSER 專用", "date": "2026-04-01",
             "url": "https://cowriding.pages.dev",
             "note": "Coser 活動頁"},
            {"title": "測測你是哪位魔法使（芙莉蓮）", "date": "2026-04-07",
             "url": "https://007-frieren-quiz.pages.dev",
             "note": "芙莉蓮角色心測 · 結果頁缺角色圖（待補）"},
        ],
    },
]


def iso_week_to_date(year, week):
    """ISO week → 該週週一的日期"""
    jan4 = datetime(year, 1, 4)
    jan4_weekday = jan4.isoweekday()  # Monday=1
    week1_monday = jan4 - timedelta(days=jan4_weekday - 1)
    return week1_monday + timedelta(weeks=week - 1)


def git_log_subject(sha):
    """查 git log 取 commit subject；找不到回 None"""
    if not sha:
        return None
    try:
        result = subprocess.run(
            ["git", "log", "-1", "--format=%s", sha],
            capture_output=True, text=True, timeout=5, cwd=PROJECT_DIR,
        )
        if result.returncode == 0:
            return result.stdout.strip() or None
    except Exception:
        pass
    return None


def fetch_cloudflare_deployments():
    """呼叫 wrangler 取得所有部署（失敗則回空 list）
    每筆同時補抓 git commit subject（若在本地 git）"""
    try:
        result = subprocess.run(
            ["npx", "wrangler", "pages", "deployment", "list",
             "--project-name", CF_PROJECT, "--json"],
            capture_output=True, text=True, timeout=60,
        )
        if result.returncode != 0:
            print(f"  ⚠️  wrangler 失敗 ({result.returncode}), 跳過 Cloudflare 區塊")
            return []
        idx = result.stdout.find("[")
        if idx < 0:
            return []
        data = json.loads(result.stdout[idx:])
        prod_only = [d for d in data if d.get("Environment") == "Production"]
        # Enrich 每筆加上 commit subject
        for d in prod_only:
            sha = d.get("Source", "")
            d["commit_subject"] = git_log_subject(sha) if sha else None
        return prod_only
    except (FileNotFoundError, subprocess.TimeoutExpired, json.JSONDecodeError) as e:
        print(f"  ⚠️  wrangler 不可用或回傳異常: {e}")
        return []


def read_archive_meta(week_dir):
    """從 archive 週的 index.html 讀出各主題 Top 1（人類可讀摘要）"""
    import re
    try:
        html = (week_dir / "index.html").read_text(encoding="utf-8")
    except Exception:
        return {}
    m = re.search(r'const DATA = (\{.*?\});', html, re.DOTALL)
    if not m:
        return {}
    try:
        data = json.loads(m.group(1))
    except Exception:
        return {}
    meta = {"topics": {}}
    for topic, emoji in [("anime", "🎌"), ("love", "💔"), ("cosplay", "✨"), ("cosmate", "📈")]:
        d = data.get(topic, {})
        top_posts = d.get("top_posts", [])
        if top_posts:
            p = top_posts[0]
            meta["topics"][topic] = {
                "emoji": emoji,
                "author": p.get("author", ""),
                "total": p.get("total_engagement", 0),
            }
    return meta


def list_archives():
    if not ARCHIVE_DIR.exists():
        return []
    entries = []
    for p in ARCHIVE_DIR.iterdir():
        if not p.is_dir():
            continue
        m = WEEK_PATTERN.match(p.name)
        if not m:
            continue
        year, week = int(m.group(1)), int(m.group(2))
        monday = iso_week_to_date(year, week)
        sunday = monday + timedelta(days=6)
        if (p / "index.html").exists():
            entries.append({
                "slug": p.name,
                "year": year,
                "week": week,
                "monday": monday,
                "sunday": sunday,
                "meta": read_archive_meta(p),
            })
    return sorted(entries, key=lambda x: (x["year"], x["week"]), reverse=True)


def render():
    archives = list_archives()

    def format_row(a):
        month = a["monday"].month
        date_range = f'{a["monday"].strftime("%Y-%m-%d")} ~ {a["sunday"].strftime("%m-%d")}（週一~週日）'
        title = f'{a["year"]} 年 {month} 月 · 第 {a["week"]:02d} 週'
        # Top 1 摘要（各主題）
        topics_meta = a.get("meta", {}).get("topics", {})
        highlights = " · ".join(
            f'{m["emoji"]}@{m["author"]} {m["total"]:,}'
            for m in topics_meta.values()
            if m.get("author")
        ) or '—'
        return (
            f'<tr>'
            f'<td><a href="{a["slug"]}/"><strong>{title}</strong><br>'
            f'<span style="color:#a0a0a0;font-size:0.8rem;font-weight:400">{date_range}</span></a></td>'
            f'<td style="font-size:0.8rem;color:#b0aea5">{highlights}</td>'
            f'<td><a href="{a["slug"]}/" style="color:#d97757">查看 →</a></td>'
            f'</tr>'
        )

    rows = "".join(format_row(a) for a in archives) or \
        '<tr><td colspan="3" style="text-align:center;color:#a0a0a0;padding:32px">目前沒有 archive</td></tr>'

    # 其他報告 / 專案區塊
    other_sections_html = ""
    for cat in OTHER_REPORTS:
        items_html = "".join(
            f'<tr>'
            f'<td><a href="{it["url"]}" target="_blank"><strong>{it["title"]}</strong><br>'
            f'<span style="color:#8a8679;font-size:0.78rem;font-weight:400">{it["date"]}</span></a></td>'
            f'<td style="font-size:0.82rem;color:#8a8679">{it["note"]}</td>'
            f'<td><a href="{it["url"]}" target="_blank" style="color:#d97757">開啟 →</a></td>'
            f'</tr>'
            for it in cat["items"]
        )
        other_sections_html += (
            f'<h2 style="font-size:1.1rem;font-weight:600;margin:32px 0 12px;color:#141413;">{cat["category"]}</h2>'
            f'<table><thead><tr><th>專案</th><th>說明</th><th>操作</th></tr></thead>'
            f'<tbody>{items_html}</tbody></table>'
        )

    # Cloudflare 歷史部署（比 reports/archive/ 更早、或跨主題的版本都在）
    deployments = fetch_cloudflare_deployments()

    def format_cf_row(d, idx):
        when = d.get("Status", "—")  # "2 minutes ago" 這類相對時間
        subject = d.get("commit_subject") or f'（舊版 · commit {d.get("Source","")[:7]} 已不在 repo）'
        marker = " 🟢 目前線上" if idx == 0 else ""
        return (
            f'<tr>'
            f'<td style="color:#b0aea5;white-space:nowrap">{when}{marker}</td>'
            f'<td style="font-size:0.85rem">{subject}</td>'
            f'<td><a href="{d.get("Deployment")}" target="_blank" style="color:#d97757">查看 →</a></td>'
            f'</tr>'
        )

    cf_rows = "".join(format_cf_row(d, i) for i, d in enumerate(deployments)) or \
        '<tr><td colspan="3" style="text-align:center;color:#a0a0a0;padding:20px">無法取得（wrangler 未認證或無網路）</td></tr>'

    html = f"""<!DOCTYPE html>
<html lang="zh-TW">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Threads 週報 Archive</title>
<link href="https://fonts.googleapis.com/css2?family=Inter:wght@300;400;600;800&display=swap" rel="stylesheet">
<style>
*{{margin:0;padding:0;box-sizing:border-box;}}
body{{background:#faf9f5;color:#141413;font-family:'Inter',sans-serif;line-height:1.6;}}
.container{{max-width:800px;margin:0 auto;padding:40px 20px;}}
header{{text-align:center;margin-bottom:40px;}}
.subtitle{{color:#8a8679;font-size:0.85rem;letter-spacing:3px;text-transform:uppercase;}}
h1{{font-size:2.4rem;font-weight:800;margin-top:10px;}}
.gen{{color:#8a8679;font-size:0.8rem;margin-top:12px;}}
table{{width:100%;border-collapse:collapse;background:#fff;border-radius:20px;overflow:hidden;border:1px solid #e8e6dc;}}
th{{text-align:left;color:#8a8679;font-size:0.8rem;padding:14px 20px;border-bottom:1px solid #e8e6dc;text-transform:uppercase;letter-spacing:1px;}}
td{{padding:14px 20px;border-bottom:1px solid #f0ede4;}}
td a{{color:#141413;text-decoration:none;font-weight:600;}}
td a:hover{{color:#d97757;}}
tr:last-child td{{border-bottom:none;}}
.back{{display:inline-block;color:#8a8679;text-decoration:none;margin-bottom:24px;}}
.back:hover{{color:#d97757;}}
</style>
</head>
<body>
<div class="container">
  <a href="../../" class="back">← 回到最新週報</a>
  <header>
    <div class="subtitle">Weekly Report Archive</div>
    <h1>📚 歷史週報</h1>
    <div class="gen">共 {len(archives)} 期 · 最新在上</div>
    <a href="https://github.com/Ionanatw/threads-dating-app-analysis/actions/workflows/weekly.yml"
       target="_blank" rel="noopener"
       style="display:inline-block;margin-top:20px;padding:12px 28px;background:#d97757;color:#fff;
              font-weight:700;border-radius:999px;text-decoration:none;font-size:0.95rem;
              box-shadow:0 0 30px rgba(217,119,87,0.4);">
      🚀 立即產出新報告
    </a>
    <div style="color:#a0a0a0;font-size:0.7rem;margin-top:8px;">
      會跳到 GitHub Actions，點右側「Run workflow」按鈕觸發
    </div>
  </header>

  <h2 style="font-size:1.1rem;font-weight:600;margin-bottom:12px;color:#141413;">週次列表（Threads 四主題週報）</h2>
  <table>
    <thead><tr><th>週次 / 區間</th><th>本週各主題 Top 1</th><th>操作</th></tr></thead>
    <tbody>{rows}</tbody>
  </table>

  {other_sections_html}

  <details style="margin-top:40px;">
    <summary style="cursor:pointer;font-size:1rem;font-weight:600;color:#141413;padding:8px 0;list-style:none;">
      ▸ 部署快照（{len(deployments)} 筆，點開展開）
    </summary>
    <p style="color:#8a8679;font-size:0.8rem;margin:12px 0;">2026-W16 前（4/14 以前）沒進 archive 體系，但每次 deploy 的版本都還在這裡能回看。</p>
    <table>
      <thead><tr><th>部署時間</th><th>版本摘要</th><th>操作</th></tr></thead>
      <tbody>{cf_rows}</tbody>
    </table>
  </details>
</div>
</body>
</html>"""
    ARCHIVE_DIR.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(html, encoding="utf-8")
    print(f"✅ archive index → {OUTPUT} ({len(archives)} 期)")


if __name__ == "__main__":
    render()
