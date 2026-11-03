#!/usr/bin/env python3
"""X 계정의 새 트윗을 받아 tweets.json으로 저장한다 (X API v2, .env의 X_BEARER_TOKEN).

사용: python3 fetch_tweets.py <계정> <출력 폴더> [--max 20]
- 계정별 마지막으로 본 트윗 id를 ~/nullstock-tweets/<계정>/state.json에 남겨 다음 실행은 그 이후 글만 읽는다
  (읽은 글 수만큼 크레딧이 나가므로 같은 글을 두 번 읽지 않는다).
- 답글·리트윗은 뺀다. 고르는 일은 하지 않는다 — 읽고 고르는 것은 스킬 절차다.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

import requests

API = "https://api.x.com/2"


def bearer() -> str:
    from dotenv import load_dotenv  # 모듈 레벨 금지 — .env 오염 함정 (post_to_x.py와 같다)

    load_dotenv(Path(__file__).resolve().parents[4] / ".env")
    token = os.environ.get("X_BEARER_TOKEN")
    if not token:
        sys.exit("[중단] .env에 X_BEARER_TOKEN이 없다")
    return token


def get(path: str, token: str, **params):
    r = requests.get(f"{API}{path}", headers={"Authorization": f"Bearer {token}"}, params=params, timeout=30)
    if r.status_code != 200:
        sys.exit(f"[중단] X API {r.status_code}: {r.text[:300]}")
    return r.json()


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("account")
    ap.add_argument("outdir")
    ap.add_argument("--max", type=int, default=20)
    args = ap.parse_args()
    account = args.account.lstrip("@")
    token = bearer()

    state_path = Path.home() / "nullstock-tweets" / account / "state.json"
    state = json.loads(state_path.read_text()) if state_path.exists() else {}

    user = get(f"/users/by/username/{account}", token)["data"]
    params = {
        "max_results": max(5, min(args.max, 100)),
        "exclude": "retweets,replies",
        "tweet.fields": "created_at,public_metrics,entities,referenced_tweets",
    }
    if state.get("since_id"):
        params["since_id"] = state["since_id"]
    res = get(f"/users/{user['id']}/tweets", token, **params)
    tweets = res.get("data", [])

    out = Path(args.outdir)
    out.mkdir(parents=True, exist_ok=True)
    rows = [
        {
            "id": t["id"],
            "created_at": t["created_at"],
            "text": t["text"],
            "link": f"https://x.com/{account}/status/{t['id']}",
            "likes": t["public_metrics"]["like_count"],
        }
        for t in tweets
    ]
    (out / "tweets.json").write_text(json.dumps(rows, ensure_ascii=False, indent=1))
    if tweets:
        state["since_id"] = max(tweets, key=lambda t: int(t["id"]))["id"]
        state_path.parent.mkdir(parents=True, exist_ok=True)
        state_path.write_text(json.dumps(state))
    print(f"{account}: 새 트윗 {len(rows)}개 → {out/'tweets.json'}")
    for r in rows:
        print(f"{r['id']} | {r['created_at'][:16]} | {r['text'][:80]!r}")


if __name__ == "__main__":
    main()
