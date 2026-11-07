#!/usr/bin/env python3
"""뉴스 전략 결과 폴더(~/nullstock-news/<날짜>/<NN-slug>/) → 연구노트 데이터.

    uv run --frozen python .claude/skills/news-strategy-test/scripts/build_news_notes.py            # 전부 다시 만든다
    uv run --frozen python .claude/skills/news-strategy-test/scripts/build_news_notes.py --check    # 쓰지 않고 목록만

- `lib/notes/newsNotes.data.json`(노트 원본 — `lib/notes/newsNotes.ts`가 글로 조립)과
  `public/notes/news/<slug>/{overview,dist}.webp`(결과 화면 사진)를 쓴다.
- 숫자는 다시 계산하지 않는다 — `result.json`의 지표·로그를 `make_note.py`와 같은 함수로 옮긴다.
- 연구노트는 종목명을 싣지 않는다(속설 노트와 같은 원칙): 종목별 손익 줄과 종목이 보이는 사진(기여도·종목·매매 기록)은 뺀다.
  AI 요약 사진도 평가 문구가 있어 뺀다. 입력 문장·기사 제목은 원문 그대로 둔다.
- 결과가 없는 폴더(해석 단계에서 멈춤), EXCLUDED, `exclude.txt`(무인 실행이 보고서에서 뺀 폴더 — 내용=이유)가 있는 폴더는 건너뛴다.
- 엔진 버전은 ENGINE_BY_DATE, 없으면 날짜 폴더의 `engine.txt`(무인 실행 `daily.sh`가 실행 시각에 남긴다). 둘 다 없으면 멈춘다.
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

from PIL import Image

sys.path.insert(0, str(Path(__file__).parent))
from make_note import card_pairs, interpretation, log_find  # noqa: E402

NEWS_ROOT = Path.home() / "nullstock-news"
REPO = Path(__file__).resolve().parents[4]
DATA_OUT = REPO / "lib/notes/newsNotes.data.json"
IMAGE_OUT = REPO / "public/notes/news"
IMAGE_MAX_WIDTH = 1400

# 결과는 있지만 노트로 올리지 않는 폴더와 이유(2026-11-07 이후는 폴더의 exclude.txt로 남긴다).
EXCLUDED = {
    "2026-10-29/90-tourism": "기사 없이 사용자 요청으로 돌린 전략",
    "2026-10-29/02-shipbuilding-earnings": "문장의 '60거래일 보유'가 '최대 63일 보유'로 해석됐다",
    "2026-10-29/03-security-volume": "문장에 없는 '종가 20거래일 연속 상승'이 매수 조건에 끼어 거래 0건",
    "2026-10-30/04-security-rsi": "해석에 문장에 없는 업종 조건이 끼어 그날 보고서에서 결과를 뺐다",
}

# 계산일에 저장소에 올라 있던 backend/engine/version.py의 ENGINE_VERSION(속설 노트와 같은 기준).
# 2026-11-07부터는 날짜 폴더의 engine.txt가 같은 값을 갖는다.
ENGINE_BY_DATE = {
    "2026-10-29": "16.43.0",
    "2026-10-30": "16.45.1", "2026-10-31": "16.45.1", "2026-11-02": "16.45.1",
    "2026-11-03": "16.45.1", "2026-11-04": "16.45.1",
    "2026-11-05": "16.47.0", "2026-11-06": "16.47.0",
}

PHOTOS = [
    ("shot_b_overview.png", "overview", "결과 요약 지표와 수익 곡선(빨강: 전략, 초록: 벤치마크)"),
    ("shot_d_dist.png", "dist", "거래별 수익률 분포와 보유 기간 분포"),
]

MINUS = re.compile(r"(?<![\w.])-(?=\d)")


def minus(text: str) -> str:
    """음수 부호를 다른 노트처럼 U+2212로 — 날짜(2022-01-03)의 하이픈은 앞이 숫자라 건드리지 않는다."""
    return MINUS.sub("−", text)


def photos(folder: Path, slug: str, write: bool) -> list[dict]:
    out = []
    for name, key, caption in PHOTOS:
        src = folder / name
        if not src.exists():
            continue
        with Image.open(src) as im:
            im = im.convert("RGB")
            if im.width > IMAGE_MAX_WIDTH:
                im = im.resize((IMAGE_MAX_WIDTH, round(im.height * IMAGE_MAX_WIDTH / im.width)), Image.LANCZOS)
            if write:
                (IMAGE_OUT / slug).mkdir(parents=True, exist_ok=True)
                im.save(IMAGE_OUT / slug / f"{key}.webp", "WEBP", quality=82, method=6)
            out.append({"key": key, "src": f"/notes/news/{slug}/{key}.webp", "caption": caption,
                        "width": im.width, "height": im.height})
    return out


def engine_of(date: str) -> str:
    if date in ENGINE_BY_DATE:
        return ENGINE_BY_DATE[date]
    recorded = NEWS_ROOT / date / "engine.txt"
    if not recorded.exists():
        sys.exit(f"[중단] {date}의 엔진 버전을 모른다 — ENGINE_BY_DATE에 더하거나 {recorded}를 남긴다")
    return recorded.read_text().strip()


def entry(folder: Path, write: bool) -> dict:
    date = folder.parent.name
    r = json.loads((folder / "result.json").read_text())
    spec = json.loads((folder / "spec.json").read_text())
    m, log = r["metrics"], r["log"]
    slug = f"news-{date.replace('-', '')}-{folder.name[3:]}"
    period = log_find(log, r"기간:\s*(\d{4}-\d{2}-\d{2}) ~ (\d{4}-\d{2}-\d{2})")
    cost = log_find(log, r"수수료\s*([\d.]+%)\s*/\s*슬리피지\s*([\d.]+%)\s*/\s*거래세\s*([\d.]+%)(?:\s*→\s*([\d.]+%))?")
    avg = log_find(log, r"평균수익:\s*([+\-][\d.]+%)\s*/\s*평균손실:\s*([+\-][\d.]+%)")
    hold = log_find(log, r"평균보유일:\s*(\d+)일")
    card = card_pairs(r["summary"])
    # 해석 절: 첫 두 줄(빈 줄·제목), 종목명이 나오는 '종목별' 줄, '미래 수익은 보장되지 않는다'가 든 '한계' 줄을 뺀다
    # (연구노트는 하단 면책이 같은 말을 한다 — 2026-11-05 사용자 지시).
    bullets = [line[2:] for line in interpretation(m, log)[2:] if not line.startswith(("- 종목별", "- 한계"))]
    return {
        "slug": slug,
        "date": date,
        "engine": engine_of(date),
        "news": spec["news"],
        "why": spec.get("why", ""),
        "name": spec.get("post_name") or r["prompt"],
        "prompt": r["prompt"],
        "card": [[k, minus(v)] for k, v in card],
        "answered": r.get("answered", []),
        "period": [period.group(1), period.group(2)] if period else None,
        "cost": (f"수수료 {cost.group(1)}, 슬리피지 {cost.group(2)}, 거래세 {cost.group(3)}"
                 + (f"→{cost.group(4)}(시행일 기준)" if cost.group(4) else "")) if cost else None,
        "metrics": {
            "ret": minus(m["roi"]),
            "profit": minus(m["total_profit"]),
            "cagr": minus(m["cagr"]),
            "mdd": minus(m["mdd"]),
            "sharpe": f"{minus(m['sharpe'])} / {minus(m['sortino'])}",
            "trades": m["trades"],
            "win": m["win_rate"],
            "pf": m["profit_factor"],
            "avgWin": minus(avg.group(1)) if avg else None,
            "avgLoss": minus(avg.group(2)) if avg else None,
            "hold": f"{hold.group(1)}일" if hold else None,
            "benchName": m["benchmark_name"],
            "bench": minus(m["benchmark"]),
        },
        "interpretation": [minus(b) for b in bullets],
        "photos": photos(folder, slug, write),
    }


def main() -> None:
    write = "--check" not in sys.argv
    entries, skipped = [], []
    for folder in sorted(NEWS_ROOT.glob("2026-*/[0-9][0-9]-*")):
        key = f"{folder.parent.name}/{folder.name}"
        if key in EXCLUDED:
            skipped.append(f"{key}: {EXCLUDED[key]}")
        elif (folder / "exclude.txt").exists():
            skipped.append(f"{key}: {(folder / 'exclude.txt').read_text().strip()}")
        elif not (folder / "result.json").exists():
            skipped.append(f"{key}: 결과 없음(해석 단계에서 멈춤)")
        else:
            entries.append(entry(folder, write))
    if write:
        DATA_OUT.write_text(json.dumps(entries, ensure_ascii=False, indent=1) + "\n")
    for e in entries:
        print(f"{e['slug']}: {e['metrics']['ret']} · 사진 {len(e['photos'])}장")
    print(f"노트 {len(entries)}편 · 건너뜀 {len(skipped)}")
    for line in skipped:
        print(f"  - {line}")


if __name__ == "__main__":
    main()
