#!/usr/bin/env python3
"""코치 LLM 동시성 부하 테스트 하니스.

N개의 코치 스트리밍 요청을 **동시에** /strategy/coach/stream 에 쏘고, 각 요청의
시작·첫 바이트·완료 시각을 기록해 실제로 병렬 처리됐는지(혹은 직렬로 줄섰는지) 판정한다.

판정 원리:
  overlap = (개별 소요시간 합) / (전체 벽시계 시간)
    - overlap ≈ N  → 완전 병렬 (동시 코칭 OK)
    - overlap ≈ 1  → 완전 직렬 (한 번에 하나씩 — 락/단일슬롯)

주의:
  - 코치는 요청별 스트림 캐시가 있어 동일 요청은 즉답된다. 그래서 user_prompt에
    요청별 nonce를 붙여 캐시를 우회한다(실제 LLM 생성을 강제).
  - 백엔드가 MLX 모드면 전역 락으로 직렬, Ollama 모드(+OLLAMA_NUM_PARALLEL>=2)면 병렬.

사용:
  python scripts/loadtest_coach_concurrency.py --concurrency 2
  python scripts/loadtest_coach_concurrency.py --url http://SERVER:8000 -n 4 --timeout 180
"""
from __future__ import annotations

import argparse
import json
import threading
import time
import urllib.request
import uuid
from statistics import mean


DEFAULT_PAYLOAD = {
    "user_prompt": "RSI 30 이하에서 매수하고 70 이상에서 매도하는 전략 어때?",
    "parsed_strategy": {
        "universe": ["KOSPI200"],
        "entry_signals": [{"indicator": "rsi", "params": {"period": 14, "threshold": 30}}],
        "exit_signals": [{"indicator": "rsi", "params": {"period": 14, "threshold": 70}}],
        "max_positions": 10,
        "stop_loss_pct": 0.05,
        "take_profit_pct": 0.15,
    },
}


def _build_payload(base: dict, idx: int) -> dict:
    """요청별 nonce를 user_prompt에 주입해 스트림 캐시를 우회한다."""
    p = json.loads(json.dumps(base))  # deep copy
    nonce = uuid.uuid4().hex[:8]
    p["user_prompt"] = f"{p['user_prompt']} (req#{idx} {nonce})"
    return p


def _build_ollama_payload(model: str, idx: int) -> dict:
    """Ollama /api/chat 직접 모드용 payload (백엔드/락을 거치지 않고 Ollama 동시성만 측정).

    temp=0 + 고정 num_predict로 요청 간 생성 길이를 균일하게 만들어, overlap 지표가
    응답 길이 편차에 흔들리지 않게 한다(직렬/병렬 판정을 깨끗하게)."""
    return {
        "model": model,
        "messages": [{
            "role": "user",
            "content": (
                "한국 주식 퀀트 투자에 대해 멈추지 말고 길고 자세히 설명해줘. "
                f"(req#{idx} {uuid.uuid4().hex[:8]})"
            ),
        }],
        "stream": True,
        "options": {"num_predict": 256, "temperature": 0.0},
    }


class Result:
    def __init__(self, idx: int):
        self.idx = idx
        self.t_start = 0.0
        self.t_first_byte = 0.0
        self.t_end = 0.0
        self.bytes = 0
        self.error: str | None = None

    @property
    def duration(self) -> float:
        return self.t_end - self.t_start

    @property
    def ttfb(self) -> float:
        return (self.t_first_byte - self.t_start) if self.t_first_byte else 0.0


def _fire(url: str, payload: dict, timeout: float, res: Result) -> None:
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(
        url, data=body, headers={"Content-Type": "application/json"}, method="POST"
    )
    res.t_start = time.perf_counter()
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            for chunk in resp:
                if not res.t_first_byte:
                    res.t_first_byte = time.perf_counter()
                res.bytes += len(chunk)
        res.t_end = time.perf_counter()
    except Exception as exc:  # noqa: BLE001
        res.t_end = time.perf_counter()
        res.error = f"{type(exc).__name__}: {exc}"


