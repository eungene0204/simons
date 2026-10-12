"""널스탁 홍보 CF(약 60초, 1920×1080·30fps)를 녹화 기록으로 편집·렌더·믹스한다.

장면: 오프닝 카드 → ① 백테스트(studio_record.mjs 기록) → '검증' 카드 → ② 워크포워드 → ③ 몬테카를로
→ '모의투자' 카드 → ④ 가상계좌(cf_tail.mjs 기록) → 끝 카드. 장면마다 목표 길이에 맞춰 배속을 계산하고,
카메라는 render_studio.py의 Camera(줌·패닝)를 그대로 쓴다. 내레이션 줄은 장면 시작에 맞춰 놓는다.

사용: uv run --with numpy python cf_build.py <head 녹화 폴더> <tail 녹화 폴더> <out.mp4> [--voice ko-KR-InJoonNeural]
  head = studio_record.mjs 폴더(frames·marks.jsonl·result.json), tail = cf_tail.mjs 폴더. 같은 폴더여도 된다.
  가상계좌 장면에는 '시연용 연출 화면' 표기를 넣는다(cf_server.mjs DEMO_LIVE_QUOTES=1로 찍은 시세라서).
  장중에 실제 시세로 찍었으면 --no-demo-note로 뺀다.
"""

from __future__ import annotations

import argparse
import json
import math
import subprocess
import sys
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFilter

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
from render_studio import CSS_H, CSS_W, FPS, OUT_H, OUT_W, Camera, Frames, ease, font, pill  # noqa: E402

ACCENT = (240, 122, 74)
INK = (243, 241, 236)
MUTED = (185, 179, 170)
FADE = 8
LOGO = HERE.parents[4] / "public" / "nullStock.png"

# ── 대본(규제 안전 원칙: 추천·전망·수익 보장 표현 없음, 기능 설명만) ─────────────────
VO = {
    "v1": "투자 아이디어, 말로 적으면 전략이 됩니다.",
    "v2": "널스탁은 문장을 매수와 매도 조건으로 바꾸고,",
    "v3": "과거 데이터로 바로 백테스트합니다.",
    "v4": "결과를 믿기 전에, 검증합니다.",
    "v5": "워크포워드 분석은 처음 보는 구간에서 설정을 다시 시험하고,",
    "v6": "몬테카를로 시뮬레이션은 수익률 흐름을 이천 번 다시 섞어, 낙폭의 범위를 보여 줍니다.",
    "v7": "검증한 전략은 가상계좌에 연결해, 실시간 시세로 모의투자합니다.",
    "v8": "설계부터 검증, 모의투자까지. 투자 연구 플랫폼, 널스탁.",
}
SUB = {  # 화면 자막(내레이션과 같은 뜻, 숫자는 아라비아 숫자)
    "v6": "몬테카를로 시뮬레이션은 수익률 흐름을 2,000번 다시 섞어, 낙폭의 범위를 보여 줍니다.",
}
DEMO_ON = True
DEMO_NOTE = "시연용 연출 화면 · 장중에는 실제 시세가 반영됩니다"
LEGAL = "모든 결과는 과거 데이터 기반 시뮬레이션이며 미래 수익을 보장하지 않습니다."


# ── 녹화 기록 ──────────────────────────────────────────────────────────────
class Rec:
    def __init__(self, folder: Path):
        self.folder = folder
        self.marks = [json.loads(x) for x in (folder / "marks.jsonl").read_text().splitlines() if x]

    def find(self, action=None, phase=None, label=None, after=0, required=True):
        for m in self.marks:
            if m["t"] >= after and (action is None or m["action"] == action) and (phase is None or m.get("phase") == phase) \
                    and (label is None or m.get("label") == label):
                return m
        if required:
            raise SystemExit(f"[중단] 기록에 없음: {action}/{phase}/{label} (after {after}) — {self.folder}")
        return None

    def box(self, label, after=0):
        m = self.find("card", "card", label, after, required=False)
        b = m and m.get("box")
        return [b["x"], b["y"], b["width"], b["height"]] if b else None


