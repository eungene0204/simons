"""수정 요청 RAG용 합성 코퍼스 생성기.

카테고리×값을 스크립트가 통제(=출력 JSON은 항상 정확)하고, 로컬 Ollama(Qwen)에는
phrasing 다양화만 맡긴다. LLM이 없거나 실패하면 시드 phrasing만으로 폴백한다.
결과를 engine/data/modify_examples.json으로 저장(커밋 대상).

실행:
    cd backend && python scripts/build_modify_corpus.py
    # 옵션: --per-value N (값당 LLM phrasing 개수), --no-llm (시드만)
"""
import argparse
import json
import os
import sys
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from llm_backend import OLLAMA_MODEL_9B  # noqa: E402

OLLAMA_BASE_URL = os.environ.get("OLLAMA_BASE_URL", "http://localhost:11434")
OLLAMA_MODEL = os.environ.get("NL_OLLAMA_MODEL", OLLAMA_MODEL_9B)

OUT_PATH = Path(__file__).resolve().parents[1] / "engine" / "data" / "modify_examples.json"


def _f(v):
    return float(v)


# 각 카테고리: (이름, [(intent, output, [seeds...]), ...])
def _build_specs():
    specs: list[tuple[str, list[tuple[str, dict, list[str]]]]] = []

    # max_positions
    items = []
    for v in [5, 8, 10, 15, 20, 30, 50]:
        items.append((
            f"포트폴리오 보유 종목 수를 {v}개로 설정/변경",
            {"max_positions": v},
            [f"종목 {v}개로", f"{v}종목으로 설정해줘", f"보유 종목을 {v}개로 바꿔줘", f"최대 {v}종목"],
        ))
    specs.append(("max_positions", items))

    # initial_capital (단위 변환)
    items = []
    for won, kor in [(10000000, "1000만원"), (30000000, "3000만원"), (50000000, "5천만원"),
                     (100000000, "1억"), (200000000, "2억"), (500000000, "5억"), (1000000000, "10억")]:
        items.append((
            f"초기 투자 자금을 {kor}으로 설정",
            {"initial_capital": _f(won)},
            [f"초기자금 {kor}으로", f"자금 {kor}으로 바꿔줘", f"{kor}으로 시작", f"투자금 {kor}"],
        ))
    specs.append(("initial_capital", items))

    # stop_loss_pct
    items = []
    for v in [3, 5, 7, 8, 10, 12, 15, 20]:
        items.append((
            f"손절선을 -{v}%로 설정",
            {"stop_loss_pct": _f(v)},
            [f"손절 {v}%", f"손절을 -{v}%로", f"{v}% 손실나면 청산", f"손절라인 {v}%로 설정"],
        ))
    specs.append(("stop_loss", items))

    # take_profit_pct
    items = []
    for v in [10, 15, 20, 25, 30, 40, 50]:
        items.append((
            f"익절(목표 수익) 기준을 {v}%로 설정",
            {"take_profit_pct": _f(v)},
            [f"익절 {v}%", f"{v}% 익절 설정", f"{v}% 수익나면 청산", f"목표 수익률 {v}%로"],
        ))
    specs.append(("take_profit", items))

    # trailing_stop_pct
    items = []
    for v in [5, 8, 10, 15, 20]:
        items.append((
            f"트레일링 스탑을 {v}%로 설정",
            {"trailing_stop_pct": _f(v)},
            [f"트레일링 스탑 {v}%", f"최고가 대비 {v}% 하락 시 청산", f"트레일링 {v}%로 설정"],
        ))
    specs.append(("trailing_stop", items))

    # max_mdd_limit_pct
    items = []
    for v in [10, 15, 20, 25, 30]:
        items.append((
            f"최대 낙폭(MDD) 한도를 {v}%로 제한",
            {"max_mdd_limit_pct": _f(v)},
            [f"MDD {v}% 제한", f"최대 낙폭 {v}%로 제한", f"낙폭 {v}% 넘으면 중단"],
        ))
    specs.append(("max_mdd", items))

    # hold_period_days
    items = []
    for days, kor in [(5, "1주"), (10, "10일"), (20, "20일"), (21, "1개월"),
                      (63, "3개월"), (126, "6개월"), (252, "1년")]:
        items.append((
            f"보유 기간을 {kor}으로 설정",
            {"hold_period_days": days},
            [f"{kor} 보유", f"{kor}동안 보유", f"보유기간 {kor}으로"],
        ))
    specs.append(("hold_period", items))

    # rebalancing_period
    items = []
    for key, kor in [("daily", "매일"), ("weekly", "매주"), ("monthly", "매월"),
                     ("bimonthly", "2개월마다"), ("quarterly", "분기마다"),
                     ("yearly", "매년"), ("none", "리밸런싱 없음")]:
        items.append((
            f"리밸런싱 주기를 '{kor}'으로 설정",
            {"rebalancing_period": key},
            [f"{kor} 리밸런싱", f"{kor} 재조정", f"리밸런싱 주기를 {kor}으로"],
        ))
    specs.append(("rebalancing", items))

    # universe
    items = []
    for uni, kor in [(["KOSPI200"], "코스피200(대형주)"), (["KOSDAQ"], "코스닥"),
                     (["KOSPI"], "코스피"), (["KOSPI", "KOSDAQ"], "전체 시장")]:
        items.append((
            f"투자 유니버스를 '{kor}'으로 변경",
            {"universe": uni},
            [f"{kor}으로 바꿔줘", f"{kor}으로 진행", f"유니버스 {kor}"],
        ))
    specs.append(("universe", items))

    # backtest_period
    items = []
    for key, kor in [("1y", "최근 1년"), ("3y", "최근 3년"), ("5y", "최근 5년"), ("full", "전체 기간")]:
        items.append((
            f"백테스트 기간을 '{kor}'으로 설정",
            {"backtest_period": key},
            [f"{kor}으로 백테스트", f"기간 {kor}으로", f"{kor} 테스트"],
        ))
    specs.append(("backtest_period", items))

    return specs