def _max_in_flight(results: list[Result]) -> int:
    """시간축에서 동시에 떠 있던 요청의 최대 개수."""
    events = []
    for r in results:
        if r.error and not r.t_first_byte:
            continue
        events.append((r.t_start, 1))
        events.append((r.t_end, -1))
    events.sort()
    cur = peak = 0
    for _, d in events:
        cur += d
        peak = max(peak, cur)
    return peak


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--url", default="http://localhost:8000")
    ap.add_argument("--endpoint", default="/strategy/coach/stream")
    ap.add_argument("-n", "--concurrency", type=int, default=2)
    ap.add_argument("--timeout", type=float, default=180.0)
    ap.add_argument("--payload-file", default=None, help="커스텀 CoachRequest JSON 파일")
    ap.add_argument("--ollama-model", default=None,
                    help="설정 시 코치 대신 Ollama /api/chat에 직접 동시 요청(백엔드/락 우회, Ollama 동시성만 측정)")
    args = ap.parse_args()

    n = args.concurrency
    if args.ollama_model:
        full_url = args.url.rstrip("/") + "/api/chat"
        payloads = [_build_ollama_payload(args.ollama_model, i) for i in range(n)]
        print(f"▶ 대상(Ollama 직접): {full_url}  model={args.ollama_model}")
    else:
        base = DEFAULT_PAYLOAD
        if args.payload_file:
            with open(args.payload_file, encoding="utf-8") as f:
                base = json.load(f)
        full_url = args.url.rstrip("/") + args.endpoint
        payloads = [_build_payload(base, i) for i in range(n)]
        print(f"▶ 대상(코치): {full_url}")
    print(f"▶ 동시 요청: {n}개 (캐시 우회 nonce 적용)\n")

    results = [Result(i) for i in range(n)]
    threads = [
        threading.Thread(target=_fire, args=(full_url, payloads[i], args.timeout, results[i]))
        for i in range(n)
    ]

    wall_start = time.perf_counter()
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    wall = time.perf_counter() - wall_start

    print("요청별 결과:")
    ok = [r for r in results if not r.error]
    for r in results:
        if r.error:
            print(f"  req#{r.idx}: ERROR {r.error}  ({r.duration:.1f}s)")
        else:
            print(f"  req#{r.idx}: 소요 {r.duration:6.1f}s | 첫바이트 {r.ttfb:5.1f}s | {r.bytes}B")

    if not ok:
        print("\n❌ 성공 요청 없음 — 백엔드/Ollama 상태를 확인하세요.")
        return

    durs = [r.duration for r in ok]
    sum_dur = sum(durs)
    overlap = sum_dur / wall if wall > 0 else 0.0
    peak = _max_in_flight(results)

    print("\n── 동시성 판정 ──")
    print(f"  성공 {len(ok)}/{n} | 전체 벽시계 {wall:.1f}s | 개별 평균 {mean(durs):.1f}s")
    print(f"  동시 진입 최대치(peak in-flight): {peak} / {n}")
    print(f"  overlap = Σ개별({sum_dur:.1f}s) / 벽시계({wall:.1f}s) = {overlap:.2f}")
    # 1차 신호: peak in-flight (응답 길이 편차에 강건). 2차: overlap.
    if peak >= n and overlap >= n * 0.6:
        verdict = f"✅ 병렬 처리됨 (peak={peak}/{n}, overlap≈{overlap:.1f}) — 동시 처리 OK"
    elif peak >= n:
        verdict = (f"✅ 동시 진입 확인(peak={peak}/{n}) — 병렬. "
                   f"overlap({overlap:.1f})이 낮으면 응답 길이 편차 때문(벽시계<Σ면 병렬)")
    elif peak <= 1:
        verdict = "⚠️ 직렬 (한 번에 하나씩) — 락 또는 단일 슬롯(MLX 모드 / OLLAMA_NUM_PARALLEL=1?)"
    else:
        verdict = f"부분 병렬 (peak={peak}/{n}) — 슬롯/VRAM 한도 점검"
    print(f"  → {verdict}")


if __name__ == "__main__":
    main()