class Edit:
    """클립과 카메라 지점을 쌓는다. 클립: {frames, from, to, speed} 또는 {card}."""

    def __init__(self):
        self.clips: list[dict] = []
        self.shots: list[dict] = []
        self.scene_at: dict[str, float] = {}

    @property
    def now(self) -> float:
        return sum(c["dur"] for c in self.clips)

    def scene(self, name: str, label: str | None = None, demo: bool = False):
        self.scene_at[name] = self.now
        self._label, self._demo = label, demo

    def card(self, kind: str, dur: float, **kw):
        self.clips.append({"card": kind, "dur": dur, **kw})

    def seg(self, rec: Rec, t0: float, t1: float, dur: float, badge: str | None = None):
        """녹화 t0~t1(ms)을 dur초로 담는다(배속 = 길이 비율, 최소 0.6배)."""
        speed = max((t1 - t0) / 1000 / dur, 0.6)
        if badge == "auto":
            badge = f"빨리 감기 ×{round(speed)}" if speed >= 3 else None
        self.clips.append({"frames": rec.folder / "frames", "from": t0, "to": t1, "speed": speed,
                           "dur": (t1 - t0) / 1000 / speed, "label": self._label, "demo": self._demo, "badge": badge})

    def shot(self, t: float, box=None, move=700, zoom_out=1.0):
        s = {"t": t, "move": move}
        if box:
            s["box"] = box
            if zoom_out != 1.0:
                s["zoom_out"] = zoom_out
        else:
            s["full"] = True
        self.shots.append(s)


def around(b: dict | list, pad_x=150, pad_y=80, h=180):
    if isinstance(b, dict):
        b = [b["x"], b["y"], b["width"], b["height"]]
    return [b[0] - pad_x, b[1] - pad_y, b[2] + pad_x * 2, max(h, b[3] + pad_y * 2)]


def press_seg(ed: Edit, rec: Rec, label: str, after: float, dur: float, tail_ms=450, action="click"):
    a = rec.find(action, "approach", label, after)
    p = rec.find(action, "press", label, a["t"])
    ed.shot(a["t"] + 350, around(a["box"]), move=550)
    ed.shot(p["t"] + tail_ms, around(a["box"]))
    ed.seg(rec, a["t"] - 150, p["t"] + tail_ms, dur)
    return p