def _ollama_phrasings(intent: str, n: int) -> list[str]:
    prompt = (
        f"다음 의도를 한국어로 표현하는 짧고 자연스러운 사용자 채팅 명령 {n}개를 만드세요.\n"
        f"의도: {intent}\n"
        "조건: 실제 사용자가 입력하듯 짧게(존댓말/반말/구어체 섞기), 의도에 명시된 숫자·값은 그대로 유지.\n"
        '출력은 JSON만: {"phrasings": ["...", "..."]}'
    )
    body = json.dumps({
        "model": OLLAMA_MODEL,
        "messages": [{"role": "user", "content": prompt}],
        "stream": False,
        "think": False,
        "format": "json",
        "options": {"temperature": 0.7, "num_ctx": 4096, "num_predict": 512},
    }).encode()
    req = urllib.request.Request(
        f"{OLLAMA_BASE_URL}/api/chat",
        data=body,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=120) as resp:
        data = json.loads(resp.read())
    content = (data.get("message") or {}).get("content", "")
    parsed = json.loads(content)
    phrasings = parsed.get("phrasings", [])
    return [p.strip() for p in phrasings if isinstance(p, str) and p.strip()]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--per-value", type=int, default=5, help="값당 LLM phrasing 개수")
    ap.add_argument("--no-llm", action="store_true", help="시드 phrasing만 사용")
    args = ap.parse_args()

    specs = _build_specs()
    corpus: list[dict] = []
    seen: set[str] = set()

    def add(request: str, category: str, output: dict):
        request = request.strip()
        if not request or request in seen:
            return
        seen.add(request)
        corpus.append({"request": request, "category": category, "output": output})

    total_items = sum(len(items) for _, items in specs)
    done = 0
    for category, items in specs:
        for intent, output, seeds in items:
            for s in seeds:
                add(s, category, output)
            if not args.no_llm:
                try:
                    for p in _ollama_phrasings(intent, args.per_value):
                        add(p, category, output)
                except Exception as e:
                    print(f"  [warn] LLM 실패 ({intent}): {e} — 시드만 사용", file=sys.stderr)
            done += 1
            print(f"  [{done}/{total_items}] {category}: {output} → 누적 {len(corpus)}개")

    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUT_PATH.write_text(json.dumps(corpus, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n✅ {len(corpus)}개 예시 → {OUT_PATH}")
    cats: dict[str, int] = {}
    for ex in corpus:
        cats[ex["category"]] = cats.get(ex["category"], 0) + 1
    for c, n in sorted(cats.items()):
        print(f"   {c}: {n}")


if __name__ == "__main__":
    main()
