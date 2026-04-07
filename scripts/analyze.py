#!/usr/bin/env python3
"""
Threads 交友軟體貼文分析器
讀取 data/raw/ 所有 JSON，去重、分類、產生 HTML 報告
"""

import json, csv, os, re, math, statistics
from pathlib import Path
from datetime import datetime, timezone, timedelta
from collections import Counter

PROJECT_DIR = Path(__file__).resolve().parent.parent
RAW_DIR = PROJECT_DIR / "data" / "raw"
OUTPUT_HTML = PROJECT_DIR / "index.html"
OUTPUT_CSV = PROJECT_DIR / "data" / "combined.csv"

TZ_TPE = timezone(timedelta(hours=8))

# ── 交友相關關鍵字 ──
DATING_KEYWORDS = [
    '交友', '軟體', 'dating', 'tinder', '探探', 'bumble', 'CMB', '配對',
    '脫單', '約會', '柴犬', 'pairs', 'eatme', 'match', '暈船', '詐騙',
    '單身', '曖昧', 'hinge', 'omi', '戀愛', '告白', '搭訕', '聯誼',
]


def load_all_posts():
    """讀取 data/raw/ 所有 JSON 並解析成統一格式"""
    posts = []
    seen = set()

    for fpath in sorted(RAW_DIR.glob("*.json")):
        with open(fpath, encoding="utf-8") as f:
            try:
                data = json.load(f)
            except json.JSONDecodeError:
                print(f"  SKIP (invalid JSON): {fpath.name}")
                continue

        if not isinstance(data, list):
            continue

        for item in data:
            # Main thread
            thread = item.get("thread", item)  # support both formats
            _add_post(thread, posts, seen, fpath.name)

            # Replies
            for reply in item.get("replies", []):
                _add_post(reply, posts, seen, fpath.name)

    return posts


def _add_post(raw, posts, seen, source):
    """Parse a single post from Apify JSON"""
    text = raw.get("text") or raw.get("captionText") or raw.get("caption", "")
    if not text:
        return

    code = raw.get("code") or raw.get("postCode", "")
    url = raw.get("url") or raw.get("postUrl", "")

    # Deduplicate by code or URL
    key = code or url
    if not key or key in seen:
        return
    seen.add(key)

    # Parse timestamp
    ts = raw.get("published_on") or raw.get("takenAt", 0)
    if ts:
        dt = datetime.fromtimestamp(ts, tz=TZ_TPE)
    else:
        dt = None

    posts.append({
        "author": raw.get("username", ""),
        "url": url,
        "text": text,
        "likes": int(raw.get("like_count") or raw.get("likeCount") or 0),
        "comments": int(raw.get("reply_count") or raw.get("directReplyCount") or 0),
        "reposts": int(raw.get("repostCount") or 0),
        "shares": int(raw.get("reshareCount") or 0),
        "dt": dt,
        "hour": dt.hour if dt else None,
        "weekday": dt.strftime("%A") if dt else None,
        "source": source,
    })


def filter_dating(posts):
    """只保留交友相關貼文"""
    return [p for p in posts if any(k.lower() in p["text"].lower() for k in DATING_KEYWORDS)]


def percentile(values, p):
    """計算百分位數"""
    if not values:
        return 0
    s = sorted(values)
    k = (len(s) - 1) * p / 100
    f = math.floor(k)
    c = math.ceil(k)
    if f == c:
        return s[int(k)]
    return s[f] * (c - k) + s[c] * (k - f)


