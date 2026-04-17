#!/usr/bin/env python3
"""
Threads 每日熱榜 HTML 渲染器
讀取 data/per_topic/{anime,love,cosplay}.json 的 top_posts（已過濾到 ~36h），
產出 B-hero 卡片風格的 daily/index.html。

每張卡片含：排名 + 原文 + AI 點評 + 四指標。
整張卡片可點擊跳轉貼文 URL。

用法：
  python3 scripts/render_daily.py              # 產 daily/index.html
  python3 scripts/render_daily.py --with-ai     # 先跑 AI 點評再渲染（會呼叫 Claude API）
"""
import json, argparse, os, ssl, urllib.request
from pathlib import Path
from datetime import datetime, timezone, timedelta

try:
    import certifi
    _CA_FILE = certifi.where()
except ImportError:
    _CA_FILE = None

PROJECT_DIR = Path(__file__).resolve().parent.parent
PER_TOPIC_DIR = PROJECT_DIR / "data" / "per_topic"
DAILY_RAW_DIR = PROJECT_DIR / "data" / "raw" / "daily"
OUTPUT_DIR = PROJECT_DIR / "daily"
OUTPUT_HTML = OUTPUT_DIR / "index.html"
TZ_TPE = timezone(timedelta(hours=8))

TOPICS = ["anime", "love", "cosplay"]
TOPIC_LABELS = {"anime": "動漫", "love": "交友", "cosplay": "Cosplay"}
TOPIC_EMOJI = {"anime": "🎌", "love": "💔", "cosplay": "✨"}
TOPIC_ACCENT = {"anime": "#0079C6", "love": "#c45a3c", "cosplay": "#7c3aed"}
TOP_N = 5

API_URL = "https://api.anthropic.com/v1/messages"
MODEL = "claude-sonnet-4-5-20250929"


def load_api_key():
    key = os.environ.get("ANTHROPIC_API_KEY")
    if key:
        return key
    env_file = PROJECT_DIR / ".env"
    if env_file.exists():
        for line in env_file.read_text().splitlines():
            if line.startswith("ANTHROPIC_API_KEY"):
                return line.split("=", 1)[1].strip().strip('"').strip("'")
    return None


def generate_ai_comment(post, topic_label):
    """呼叫 Claude API 產出單篇短評（40-80 字）"""
    api_key = load_api_key()
    if not api_key:
        return None
    prompt = f"""你是 Threads 社群分析師。以下是一篇「{topic_label}」主題的熱門貼文：

作者：@{post['author']}
互動：❤️{post['likes']} 💬{post['comments']} 🔁{post['reposts']} ✈️{post['shares']}（總 {post['total_engagement']}）
類型：Type {post['primary_type']}
原文：{post['text'][:300]}

請用繁體中文寫一段 40-80 字的點評，包含：
1. 為什麼這篇會爆紅（觸發什麼情緒/機制）
2. CosMate（Coser 交友 App）可以怎麼模仿這類內容

直接回純文字，不要 JSON、不要引號、不要「根據資料」開頭。"""

    body = json.dumps({
        "model": MODEL, "max_tokens": 300,
        "messages": [{"role": "user", "content": prompt}],
    }).encode("utf-8")
    req = urllib.request.Request(API_URL, data=body, method="POST", headers={
        "content-type": "application/json",
        "x-api-key": api_key,
        "anthropic-version": "2023-06-01",
    })
    ctx = ssl.create_default_context(cafile=_CA_FILE) if _CA_FILE else ssl.create_default_context()
    import time as _t
    for attempt in range(3):
        try:
            with urllib.request.urlopen(req, timeout=60, context=ctx) as resp:
                result = json.loads(resp.read().decode("utf-8"))
            return result["content"][0]["text"].strip()
        except urllib.error.HTTPError as e:
            if e.code == 429 and attempt < 2:
                wait = (attempt + 1) * 5
                print(f"    ⏳ 429 rate limit，等 {wait}s 後重試...")
                _t.sleep(wait)
                continue
            print(f"    ⚠️  AI 點評失敗: {e}")
            return None
        except Exception as e:
            print(f"    ⚠️  AI 點評失敗: {e}")
            return None