# ── 장면 구성 ───────────────────────────────────────────────────────────────
def build(head: Rec, tail: Rec) -> Edit:
    ed = Edit()
    ed.scene("open")
    ed.card("open", 3.2)

    # ① 백테스트 — 입력 → 해석 대기 → 해석 카드 → 칩 → 확정·시작 → 실행 → 결과
    ed.scene("backtest", "백테스트")
    a0 = head.find("type", "approach")
    t0 = head.find("type", "typing")
    send = head.find("type", "send")
    ib = t0["box"]
    ed.shot(a0["t"] - 200, None, move=10)
    ed.shot(t0["t"] + 300, [ib["x"], ib["y"] + 10, 600, ib["height"]], move=900)
    ed.shot(send["t"] - 300, [ib["x"] + ib["width"] - 600, ib["y"] + 10, 600, ib["height"]], move=max(send["t"] - t0["t"] - 900, 600))
    ed.seg(head, a0["t"] - 200, send["t"] + 200, 2.6)
    card_m = head.find("appear", "appear", "card")
    status = head.find("appear", "appear", "status", required=False)
    ed.shot(send["t"] + 900, None, move=700)
    if status and status.get("box"):
        sb = status["box"]
        ed.shot(card_m["t"] - 600, [sb["x"] - 10, sb["y"] - 10, 420, 45], move=1800)
    ed.seg(head, send["t"] + 200, card_m["t"] - 300, 1.4, badge="auto")
    summ = head.box("summary") or [card_m["box"]["x"], card_m["box"]["y"], 600, 200]
    sbox = [summ[0], summ[1], min(summ[2], 620), min(summ[3], 260)]
    ed.shot(card_m["t"] + 500, sbox, move=800)
    ed.shot(card_m["t"] + 2600, sbox)
    ed.seg(head, card_m["t"] - 300, card_m["t"] + 2600, 2.4)
    conf = head.find("click", "approach", "이 전략으로 확정")
    # 칩 = 해석 카드 뒤 ~ 확정 전의 클릭(같은 폴더에 cf_tail 기록이 이어 쌓여도 섞이지 않게 확정 시각으로 자른다)
    chips = [m for m in head.marks if m["action"] == "click" and m["phase"] == "approach" and card_m["t"] < m["t"] < conf["t"]]
    per = 2.2 / max(len(chips), 1)
    for c in chips:
        press_seg(ed, head, c["label"], c["t"], per, tail_ms=350)
    full = head.box("summary_full")
    if full:
        fb = [full[0], full[1], min(full[2], 560), min(full[3], 320)]
        ed.shot(conf["t"] - 900, fb, move=500)
        ed.shot(conf["t"] - 100, fb)
        ed.seg(head, conf["t"] - 1200, conf["t"] - 100, 0.8)
    press_seg(ed, head, "이 전략으로 확정", conf["t"] - 200, 0.9)
    start_p = press_seg(ed, head, "백테스트 시작하기", conf["t"], 0.9, tail_ms=300)
    res = head.find("appear", "appear", "result")
    ed.shot(start_p["t"] + 1500, None, move=1000)
    ed.seg(head, start_p["t"] + 300, res["t"] - 200, 1.1, badge="auto")
    hold = head.find("hold", "hold")
    mb = head.box("metrics")
    t = hold["t"] + 300
    ed.shot(t + 1100, None)
    ed.seg(head, t, t + 1100, 0.9)
    if mb:
        ed.shot(t + 1100 + 900, mb, move=900)
        ed.shot(t + 1100 + 3300, mb)
        ed.seg(head, t + 1100, t + 1100 + 3300, 2.7)

    # 전환 카드
    ed.scene("verify_card")
    ed.card("verify", 2.4)

    # ② 워크포워드
    ed.scene("wf", "워크포워드 분석")
    sc = tail.find("scene", "scene", "optimize")["t"]
    ed.shot(sc, None, move=10)
    p = press_seg(ed, tail, "전략 최적화", sc, 1.0, tail_ms=350)
    panel = tail.find("appear", "appear", "wf_panel", p["t"])
    settings = tail.box("wf_settings", sc)
    if settings:
        ed.shot(panel["t"] + 700, [settings[0], settings[1], settings[2] * 0.62, 470], move=800)
        ed.shot(panel["t"] + 2600, [settings[0], settings[1], settings[2] * 0.62, 470])
    ed.seg(tail, p["t"] + 350, panel["t"] + 2600, 1.3)
    params = tail.box("wf_params", sc)
    run_sc = tail.find("scene", "scene", "wf_run")["t"]
    if params:
        ed.shot(run_sc - 1200, [params[0], params[1], params[2], min(params[3], 330)], move=1100)
        ed.shot(run_sc, [params[0], params[1], params[2], min(params[3], 330)])
    ed.seg(tail, panel["t"] + 2600, run_sc, 1.2)
    p = press_seg(ed, tail, "워크포워드 분석 시작", run_sc, 0.9, tail_ms=300)
    prog = tail.find("appear", "appear", "wf_progress", p["t"], required=False)
    res = tail.find("appear", "appear", "wf_result", p["t"])
    if prog and prog.get("box"):
        ed.shot(p["t"] + 1500, None, move=900)
    ed.seg(tail, p["t"] + 300, res["t"] + 600, 1.4, badge="auto")
    rs = tail.find("scene", "scene", "wf_result")["t"]
    summ = tail.box("wf_summary", rs)
    met = tail.box("wf_metrics", rs)
    table = tail.box("wf_table", rs)
    whold = tail.find("hold", "wf_hold", after=rs)["t"]
    ed.shot(rs, None, move=500)
    if summ:
        ed.shot(rs + 2500, [summ[0], summ[1], summ[2] * 0.75, summ[3]], move=900)
        ed.shot(whold - 900, [summ[0], summ[1], summ[2] * 0.75, summ[3]])
    ed.seg(tail, res["t"] + 600, whold - 900, 2.0)
    if met and table:
        ed.shot(whold + 300, None, move=700)
        ed.shot(whold + 1600, met, move=900)
        ed.shot(whold + 3600, met)
        ed.shot(whold + 4800, table, move=1000)
        ed.shot(whold + 7000, table)
    ed.seg(tail, whold - 900, whold + 7000, 3.2)

    # ③ 몬테카를로
    ed.scene("mc", "몬테카를로 시뮬레이션")
    msc = tail.find("scene", "scene", "mc")["t"]
    ed.shot(msc, None, move=10)
    p = press_seg(ed, tail, "몬테카를로", msc, 0.9, action="label", tail_ms=350)
    p = press_seg(ed, tail, "2,000", p["t"], 0.9, tail_ms=300)
    p = press_seg(ed, tail, "몬테카를로 실행", p["t"], 0.9, tail_ms=300)
    mres = tail.find("appear", "appear", "mc_result", p["t"])
    mrs = tail.find("scene", "scene", "mc_result")["t"]
    ed.seg(tail, p["t"] + 300, mrs, 0.8, badge="auto")
    stats = tail.box("mc_stats", mrs)
    dist = tail.box("mc_dist", mrs)
    mhold = tail.find("hold", "mc_hold", after=mrs)["t"]
    ed.shot(mrs + 300, None, move=300)
    if stats:
        ed.shot(mrs + 2600, stats, move=900)
        ed.shot(mhold - 1300, stats)
    ed.seg(tail, mrs, mhold - 1300, 2.2)
    if dist:
        ed.shot(mhold + 200, dist, move=1100)
        ed.shot(mhold + 5500, dist)
    ed.seg(tail, mhold - 1300, mhold + 5500, 2.6)

    # 전환 카드
    ed.scene("paper_card")
    ed.card("paper", 2.2)

    # ④ 가상계좌 — 계좌 만들기 → 모의투자 → 상세(시세) → 종목 화면
    ed.scene("account", "가상계좌 모의투자", demo=True)
    asc = tail.find("scene", "scene", "account_create")["t"]
    ed.shot(asc, None, move=10)
    p = press_seg(ed, tail, "계좌 만들기", asc, 0.9, tail_ms=300)
    ty = tail.find("type", "typing", "account_name", p["t"])
    modal = tail.box("account_modal", p["t"])
    nb = ty["box"]
    ed.shot(ty["t"] - 200, [nb["x"] - 20, nb["y"] - 40, nb["width"] + 40, nb["height"] + 80], move=900)
    mk = tail.find("click", "approach", "만들기", ty["t"])
    ed.shot(mk["t"] - 300, [nb["x"] - 20, nb["y"] - 40, nb["width"] + 40, nb["height"] + 80])
    ed.seg(tail, p["t"] + 300, mk["t"] - 300, 1.6)
    del modal
    p = press_seg(ed, tail, "만들기", mk["t"] - 400, 0.9, tail_ms=900)
    ac = tail.find("scene", "scene", "account")["t"]
    p = press_seg(ed, tail, "모의투자", ac, 0.8, tail_ms=300, action="click")
    op = tail.find("click", "approach", "계좌 열기", p["t"])
    ed.shot(p["t"] + 800, None, move=600)
    ed.seg(tail, p["t"] + 300, op["t"] - 100, 0.7)
    p = press_seg(ed, tail, "계좌 열기", op["t"] - 200, 0.8, tail_ms=300)
    live = tail.find("scene", "scene", "account_live")["t"]
    ed.shot(p["t"] + 900, None, move=500)
    ed.seg(tail, p["t"] + 300, live, 0.8, badge=None)
    tracked = tail.box("tracked", live)
    ahold = tail.find("hold", "account_hold", after=live)["t"]
    pr = tail.find("appear", "appear", "tracked_prices", after=live - 30000, required=False)
    pr_t = pr["t"] if pr else ahold + 5500  # 리허설 기록(시세 채움 표시 전)은 hold 뒤 5.5초에 시세가 찼다
    ed.shot(pr_t, None, move=10)
    ed.seg(tail, pr_t - 200, pr_t + 700, 0.9)
    if tracked:
        tb = [tracked[0], tracked[1] - 40, tracked[2] * 0.95, tracked[3] * 0.62]
        ed.shot(pr_t + 1700, tb, move=1000)
        ed.shot(pr_t + 6700, tb)
    ed.seg(tail, pr_t + 700, pr_t + 6700, 3.2)
    ssc = tail.find("scene", "scene", "stock")["t"]
    sp = tail.box("stock_price", ssc)
    shold = tail.find("hold", "stock_hold", after=ssc)["t"]
    ed.shot(shold, None, move=10)
    if sp:
        box = [0, 75, 760, 230]
        ed.shot(shold + 800, box, move=700)
        ed.shot(shold + 7000, box)
    ed.seg(tail, shold, shold + 7000, 2.2)

    ed.scene("end")
    ed.card("end", 7.0)
    return ed