def classify_posts(posts):
    """根據百分位門檻將貼文分類為 Type A-E + X"""
    likes = [p["likes"] for p in posts]
    comments = [p["comments"] for p in posts]
    reposts = [p["reposts"] for p in posts]
    shares = [p["shares"] for p in posts]
    total_eng = [p["likes"] + p["comments"] + p["reposts"] + p["shares"] for p in posts]

    thresholds = {
        "likes_p90": percentile(likes, 90),
        "likes_p75": percentile(likes, 75),
        "likes_p25": percentile(likes, 25),
        "comments_p90": percentile(comments, 90),
        "comments_p75": percentile(comments, 75),
        "reposts_p90": percentile(reposts, 90),
        "shares_p90": percentile(shares, 90),
        "engagement_p50": percentile(total_eng, 50),
    }

    percentiles = {}
    for metric_name, values in [("likes", likes), ("comments", comments), ("reposts", reposts), ("shares", shares)]:
        percentiles[metric_name] = {
            "p25": percentile(values, 25),
            "p50": percentile(values, 50),
            "p75": percentile(values, 75),
            "p90": percentile(values, 90),
            "p95": percentile(values, 95),
        }

    for p in posts:
        eng = p["likes"] + p["comments"] + p["reposts"] + p["shares"]
        p["total_engagement"] = eng
        comment_rate = p["comments"] / max(p["likes"], 1) * 100

        types = []

        # Type A: 全能爆款 — all metrics above P90
        if (p["likes"] >= thresholds["likes_p90"] and
            p["comments"] >= thresholds["comments_p90"]):
            types.append("A")

        # Type B: 私域擴散型 — high reposts + shares (threshold must be > 0)
        rs = p["reposts"] + p["shares"]
        rs_p75 = percentile([pp["reposts"] + pp["shares"] for pp in posts], 75)
        if rs > 0 and rs >= max(rs_p75, 1) and "A" not in types:
            types.append("B")

        # Type C: 戰場議論型 — high comments, comment rate > 3%
        if p["comments"] >= thresholds["comments_p75"] and comment_rate > 3 and "A" not in types:
            types.append("C")

        # Type D: 靜默共鳴型 — high likes, low comments (likes must be meaningful)
        comments_p25 = percentile(comments, 25)
        if (p["likes"] >= thresholds["likes_p75"] and p["likes"] > 0 and
            p["comments"] <= max(comments_p25, 5) and "A" not in types):
            types.append("D")

        # Type E: 穩定互動型 — above median but not in A-D
        if not types and eng >= thresholds["engagement_p50"] and p["likes"] >= thresholds["likes_p25"]:
            types.append("E")

        # Type X: 長尾內容
        if not types:
            types.append("X")

        p["types"] = types
        p["primary_type"] = types[0]
        p["comment_rate"] = comment_rate
        p["share_rate"] = p["shares"] / max(eng, 1) * 100

    return posts, thresholds, percentiles


def time_analysis(posts):
    """分析發文時段"""
    hourly = {}
    for h in range(24):
        hour_posts = [p for p in posts if p["hour"] == h]
        hourly[h] = {
            "count": len(hour_posts),
            "avg_engagement": statistics.mean([p["total_engagement"] for p in hour_posts]) if hour_posts else 0,
        }

    day_names = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
    day_labels = ["週一", "週二", "週三", "週四", "週五", "週六", "週日"]
    daily = {}
    for i, day in enumerate(day_names):
        day_posts = [p for p in posts if p["weekday"] == day]
        daily[day_labels[i]] = {
            "count": len(day_posts),
            "avg_engagement": statistics.mean([p["total_engagement"] for p in day_posts]) if day_posts else 0,
        }

    return hourly, daily


# ── HTML 報告產生 ──

TYPE_INFO = {
    "A": {"name": "全能爆款", "emoji": "\U0001f525", "color": "#d97757", "desc": "多項指標全面爆發，具備病毒式傳播潛力"},
    "B": {"name": "私域擴散型", "emoji": "\u2708\ufe0f", "color": "#6a9bcc", "desc": "高轉發＋分享，內容被大量私傳或轉貼到社群外"},
    "C": {"name": "戰場議論型", "emoji": "\U0001f4ac", "color": "#788c5d", "desc": "留言區活躍，觸發高度討論或爭議"},
    "D": {"name": "靜默共鳴型", "emoji": "\u2764\ufe0f", "color": "#b0aea5", "desc": "大量按讚但幾乎不留言，引發內心共鳴但不想公開表態"},
    "E": {"name": "穩定互動型", "emoji": "\U0001f4ca", "color": "#e8e6dc", "desc": "中等互動，各指標均衡但無特別突出維度"},
    "X": {"name": "長尾內容", "emoji": "\U0001fae7", "color": "#141413", "desc": "低互動貼文，屬於內容生態的基礎流量"},
}


