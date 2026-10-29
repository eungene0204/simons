"""연합뉴스 RSS에서 최근 기사를 모은다(무료 — X API 크레딧을 쓰지 않는다).

사용: python3 fetch_yonhap.py <출력 폴더> [--hours 24]
출력: <출력 폴더>/news.json, 표준 출력에 `번호 | 시각 | 분야 | 제목` 목록.
어느 기사가 전략 테스트감인지는 이 스크립트가 고르지 않는다 — 에이전트가 제목·요약을 읽고 고른다.
"""
from __future__ import annotations

import json
import sys
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from pathlib import Path

FEEDS = {"경제": "economy", "마켓+": "market", "산업": "industry", "국제": "international"}
KST = timezone(timedelta(hours=9))


def fetch(feed: str) -> list[dict]:
    req = urllib.request.Request(f"https://www.yna.co.kr/rss/{feed}.xml", headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=20) as r:
        root = ET.fromstring(r.read())
    return [
        {
            "title": (it.findtext("title") or "").strip(),
            "link": (it.findtext("link") or "").strip(),
            "published": parsedate_to_datetime(it.findtext("pubDate")).astimezone(KST),
            "summary": (it.findtext("description") or "").strip(),
        }
        for it in root.iter("item")
    ]


def main() -> None:
    out = Path(sys.argv[1])
    hours = int(sys.argv[sys.argv.index("--hours") + 1]) if "--hours" in sys.argv else 24
    since = datetime.now(KST) - timedelta(hours=hours)
    seen: dict[str, dict] = {}
    for label, feed in FEEDS.items():
        for item in fetch(feed):
            if item["published"] >= since and item["link"] not in seen:
                seen[item["link"]] = {**item, "section": label}
    items = sorted(seen.values(), key=lambda x: x["published"], reverse=True)
    out.mkdir(parents=True, exist_ok=True)
    rows = [{**x, "published": x["published"].isoformat()} for x in items]
    (out / "news.json").write_text(json.dumps(rows, ensure_ascii=False, indent=1))
    for i, x in enumerate(items):
        print(f"{i} | {x['published']:%m-%d %H:%M} | {x['section']} | {x['title']}")
    print(f"[{len(items)}건, 최근 {hours}시간] {out / 'news.json'}")


if __name__ == "__main__":
    main()
