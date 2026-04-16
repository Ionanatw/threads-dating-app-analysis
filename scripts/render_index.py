#!/usr/bin/env python3
"""
讀取 data/per_topic/{anime,love,cosplay}.json，產出三 tab 版的 index.html
資料以 <script>const DATA = {...}</script> 內嵌，避免 fetch CORS 問題。
"""
import json
from pathlib import Path
from datetime import datetime, timezone, timedelta

PROJECT_DIR = Path(__file__).resolve().parent.parent
PER_TOPIC_DIR = PROJECT_DIR / "data" / "per_topic"
OUTPUT_HTML = PROJECT_DIR / "index.html"
ARCHIVE_DIR = PROJECT_DIR / "reports" / "archive"

TOPICS = ["anime", "love", "cosplay", "cosmate"]
TOPIC_LABELS = {"anime": "動漫", "love": "交友", "cosplay": "Cosplay", "cosmate": "CosMate"}
TOPIC_EMOJI = {"anime": "🎌", "love": "💔", "cosplay": "✨", "cosmate": "📈"}
TOPIC_ACCENT = {"anime": "#0079C6", "love": "#ff3b5c", "cosplay": "#a855f7", "cosmate": "#d97757"}

TZ_TPE = timezone(timedelta(hours=8))


def load_all():
    data = {}
    for t in TOPICS:
        p = PER_TOPIC_DIR / f"{t}.json"
        if not p.exists():
            print(f"  ⚠️  missing: {p}")
            continue
        data[t] = json.load(open(p, encoding="utf-8"))
    return data


def fmt_date(iso):
    if not iso:
        return "—"
    return iso[:10]