# ── 그리기 ──────────────────────────────────────────────────────────────────
def _bg() -> Image.Image:
    y, x = np.mgrid[0:OUT_H, 0:OUT_W]
    d = np.sqrt(((x - OUT_W * 0.3) / 1200) ** 2 + ((y - OUT_H * 0.2) / 700) ** 2)
    k = np.clip(d / 1.0, 0, 1)[..., None]
    c = (1 - k) * np.array([38, 33, 29]) + k * np.array([20, 19, 18])
    c = c + np.random.default_rng(3).normal(0, 0.9, c.shape)  # 디더 — 8비트 그라데이션의 줄무늬를 지운다
    return Image.fromarray(np.clip(c, 0, 255).astype("uint8"))


BG = None
LOGO_IMG = None


def logo(size: int) -> Image.Image:
    global LOGO_IMG
    if LOGO_IMG is None:
        im = Image.open(LOGO).convert("RGB").crop((510, 215, 910, 545))
        a = np.asarray(im).astype(float)
        lum = (0.2126 * a[..., 0] + 0.7152 * a[..., 1] + 0.0722 * a[..., 2]) / 255
        alpha = np.clip((lum - 0.2) * 2.2 + 0.18, 0, 1) * (lum > 0.12)
        rgba = np.dstack([np.full(lum.shape + (3,), ACCENT), alpha * 255]).astype("uint8")
        LOGO_IMG = Image.fromarray(rgba, "RGBA")
    w = size
    return LOGO_IMG.resize((w, round(w * 330 / 400)), Image.LANCZOS)


