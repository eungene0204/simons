"""studio_record.mjs의 기록(marks.jsonl·result.json)으로 표준 편집 계획(plan.json)과 카드 명세를 만든다.
그래프 중심 연출(2026-10-19): marks의 `graph` 기록(처음 그래프 / 칩 답변으로 붙은 노드 / 확정 직전 완성 그래프)으로 그래프 장면을 만든다.

2026-10-10 속설 검증 #1 영상에서 손으로 맞춘 연출 규칙을 그대로 코드로 옮겼다 — 같은 규칙이면 같은 수준이 나온다.
사람이 정하는 것은 meta.json(제목 문구·사건 구간 자막)뿐이다.

사용: uv run python make_plan.py <녹화 폴더> meta.json
  meta: { "chip_captions": {"10거래일 안에": "하단 터치 인정 기간 — 10거래일", "익절 안 함": "익절 — 안 함"},   # 선택 사항: 칩 답변 → 자막(항목 — 값). 없으면 "④ <칩 글자>"
          "eyebrow": "속설 검증 #2", "title": "“…”", "subtitle": "…",
          "end_eyebrow": "속설 검증 #2 결과",          # 생략하면 eyebrow + " 결과"
          "events": [ {"caption": "2023년 10월 …", "box": [x, y, w, h]} ] }   # 결과 화면 CSS px, 선택
출력: <폴더>/plan.json, title.json, end.json
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

# ── 연출 규칙(2026-10-10 기준선) ─────────────────────────────────────────────
TITLE_SEC, END_SEC = 2.6, 3.6
TYPING_TARGET_SEC = 4.5          # 입력 장면 길이 목표(배속을 여기에 맞춘다, 최소 1배)
WAIT_TARGET_SEC = 3.5            # 해석 대기 빨리 감기 길이
RUN_TARGET_SEC = 2.3             # 백테스트 실행 빨리 감기 길이
CARD_SEC = 6.0                   # 해석 카드 보여 주기
FULL_CARD_SEC = 3.5              # 다 채워진 조건 카드 보여 주기(확정 버튼으로 다가가기 직전까지)
CHIP_SPEED = 1.3
GRAPH_BUILD_SEC = 8.0            # 처음 그려지는 그래프 — 노드가 하나씩 나타나는 연출(앱 상한 약 7초)을 통째로 보여 준다
GRAPH_BEAT_SEC = 2.8             # 칩 답변 뒤 그래프에 노드가 붙는 순간으로 당겨 보여 주기
GRAPH_PAN_W = 900                # 처음 그래프를 훑을 때 담는 폭(CSS px) — 약 1.6배 — 어지럽지 않은 정도
GRAPH_FIT_W = 760                # 그래프를 당길 때 담는 폭(CSS px) — 화면 맞춤 그래프가 한눈에 읽히는 정도
CHIP_TAIL_MS = 500               # 누른 직후 여기서 끊는다 — 다음 질문이 뜨며 화면이 밀려 물결이 다른 칩 위에 남는다
LINE_CHARS = 62                  # 입력창 한 줄에 들어가는 글자 수(1440 화면, 894px 입력창)
ZOOM_W = 860                     # 입력·카드를 당길 때 담는 폭(CSS px) — 약 1.7배

CAPTIONS = {
    "type": "① 전략을 한 문장으로 적습니다",
    "wait": "② 널스탁이 문장을 읽고 전략 구조로 해석합니다",
    "card": "③ 해석한 전략이 그래프로 그려집니다",  # 2026-10-19: 해석 결과의 정본 화면은 전략 그래프다 — "항목별로 정리해 줍니다"(텍스트 목록) 문구는 쓰지 않는다
    "card_text": "③ 해석한 전략이 정리됩니다",  # 그래프를 못 찾았을 때만(구 녹화·텍스트 보기)
    "graph_add": "그래프에 추가",
    "chip": "④ 문장에 없던 설정은 버튼으로 답합니다",
    "confirm": "⑤ 완성된 전략 그래프를 확인하고 확정합니다",
    "run": "⑥ 과거 데이터로 백테스트를 돌립니다",
    "result": "⑦ 결과",
}


def chip_box(b: dict) -> list[float]:
    return [b["x"] - 150, b["y"] - 80, b["width"] + 300, 180]


def load(folder: Path):
    marks = [json.loads(line) for line in (folder / "marks.jsonl").read_text().splitlines() if line]
    result = json.loads((folder / "result.json").read_text())
    return marks, result


def find(marks, action=None, phase=None, label=None, after=0):
    for m in marks:
        if m["t"] >= after and (action is None or m["action"] == action) and (phase is None or m.get("phase") == phase) \
                and (label is None or m.get("label") == label):
            return m
    return None


def graph_marks(marks, phase):
    return [m for m in marks if m["action"] == "graph" and m.get("phase") == phase]


def graph_box(b: dict, width: float = GRAPH_FIT_W) -> list[float]:
    """그래프(또는 새 노드) 상자 → 카메라 상자. 너무 작으면 노드 둘레를 넉넉히 담는다."""
    w = max(b["width"] + 120, width * 0.55)
    h = max(b["height"] + 90, w * 9 / 16 * 0.6)
    return [b["x"] + b["width"] / 2 - w / 2, b["y"] + b["height"] / 2 - h / 2, w, h]


def graph_caption(texts: list[str]) -> str:
    seen: list[str] = []
    for t in texts:
        if t not in seen:
            seen.append(t)
    return f"{CAPTIONS['graph_add']} — " + " · ".join(seen[:4])


def summary_parts(text: str) -> dict:
    """확정 직전 요약(텍스트로 읽은 그래프 내용) → 칸별 값. 앱 출력의 표기 정규화일 뿐 사용자 원문은 읽지 않는다."""
    lines = [line.strip() for line in text.splitlines() if line.strip()]

    def after(key: str, last: bool = False):
        idx = [i for i, l in enumerate(lines) if l == key]
        return lines[(idx[-1] if last else idx[0]) + 1] if idx and (idx[-1] if last else idx[0]) + 1 < len(lines) else ""

    def rest(prefix: str):
        return next((l[len(prefix):].strip() for l in lines if l.startswith(prefix)), "")

    headers = {"현재까지 이해한 전략", "투자 대상", "매수 규칙", "매도 규칙", "자금 배분", "리밸런싱"}

    def group(key: str) -> list[str]:
        """그래프 칸 제목 아래 항목 전부(다음 칸 제목 전까지). 제목 바로 다음 한 줄만 읽으면 `업종: 조선`·`최대 10종목 보유` 같은 두 번째 이후 항목이 글에서 빠진다(2026-10-20)."""
        idx = [i for i, l in enumerate(lines) if l == key]
        if not idx:
            return []
        out = []
        for l in lines[idx[-1] + 1:]:
            if l in headers or l.startswith("모든 조건을"):
                break
            out.append(l)
        return out

    universe_items = group("투자 대상")
    return {"universe": after("투자 대상"), "universe_items": universe_items, "allocation_items": group("자금 배분"),
            "buy": after("매수 규칙"), "sell": after("매도 규칙"),
            "capital": rest("초기 자본 "), "period": rest("백테스트 기간 "), "rebalance": after("리밸런싱", last=True)}


def with_defaults(meta: dict, result: dict) -> dict:
    """meta.json을 비워 두어도 같은 모양이 나오게 채운다(2026-10-19 — 사람이 정하는 것은 post_name뿐)."""
    p = summary_parts(result["summary"])
    out = dict(meta)
    out.setdefault("eyebrow", "전략 만들기")
    out.setdefault("title", f"“{result['prompt']}”")
    max_hold = next((i for i in p["allocation_items"] if re.fullmatch(r"최대 \d+종목 보유", i)), "")
    steps = [*p["universe_items"], f"{p['buy']} 매수" if p["buy"] else "", f"{p['sell']} 매도" if p["sell"] else "", max_hold, p["period"] and f"최근 {p['period']}"]
    out.setdefault("subtitle", " · ".join(x for x in [*steps, p["capital"]] if x))
    out.setdefault("end_title", " · ".join(x for x in (*p["universe_items"], (f"{p['buy']} 매수, {p['sell']} 매도" if p["buy"] and p["sell"] else "")) if x) or out["title"])
    dates = next((re.sub(r"\s*\(.*", "", l.split("기간:")[1]).strip() for l in result["log"] if l.startswith("기간:")), "")
    m = result["metrics"]
    out.setdefault("end_subtitle", " · ".join(x for x in (dates, f"최근 {p['period']}" if p["period"] else "", f"같은 기간 {m['benchmark_name']} {m['benchmark']}") if x))
    out.setdefault("end_footer", "널스탁 · 과거 데이터 기준 백테스트 결과")
    return out


def summary_fields(text: str) -> dict:
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    keys = ("유니버스", "매수 조건", "매도 조건", "최대 보유", "리밸런싱", "백테스트 기간", "초기 자본", "리스크 관리")
    return {k: lines[lines.index(k) + 1] for k in keys if k in lines and lines.index(k) + 1 < len(lines)}


def build(folder: Path, meta: dict) -> dict:
    marks, result = load(folder)
    clips: list[dict] = [{"card": "title.png", "dur": TITLE_SEC}]
    shots: list[dict] = []

    # ① 입력 — 입력창 왼쪽을 2배로 당기고, 글자가 써지는 줄을 따라 좌우로 패닝, 보낼 때 입력창 전체로 빠진다
    a0 = find(marks, "type", "approach")
    t0 = find(marks, "type", "typing")
    send = find(marks, "type", "send")
    ib = t0["box"]
    typing_ms = send["t"] - t0["t"]
    speed = max(1.0, round((send["t"] - a0["t"] + 450) / 1000 / TYPING_TARGET_SEC, 2))
    clips.append({"from": a0["t"] - 300, "to": send["t"] + 150, "speed": speed, "caption": CAPTIONS["type"]})
    shots.append({"t": a0["t"] - 300, "full": True})
    n = len(result["prompt"])
    right_x = ib["x"] + ib["width"] - ZOOM_W
    for k in range(max(1, -(-n // LINE_CHARS))):
        y = ib["y"] + 18 + 15 * k
        start = t0["t"] + typing_ms * min(k * LINE_CHARS / n, 1)
        end = t0["t"] + typing_ms * min((k + 1) * LINE_CHARS / n, 1)
        shots.append({"t": start if k else t0["t"], "box": [ib["x"], y, ZOOM_W, ib["height"]], "move": 1300 if k == 0 else 700})
        if (k + 1) * LINE_CHARS < n:  # 이 줄이 끝까지 차면 오른쪽 끝까지 따라간다
            shots.append({"t": end, "box": [right_x, y, ZOOM_W, ib["height"]], "move": max(end - start - 300, 600)})
    shots.append({"t": send["t"] - 500, "box": shots[-1]["box"]})
    shots.append({"t": send["t"] + 100, "box": [ib["x"], ib["y"], ib["width"], ib["height"]], "move": 700})

    # ② 해석 대기 — 빨리 감기, 진행 표시로 당긴다
    label = find(marks, "label", "press", "대화 기록 닫기")
    status = find(marks, "appear", "appear", "status")
    card_appear = find(marks, "appear", "appear", "card")
    w_from = max(send["t"] + 1500, (label["t"] + 700) if label else 0)
    w_to = card_appear["t"] - 400
    if w_to - w_from < 2 * WAIT_TARGET_SEC * 1000:  # '대화 기록 닫기' 클릭이 늦으면 창이 0.7초로 줄어 ②가 스쳐 간다(10-13 #8) — 전송 직후부터 쓴다
        w_from = max(send["t"] + 1000, w_to - 2 * WAIT_TARGET_SEC * 1000)
    w_speed = max(2, round((w_to - w_from) / 1000 / WAIT_TARGET_SEC))
    clips.append({"from": w_from, "to": w_to, "speed": w_speed, "caption": CAPTIONS["wait"], "badge": f"빨리 감기 ×{w_speed}"})
    shots.append({"t": send["t"] + 1600, "full": True, "move": 900})
    if status and status.get("box"):
        sb = status["box"]
        shots.append({"t": w_from + 2500, "box": [sb["x"] - 10, sb["y"] - 10, 420, 45], "move": 2500})
        shots.append({"t": w_to, "box": [sb["x"] - 10, sb["y"] - 10, 420, 45]})

    # ③ 해석 카드
    summary = find(marks, "card", "card", "summary")
    c_from = card_appear["t"] - 300
    c_to = c_from + CARD_SEC * 1000
    first_chip = find(marks, "click", "approach", result["answered"][0], after=c_from) if result["answered"] else None
    c_speed = 1
    if first_chip and first_chip["t"] - 200 < c_to:  # 카드와 첫 질문이 거의 동시에 뜨면 6초 창이 첫 칩 클릭을 품어 ④에서 같은 클릭이 반복된다(10-13 #8)
        c_from = card_appear["t"] - 50  # 느리게 늘리는 구간이라 카드가 뜨기 전 빈 화면이 길어지지 않게 시작을 당긴다
        c_to = first_chip["t"] - 200
        c_speed = max(0.1, (c_to - c_from) / 1000 / CARD_SEC)  # 짧은 구간을 CARD_SEC만큼 천천히 보여 준다
    g0 = (graph_marks(marks, "initial") or [None])[0]
    if g0:  # 그래프가 노드 하나씩 그려지는 연출을 통째로 보여 준다(녹화가 연출이 끝날 때까지 칩을 누르지 않고 기다렸다)
        c_from, c_to = g0["t"] + 60, g0["t"] + GRAPH_BUILD_SEC * 1000
        clips.append({"from": c_from, "to": c_to, "speed": 1, "caption": CAPTIONS["card"]})
        cv = g0["canvas"]   # 노드가 왼쪽 → 오른쪽 흐름으로 하나씩 그려지므로 카메라도 그래프를 따라 좌→우로 훑는다
        pw = min(GRAPH_PAN_W, cv["width"])
        spans = [cv["x"], cv["x"] + (cv["width"] - pw) / 2, cv["x"] + cv["width"] - pw]
        for k, x in enumerate(spans):
            shots.append({"t": g0["t"] + 600 + k * (GRAPH_BUILD_SEC * 1000 - 900) / 3, "box": [x, cv["y"] - 20, pw, cv["height"] + 40], "move": 1500 if k else 900})
        shots.append({"t": c_to, "box": [spans[-1], cv["y"] - 20, pw, cv["height"] + 40]})
    else:
        clips.append({"from": c_from, "to": c_to, "speed": c_speed, "caption": CAPTIONS["card_text"]})
        if summary:
            b = summary["box"]
            box = [b["x"], b["y"], min(b["width"], 600), min(b["height"], 280)]
        else:
            b = card_appear["box"]
            box = [b["x"], b["y"], 600, 190]
        shots.append({"t": card_appear["t"] + 700, "box": box, "move": 900})
        shots.append({"t": c_to, "box": box})

    # ④ 칩 답변 — 칩마다 다가가는 순간부터 누른 직후까지
    confirm_a = find(marks, "click", "approach", "이 전략으로 확정")
    last_press = None
    for ans in result["answered"]:
        a = find(marks, "click", "approach", ans, after=c_from)
        p = find(marks, "click", "press", ans, after=a["t"])
        clips.append({"from": a["t"] - 200, "to": p["t"] + CHIP_TAIL_MS, "speed": CHIP_SPEED, "caption": "④ " + meta.get("chip_captions", {}).get(ans, ans)})  # 항목·값만 적는다("문장에 없던 값은 버튼으로 답합니다" 안내 문구는 뺐다 — 10-13 사용자 지시)
        shots.append({"t": a["t"] + 500, "box": chip_box(a["box"]), "move": 500})
        shots.append({"t": p["t"] + CHIP_TAIL_MS, "box": chip_box(a["box"])})
        last_press = p
        # 이 답으로 그래프가 달라졌으면, 노드가 붙는 순간으로 당겨 보여 준다(그래프 중심 연출 — 2026-10-19)
        ga = next((m for m in graph_marks(marks, "add") if m["label"] == ans and m["t"] >= p["t"]), None)
        if ga:
            g_from = max(ga["t"] + 60, p["t"] + CHIP_TAIL_MS)   # 그래프를 패널 위로 스크롤한 직후부터
            clips.append({"from": g_from, "to": ga["t"] + GRAPH_BEAT_SEC * 1000, "speed": 1, "caption": graph_caption(ga["texts"])})
            nb = graph_box(ga["box"])
            shots.append({"t": g_from + 500, "box": graph_box(ga["canvas"], GRAPH_FIT_W * 1.4), "move": 450})   # 먼저 그래프 전체를 담고
            shots.append({"t": ga["t"] + 900, "box": nb, "move": 700})                                          # 새 노드로 당긴다
            shots.append({"t": ga["t"] + GRAPH_BEAT_SEC * 1000, "box": nb})
            last_press = {"t": ga["t"] + (GRAPH_BEAT_SEC * 1000 - CHIP_TAIL_MS)}

    # ⑤ 완성된 조건 카드 → 확정 버튼
    full = find(marks, "card", "card", "summary_full")
    gf = (graph_marks(marks, "final") or [None])[0]
    fb = graph_box(gf["canvas"], GRAPH_FIT_W * 1.2) if gf else None
    fb = {"x": fb[0], "y": fb[1], "width": fb[2], "height": fb[3]} if fb else full["box"]
    f_from = max((last_press["t"] + CHIP_TAIL_MS) if last_press else 0, confirm_a["t"] - 100 - FULL_CARD_SEC * 1000)
    clips.append({"from": f_from, "to": confirm_a["t"] - 100, "speed": 1, "caption": CAPTIONS["confirm"]})
    shots.append({"t": f_from + 600, "box": [fb["x"], fb["y"], fb["width"], fb["height"]] if gf else [fb["x"], fb["y"], min(fb["width"], 500), min(fb["height"], 300)], "move": 500})
    shots.append({"t": confirm_a["t"] - 100, "box": shots[-1]["box"]})
    confirm_p = find(marks, "click", "press", "이 전략으로 확정")
    clips.append({"from": confirm_a["t"] - 100, "to": confirm_p["t"] + CHIP_TAIL_MS, "speed": CHIP_SPEED, "caption": CAPTIONS["confirm"]})
    shots.append({"t": confirm_a["t"] + 500, "box": chip_box(confirm_a["box"]), "move": 500})
    shots.append({"t": confirm_p["t"] + CHIP_TAIL_MS, "box": chip_box(confirm_a["box"])})

    # ⑤-2 지정 종목 노드 펼치기 — 녹화가 확정 그래프의 '지정 종목 N개' 노드를 눌렀을 때만(universe 기록). 노드로 다가가 눌러 펼친 뒤 펼쳐진 그래프로 당겨 읽을 시간을 준다
    uni_p = next((m for m in marks if m["action"] == "universe" and m.get("phase") == "press"), None)
    uni_a = next((m for m in marks if m["action"] == "universe" and m.get("phase") == "approach"), None)
    uni_c = find(marks, "card", "card", "universe")
    if uni_p and uni_a and uni_c:
        import re
        n = uni_c.get("count") or (re.search(r"지정 종목\s*(\d+)개", result.get("summary", "")) or [None, ""])[1]
        cap = f"지정 종목 {n}개 노드를 눌러 펼치면 — 해석된 종목 목록이 나옵니다" if n else "지정 종목 노드를 눌러 펼치면 — 해석된 종목 목록이 나옵니다"
        u_to = uni_c["t"] + 5200
        clips.append({"from": uni_a["t"] - 200, "to": u_to, "speed": 1, "caption": cap})
        shots.append({"t": uni_a["t"] + 300, "box": chip_box(uni_a["box"]), "move": 500})
        shots.append({"t": uni_p["t"] + 400, "box": chip_box(uni_a["box"])})
        nb = uni_p["box"]   # 누른 노드 — 펼친 목록은 이 노드 바로 아래에 붙는다
        zb = [nb["x"] - 110, nb["y"] - 40, nb["width"] + 220, 330]
        shots.append({"t": uni_c["t"] + 200, "box": zb, "move": 800})
        shots.append({"t": u_to, "box": zb})

    # ⑥ 시작 버튼 → 실행(빨리 감기, 전체 화면)
    start_a = find(marks, "click", "approach", "백테스트 시작하기")
    start_p = find(marks, "click", "press", "백테스트 시작하기")
    res = find(marks, "appear", "appear", "result")
    clips.append({"from": start_a["t"] - 200, "to": start_p["t"] + 400, "speed": CHIP_SPEED, "caption": CAPTIONS["run"]})
    shots.append({"t": start_a["t"] + 500, "box": chip_box(start_a["box"]), "move": 500})
    shots.append({"t": start_p["t"] + 400, "box": chip_box(start_a["box"])})
    r_speed = max(2, round((res["t"] - 200 - start_p["t"] - 400) / 1000 / RUN_TARGET_SEC))
    clips.append({"from": start_p["t"] + 400, "to": res["t"] - 200, "speed": r_speed, "caption": CAPTIONS["run"], "badge": f"빨리 감기 ×{r_speed}"})
    shots.append({"t": start_p["t"] + 2400, "full": True, "move": 1800})

    # ⑦ 결과 둘러보기 — 커서를 치운(hold) 뒤의 정지 화면에서: 전체 → 지표 줄 → 벤치마크·승률 칸 → 사건 구간 → 전체
    hold = find(marks, "hold", "hold")
    mb = find(marks, "card", "card", "metrics")["box"]
    m = result["metrics"]
    tour = [
        (1.8, CAPTIONS["result"], None),
        (3.5, f"투자 수익률 {m['roi']} · 최대 낙폭 {m['mdd']} · 승률 {m['win_rate']}", [mb["x"], mb["y"], mb["width"], mb["height"]]),
        (4.0, f"같은 기간 {m['benchmark_name']} {m['benchmark']}",
         [mb["x"] + mb["width"] * 0.33, mb["y"] + mb["height"] * 0.45, mb["width"] * 0.67, mb["height"] * 0.55]),
        *[(4.5, e["caption"], e["box"]) for e in meta.get("events", [])],
        (2.0, None, None),
    ]
    t = hold["t"] + 300
    done = find(marks, "done", "done")
    budget_end = (done or {"t": float("inf")})["t"]
    shots.append({"t": t + 1600, "full": True})
    for dur, caption, box in tour:
        clip = {"from": t, "to": t + dur * 1000, "speed": 1}
        if caption:
            clip["caption"] = caption
        clips.append(clip)
        shots.append({"t": t + 1100, **({"box": box} if box else {"full": True}), "move": 1100 if box else 1400})
        shots.append({"t": t + dur * 1000, **({"box": box} if box else {"full": True})})
        t += dur * 1000
    if t > budget_end:
        raise SystemExit(f"[중단] 결과 정지 화면이 {(t - budget_end) / 1000:.1f}초 모자란다 — studio_record.mjs의 hold를 늘려 다시 녹화")
    clips.append({"card": "end.png", "dur": END_SEC})
    return {"frames": "frames", "clips": clips, "shots": sorted(shots, key=lambda s: s["t"])}


def cards(result: dict, meta: dict) -> tuple[dict, dict]:
    s = summary_fields(result["summary"])
    m = result["metrics"]
    period = next((re.sub(r"\s*\(.*", "", line.split("기간:")[1]).strip() for line in result["log"] if line.startswith("기간:")), "")
    title = {"eyebrow": meta["eyebrow"], "title": meta["title"], "subtitle": meta.get("subtitle", "")}
    sell = s.get("매도 조건", "")
    sell = sell if sell.endswith("매도") else f"{sell} 매도"   # "최대 63일 보유 후 매도"에 '매도'를 또 붙이지 않는다
    end = {
        "eyebrow": meta.get("end_eyebrow", f"{meta['eyebrow']} 결과"),
        "title": meta.get("end_title", f"{s.get('유니버스', '')} · {s.get('매수 조건', '')} 매수, {sell}"),
        "subtitle": meta.get("end_subtitle", " · ".join(x for x in (
            period, f"최대 {s['최대 보유']}" if "최대 보유" in s else "", s.get("리스크 관리", "").split(" · ")[0],
            f"같은 기간 {m['benchmark_name']} {m['benchmark']}") if x)),
        "stats": [["투자 수익률", m["roi"]], ["연평균(CAGR)", m["cagr"]], ["최대 낙폭", m["mdd"]], ["승률", m["win_rate"]]],
        "footer": meta.get("end_footer", "같은 문장으로 직접 돌려 보기 → 본문 링크"),
    }
    return title, end


if __name__ == "__main__":
    folder, meta = Path(sys.argv[1]), json.loads(Path(sys.argv[2]).read_text())
    result = json.loads((folder / "result.json").read_text())
    meta = with_defaults(meta, result)
    plan = build(folder, meta)
    title, end = cards(result, meta)
    (folder / "plan.json").write_text(json.dumps(plan, ensure_ascii=False, indent=1))
    (folder / "title.json").write_text(json.dumps(title, ensure_ascii=False, indent=1))
    (folder / "end.json").write_text(json.dumps(end, ensure_ascii=False, indent=1))
    total = sum(c.get("dur", 0) or (c["to"] - c["from"]) / 1000 / c["speed"] for c in plan["clips"])
    print(f"plan.json — 클립 {len(plan['clips'])}개, 약 {total:.1f}초")