def render():
    data = load_all()
    if not data:
        raise SystemExit("No per_topic data found. Run analyze_by_topic.py --all first.")

    now = datetime.now(TZ_TPE)
    generated = now.strftime("%Y-%m-%d %H:%M")
    iso_year, iso_week, _ = now.isocalendar()
    week_slug = f"{iso_year}-W{iso_week:02d}"

    # 內嵌 JSON
    embedded = json.dumps(data, ensure_ascii=False)

    # Tab buttons + panels
    tab_buttons = "".join(
        f'<button class="tab-btn{" active" if i==0 else ""}" data-topic="{t}" '
        f'style="--accent:{TOPIC_ACCENT[t]}">'
        f'{TOPIC_EMOJI[t]} {TOPIC_LABELS[t]}'
        f'</button>'
        for i, t in enumerate(TOPICS)
    )

    panels = "".join(
        f'<div class="panel{" active" if i==0 else ""}" id="panel-{t}" data-topic="{t}"></div>'
        for i, t in enumerate(TOPICS)
    )

    html = f"""<!DOCTYPE html>
<html lang="zh-TW">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Threads 週一熱門報告 — 動漫 × 交友 × Cosplay</title>
<link href="https://fonts.googleapis.com/css2?family=Inter:wght@300;400;600;800&display=swap" rel="stylesheet">
<style>
:root {{
  --bg: #faf9f5;
  --card-bg: #ffffff;
  --glass-border: #e8e6dc;
  --text-primary: #141413;
  --text-secondary: #8a8679;
  --accent-warm: #d97757;
}}
* {{ margin:0; padding:0; box-sizing:border-box; }}
body {{ background:var(--bg); color:var(--text-primary); font-family:'Inter',sans-serif; line-height:1.6; }}
.container {{ max-width:1200px; margin:0 auto; padding:40px 20px; }}
header {{ text-align:center; margin-bottom:40px; }}
.subtitle {{ color:var(--text-secondary); font-size:0.85rem; letter-spacing:3px; text-transform:uppercase; }}
h1 {{ font-size:2.4rem; font-weight:800; letter-spacing:-1px; margin-top:10px; line-height:1.2; }}
.gen {{ color:var(--text-secondary); font-size:0.8rem; margin-top:12px; }}

.tabs {{ display:flex; justify-content:center; gap:8px; margin-bottom:32px; flex-wrap:wrap; }}
.tab-btn {{
  background:var(--card-bg); color:var(--text-primary);
  border:1px solid var(--glass-border); border-radius:999px;
  padding:10px 24px; font-size:0.95rem; font-weight:600; cursor:pointer;
  transition:all 0.2s; font-family:inherit;
}}
.tab-btn:hover {{ background:#f3f1ea; }}
.tab-btn.active {{ background:var(--accent); border-color:var(--accent); color:#fff; box-shadow:0 4px 16px color-mix(in srgb,var(--accent) 25%,transparent); }}

.panel {{ display:none; }}
.panel.active {{ display:block; }}

.metrics-grid {{ display:grid; grid-template-columns:repeat(auto-fit,minmax(180px,1fr)); gap:16px; margin-bottom:32px; }}
.metric-card {{ background:var(--card-bg); border:1px solid var(--glass-border); border-radius:16px; padding:20px; text-align:center; }}
.metric-value {{ font-size:1.8rem; font-weight:800; display:block; }}
.metric-label {{ font-size:0.75rem; color:var(--text-secondary); text-transform:uppercase; margin-top:4px; }}

.section-title {{ font-size:1.3rem; font-weight:800; margin:32px 0 16px; display:flex; align-items:center; gap:10px; }}
.section-title small {{ font-size:0.8rem; color:var(--text-secondary); font-weight:400; }}

.card {{ background:var(--card-bg); border:1px solid var(--glass-border); border-radius:20px; padding:24px; margin-bottom:24px; }}

table {{ width:100%; border-collapse:collapse; }}
th {{ text-align:left; color:var(--text-secondary); font-size:0.75rem; font-weight:600; padding:8px 10px; border-bottom:1px solid var(--glass-border); text-transform:uppercase; letter-spacing:0.5px; }}
td {{ padding:12px 10px; border-bottom:1px solid var(--glass-border); font-size:0.88rem; }}
td.num {{ text-align:right; font-variant-numeric:tabular-nums; }}
td a {{ color:var(--text-primary); text-decoration:none; }}
td a:hover {{ color:var(--accent); }}
.text-cell {{ max-width:480px; color:var(--text-secondary); }}

.type-row {{ display:flex; align-items:center; gap:12px; margin-bottom:8px; }}
.type-badge {{ width:36px; height:36px; border-radius:8px; display:flex; align-items:center; justify-content:center; font-size:18px; flex-shrink:0; }}
.type-info {{ flex:1; }}
.type-name {{ font-size:0.9rem; font-weight:600; }}
.type-desc {{ font-size:0.75rem; color:var(--text-secondary); }}
.type-bar-wrap {{ width:140px; height:8px; background:#f0ede4; border-radius:4px; overflow:hidden; }}
.type-bar {{ height:100%; border-radius:4px; }}

.hourly {{ display:grid; grid-template-columns:repeat(24,1fr); gap:3px; height:120px; align-items:end; margin-top:12px; }}
.hour-bar {{ background:var(--accent); border-radius:3px 3px 0 0; opacity:0.7; min-height:2px; position:relative; transition:opacity 0.2s; }}
.hour-bar:hover {{ opacity:1; }}
.hour-bar:hover::after {{ content:attr(data-tooltip); position:absolute; bottom:100%; left:50%; transform:translateX(-50%); background:#141413; color:#fff; padding:4px 8px; border-radius:4px; font-size:11px; white-space:nowrap; pointer-events:none; z-index:10; }}
.hour-labels {{ display:grid; grid-template-columns:repeat(24,1fr); gap:3px; margin-top:6px; font-size:9px; color:var(--text-secondary); text-align:center; }}

.daily {{ display:grid; grid-template-columns:repeat(7,1fr); gap:8px; margin-top:12px; }}
.day-cell {{ background:#f3f1ea; border-radius:8px; padding:10px; text-align:center; }}
.day-cell .label {{ font-size:0.75rem; color:var(--text-secondary); }}
.day-cell .count {{ font-size:1.2rem; font-weight:700; }}
.day-cell .eng {{ font-size:0.7rem; color:var(--accent); }}

footer {{ text-align:center; color:var(--text-secondary); font-size:0.75rem; margin-top:40px; padding-top:24px; border-top:1px solid var(--glass-border); }}

@media (max-width:768px) {{
  h1 {{ font-size:1.8rem; }}
  .text-cell {{ max-width:200px; overflow:hidden; text-overflow:ellipsis; white-space:nowrap; }}
  .hourly {{ height:80px; }}
  .daily {{ grid-template-columns:repeat(7,1fr); gap:4px; }}
  .day-cell {{ padding:6px 4px; }}
}}
</style>
</head>
<body>
<div class="container">
  <header>
    <div class="subtitle">Weekly Trends Insight · <a href="https://threads-analytics-report.pages.dev/reports/archive/" style="color:var(--text-secondary);text-decoration:underline;">📚 歷史週報</a></div>
    <h1>Threads 週一熱門報告<br>動漫 × 交友 × Cosplay</h1>
    <div class="gen">Generated {generated} GMT+8 · 本週 {week_slug} · 主報告近 30 天 · 進階區塊近 7 天</div>
  </header>

  <div class="tabs">{tab_buttons}</div>

  {panels}

  <footer>
    Data: Apify Threads scraper · Analysis: percentile-based classification (Type A-E + X) · Powered by Claude
  </footer>
</div>

<script>
const DATA = {embedded};

function escapeHtml(s) {{
  return String(s).replace(/[&<>"']/g, c => ({{'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}}[c]));
}}

function fmt(n) {{ return n.toLocaleString(); }}

function fmtDate(iso) {{ return iso ? iso.slice(0,10) : '—'; }}

function renderPanel(topic, accent) {{
  const d = DATA[topic];
  if (!d) return '<p style="color:#a0a0a0;text-align:center;padding:40px;">No data</p>';

  // Hero metrics
  const top1 = d.top_posts[0];
  const daysWindow = d.days_window || 30;

  let html = `
    <div class="metrics-grid">
      <div class="metric-card">
        <span class="metric-value" style="color:${{accent}}">${{d.total_posts}}</span>
        <span class="metric-label">近 ${{daysWindow}} 天貼文</span>
      </div>
      <div class="metric-card">
        <span class="metric-value" style="color:${{accent}}">${{d.total_posts_7d}}</span>
        <span class="metric-label">近 7 天貼文</span>
      </div>
      <div class="metric-card">
        <span class="metric-value" style="color:${{accent}}">${{fmt(top1.likes)}}</span>
        <span class="metric-label">最高單篇按讚</span>
      </div>
      <div class="metric-card">
        <span class="metric-value" style="color:${{accent}}">${{fmt(d.thresholds.likes_p90)}}</span>
        <span class="metric-label">爆款門檻 (P90)</span>
      </div>
    </div>
  `;

  // Helper to render a post table
  function renderPostTable(posts) {{
    let h = `<div class="card"><table>
      <thead><tr>
        <th>排名</th><th>用戶</th><th>內容</th>
        <th class="num">❤️</th><th class="num">💬</th><th class="num">🔁</th><th class="num">✈️</th>
        <th class="num">類型</th>
      </tr></thead><tbody>`;
    posts.forEach((p, i) => {{
      const text = p.text.replace(/\\n/g, ' ').slice(0, 70);
      const linkOpen = p.url ? `<a href="${{escapeHtml(p.url)}}" target="_blank" rel="noopener">` : '';
      const linkClose = p.url ? '</a>' : '';
      h += `<tr>
        <td style="color:${{accent}};font-weight:700">#${{i+1}}</td>
        <td>${{linkOpen}}@${{escapeHtml(p.author)}}${{linkClose}}</td>
        <td class="text-cell">${{escapeHtml(text)}}</td>
        <td class="num">${{fmt(p.likes)}}</td>
        <td class="num">${{fmt(p.comments)}}</td>
        <td class="num">${{fmt(p.reposts)}}</td>
        <td class="num">${{fmt(p.shares)}}</td>
        <td class="num"><span style="background:${{d.type_info[p.primary_type].color}};color:#000;padding:2px 8px;border-radius:4px;font-size:0.75rem;font-weight:600">${{p.primary_type}}</span></td>
      </tr>`;
    }});
    h += `</tbody></table></div>`;
    return h;
  }}

  // 標準：只取非 Type X（A/B/C/D/E）
  const qualified30d = d.top_posts.filter(p => p.primary_type !== 'X');
  const qualified7d = (d.top_posts_7d || []).filter(p => p.primary_type !== 'X');

  // Top 10 posts — 近 N 天
  html += `<h2 class="section-title">🔥 Top 10 熱門貼文 <small>近 ${{daysWindow}} 天 · 排除 Type X 長尾</small></h2>`;
  if (qualified30d.length > 0) {{
    html += renderPostTable(qualified30d.slice(0, 10));
  }} else {{
    html += `<div class="card" style="text-align:center;color:var(--text-secondary);padding:32px">近 ${{daysWindow}} 天無符合標準貼文</div>`;
  }}

  // Top 10 posts — 近 7 天（進階區塊）
  html += `<h2 class="section-title">⚡ 近 7 天最熱 <small>${{d.total_posts_7d}} 篇 · 僅列符合標準（A-E）</small></h2>`;
  if (qualified7d.length > 0) {{
    html += renderPostTable(qualified7d.slice(0, 10));
  }} else {{
    html += `<div class="card" style="text-align:center;color:var(--text-secondary);padding:32px">本週無符合標準貼文</div>`;
  }}

  // Type distribution
  html += `<h2 class="section-title">📊 互動類型分布 <small>單篇可同時符合多型</small></h2><div class="card">`;
  const maxCount = Math.max(...Object.values(d.type_counts));
  ['A','B','C','D','E','X'].forEach(t => {{
    const info = d.type_info[t];
    const cnt = d.type_counts[t];
    const pct = Math.round(cnt / d.total_posts * 100);
    const barW = maxCount ? Math.round(cnt / maxCount * 100) : 0;
    html += `<div class="type-row">
      <div class="type-badge" style="background:${{info.color}}">${{info.emoji}}</div>
      <div class="type-info">
        <div class="type-name">Type ${{t}}：${{info.name}} <span style="color:${{accent}}">${{cnt}}篇 (${{pct}}%)</span></div>
        <div class="type-desc">${{info.desc}}</div>
      </div>
      <div class="type-bar-wrap"><div class="type-bar" style="background:${{info.color}};width:${{barW}}%"></div></div>
    </div>`;
  }});
  html += `</div>`;

  // Hourly distribution
  html += `<h2 class="section-title">⏰ 24 小時發文分布 <small>台北時間 GMT+8</small></h2><div class="card">`;
  const hourlyArr = Array.from({{length:24}}, (_,h) => d.hourly[h] || {{count:0,avg_engagement:0}});
  const maxH = Math.max(...hourlyArr.map(x => x.count)) || 1;
  html += `<div class="hourly">`;
  hourlyArr.forEach((h, i) => {{
    const ht = Math.round(h.count / maxH * 100);
    html += `<div class="hour-bar" style="height:${{ht}}%;background:${{accent}}" data-tooltip="${{i}}:00 · ${{h.count}}篇 · 平均${{Math.round(h.avg_engagement).toLocaleString()}}互動"></div>`;
  }});
  html += `</div><div class="hour-labels">`;
  for (let h = 0; h < 24; h++) html += `<div>${{h % 3 === 0 ? h : ''}}</div>`;
  html += `</div></div>`;

  // Daily distribution
  html += `<h2 class="section-title">📅 週間分布</h2><div class="card"><div class="daily">`;
  ['週一','週二','週三','週四','週五','週六','週日'].forEach(day => {{
    const dd = d.daily[day] || {{count:0,avg_engagement:0}};
    html += `<div class="day-cell">
      <div class="label">${{day}}</div>
      <div class="count">${{dd.count}}</div>
      <div class="eng">${{Math.round(dd.avg_engagement).toLocaleString()}}</div>
    </div>`;
  }});
  html += `</div></div>`;

  // AI 洞察分析（若有）
  const insight = d.ai_insight;
  if (insight) {{
    html += `<h2 class="section-title" style="margin-top:48px">🧠 AI 洞察分析</h2>`;
    html += `<div class="card" style="border-left:4px solid ${{accent}};padding:28px;">`;
    html += `<div style="font-size:1.2rem;font-weight:800;margin-bottom:20px;line-height:1.4;">${{escapeHtml(insight.headline)}}</div>`;

    (insight.patterns || []).forEach((pat, i) => {{
      html += `<div style="margin-bottom:24px${{i > 0 ? ';border-top:1px solid var(--glass-border);padding-top:20px' : ''}}">`;
      html += `<div style="font-weight:700;font-size:1rem;margin-bottom:6px;">${{['🔥','✈️','💬','❤️'][i] || '📊'}} ${{escapeHtml(pat.name)}} <span style="color:${{accent}};font-size:0.85rem;font-weight:600;">${{escapeHtml(pat.trigger_type)}}</span></div>`;
      html += `<div style="color:var(--text-secondary);font-size:0.9rem;margin-bottom:12px;">${{escapeHtml(pat.desc)}}</div>`;

      // 代表案例
      (pat.examples || []).forEach(ex => {{
        html += `<div style="background:var(--bg);border-radius:10px;padding:12px 16px;margin-bottom:8px;">`;
        html += `<span style="font-weight:600;color:${{accent}}">${{escapeHtml(ex.author)}}</span>`;
        html += ` <span style="font-size:0.8rem;color:var(--text-secondary)">${{escapeHtml(ex.metric)}}</span><br>`;
        html += `<span style="font-size:0.88rem">「${{escapeHtml(ex.text)}}」</span>`;
        html += `</div>`;
      }});

      // 操作要點
      html += `<div style="margin-top:10px;padding:10px 14px;background:#f8f5ee;border-radius:8px;font-size:0.85rem;">`;
      html += `<strong>操作要點：</strong>${{escapeHtml(pat.actionable)}}`;
      html += `</div></div>`;
    }});

    // 隱藏發現
    if (insight.hidden_finding) {{
      html += `<div style="margin-top:20px;padding:16px 20px;background:linear-gradient(135deg,#141413,#2a2924);color:#fff;border-radius:12px;">`;
      html += `<div style="font-size:0.75rem;text-transform:uppercase;letter-spacing:2px;color:${{accent}};margin-bottom:8px;">Hidden Finding</div>`;
      html += `<div style="font-size:0.95rem;line-height:1.6;">${{escapeHtml(insight.hidden_finding)}}</div>`;
      html += `</div>`;
    }}

    html += `</div>`;
  }}

  return html;
}}

// Init
document.querySelectorAll('.panel').forEach(panel => {{
  const topic = panel.dataset.topic;
  const accent = getComputedStyle(document.querySelector(`.tab-btn[data-topic="${{topic}}"]`)).getPropertyValue('--accent').trim();
  panel.innerHTML = renderPanel(topic, accent);
}});

// Tab switching
document.querySelectorAll('.tab-btn').forEach(btn => {{
  btn.addEventListener('click', () => {{
    const topic = btn.dataset.topic;
    document.querySelectorAll('.tab-btn').forEach(b => b.classList.remove('active'));
    document.querySelectorAll('.panel').forEach(p => p.classList.remove('active'));
    btn.classList.add('active');
    document.getElementById('panel-' + topic).classList.add('active');
  }});
}});
</script>
</body>
</html>"""

    OUTPUT_HTML.write_text(html, encoding="utf-8")
    print(f"✅ {OUTPUT_HTML} ({len(html):,} bytes)")

    # 同時寫 archive — 歷史版本保留（為了從 /archive/ 相對路徑正確載入，連結用 ../../）
    week_dir = ARCHIVE_DIR / week_slug
    week_dir.mkdir(parents=True, exist_ok=True)
    archive_html = html.replace('href="reports/archive/"', 'href="../"')
    (week_dir / "index.html").write_text(archive_html, encoding="utf-8")
    print(f"📚 archive → reports/archive/{week_slug}/index.html")


if __name__ == "__main__":
    render()
