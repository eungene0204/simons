"""studio_server.mjs가 남긴 2배 해상도 프레임으로 줌·패닝 연출 영상을 만든다(1920×1080, 60fps, H.264).

카메라는 "이 시각까지 이 영역을 담는다"는 지점(shot)들을 따라 움직인다. 지점 사이는 ease-in-out으로
옮기고, 줌 배율은 로그 공간에서 보간해 당기고 빠지는 속도가 일정하게 느껴지게 한다.

사용: uv run python render_studio.py plan.json out.mp4

plan.json:
{
  "frames": "frames",                       # studio_server.mjs 출력 폴더(index.tsv 포함)
  "clips": [
    {"card": "title.png", "dur": 2.8},     # 1920×1080 이미지 카드(천천히 4% 줌인)
    {"from": <ms>, "to": <ms>, "speed": 1.0,
     "caption": "① 전략을 한 문장으로 적습니다", "badge": "빨리 감기 ×15"}
  ],
  "shots": [                                 # 시각은 ms(스크린캐스트 시계), 영역은 CSS px(1440×810)
    {"t": <ms>, "box": [x, y, w, h], "move": 700},   # t까지 box를 담는다(move ms 동안 옮겨 감)
    {"t": <ms>, "full": true}
  ]
}
"""

from __future__ import annotations

import bisect
import json
import math
import subprocess
import sys
from functools import lru_cache
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

OUT_W, OUT_H, FPS = 1920, 1080, 60   # 60fps — 원본 화면이 평균 15fps라 출력 프레임을 촘촘히 해야 카메라 이동이 매끄럽다(2026-10-20)
CSS_W, CSS_H, SCALE = 1440, 810, 2      # 녹화 화면(CSS px)과 프레임 배율
PAD = 1.30                               # 담을 영역 둘레 여백
NAV_H = 78                               # 상단 메뉴 바 높이(CSS px)
MIN_VIEW_W = 840                         # 가장 크게 당겼을 때 화면 폭(CSS px) — 약 1.7배(2.8배는 어지러웠다, 2026-10-20 사용자 지시)
MIN_MOVE_MS = 1300                       # 카메라 이동 최소 시간 — 짧은 이동은 휙휙 움직이는 느낌을 만든다
SPRING_W = 4.0                           # 카메라 스프링 고유 진동수(rad/s, 재생 시간 기준) — 클수록 빨리 따라간다. 4.0이면 이동이 약 1.5초에 걸친다
BLEND_MAX_GAP_MS = 200                   # 원본 프레임 사이가 이보다 벌어지면(화면이 멈춘 구간) 섞지 않는다
FADE_FRAMES = 8 * FPS // 30                          # 클립 사이 디졸브
FONT = "/System/Library/Fonts/AppleSDGothicNeo.ttc"
ACCENT = (240, 122, 74)


def ease(u: float) -> float:
    u = min(max(u, 0.0), 1.0)
    return 4 * u ** 3 if u < 0.5 else 1 - (-2 * u + 2) ** 3 / 2


def view_for(shot: dict) -> tuple[float, float, float]:
    """shot → (중심 x, 중심 y, 화면 폭) CSS px. 16:9를 유지하고 화면 밖으로 나가지 않게 민다."""
    if shot.get("full"):
        return CSS_W / 2, CSS_H / 2, CSS_W
    x, y, w, h = shot["box"]
    view_w = max(w * PAD, h * PAD * CSS_W / CSS_H, MIN_VIEW_W)
    view_w = min(view_w * shot.get("zoom_out", 1.0), CSS_W)
    return x + w / 2, y + h / 2, view_w


def clamp_view(cx: float, cy: float, vw: float) -> tuple[float, float, float, float]:
    vw = min(vw, CSS_W)  # 로그 보간의 부동소수 오차로 화면보다 아주 조금 커질 수 있다
    vh = vw * CSS_H / CSS_W
    left = max(min(cx - vw / 2, CSS_W - vw), 0)
    top = max(min(cy - vh / 2, CSS_H - vh), 0)
    # 당긴 장면 위쪽에 상단 메뉴 바가 걸쳐 보이면 산만하다 — 메뉴 바 아래로 내린다(그래프 장면).
    # 배율 0.7 경계에서 한 번에 튀지 않게 0.7→0.5 구간에서 서서히 적용한다
    ramp = min(max((CSS_W * 0.7 - vw) / (CSS_W * 0.2), 0.0), 1.0)
    if ramp > 0 and top < NAV_H:
        top = top + (min(NAV_H, CSS_H - vh) - top) * ramp
    return left, top, vw, vh


