"""studio_server.mjs가 남긴 2배 해상도 프레임으로 줌·패닝 연출 영상을 만든다(1920×1080, 30fps, H.264).

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

OUT_W, OUT_H, FPS = 1920, 1080, 30
CSS_W, CSS_H, SCALE = 1440, 810, 2      # 녹화 화면(CSS px)과 프레임 배율
PAD = 1.30                               # 담을 영역 둘레 여백
NAV_H = 78                               # 상단 메뉴 바 높이(CSS px)
MIN_VIEW_W = 520                         # 가장 크게 당겼을 때 화면 폭(CSS px) — 약 2.8배
FADE_FRAMES = 8                          # 클립 사이 디졸브
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
    if vw < CSS_W * 0.7 and top < NAV_H:  # 당긴 장면 위쪽에 상단 메뉴 바가 걸쳐 보이면 산만하다 — 메뉴 바 아래로 내린다(그래프 장면)
        top = min(NAV_H, CSS_H - vh)
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
        start = shot["t"] - shot.get("move", 700)
        u = ease((t - start) / max(shot["t"] - start, 1)) if t > start else 0.0
        cx = prev[0] + (nxt[0] - prev[0]) * u
        cy = prev[1] + (nxt[1] - prev[1]) * u
        vw = math.exp(math.log(prev[2]) + (math.log(nxt[2]) - math.log(prev[2])) * u)
        return clamp_view(cx, cy, vw)


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
            make = lambda k, clip=clip: _screen(frames, camera, clip, k)  # noqa: E731
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


def _screen(frames: Frames, camera: Camera, clip: dict, k: int) -> Image.Image:
    t = clip["from"] + k / FPS * 1000 * clip.get("speed", 1.0)
    left, top, vw, vh = camera.at(t)
    src = frames.at(t)
    img = src.resize((OUT_W, OUT_H), Image.LANCZOS, box=(left * SCALE, top * SCALE, (left + vw) * SCALE, (top + vh) * SCALE))
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