def generate_html(posts, thresholds, percentiles, hourly, daily):
    """產生完整 HTML 報告"""
    n = len(posts)
    classified = sum(1 for p in posts if p["primary_type"] != "X")
    rate = round(classified / n * 100) if n else 0
    type_counts = Counter(p["primary_type"] for p in posts)
    now = datetime.now(TZ_TPE).strftime("%Y-%m-%d")

    # Date range
    dates = [p["dt"] for p in posts if p["dt"]]
    date_range = ""
    if dates:
        date_range = f"{min(dates).strftime('%Y-%m')} ~ {max(dates).strftime('%Y-%m')}"

    html = f"""<!DOCTYPE html>
<html lang="zh-TW">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Threads 交友軟體貼文分析報告</title>
<link href="https://fonts.googleapis.com/css2?family=Poppins:wght@400;600;700&family=Lora:wght@400;500;600&display=swap" rel="stylesheet">
<style>
*{{margin:0;padding:0;box-sizing:border-box;}}
body{{background:#faf9f5;color:#141413;font-family:Lora,Georgia,serif;}}
::selection{{background:#d97757;color:#faf9f5;}}
@media(max-width:768px){{
  .hero-stats{{flex-direction:column;gap:16px!important;}}
  .insight-grid{{grid-template-columns:1fr!important;}}
  .post-table{{font-size:12px;}}
}}
</style>
</head>
<body>

<div style="background:#141413;padding:60px 40px 50px;text-align:center;">
<div style="max-width:800px;margin:0 auto;">
<div style="font-family:Poppins,Arial,sans-serif;font-size:11px;text-transform:uppercase;letter-spacing:3px;color:#d97757;margin-bottom:16px;">Threads Analytics Report</div>
<h1 style="font-family:Poppins,Arial,sans-serif;font-size:36px;font-weight:700;color:#faf9f5;line-height:1.3;">交友軟體貼文<br>互動分類分析</h1>
<p style="font-family:Lora,Georgia,serif;font-size:16px;color:#b0aea5;margin-top:16px;">百分位自動校正門檻 &middot; 五大互動模式 &middot; 時段洞察</p>
<div class="hero-stats" style="display:flex;justify-content:center;gap:32px;margin-top:28px;">
<div><span style="font-family:Poppins,Arial,sans-serif;font-size:28px;font-weight:700;color:#d97757;">{n}</span><br><span style="font-size:12px;color:#b0aea5;">篇貼文</span></div>
<div><span style="font-family:Poppins,Arial,sans-serif;font-size:28px;font-weight:700;color:#6a9bcc;">{rate}%</span><br><span style="font-size:12px;color:#b0aea5;">有效分類率</span></div>
<div><span style="font-family:Poppins,Arial,sans-serif;font-size:28px;font-weight:700;color:#788c5d;">5</span><br><span style="font-size:12px;color:#b0aea5;">互動類型</span></div>
</div>
</div>
</div>

<div style="max-width:900px;margin:0 auto;padding:40px 24px;">

<h2 style="font-family:Poppins,Arial,sans-serif;font-size:24px;color:#141413;margin-bottom:24px;">分類分佈總覽</h2>
<p style="font-family:Lora,Georgia,serif;font-size:14px;color:#b0aea5;margin-bottom:20px;">部分貼文可能同時符合多個類型條件，因此各類型加總會超過 100%</p>
"""

    # Type distribution bars
    max_count = max(type_counts.values()) if type_counts else 1
    for t in ["A", "B", "C", "D", "E", "X"]:
        info = TYPE_INFO[t]
        count = sum(1 for p in posts if t in p["types"])
        pct = round(count / n * 100) if n else 0
        bar_w = round(count / max_count * 100) if max_count else 0
        text_color = "#faf9f5" if t in ["A", "X"] else "#141413"
        html += f"""<div style="display:flex;align-items:center;margin-bottom:10px;">
<div style="width:40px;height:40px;border-radius:8px;background:{info['color']};display:flex;align-items:center;justify-content:center;font-size:18px;color:{text_color};">{info['emoji']}</div>
<div style="margin-left:12px;flex:1;">
<div style="font-family:Poppins,Arial,sans-serif;font-size:14px;font-weight:600;color:#141413;">Type {t}：{info['name']} <span style="color:#d97757;">{count}篇 ({pct}%)</span></div>
<div style="font-family:Lora,Georgia,serif;font-size:12px;color:#b0aea5;margin-top:2px;">{info['desc']}</div>
</div>
<div style="width:140px;height:8px;background:#e8e6dc;border-radius:4px;overflow:hidden;">
<div style="height:100%;background:{info['color']};width:{bar_w}%;border-radius:4px;"></div>
</div>
</div>"""

    # Thresholds
    html += """
<h2 style="font-family:Poppins,Arial,sans-serif;font-size:24px;color:#141413;margin:48px 0 20px;">自動校正門檻</h2>
<p style="font-family:Lora,Georgia,serif;font-size:14px;color:#b0aea5;margin-bottom:20px;">基於貼文的百分位數動態計算，隨樣本增加自動調整</p>
"""

    for t, rule in [("A", f"❤️≥{thresholds['likes_p90']:.0f} 💬≥{thresholds['comments_p90']:.0f}"),
                     ("B", f"(🔁+✈️)≥P75，排除A"),
                     ("C", f"💬≥{thresholds['comments_p75']:.0f}，留言率>3%，排除A"),
                     ("D", f"❤️≥{thresholds['likes_p75']:.0f} 💬<P25，排除A"),
                     ("E", f"❤️≥P25，總互動≥P50，未歸入A-D")]:
        info = TYPE_INFO[t]
        html += f"""<div style="background:#faf9f5;border:1px solid #e8e6dc;border-radius:12px;padding:16px;margin-bottom:12px;border-left:4px solid {info['color']};">
<div style="font-family:Poppins,Arial,sans-serif;font-size:14px;font-weight:600;color:#141413;">{info['emoji']} Type {t}：{info['name']}</div>
<div style="font-family:Lora,Georgia,serif;font-size:13px;color:#b0aea5;margin-top:6px;">{rule}</div>
</div>"""

    # Percentile table
    html += """
<h2 style="font-family:Poppins,Arial,sans-serif;font-size:24px;color:#141413;margin:48px 0 20px;">指標百分位參考表</h2>
<div style="overflow-x:auto;">
<table style="width:100%;border-collapse:collapse;background:#faf9f5;border-radius:12px;overflow:hidden;">
<thead><tr style="background:#141413;">
<th style="padding:10px 12px;font-family:Poppins,Arial,sans-serif;font-size:12px;color:#faf9f5;text-align:left;">指標</th>
<th style="padding:10px 12px;font-family:Poppins,Arial,sans-serif;font-size:12px;color:#b0aea5;text-align:right;">P25</th>
<th style="padding:10px 12px;font-family:Poppins,Arial,sans-serif;font-size:12px;color:#faf9f5;text-align:right;">P50</th>
<th style="padding:10px 12px;font-family:Poppins,Arial,sans-serif;font-size:12px;color:#faf9f5;text-align:right;">P75</th>
<th style="padding:10px 12px;font-family:Poppins,Arial,sans-serif;font-size:12px;color:#d97757;text-align:right;">P90</th>
<th style="padding:10px 12px;font-family:Poppins,Arial,sans-serif;font-size:12px;color:#d97757;text-align:right;">P95</th>
</tr></thead><tbody>"""

    metric_labels = {"likes": "❤️ Likes", "comments": "💬 Comments", "reposts": "🔁 Reposts", "shares": "✈️ Shares"}
    for metric, label in metric_labels.items():
        vals = percentiles[metric]
        html += f"""<tr>
<td style="padding:8px 12px;border-bottom:1px solid #e8e6dc;font-family:Poppins,Arial,sans-serif;font-size:13px;font-weight:600;color:#141413;">{label}</td>"""
        for pname, style in [("p25","color:#b0aea5"), ("p50","color:#141413"), ("p75","color:#141413;font-weight:600"), ("p90","color:#d97757;font-weight:600"), ("p95","color:#d97757;font-weight:600")]:
            html += f'<td style="padding:8px 12px;border-bottom:1px solid #e8e6dc;font-family:Lora,Georgia,serif;font-size:13px;{style};text-align:right;">{vals[pname]:,.0f}</td>'
        html += "</tr>"

    html += "</tbody></table></div>"

    # Time analysis
    timed_posts = [p for p in posts if p["hour"] is not None]
    if timed_posts:
        html += """
<h2 style="font-family:Poppins,Arial,sans-serif;font-size:24px;color:#141413;margin:48px 0 8px;">發文時段分析</h2>
<p style="font-family:Lora,Georgia,serif;font-size:14px;color:#b0aea5;margin-bottom:24px;">台北時間 GMT+8 &middot; <span style="color:#d97757;">■</span> 發文數量 &middot; <span style="color:#6a9bcc;">■</span> 平均互動數</p>
<div style="background:#faf9f5;border:1px solid #e8e6dc;border-radius:12px;padding:20px 16px;">
<h3 style="font-family:Poppins,Arial,sans-serif;font-size:16px;color:#141413;margin-bottom:16px;">24 小時分佈</h3>"""

        max_count_h = max(hourly[h]["count"] for h in range(24)) or 1
        max_eng_h = max(hourly[h]["avg_engagement"] for h in range(24)) or 1

        for h in range(24):
            hd = hourly[h]
            bar_count = round(hd["count"] / max_count_h * 200)
            bar_eng = round(hd["avg_engagement"] / max_eng_h * 200)
            html += f"""<div style="display:flex;align-items:center;margin-bottom:3px;">
<span style="width:45px;font-family:Lora,Georgia,serif;font-size:12px;color:#b0aea5;text-align:right;padding-right:8px;">{h:02d}:00</span>
<div style="width:210px;display:flex;align-items:center;">
<div style="height:16px;background:#d97757;border-radius:3px;width:{bar_count}px;opacity:0.8;"></div>
<span style="font-size:11px;color:#b0aea5;margin-left:4px;">{hd['count']}</span>
</div>
<div style="width:210px;display:flex;align-items:center;">
<div style="height:16px;background:#6a9bcc;border-radius:3px;width:{bar_eng}px;opacity:0.7;"></div>
<span style="font-size:11px;color:#b0aea5;margin-left:4px;">{hd['avg_engagement']:,.0f}</span>
</div>
</div>"""

        html += "</div>"

        # Key insights
        peak_count_h = max(range(24), key=lambda h: hourly[h]["count"])
        peak_eng_h = max(range(24), key=lambda h: hourly[h]["avg_engagement"])
        peak_day_count = max(daily.items(), key=lambda x: x[1]["count"])
        peak_day_eng = max(daily.items(), key=lambda x: x[1]["avg_engagement"])

        html += f"""
<div class="insight-grid" style="background:#141413;border-radius:16px;padding:32px;margin-top:40px;">
<h2 style="font-family:Poppins,Arial,sans-serif;font-size:20px;color:#faf9f5;margin-bottom:20px;">關鍵發現</h2>
<div class="insight-grid" style="display:grid;grid-template-columns:1fr 1fr;gap:16px;">
<div style="background:rgba(217,119,87,0.15);border-radius:10px;padding:16px;">
<div style="font-family:Poppins,Arial,sans-serif;font-size:13px;color:#d97757;font-weight:600;">發文最高峰</div>
<div style="font-family:Poppins,Arial,sans-serif;font-size:24px;color:#faf9f5;font-weight:700;">{peak_count_h:02d}:00</div>
<div style="font-family:Lora,Georgia,serif;font-size:12px;color:#b0aea5;">{hourly[peak_count_h]['count']}篇</div>
</div>
<div style="background:rgba(106,155,204,0.15);border-radius:10px;padding:16px;">
<div style="font-family:Poppins,Arial,sans-serif;font-size:13px;color:#6a9bcc;font-weight:600;">最高互動時段</div>
<div style="font-family:Poppins,Arial,sans-serif;font-size:24px;color:#faf9f5;font-weight:700;">{peak_eng_h:02d}:00</div>
<div style="font-family:Lora,Georgia,serif;font-size:12px;color:#b0aea5;">平均 {hourly[peak_eng_h]['avg_engagement']:,.0f} 互動</div>
</div>
<div style="background:rgba(120,140,93,0.15);border-radius:10px;padding:16px;">
<div style="font-family:Poppins,Arial,sans-serif;font-size:13px;color:#788c5d;font-weight:600;">最多發文日</div>
<div style="font-family:Poppins,Arial,sans-serif;font-size:24px;color:#faf9f5;font-weight:700;">{peak_day_count[0]}</div>
<div style="font-family:Lora,Georgia,serif;font-size:12px;color:#b0aea5;">{peak_day_count[1]['count']}篇</div>
</div>
<div style="background:rgba(176,174,165,0.15);border-radius:10px;padding:16px;">
<div style="font-family:Poppins,Arial,sans-serif;font-size:13px;color:#b0aea5;font-weight:600;">最高互動日</div>
<div style="font-family:Poppins,Arial,sans-serif;font-size:24px;color:#faf9f5;font-weight:700;">{peak_day_eng[0]}</div>
<div style="font-family:Lora,Georgia,serif;font-size:12px;color:#b0aea5;">平均 {peak_day_eng[1]['avg_engagement']:,.0f} 互動</div>
</div>
</div>
</div>"""

    # Post details per type
    html += """
<h2 style="font-family:Poppins,Arial,sans-serif;font-size:24px;color:#141413;margin:48px 0 8px;">各類型貼文明細</h2>
<p style="font-family:Lora,Georgia,serif;font-size:14px;color:#b0aea5;margin-bottom:8px;">依總互動數排序，每類最多顯示 15 篇</p>
"""

    for t in ["A", "B", "C", "D", "E", "X"]:
        info = TYPE_INFO[t]
        type_posts = sorted([p for p in posts if t in p["types"]], key=lambda x: x["total_engagement"], reverse=True)[:15]
        if not type_posts:
            continue
        count = sum(1 for p in posts if t in p["types"])
        text_color = "#faf9f5" if t in ["A", "X"] else "#141413"

        html += f"""
<div style="margin-top:40px;">
<h3 style="font-family:Poppins,Arial,sans-serif;font-size:20px;color:#141413;margin-bottom:6px;">{info['emoji']} Type {t}：{info['name']} <span style="font-size:14px;color:#d97757;">({count}篇)</span></h3>
<p style="font-family:Lora,Georgia,serif;font-size:14px;color:#b0aea5;margin-bottom:16px;">{info['desc']}</p>
<div style="overflow-x:auto;">
<table class="post-table" style="width:100%;border-collapse:collapse;background:#faf9f5;border-radius:12px;overflow:hidden;">
<thead><tr style="background:#141413;">
<th style="padding:10px 12px;font-family:Poppins,Arial,sans-serif;font-size:12px;color:#faf9f5;text-align:left;">帳號</th>
<th style="padding:10px 12px;font-family:Poppins,Arial,sans-serif;font-size:12px;color:#faf9f5;text-align:left;">內容摘要</th>
<th style="padding:10px 12px;font-family:Poppins,Arial,sans-serif;font-size:12px;color:#faf9f5;text-align:right;">❤️</th>
<th style="padding:10px 12px;font-family:Poppins,Arial,sans-serif;font-size:12px;color:#faf9f5;text-align:right;">💬</th>
<th style="padding:10px 12px;font-family:Poppins,Arial,sans-serif;font-size:12px;color:#faf9f5;text-align:right;">🔁</th>
<th style="padding:10px 12px;font-family:Poppins,Arial,sans-serif;font-size:12px;color:#faf9f5;text-align:right;">✈️</th>
<th style="padding:10px 12px;font-family:Poppins,Arial,sans-serif;font-size:12px;color:#d97757;text-align:right;">總互動</th>
</tr></thead><tbody>"""

        for p in type_posts:
            excerpt = p["text"].replace("\n", " ")[:60]
            html += f"""<tr>
<td style="padding:10px 12px;border-bottom:1px solid #e8e6dc;font-family:Lora,Georgia,serif;font-size:13px;color:#141413;">@{p['author']}</td>
<td style="padding:10px 12px;border-bottom:1px solid #e8e6dc;font-family:Lora,Georgia,serif;font-size:13px;color:#141413;max-width:280px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;">{excerpt}</td>
<td style="padding:10px 12px;border-bottom:1px solid #e8e6dc;font-family:Lora,Georgia,serif;font-size:13px;color:#141413;text-align:right;">{p['likes']:,}</td>
<td style="padding:10px 12px;border-bottom:1px solid #e8e6dc;font-family:Lora,Georgia,serif;font-size:13px;color:#141413;text-align:right;">{p['comments']:,}</td>
<td style="padding:10px 12px;border-bottom:1px solid #e8e6dc;font-family:Lora,Georgia,serif;font-size:13px;color:#141413;text-align:right;">{p['reposts']:,}</td>
<td style="padding:10px 12px;border-bottom:1px solid #e8e6dc;font-family:Lora,Georgia,serif;font-size:13px;color:#141413;text-align:right;">{p['shares']:,}</td>
<td style="padding:10px 12px;border-bottom:1px solid #e8e6dc;font-family:Lora,Georgia,serif;font-size:13px;color:#d97757;text-align:right;font-weight:600;">{p['total_engagement']:,}</td>
</tr>"""

        html += "</tbody></table></div></div>"

    # Footer
    html += f"""
<div style="margin-top:60px;padding-top:24px;border-top:1px solid #e8e6dc;text-align:center;">
<p style="font-family:Lora,Georgia,serif;font-size:12px;color:#b0aea5;">Threads 交友軟體互動分析 &middot; 資料日期 {date_range} &middot; 樣本 {n} 篇 &middot; 百分位自動校正</p>
<p style="font-family:Lora,Georgia,serif;font-size:11px;color:#b0aea5;margin-top:4px;">Generated {now} &middot; Powered by Claude</p>
</div>
</div>
</body>
</html>"""

    return html