class Camera:
    def __init__(self, shots: list[dict]):
        self.shots = sorted(shots, key=lambda s: s["t"])
        self.views = [view_for(s) for s in self.shots]

    def at(self, t: float) -> tuple[float, float, float, float]:
        times = [s["t"] for s in self.shots]
        i = bisect.bisect_right(times, t)
        if i == 0:
            return clamp_view(*self.views[0])
        prev = self.views[i - 1]
        if i == len(self.shots):
            return clamp_view(*prev)
        nxt, shot = self.views[i], self.shots[i]
        start = max(times[i - 1], shot["t"] - max(shot.get("move", 700), MIN_MOVE_MS))
        u = ease((t - start) / max(shot["t"] - start, 1)) if t > start else 0.0
        cx = prev[0] + (nxt[0] - prev[0]) * u
        cy = prev[1] + (nxt[1] - prev[1]) * u
        vw = math.exp(math.log(prev[2]) + (math.log(nxt[2]) - math.log(prev[2])) * u)
        return clamp_view(cx, cy, vw)

    def target(self, t: float) -> tuple[float, float, float]:
        """t에 카메라가 향해야 할 (중심 x, 중심 y, 폭). 지점 사이를 보간하지 않고 계단으로 내놓는다 — 부드럽게 옮기는 건 CameraRig 몫이다."""
        times = [s["t"] for s in self.shots]
        i = bisect.bisect_right(times, t)
        if i == 0:
            return self.views[0]
        if i == len(self.shots):
            return self.views[-1]
        start = max(times[i - 1], times[i] - max(self.shots[i].get("move", 700), MIN_MOVE_MS))
        return self.views[i] if t >= start else self.views[i - 1]


class CameraRig:
    """목표를 2단 임계감쇠 스프링으로 따라가는 카메라. 목표가 갑자기 바뀌어도 속도·가속도가 이어져 출발·도착이 부드럽다
    (지점 보간은 지점 시각이 가까우면 짧고 급한 이동이 생겨 화면이 떨렸다 — 2026-10-20 사용자 지시). 폭은 로그 공간에서 따라간다."""

    def __init__(self, camera: Camera):
        self.camera = camera
        self.state = None

    def _goal(self, t: float) -> list[float]:
        # 가장자리·메뉴 바 보정은 스프링 앞에서 목표에 먼저 적용한다 — 스프링 뒤에서 하면 가장자리로 달려가다 보정에 막혀 갑자기 멈춘다(떨림)
        left, top, vw, _ = clamp_view(*self.camera.target(t))
        return [left, top, math.log(vw)]

    def snap(self, t: float) -> None:
        p = self._goal(t)
        self.state = {"p1": p[:], "v1": [0.0] * 3, "p2": p[:], "v2": [0.0] * 3}

    def step(self, t: float, dt: float) -> tuple[float, float, float, float]:
        goal = self._goal(t)
        st = self.state
        w, n = SPRING_W, 8
        h = dt / n
        for _ in range(n):
            for src, p, v in ((goal, "p1", "v1"), (st["p1"], "p2", "v2")):
                for a in range(3):
                    acc = -2 * w * st[v][a] - w * w * (st[p][a] - src[a])
                    st[v][a] += acc * h
                    st[p][a] += st[v][a] * h
        vw = min(math.exp(st["p2"][2]), CSS_W)
        vh = vw * CSS_H / CSS_W
        return min(max(st["p2"][0], 0), CSS_W - vw), min(max(st["p2"][1], 0), CSS_H - vh), vw, vh


class Frames:
    def __init__(self, folder: Path):
        rows = [line.split("\t") for line in (folder / "index.tsv").read_text().splitlines() if line]
        self.folder = folder
        self.names = [r[0] for r in rows]
        self.times = [int(r[1]) for r in rows]

    @lru_cache(maxsize=4)
    def image(self, name: str) -> Image.Image:
        return Image.open(self.folder / f"{name}.jpg").convert("RGB")

    def at(self, t: float) -> Image.Image:
        i = max(bisect.bisect_right(self.times, t) - 1, 0)  # 화면이 안 바뀌면 프레임이 없다 — 마지막 프레임 유지
        return self.image(self.names[i])

    def pair(self, t: float) -> tuple[Image.Image, Image.Image, float]:
        """t 앞뒤 원본 프레임과 섞는 비율. 원본은 화면이 바뀔 때만 생겨 평균 15fps라, 출력 프레임에서 한 장을 여러 번 쓰면
        카메라는 매 프레임 움직이는데 내용은 격프레임으로 갱신돼 확대 장면이 떨린다(2026-10-20)."""
        i = max(bisect.bisect_right(self.times, t) - 1, 0)
        j = i + 1
        if j >= len(self.times) or self.times[j] - self.times[i] > BLEND_MAX_GAP_MS or t <= self.times[i]:
            img = self.image(self.names[i])
            return img, img, 0.0
        return self.image(self.names[i]), self.image(self.names[j]), (t - self.times[i]) / (self.times[j] - self.times[i])


@lru_cache(maxsize=8)
def font(size: int) -> ImageFont.FreeTypeFont:
    return ImageFont.truetype(FONT, size, index=6)  # AppleSDGothicNeo Bold