def load_topic_data(topic):
    path = PER_TOPIC_DIR / f"{topic}.json"
    if not path.exists():
        return None
    return json.load(open(path, encoding="utf-8"))


def save_daily_raw(date_str, topic, posts):
    """儲存 daily raw 到 data/raw/daily/YYYY-MM-DD/{topic}.json"""
    day_dir = DAILY_RAW_DIR / date_str
    day_dir.mkdir(parents=True, exist_ok=True)
    out = {
        "date": date_str,
        "window_hours": 36,
        "topic": topic,
        "scraped_at": datetime.now(TZ_TPE).isoformat(),
        "posts": posts,
    }
    (day_dir / f"{topic}.json").write_text(
        json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8"
    )


def escape(s):
    return str(s).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace('"', "&quot;")


def render():
    parser = argparse.ArgumentParser()
    parser.add_argument("--with-ai", action="store_true", help="產 AI 單篇點評（需 ANTHROPIC_API_KEY）")
    args = parser.parse_args()

    now = datetime.now(TZ_TPE)
    generated = now.strftime("%Y-%m-%d %H:%M")
    date_str = now.strftime("%Y-%m-%d")

    # 收集各主題 top N
    all_topics_data = {}
    for topic in TOPICS:
        data = load_topic_data(topic)
        if not data:
            print(f"  ⚠️  {topic}: 無資料")
            continue
        # 取 top N（已過濾到 --days 2 的 ~36h 窗口）
        qualified = [p for p in data.get("top_posts", []) if p.get("primary_type") != "X"][:TOP_N]
        if not qualified:
            qualified = data.get("top_posts", [])[:TOP_N]

        # AI 點評
        if args.with_ai:
            import time as _time
            print(f"  🤖 {topic}: 產 AI 點評（{len(qualified)} 篇）")
            for idx, p in enumerate(qualified):
                if idx > 0:
                    _time.sleep(3)  # 避免 429 rate limit
                comment = generate_ai_comment(p, TOPIC_LABELS[topic])
                p["ai_comment"] = comment or ""
        else:
            for p in qualified:
                p["ai_comment"] = p.get("ai_comment", "")

        all_topics_data[topic] = qualified

        # 儲存 daily raw
        save_daily_raw(date_str, topic, [
            {k: p[k] for k in ["author", "url", "text", "likes", "comments",
                                "reposts", "shares", "total_engagement",
                                "primary_type", "dt", "ai_comment"]}
            for p in qualified
        ])

    if not all_topics_data:
        print("❌ 無任何主題資料")
        return

    # 內嵌 JSON
    embedded = json.dumps(all_topics_data, ensure_ascii=False)

    # Tab buttons
    tab_buttons = "".join(
        f'<button class="tab{" active" if i == 0 else ""}" data-topic="{t}" '
        f'style="--tab-accent:{TOPIC_ACCENT[t]}">'
        f'{TOPIC_EMOJI[t]} {TOPIC_LABELS[t]}</button>'
        for i, t in enumerate(TOPICS) if t in all_topics_data
    )

    panels = "".join(
        f'<div class="panel{" active" if i == 0 else ""}" id="panel-{t}"></div>'
        for i, t in enumerate(TOPICS) if t in all_topics_data
    )

    html = f"""<!DOCTYPE html>
<html lang="zh-TW">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Threads 今日最熱 — {date_str}</title>
<link href="https://fonts.googleapis.com/css2?family=Noto+Serif+TC:wght@400;600;700&family=Inter:wght@400;600;800&display=swap" rel="stylesheet">
<style>
:root {{ --bg:#f5f0e8; --card:#fffdf7; --border:#ddd5c4; --text:#1a1a18; --muted:#7a7568; --accent:#c45a3c; }}
* {{ margin:0; padding:0; box-sizing:border-box; }}
body {{ background:var(--bg); color:var(--text); font-family:'Noto Serif TC','Georgia',serif; line-height:1.7; }}
.container {{ max-width:720px; margin:0 auto; padding:32px 16px; }}

header {{ text-align:center; margin-bottom:36px; border-bottom:3px double var(--border); padding-bottom:24px; }}
.edition {{ font-family:'Inter',sans-serif; font-size:0.7rem; color:var(--muted); letter-spacing:4px; text-transform:uppercase; }}
h1 {{ font-size:2rem; font-weight:700; margin:8px 0; letter-spacing:1px; }}
.sub {{ font-size:0.85rem; color:var(--muted); font-style:italic; }}
.nav-links {{ font-family:'Inter',sans-serif; font-size:0.75rem; margin-top:12px; }}
.nav-links a {{ color:var(--accent); text-decoration:none; }}

.tabs {{ display:flex; justify-content:center; gap:20px; margin-bottom:28px; }}
.tab {{ font-family:'Inter',sans-serif; font-size:0.8rem; font-weight:600; letter-spacing:2px; text-transform:uppercase; color:var(--muted); cursor:pointer; padding-bottom:4px; border:none; background:none; transition:all 0.2s; }}
.tab:hover {{ color:var(--text); }}
.tab.active {{ color:var(--tab-accent); border-bottom:2px solid var(--tab-accent); }}

.panel {{ display:none; }}
.panel.active {{ display:block; }}

.post-card {{
  display:block; text-decoration:none; color:inherit;
  background:var(--card); border:1px solid var(--border); border-radius:6px;
  padding:28px 28px 20px; margin-bottom:20px; position:relative;
  transition:box-shadow 0.2s, border-color 0.2s; cursor:pointer;
}}
.post-card:hover {{ box-shadow:0 6px 24px rgba(0,0,0,0.08); border-color:var(--accent); }}

.rank-badge {{ position:absolute; top:-10px; left:20px; background:var(--accent); color:#fff; font-family:'Inter',sans-serif; font-size:0.7rem; font-weight:800; padding:4px 12px; border-radius:14px; letter-spacing:1px; }}
.topic-tag {{ font-family:'Inter',sans-serif; font-size:0.62rem; letter-spacing:3px; text-transform:uppercase; color:var(--accent); font-weight:700; margin-bottom:6px; }}
.author-row {{ display:flex; align-items:center; gap:8px; margin-bottom:10px; flex-wrap:wrap; }}
.author {{ font-family:'Inter',sans-serif; font-weight:700; font-size:0.9rem; }}
.time {{ font-family:'Inter',sans-serif; font-size:0.7rem; color:var(--muted); }}
.type-badge {{ font-family:'Inter',sans-serif; font-size:0.62rem; font-weight:700; padding:2px 8px; border-radius:4px; background:#f0ede4; color:var(--muted); }}

.original-text {{ font-size:1rem; line-height:1.85; margin:14px 0; padding:14px 18px; background:#faf8f2; border-left:3px solid var(--border); border-radius:0 6px 6px 0; white-space:pre-wrap; word-break:break-word; }}

.ai-comment {{ margin:14px 0; padding:12px 16px; background:linear-gradient(135deg,#1a1a18,#2a2924); color:#f5f0e8; border-radius:8px; font-family:'Inter',sans-serif; font-size:0.85rem; line-height:1.65; }}
.ai-comment .label {{ font-size:0.62rem; letter-spacing:2px; text-transform:uppercase; color:var(--accent); margin-bottom:4px; display:block; }}

.metrics {{ display:flex; gap:14px; font-family:'Inter',sans-serif; font-size:0.78rem; color:var(--muted); padding-top:10px; border-top:1px solid var(--border); flex-wrap:wrap; }}
.metrics span {{ display:flex; align-items:center; gap:3px; }}
.metrics .total {{ color:var(--accent); font-weight:800; font-size:0.85rem; margin-left:auto; }}

.empty {{ text-align:center; color:var(--muted); padding:40px; font-style:italic; }}

footer {{ text-align:center; color:var(--muted); font-size:0.7rem; margin-top:32px; padding-top:16px; border-top:1px solid var(--border); font-family:'Inter',sans-serif; }}
footer a {{ color:var(--accent); text-decoration:none; }}

@media (max-width:640px) {{
  .container {{ padding:20px 12px; }}
  h1 {{ font-size:1.5rem; }}
  .post-card {{ padding:20px 16px 16px; }}
  .original-text {{ font-size:0.92rem; padding:10px 14px; }}
}}
</style>
</head>
<body>
<div class="container">
  <header>
    <div class="edition">Daily Hot · {date_str}</div>
    <h1>Threads 今日最熱</h1>
    <div class="sub">過去 36 小時 · {' × '.join(TOPIC_LABELS[t] for t in TOPICS if t in all_topics_data)}</div>
    <div class="nav-links">
      <a href="https://threads-analytics-report.pages.dev/">← 週報</a>
      &nbsp;·&nbsp;
      <a href="https://threads-analytics-report.pages.dev/reports/archive/">📚 Archive</a>
    </div>
  </header>

  <div class="tabs">{tab_buttons}</div>
  {panels}

  <footer>
    36h window · Playwright scraper · AI by Claude · Generated {generated} GMT+8<br>
    <a href="https://threads-analytics-report.pages.dev/">週報</a> · <a href="https://threads-analytics-report.pages.dev/reports/archive/">Archive</a>
  </footer>
</div>

<script>
const DATA = {embedded};

const TYPE_NAMES = {{
  'A': '全能爆款', 'B': '私域擴散', 'C': '戰場議論',
  'D': '靜默共鳴', 'E': '穩定互動', 'X': '長尾'
}};
const TYPE_EMOJI = {{
  'A': '🔥', 'B': '✈️', 'C': '💬', 'D': '❤️', 'E': '📊', 'X': '🫧'
}};

function esc(s) {{ return String(s).replace(/[&<>"']/g, c => ({{'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}}[c])); }}
function fmt(n) {{ return n.toLocaleString(); }}

function renderPanel(topic) {{
  const posts = DATA[topic];
  if (!posts || !posts.length) return '<div class="empty">近 36 小時無符合標準貼文</div>';

  return posts.map((p, i) => {{
    const text = (p.text || '').replace(/\\n/g, '<br>').slice(0, 400);
    const dt = p.dt ? p.dt.slice(0, 16).replace('T', ' ') : '';
    const typeName = TYPE_NAMES[p.primary_type] || p.primary_type;
    const typeEmoji = TYPE_EMOJI[p.primary_type] || '';
    const aiHtml = p.ai_comment
      ? `<div class="ai-comment"><span class="label">🧠 AI 點評</span>${{esc(p.ai_comment)}}</div>`
      : '';
    const url = p.url || '#';

    return `<a href="${{esc(url)}}" target="_blank" rel="noopener" class="post-card">
      <div class="rank-badge">#${{i + 1}}</div>
      <div class="author-row">
        <div class="author">@${{esc(p.author)}}</div>
        <div class="time">${{dt}}</div>
        <div class="type-badge">${{typeEmoji}} Type ${{p.primary_type}} ${{typeName}}</div>
      </div>
      <div class="original-text">${{text}}</div>
      ${{aiHtml}}
      <div class="metrics">
        <span>❤️ ${{fmt(p.likes)}}</span>
        <span>💬 ${{fmt(p.comments)}}</span>
        <span>🔁 ${{fmt(p.reposts)}}</span>
        <span>✈️ ${{fmt(p.shares)}}</span>
        <span class="total">${{fmt(p.total_engagement)}} 互動</span>
      </div>
    </a>`;
  }}).join('');
}}

// Init panels
document.querySelectorAll('.panel').forEach(panel => {{
  panel.innerHTML = renderPanel(panel.id.replace('panel-', ''));
}});

// Tab switching
document.querySelectorAll('.tab').forEach(btn => {{
  btn.addEventListener('click', () => {{
    document.querySelectorAll('.tab').forEach(b => b.classList.remove('active'));
    document.querySelectorAll('.panel').forEach(p => p.classList.remove('active'));
    btn.classList.add('active');
    document.getElementById('panel-' + btn.dataset.topic).classList.add('active');
  }});
}});
</script>
</body>
</html>"""

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    OUTPUT_HTML.write_text(html, encoding="utf-8")
    print(f"✅ {OUTPUT_HTML} ({len(html):,} bytes)")


if __name__ == "__main__":
    render()
