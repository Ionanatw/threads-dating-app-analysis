#!/usr/bin/env python3
"""
Playwright 版多主題爬蟲（取代 Apify 版 scrape_multi_topic.py）
呼叫 cosmate-ai-nexus/skills/threads-analytics/scrape_threads.py 作為底層爬蟲，
將輸出轉成跟 Apify 相容的 raw JSON 格式，讓 analyze_by_topic.py 不用改。

優勢：拿得到 Apify 拿不到的 repost/share。
代價：需要 cookies-file（本機跑請先用 --dump-cookies 一次產生）。

用法：
  python3 scripts/scrape_playwright_topics.py                   # 全部三主題
  python3 scripts/scrape_playwright_topics.py anime cosplay     # 指定主題
"""
import json, sys, os, subprocess, tempfile
from pathlib import Path
from datetime import datetime, timezone, timedelta

PROJECT_DIR = Path(__file__).resolve().parent.parent
RAW_DIR = PROJECT_DIR / "data" / "raw"
SCRAPE_THREADS = Path(
    "/Users/ionachen/Documents/Claude/cosmate-ai-nexus/skills/threads-analytics/scripts/scrape_threads.py"
)
DEFAULT_COOKIES = Path("~/.cosmate/threads_cookies.json").expanduser()
TZ_TPE = timezone(timedelta(hours=8))

# 主題 → 搜尋目標清單（hashtag 優先，補 keyword）
# 來自 scrape_multi_topic.py:TOPICS 的語意，但格式改成 scrape_threads 吃的
TOPIC_TARGETS = {
    "anime": [
        "hashtag:動漫", "keyword:咒術迴戰", "keyword:芙莉蓮", "keyword:我推的孩子",
        "keyword:排球少年", "keyword:鬼滅之刃", "keyword:MAPPA", "keyword:動畫瘋",
    ],
    "love": [
        "hashtag:交友軟體", "keyword:曖昧", "keyword:暈船", "keyword:脫單",
        "keyword:約會", "keyword:告白", "keyword:單身", "keyword:戀愛",
    ],
    "cosplay": [
        "hashtag:cosplay", "hashtag:漫展", "keyword:coser", "keyword:cos服",
        "keyword:CWT", "keyword:FF", "keyword:ACOSTA", "keyword:CCF",
    ],
}


def resolve_cookies_file():
    """優先：env var > default path"""
    env_file = os.environ.get("COSMATE_THREADS_COOKIES_FILE")
    if env_file and Path(env_file).expanduser().exists():
        return Path(env_file).expanduser()
    if DEFAULT_COOKIES.exists():
        return DEFAULT_COOKIES
    return None


def iso_to_unix(iso_str):
    """ISO8601 字串 → Unix timestamp"""
    if not iso_str:
        return 0
    try:
        dt = datetime.fromisoformat(iso_str.replace("Z", "+00:00"))
        return int(dt.timestamp())
    except Exception:
        return 0


def scrape_topic(topic, cookies_file, scroll=8):
    """對單一主題跑 Playwright 爬蟲，輸出到 tempfile，回傳 list of posts"""
    targets = TOPIC_TARGETS[topic]
    targets_arg = ",".join(targets)

    with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as tf:
        tmp_output = tf.name

    cmd = [
        "python3", str(SCRAPE_THREADS),
        "--targets", targets_arg,
        "--output", tmp_output,
        "--scroll", str(scroll),
        "--cookies-file", str(cookies_file),
    ]
    print(f"\n▶ 爬取 {topic}（{len(targets)} 個搜尋目標）")
    result = subprocess.run(cmd, capture_output=False)
    if result.returncode != 0:
        print(f"  ❌ scrape_threads 失敗（exit {result.returncode}）")
        return []

    try:
        data = json.load(open(tmp_output))
    finally:
        os.unlink(tmp_output)

    return data.get("posts", [])


def convert_to_apify_format(posts):
    """把 scrape_threads 格式 → Apify-like raw format（analyze_by_topic 吃的格式）"""
    items = []
    for p in posts:
        username = (p.get("account") or "").lstrip("@")
        if not username or not p.get("content_summary"):
            continue
        items.append({
            "thread": {
                "username": username,
                "url": p.get("url", ""),
                "postUrl": p.get("url", ""),
                "code": p.get("code", ""),
                "postCode": p.get("code", ""),
                "text": p.get("content_summary", ""),
                "captionText": p.get("content_summary", ""),
                "like_count": p.get("likes", 0),
                "likeCount": p.get("likes", 0),
                "reply_count": p.get("comments", 0),
                "directReplyCount": p.get("comments", 0),
                "repostCount": p.get("reposts", 0),
                "reshareCount": p.get("shares", 0),
                "published_on": iso_to_unix(p.get("timestamp", "")),
                "takenAt": iso_to_unix(p.get("timestamp", "")),
            },
            "replies": [],
        })
    return items


def main():
    import argparse as _ap
    parser = _ap.ArgumentParser(description="Playwright 多主題爬蟲")
    parser.add_argument("topics", nargs="*", default=list(TOPIC_TARGETS.keys()),
                        help="指定主題（預設全部）")
    parser.add_argument("--scroll", type=int, default=8,
                        help="每搜尋目標捲動次數（daily 建議 4，weekly 建議 8）")
    args = parser.parse_args()

    topics = args.topics
    scroll = args.scroll
    unknown = [t for t in topics if t not in TOPIC_TARGETS]
    if unknown:
        sys.exit(f"❌ 未知主題: {unknown}。可選: {list(TOPIC_TARGETS.keys())}")

    cookies_file = resolve_cookies_file()
    if not cookies_file:
        sys.exit(
            "❌ 找不到 cookies file。請先跑：\n"
            f"   python3 {SCRAPE_THREADS} --dump-cookies ~/.cosmate/threads_cookies.json"
        )
    print(f"🍪 使用 cookies: {cookies_file}")

    RAW_DIR.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now(TZ_TPE).strftime("%Y-%m-%d_%H%M%S")

    total = 0
    for topic in topics:
        posts = scrape_topic(topic, cookies_file, scroll=scroll)
        if not posts:
            print(f"  ⚠️  {topic}: 0 筆，跳過")
            continue

        items = convert_to_apify_format(posts)
        out_path = RAW_DIR / f"{topic}_{timestamp}.json"
        with open(out_path, "w", encoding="utf-8") as f:
            json.dump(items, f, ensure_ascii=False, indent=2)
        total += len(items)
        repost_cnt = sum(1 for it in items if it["thread"]["repostCount"] > 0)
        share_cnt = sum(1 for it in items if it["thread"]["reshareCount"] > 0)
        print(f"  ✅ {topic}: {len(items)} 筆 → {out_path.name}")
        print(f"     repost>0: {repost_cnt} 筆｜share>0: {share_cnt} 筆")

    print(f"\n═══ 總計 {total} 筆貼文，來源 Playwright ═══")


if __name__ == "__main__":
    main()