def pill(img: Image.Image, text: str, *, anchor: str, alpha: float, size: int = 40, accent: bool = False) -> None:
    """반투명 알약 모양 자막. anchor=bottom(가운데 아래)·top-right."""
    if alpha <= 0:
        return
    f = font(size)
    l, t, r, b = f.getbbox(text)
    while r - l + int(size * 0.8) * 2 > OUT_W - 120 and size > 24:  # 자막이 화면보다 길면(그래프에 노드가 여럿 붙는 장면) 글자를 줄여 한 줄에 담는다
        size -= 2
        f = font(size)
        l, t, r, b = f.getbbox(text)
    pad_x, pad_y = int(size * 0.8), int(size * 0.45)
    w, h = r - l + pad_x * 2, b - t + pad_y * 2
    x, y = ((OUT_W - w) // 2, OUT_H - h - 64) if anchor == "bottom" else (OUT_W - w - 48, 48)
    layer = Image.new("RGBA", img.size, (0, 0, 0, 0))
    d = ImageDraw.Draw(layer)
    bg = (*ACCENT, int(235 * alpha)) if accent else (18, 17, 16, int(215 * alpha))
    d.rounded_rectangle((x, y, x + w, y + h), radius=h // 2, fill=bg)
    d.text((x + pad_x - l, y + pad_y - t), text, font=f, fill=(255, 255, 255, int(255 * alpha)))
    img.paste(Image.alpha_composite(img.convert("RGBA"), layer).convert("RGB"))


def render(plan: dict, out: Path, base: Path) -> None:
    frames = Frames(base / plan.get("frames", "frames"))
    camera = Camera(plan["shots"])
    rig = CameraRig(camera)
    first_screen = True
    enc = subprocess.Popen(
        ["ffmpeg", "-v", "error", "-y", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{OUT_W}x{OUT_H}", "-r", str(FPS),
         "-i", "-", "-c:v", "libx264", "-preset", "slow", "-crf", "18", "-pix_fmt", "yuv420p", "-movflags", "+faststart", str(out)],
        stdin=subprocess.PIPE,
    )
    last: Image.Image | None = None
    total = 0
    for clip in plan["clips"]:
        if "card" in clip:
            card = Image.open(base / clip["card"]).convert("RGB").resize((OUT_W, OUT_H))
            n = round(clip["dur"] * FPS)
            make = lambda k, n=n, card=card: _ken_burns(card, k / max(n - 1, 1))  # noqa: E731
        else:
            n = max(1, round((clip["to"] - clip["from"]) / 1000 / clip.get("speed", 1.0) * FPS))
            if first_screen:
                rig.snap(clip["from"])  # 첫 화면 장면만 목표에 바로 놓는다 — 컷을 지날 때마다 놓으면 프레이밍이 순간이동해 떨려 보인다
                first_screen = False
            make = lambda k, clip=clip: _screen(frames, rig, clip, k)  # noqa: E731
        for k in range(n):
            img = make(k)
            if last is not None and k < FADE_FRAMES:
                img = Image.blend(last, img, (k + 1) / (FADE_FRAMES + 1))
            enc.stdin.write(img.tobytes())
            total += 1
            if k == n - 1:
                last = img
        print(f"clip {plan['clips'].index(clip) + 1}/{len(plan['clips'])} — {n} frames", flush=True)
    enc.stdin.close()
    enc.wait()
    print(f"done {out} {total / FPS:.1f}s")


def _ken_burns(card: Image.Image, u: float) -> Image.Image:
    z = 1 + 0.04 * ease(u)
    w, h = OUT_W / z, OUT_H / z
    return card.resize((OUT_W, OUT_H), Image.LANCZOS, box=((OUT_W - w) / 2, (OUT_H - h) / 2, (OUT_W + w) / 2, (OUT_H + h) / 2))


def _screen(frames: Frames, rig: CameraRig, clip: dict, k: int) -> Image.Image:
    t = clip["from"] + k / FPS * 1000 * clip.get("speed", 1.0)
    left, top, vw, vh = rig.step(t, 1 / FPS)
    a, b, w = frames.pair(t)
    box = (left * SCALE, top * SCALE, (left + vw) * SCALE, (top + vh) * SCALE)
    img = a.resize((OUT_W, OUT_H), Image.LANCZOS, box=box)
    if w > 0:
        img = Image.blend(img, b.resize((OUT_W, OUT_H), Image.LANCZOS, box=box), w)
    elapsed = k / FPS
    remaining = ((clip["to"] - clip["from"]) / 1000 / clip.get("speed", 1.0)) - elapsed
    alpha = min(1.0, elapsed / 0.3, remaining / 0.25)
    if clip.get("caption"):
        pill(img, clip["caption"], anchor="bottom", alpha=alpha)
    if clip.get("badge"):
        pill(img, clip["badge"], anchor="top-right", alpha=alpha, size=30, accent=True)
    return img


if __name__ == "__main__":
    plan_path, out_path = Path(sys.argv[1]), Path(sys.argv[2])
    render(json.loads(plan_path.read_text()), out_path, plan_path.parent)