def save_csv(posts):
    """存成 CSV"""
    OUTPUT_CSV.parent.mkdir(parents=True, exist_ok=True)
    with open(OUTPUT_CSV, "w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=[
            "author", "url", "text", "likes", "comments", "reposts", "shares",
            "total_engagement", "primary_type", "types", "comment_rate", "share_rate", "source"
        ])
        writer.writeheader()
        for p in posts:
            writer.writerow({
                "author": p["author"],
                "url": p["url"],
                "text": p["text"],
                "likes": p["likes"],
                "comments": p["comments"],
                "reposts": p["reposts"],
                "shares": p["shares"],
                "total_engagement": p["total_engagement"],
                "primary_type": p["primary_type"],
                "types": "+".join(p["types"]),
                "comment_rate": round(p["comment_rate"], 1),
                "share_rate": round(p["share_rate"], 1),
                "source": p["source"],
            })


def main():
    print("=== Threads 交友軟體分析器 ===")
    print(f"讀取 {RAW_DIR} ...")

    posts = load_all_posts()
    print(f"  載入貼文: {len(posts)} 篇")

    dating = filter_dating(posts)
    print(f"  交友相關: {len(dating)} 篇")

    if not dating:
        print("ERROR: 沒有找到交友相關貼文")
        return

    dating, thresholds, percentiles = classify_posts(dating)
    hourly, daily = time_analysis(dating)

    print(f"\n分類結果:")
    for t in ["A", "B", "C", "D", "E", "X"]:
        count = sum(1 for p in dating if t in p["types"])
        print(f"  Type {t} ({TYPE_INFO[t]['name']}): {count} 篇")

    html = generate_html(dating, thresholds, percentiles, hourly, daily)
    with open(OUTPUT_HTML, "w", encoding="utf-8") as f:
        f.write(html)
    print(f"\n報告已產生: {OUTPUT_HTML}")

    save_csv(dating)
    print(f"CSV 已存檔: {OUTPUT_CSV}")

    print(f"\nNext: run 'scripts/deploy.sh' to deploy to Cloudflare Pages")


if __name__ == "__main__":
    main()