def text_at(img: Image.Image, xy, text: str, size: int, color, alpha: float, anchor="la"):
    if alpha <= 0:
        return
    layer = Image.new("RGBA", img.size, (0, 0, 0, 0))
    ImageDraw.Draw(layer).text(xy, text, font=font(size), fill=(*color, int(255 * alpha)), anchor=anchor)
    img.alpha_composite(layer)


def rise(t: float, delay: float, dur=0.55) -> tuple[float, float]:
    u = ease((t - delay) / dur)
    return u, (1 - u) * 46


def card_frame(kind: str, t: float, dur: float) -> Image.Image:
    global BG
    if BG is None:
        BG = _bg()
    z = 1 + 0.035 * (t / dur)
    w, h = OUT_W / z, OUT_H / z
    img = BG.resize((OUT_W, OUT_H), Image.BILINEAR, box=((OUT_W - w) / 2, (OUT_H - h) / 2, (OUT_W + w) / 2, (OUT_H + h) / 2)).convert("RGBA")
    out_a = min(1.0, (dur - t) / 0.35) if kind != "end" else 1.0
    if kind == "open":
        u, dy = rise(t, 0.15)
        text_at(img, (160, 380 + dy), "투자 아이디어를", 104, INK, u * out_a)
        u, dy = rise(t, 0.45)
        text_at(img, (160, 510 + dy), "검증 가능한 전략으로.", 104, ACCENT, u * out_a)
        u, _ = rise(t, 0.9)
        lg = logo(64)
        lay = Image.new("RGBA", img.size, (0, 0, 0, 0))
        lay.paste(lg, (160, 120), lg)
        img.alpha_composite(Image.blend(Image.new("RGBA", img.size, (0, 0, 0, 0)), lay, u * out_a))
        text_at(img, (244, 132), "널스탁", 44, INK, u * out_a)
        bar = ease((t - 0.7) / 0.8)
        ImageDraw.Draw(img).rectangle((160, 680, 160 + int(220 * bar), 686), fill=(*ACCENT, int(255 * out_a)))
    elif kind in ("verify", "paper"):
        eyebrow, title = ("STEP 2", "결과를 믿기 전에, 검증.") if kind == "verify" else ("STEP 3", "그리고, 모의투자.")
        u, dy = rise(t, 0.05, 0.45)
        text_at(img, (OUT_W // 2, 430 + dy), eyebrow, 40, ACCENT, u * out_a, anchor="ma")
        u, dy = rise(t, 0.25, 0.5)
        text_at(img, (OUT_W // 2, 500 + dy), title, 112, INK, u * out_a, anchor="ma")
    elif kind == "end":
        u, dy = rise(t, 0.1, 0.7)
        lg = logo(230)
        lay = Image.new("RGBA", img.size, (0, 0, 0, 0))
        lay.paste(lg, ((OUT_W - lg.width) // 2, int(250 + dy)), lg)
        img.alpha_composite(Image.blend(Image.new("RGBA", img.size, (0, 0, 0, 0)), lay, u))
        u, dy = rise(t, 0.5)
        text_at(img, (OUT_W // 2, 480 + dy), "널스탁", 120, INK, u, anchor="ma")
        u, dy = rise(t, 0.85)
        text_at(img, (OUT_W // 2, 640 + dy), "설계  ·  검증  ·  모의투자", 50, MUTED, u, anchor="ma")
        u, dy = rise(t, 1.2)
        if u > 0:
            f = font(46)
            tw = f.getlength("nullstock.im")
            x0, y0 = (OUT_W - tw) / 2 - 44, 745 + dy
            d = ImageDraw.Draw(img)
            d.rounded_rectangle((x0, y0, x0 + tw + 88, y0 + 84), radius=42, fill=(*ACCENT, int(240 * u)))
            text_at(img, (OUT_W // 2, y0 + 16), "nullstock.im", 46, (255, 255, 255), u, anchor="ma")
        u, _ = rise(t, 1.6)
        text_at(img, (OUT_W // 2, 1000), LEGAL, 24, (143, 137, 127), u, anchor="ma")
        if t > dur - 0.6:  # 끝에서 검게 사라진다
            k = (t - (dur - 0.6)) / 0.6
            img = Image.blend(img, Image.new("RGBA", img.size, (0, 0, 0, 255)), ease(k))
    return img.convert("RGB")


def label_chip(img: Image.Image, text: str, alpha: float):
    """왼쪽 위 장면 라벨(주황 점 + 글자)."""
    if alpha <= 0:
        return
    f = font(34)
    w = f.getlength(text)
    x, y, h = 48, 44, 70
    lay = Image.new("RGBA", img.size, (0, 0, 0, 0))
    d = ImageDraw.Draw(lay)
    d.rounded_rectangle((x, y, x + w + 92, y + h), radius=h // 2, fill=(18, 17, 16, int(225 * alpha)))
    d.ellipse((x + 28, y + 27, x + 44, y + 43), fill=(*ACCENT, int(255 * alpha)))
    d.text((x + 62, y + h / 2), text, font=f, fill=(255, 255, 255, int(255 * alpha)), anchor="lm")
    img.paste(Image.alpha_composite(img.convert("RGBA"), lay).convert("RGB"))


def small_note(img: Image.Image, text: str, alpha: float):
    f = font(24)
    w = f.getlength(text)
    x, y = OUT_W - w - 48 - 36, 52
    lay = Image.new("RGBA", img.size, (0, 0, 0, 0))
    d = ImageDraw.Draw(lay)
    d.rounded_rectangle((x, y, x + w + 36, y + 50), radius=25, fill=(18, 17, 16, int(200 * alpha)))
    d.text((x + 18, y + 25), text, font=f, fill=(220, 214, 205, int(255 * alpha)), anchor="lm")
    img.paste(Image.alpha_composite(img.convert("RGBA"), lay).convert("RGB"))


def subtitle(img: Image.Image, text: str, alpha: float):
    f = font(40)
    w = f.getlength(text)
    pad_x, h = 34, 76
    x, y = (OUT_W - w) / 2 - pad_x, OUT_H - h - 58
    lay = Image.new("RGBA", img.size, (0, 0, 0, 0))
    d = ImageDraw.Draw(lay)
    d.rounded_rectangle((x, y, x + w + pad_x * 2, y + h), radius=18, fill=(12, 11, 10, int(205 * alpha)))
    d.text((OUT_W / 2, y + h / 2), text, font=f, fill=(255, 255, 255, int(255 * alpha)), anchor="mm")
    img.paste(Image.alpha_composite(img.convert("RGBA"), lay).convert("RGB"))


# ── 렌더 ────────────────────────────────────────────────────────────────────
def render(ed: Edit, out: Path, subs: list[tuple[float, float, str]]):
    camera = Camera(ed.shots)
    frames_cache: dict[Path, Frames] = {}
    enc = subprocess.Popen(
        ["ffmpeg", "-v", "error", "-y", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{OUT_W}x{OUT_H}", "-r", str(FPS),
         "-i", "-", "-c:v", "libx264", "-preset", "slow", "-crf", "17", "-pix_fmt", "yuv420p", str(out)],
        stdin=subprocess.PIPE,
    )
    last = None
    T = 0.0
    prev_label = None
    for ci, clip in enumerate(ed.clips):
        n = max(1, round(clip["dur"] * FPS))
        for k in range(n):
            tt = k / FPS
            if "card" in clip:
                img = card_frame(clip["card"], tt, clip["dur"])
            else:
                fr = frames_cache.setdefault(clip["frames"], Frames(clip["frames"]))
                t = clip["from"] + tt * 1000 * clip["speed"]
                left, top, vw, vh = camera.at(t)
                src = fr.at(t)
                img = src.resize((OUT_W, OUT_H), Image.LANCZOS, box=(left * 2, top * 2, (left + vw) * 2, (top + vh) * 2))
                if clip.get("label"):
                    la = 1.0 if prev_label == clip["label"] else min(1.0, tt / 0.3)
                    label_chip(img, clip["label"], la)
                if clip.get("demo") and DEMO_ON:
                    small_note(img, DEMO_NOTE, 1.0)
                if clip.get("badge"):
                    rem = clip["dur"] - tt
                    pill(img, clip["badge"], anchor="top-right", alpha=min(1, tt / 0.2, rem / 0.2), size=28, accent=True)
            now = T + tt
            for s0, s1, text in subs:
                if s0 <= now < s1 and clip.get("card") != "end":  # 끝 카드는 같은 문구가 화면에 있다 — 면책 줄과 겹치지 않게 자막을 뺀다
                    subtitle(img, text, min(1.0, (now - s0) / 0.2, (s1 - now) / 0.2))
            if last is not None and k < FADE:
                img = Image.blend(last, img, (k + 1) / (FADE + 1))
            enc.stdin.write(img.tobytes())
            if k == n - 1:
                last = img
        prev_label = clip.get("label")
        T += n / FPS
        print(f"clip {ci + 1}/{len(ed.clips)} {clip.get('card') or clip.get('label') or ''} {n}f", flush=True)
    enc.stdin.close()
    enc.wait()
    return T


def tts(voice: str, workdir: Path) -> dict[str, tuple[Path, float]]:
    sys.path.insert(0, str(HERE))
    out = {}
    for key, text in VO.items():
        raw = workdir / f"{key}_raw.mp3"
        wav = workdir / f"{key}.wav"
        if not wav.exists():
            r = subprocess.run(["uvx", "edge-tts", "--voice", voice, "--rate=+8%", "--text", text, "--write-media", str(raw)],
                               capture_output=True)
            if r.returncode != 0 or not raw.exists() or raw.stat().st_size == 0:
                # edge-tts는 2026-10-12부터 403 — Gemini TTS(Charon)로 넘어간다. 한 편 안에서 목소리가 섞이지 않게 남은 줄도 Gemini로 간다
                import cf_tts_gemini
                pcm = workdir / f"{key}.pcm"
                pcm.write_bytes(cf_tts_gemini.synth(text, "Charon", cf_tts_gemini.load_key()))
                subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "s16le", "-ar", "24000", "-ac", "1", "-i", str(pcm), str(raw)], check=True)
                pcm.unlink()
                voice = "gemini"
            # 앞뒤 무음을 걷어낸다(줄 길이를 정확히 재야 장면에 맞춰 놓을 수 있다)
            subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", str(raw), "-af",
                            "silenceremove=start_periods=1:start_threshold=-45dB,areverse,silenceremove=start_periods=1:start_threshold=-45dB,areverse",
                            "-ar", "44100", "-ac", "2", str(wav)], check=True)
        dur = float(subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(wav)],
                                   capture_output=True, text=True).stdout)
        out[key] = (wav, dur)
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("head")
    ap.add_argument("tail")
    ap.add_argument("out")
    ap.add_argument("--voice", default="ko-KR-InJoonNeural")
    ap.add_argument("--work", default="cf_work")
    ap.add_argument("--no-demo-note", action="store_true", help="장중 실제 시세로 찍었을 때(DEMO_LIVE_QUOTES 없이) 연출 표기를 뺀다")
    args = ap.parse_args()
    global DEMO_ON
    DEMO_ON = not args.no_demo_note
    work = Path(args.work)
    work.mkdir(exist_ok=True)

    ed = build(Rec(Path(args.head)), Rec(Path(args.tail)))
    sa = ed.scene_at
    total = ed.now
    voice = tts(args.voice, work)
    # 내레이션 배치 — 장면 시작 기준(초)
    place = {
        "v1": sa["open"] + 0.35, "v2": sa["backtest"] + 0.9, "v3": sa["backtest"] + 7.4,
        "v4": sa["verify_card"] + 0.15, "v5": sa["wf"] + 1.2, "v6": sa["mc"] + 0.4,
        "v7": sa["account"] + 0.5, "v8": sa["end"] + 0.4,
    }
    subs = []
    keys = list(place)
    for i, k in enumerate(keys):
        start = place[k]
        end = start + voice[k][1] + 0.25
        if i + 1 < len(keys) and end > place[keys[i + 1]] - 0.1:
            print(f"[경고] {k}가 다음 줄과 {end - place[keys[i + 1]]:.2f}초 겹친다")
        subs.append((start, end, SUB.get(k, VO[k])))
    print(f"편집 길이 {total:.1f}초, 장면 시작 {json.dumps({k: round(v, 1) for k, v in sa.items()}, ensure_ascii=False)}")

    video = work / "video.mp4"
    T = render(ed, video, subs)

    music = work / "music.wav"
    hits = [sa["backtest"], sa["verify_card"], sa["paper_card"], sa["end"]]
    subprocess.run(["uv", "run", "--with", "numpy", "python", str(HERE / "cf_music.py"), str(music), f"{T + 0.5:.2f}",
                    f"{sa['backtest']:.2f}", f"{sa['end']:.2f}", *[f"{h:.2f}" for h in hits]], check=True)

    # 믹스: 내레이션을 제자리에 놓고, 음악은 내레이션이 나올 때 눌러 준다(사이드체인) → -14 LUFS
    inputs = ["-i", str(video), "-i", str(music)]
    chains = []
    for i, k in enumerate(keys):
        inputs += ["-i", str(voice[k][0])]
        ms = int(place[k] * 1000)
        chains.append(f"[{i + 2}:a]adelay={ms}|{ms},volume=1.0[v{i}]")
    vo_mix = "".join(f"[v{i}]" for i in range(len(keys))) + f"amix=inputs={len(keys)}:normalize=0,asplit=2[vo][sc]"
    graph = ";".join(chains + [vo_mix,
                               "[1:a]volume=0.55[m]",
                               "[m][sc]sidechaincompress=threshold=0.03:ratio=6:attack=20:release=350[md]",
                               f"[md][vo]amix=inputs=2:normalize=0,atrim=0:{T:.3f},loudnorm=I=-14:TP=-1.5:LRA=11[a]"])
    subprocess.run(["ffmpeg", "-v", "error", "-y", *inputs, "-filter_complex", graph, "-map", "0:v", "-map", "[a]",
                    "-c:v", "copy", "-c:a", "aac", "-b:a", "192k", "-movflags", "+faststart", args.out], check=True)
    print("done", args.out, f"{T:.1f}s")


if __name__ == "__main__":
    main()
