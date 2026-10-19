"""널스탁 홍보 CF 2편 — 금융 모션그래픽(motion.html) + 제품 화면(브라우저 창 액자)을 엮는다(약 56초).

흐름: 캔들 벽 오프닝 → KOSPI200 등락 히트맵 → 로고 → 백테스트(제품) → 워크포워드(모션→제품)
→ 몬테카를로(모션→제품) → 시세 전광판 → 가상계좌(제품) → 끝 카드.
제품 화면은 cf_build.build()가 만든 편집(같은 녹화 기록)에서 장면별 클립을 골라 목표 길이에 맞춰 배속한다.

사용: uv run --with numpy python cf2_build.py <녹화 폴더> <motion 폴더> <out.mp4> [--script cf2_script.json]
  녹화 폴더 = cf_run.sh 작업 폴더(frames·marks.jsonl·result.json), motion 폴더 = render_motion.mjs 출력.
  대본·화면 문구·장면 길이는 cf2_script.json(motion 렌더도 같은 파일의 copy·scenes를 쓴다 — cf2_run.sh가 둘을 맞춘다).
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import time
import subprocess
import sys
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFilter

HERE = Path("/Users/eugene/nullalgo/simons/.claude/skills/x-backtest-post/scripts/cf")
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent))
from cf_build import Rec  # noqa: E402
import cf_tts_gemini  # noqa: E402
from render_studio import FPS, OUT_H, OUT_W, Camera, Frames, ease, font  # noqa: E402

ACCENT = (240, 122, 74)
XFADE = 6

NO_SUB_SCENES = {"open", "heat", "title", "end"}  # 같은 문구가 화면 제목으로 이미 나온다

# 창 액자(브라우저 모양): 내용 1560×878 + 위 막대 36
CW, CH, BAR = 1560, 878, 36
WX, WY = (OUT_W - CW) // 2, (OUT_H - CH - BAR) // 2 + 6


def scene_clips(ed):
    """cf_build 편집의 클립을 장면 이름별로 묶는다(장면 시작 시각 기준)."""
    starts = sorted(ed.scene_at.items(), key=lambda kv: kv[1])
    groups: dict[str, list] = {k: [] for k, _ in starts}
    t = 0.0
    for c in ed.clips:
        name = [k for k, v in starts if v <= t + 1e-6][-1]
        groups[name].append(c)
        t += c["dur"]
    return groups


def fit(clips, target):
    k = sum(c["dur"] for c in clips) / target
    return [{**c, "speed": c["speed"] * k, "dur": c["dur"] / k} for c in clips]


class Frame:
    """프레임 한 장을 만드는 재료: motion 장면 프레임 또는 제품 클립."""


def load_motion(folder: Path, scene: str):
    files = sorted((folder / scene).glob("*.jpg"))
    if not files:
        raise SystemExit(f"[중단] motion/{scene} 프레임이 없다")
    return files


def window_mask():
    m = Image.new("L", (CW, CH + BAR), 0)
    ImageDraw.Draw(m).rounded_rectangle((0, 0, CW - 1, CH + BAR - 1), radius=18, fill=255)
    return m


MASK = None
SHADOW = None


def compose_window(bg: Image.Image, content: Image.Image, scale: float, alpha: float) -> Image.Image:
    global MASK, SHADOW
    if MASK is None:
        MASK = window_mask()
        sh = Image.new("L", (OUT_W, OUT_H), 0)
        ImageDraw.Draw(sh).rounded_rectangle((WX + 10, WY + 30, WX + CW - 10, WY + CH + BAR + 40), radius=24, fill=200)
        SHADOW = sh.filter(ImageFilter.GaussianBlur(38))
    win = Image.new("RGB", (CW, CH + BAR), (24, 23, 22))
    d = ImageDraw.Draw(win)
    for i, c in enumerate([(255, 95, 86), (255, 189, 46), (39, 201, 63)]):
        d.ellipse((18 + i * 22, 12, 30 + i * 22, 24), fill=c)
    f = font(17)
    d.rounded_rectangle((CW / 2 - 160, 7, CW / 2 + 160, 29), radius=11, fill=(38, 36, 34))
    d.text((CW / 2, 18), "nullstock.im", font=f, fill=(170, 164, 156), anchor="mm")
    win.paste(content, (0, BAR))
    out = bg.copy()
    out.paste(Image.new("RGB", out.size, (0, 0, 0)), (0, 0), SHADOW.point(lambda v: int(v * alpha * .85)))
    if scale != 1.0:
        w, h = int(CW * scale), int((CH + BAR) * scale)
        win_s, mask_s = win.resize((w, h), Image.LANCZOS), MASK.resize((w, h), Image.LANCZOS)
        x, y = WX + (CW - w) // 2, WY + (CH + BAR - h) // 2
    else:
        win_s, mask_s, x, y = win, MASK, WX, WY
    out.paste(win_s, (x, y), mask_s.point(lambda v: int(v * alpha)))
    return out


def label(img: Image.Image, text: str, alpha: float):
    if alpha <= 0:
        return
    f = font(30)
    lay = Image.new("RGBA", img.size, (0, 0, 0, 0))
    d = ImageDraw.Draw(lay)
    d.ellipse((WX + 4, 34, WX + 18, 48), fill=(*ACCENT, int(255 * alpha)))
    d.text((WX + 30, 41), text, font=f, fill=(243, 241, 236, int(255 * alpha)), anchor="lm")
    img.paste(Image.alpha_composite(img.convert("RGBA"), lay).convert("RGB"))


DEMO_NOTE = "시연용 연출 화면 · 장중에는 실제 시세가 반영됩니다"


def demo_note(img: Image.Image):
    """연출 시세(cf_server DEMO_LIVE_QUOTES)로 찍은 가상계좌 장면 표기 — 실제 종목명에 지어낸 가격 움직임을 표기 없이 내보내지 않는다."""
    f = font(22)
    w = f.getlength(DEMO_NOTE)
    x, y = WX + CW - w - 40, 26
    lay = Image.new("RGBA", img.size, (0, 0, 0, 0))
    d = ImageDraw.Draw(lay)
    d.rounded_rectangle((x, y, x + w + 32, y + 44), radius=22, fill=(18, 17, 16, 210))
    d.text((x + 16, y + 22), DEMO_NOTE, font=f, fill=(220, 214, 205, 255), anchor="lm")
    img.paste(Image.alpha_composite(img.convert("RGBA"), lay).convert("RGB"))


def subtitle(img: Image.Image, text: str, alpha: float):
    f = font(36)
    w = f.getlength(text)
    x, y, h = (OUT_W - w) / 2 - 30, OUT_H - 118, 66
    lay = Image.new("RGBA", img.size, (0, 0, 0, 0))
    d = ImageDraw.Draw(lay)
    d.rounded_rectangle((x, y, x + w + 60, y + h), radius=14, fill=(10, 9, 8, int(200 * alpha)))
    d.text((OUT_W / 2, y + h / 2), text, font=f, fill=(255, 255, 255, int(255 * alpha)), anchor="mm")
    img.paste(Image.alpha_composite(img.convert("RGBA"), lay).convert("RGB"))


def load_voice(lines: list[dict], voice: str, model: str, work: Path):
    """줄마다 Gemini TTS로 합성한다. 파일 이름에 문장·음성·모델의 해시를 넣어, 대본을 고친 줄만 다시 합성한다."""
    out, key = {}, None
    cf_tts_gemini.MODEL = model
    for ln in lines:
        h = hashlib.sha1(f"{ln['text']}|{voice}|{model}".encode()).hexdigest()[:8]
        wav = work / f"{ln['key']}_{h}.wav"
        if not wav.exists():
            if key:  # 무료 등급은 분당 요청 수도 작다 — 줄 사이에 간격을 둔다
                time.sleep(float(os.environ.get("CF_TTS_GAP", "22")))
            key = key or cf_tts_gemini.load_key()
            raw = work / f"{ln['key']}.pcm"
            raw.write_bytes(cf_tts_gemini.synth(ln["text"], voice, key))
            subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "s16le", "-ar", "24000", "-ac", "1", "-i", str(raw), "-af",
                            "silenceremove=start_periods=1:start_threshold=-45dB,areverse,silenceremove=start_periods=1:start_threshold=-45dB,areverse",
                            "-ar", "44100", "-ac", "2", str(wav)], check=True)
            raw.unlink()
            print(f"TTS {ln['key']} ({model})", flush=True)
        dur = float(subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(wav)],
                                   capture_output=True, text=True).stdout)
        out[ln["key"]] = (wav, dur)
    return out


def build_cf(h):
    from cf_build import Edit
    e = Edit()

    def tm(action, label, phase=None):
        return h.find(action, phase, label)["t"]

    def seg(a, b, d):
        e.seg(h, a, b, d)

    e.scene("input", "전략 문장 입력")
    a, b = tm("type", "input", "approach"), tm("type", "input", "send")
    e.shot(a, None, move=1)
    ib = h.find("type", "approach", "input")["box"]
    e.shot(a + 300, [ib["x"] - 150, ib["y"] - 90, ib["width"] + 300, ib["height"] + 180], move=700)
    seg(a, b + 300, 2.6)
    c = tm("appear", "card", "appear")
    e.shot(c - 200, None, move=500)
    seg(c, c + 3000, 2.4)
    e.scene("graph", "전략 그래프")
    a, b = tm("scene", "graph_final_start", "scene"), tm("scene", "graph_final_end", "scene")
    e.shot(a, None, move=1)
    e.shot(a + 1800, [110, 400, 1200, 400], move=900)
    e.shot(a + 5600, None, move=900)
    seg(a, b, 5.0)
    e.scene("backtest", "백테스트")
    r = tm("appear", "result", "appear")
    hold = tm("hold", None, "hold")
    m = h.box("metrics")
    e.shot(r, None, move=1)
    if m:
        e.shot(r + 1500, [m[0] - 60, m[1] - 40, m[2] + 120, max(m[3] + 80, 220)], move=800)
    e.shot(hold + 1200, None, move=800)
    seg(r, hold + 4800, 6.0)
    e.scene("wf", "워크포워드 분석")
    a = tm("scene", "wf_run", "scene")
    seg(a - 3500, a - 500, 2)
    a = tm("appear", "wf_progress", "appear")
    seg(a + 6000, a + 10000, 2)
    seg(a + 12000, a + 16000, 2)
    e.scene("mc", "몬테카를로 시뮬레이션")
    a, b = tm("scene", "mc_result", "scene"), tm("hold", None, "mc_hold")
    seg(a, a + 2000, 1.5)
    seg(b - 2000, b, 2)
    seg(b + 500, b + 5000, 2.5)
    e.scene("account", "가상계좌 모의투자", demo=True)
    a, b, z = tm("scene", "account_create", "scene"), tm("scene", "account_live", "scene"), tm("hold", None, "account_hold")
    seg(a, a + 1600, 1)
    seg(b, b + 1200, 1)
    seg(z, z + 2000, 1.5)
    seg(z + 2500, z + 4500, 1.5)
    seg(z + 5000, z + 7000, 1)
    return e


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("rec")
    ap.add_argument("motion")
    ap.add_argument("out")
    ap.add_argument("--script", default=str(HERE / "cf2_script.json"))
    ap.add_argument("--work", default="cf2_work")
    a = ap.parse_args()
    work = Path(a.work)
    work.mkdir(exist_ok=True)
    script = json.loads(Path(a.script).read_text())
    sc = script["scenes"]
    rec = Rec(Path(a.rec))
    demo_quotes = (Path(a.rec) / "demo_quotes.flag").exists()  # cf_run.sh --demo-quotes가 남긴다
    if demo_quotes:
        print("연출 시세 녹화 — 가상계좌 장면에 '시연용 연출 화면' 표기")
    motion = Path(a.motion)

    lines = script["lines"]
    voice = load_voice(lines, script["voice"], script["tts_model"], work)
    sc["input"] = max(sc["input"], voice["v2"][1] + 0.7)
    sc["graph"] = max(sc["graph"], voice["g1"][1] + 1.2)
    sc["backtest"] = max(sc["backtest"], voice["v34"][1] + 0.9)
    ed = build_cf(rec)
    gr = scene_clips(ed)
    acct = gr["account"]
    # 가상계좌: 이름 입력·만들기 + 시세 채워진 상세(전체·모니터링 확대) + 종목 화면 — 이동 장면(메뉴·목록)은 뺀다
    acct_pick = acct
    product = {
        "input": (fit(gr["input"], sc["input"]), "전략 문장 입력"),
        "graph": (fit(gr["graph"], sc["graph"]), "전략 그래프"),
        "backtest": (fit(gr["backtest"], sc["backtest"]), "백테스트"),
        "wf": (fit(gr["wf"], sc["wf"]), "워크포워드 분석"),
        "mc": (fit(gr["mc"], sc["mc"]), "몬테카를로 시뮬레이션"),
        "account": (fit(acct_pick, sc["account"]), "가상계좌 모의투자"),
    }
    timeline = [("m", "open", sc["open"]), ("m", "heat", sc["heat"]), ("m", "title", sc["title"]), ("p", "input", sc["input"]), ("p", "graph", sc["graph"]), ("p", "backtest", sc["backtest"]),
                ("m", "wf", sc["wf_motion"]), ("p", "wf", sc["wf"]), ("m", "mc", sc["mc_motion"]), ("p", "mc", sc["mc"]),
                ("m", "live", sc["live"]), ("p", "account", sc["account"]), ("m", "end", sc["end"])]
    starts, t = [], 0.0
    for item in timeline:
        starts.append(t)
        t += item[2]
    total = t
    at = {f"{k}:{n}": s for (k, n, _), s in zip(timeline, starts)}

    place = {}
    for ln in lines:
        if "after" in ln:
            place[ln["key"]] = place[ln["after"]] + voice[ln["after"]][1] + ln.get("gap", 0.3)
        else:
            place[ln["key"]] = at[ln["at"]] + ln.get("offset", 0.0)
    place = dict(sorted(place.items(), key=lambda kv: kv[1]))
    text_of = {ln["key"]: ln.get("sub", ln["text"]) for ln in lines}
    keys = list(place)
    subs = []
    for i, k in enumerate(keys):
        s, e = place[k], place[k] + voice[k][1] + 0.2
        if i + 1 < len(keys) and e > place[keys[i + 1]] - 0.05:
            print(f"[경고] {k}가 다음 줄과 {e - place[keys[i + 1]]:.2f}초 겹친다")
        tx = text_of[k]
        if isinstance(tx, list):
            tot, cur = sum(len(x) for x in tx), s
            for x in tx:
                d = (e - s) * len(x) / tot
                subs.append((cur, cur + d, x))
                cur += d
        else:
            subs.append((s, e, tx))
    print(f"길이 {total:.1f}초 · " + " ".join(f"{k}={v:.1f}" for k, v in at.items()))

    camera = Camera(ed.shots)
    fcache: dict = {}
    bg_files = load_motion(motion, "bg")
    video = work / "video.mp4"
    enc = subprocess.Popen(["ffmpeg", "-v", "error", "-y", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{OUT_W}x{OUT_H}",
                            "-r", str(FPS), "-i", "-", "-c:v", "libx264", "-preset", "slow", "-crf", "17", "-pix_fmt", "yuv420p", str(video)],
                           stdin=subprocess.PIPE)
    last = None
    gidx = 0
    for (kind, name, dur), t0 in zip(timeline, starts):
        n = round(dur * FPS)
        if kind == "m":
            files = load_motion(motion, name)
        else:
            clips, lab = product[name]
            bounds, acc = [], 0.0
            for c in clips:
                bounds.append((acc, acc + c["dur"], c))
                acc += c["dur"]
        for k in range(n):
            tt = k / FPS
            if kind == "m":
                img = Image.open(files[min(k, len(files) - 1)]).convert("RGB")
            else:
                bg = Image.open(bg_files[gidx % len(bg_files)]).convert("RGB")
                c = next((c for s, e, c in bounds if s <= tt < e), bounds[-1][2])
                s0 = next((s for s, e, cc in bounds if cc is c))
                rt = c["from"] + (tt - s0) * 1000 * c["speed"]
                fr = fcache.setdefault(c["frames"], Frames(c["frames"]))
                left, top, vw, vh = camera.at(rt)
                content = fr.at(rt).resize((CW, CH), Image.LANCZOS, box=(left * 2, top * 2, (left + vw) * 2, (top + vh) * 2))
                u = ease(tt / 0.45)
                img = compose_window(bg, content, 0.94 + 0.06 * u, min(1.0, tt / 0.25))
                label(img, lab, min(1.0, tt / 0.4))
                if demo_quotes and name == "account":
                    demo_note(img)
                if c.get("badge"):
                    pass  # 빨리 감기 배지는 2편에서 쓰지 않는다(글에 밝힌다)
            now = t0 + tt
            if name not in NO_SUB_SCENES or kind == "p":
                for s, e, txt in subs:
                    if s <= now < e:
                        subtitle(img, txt, min(1.0, (now - s) / 0.2, (e - now) / 0.2))
            if last is not None and k < XFADE:
                img = Image.blend(last, img, (k + 1) / (XFADE + 1))
            enc.stdin.write(img.tobytes())
            gidx += 1
            if k == n - 1:
                last = img
        print(f"{kind}:{name} {n}f", flush=True)
    enc.stdin.close()
    enc.wait()

    music = work / "music.wav"
    hits = [at["m:heat"], at["m:title"], at["m:wf"], at["m:mc"], at["m:live"], at["m:end"]]
    subprocess.run(["uv", "run", "--with", "numpy", "python", str(HERE / "cf_music.py"), str(music), f"{total + 0.5:.2f}",
                    f"{at['m:title']:.2f}", f"{at['m:end']:.2f}", *[f"{h:.2f}" for h in hits]], check=True)
    inputs = ["-i", str(video), "-i", str(music)]
    chains = []
    for i, k in enumerate(keys):
        inputs += ["-i", str(voice[k][0])]
        ms = int(place[k] * 1000)
        chains.append(f"[{i + 2}:a]adelay={ms}|{ms}[v{i}]")
    graph = ";".join(chains + ["".join(f"[v{i}]" for i in range(len(keys))) + f"amix=inputs={len(keys)}:normalize=0,asplit=2[vo][sc]",
                               "[1:a]volume=0.6[m]", "[m][sc]sidechaincompress=threshold=0.03:ratio=6:attack=20:release=350[md]",
                               f"[md][vo]amix=inputs=2:normalize=0,atrim=0:{total:.3f},loudnorm=I=-14:TP=-1.5:LRA=11[a]"])
    subprocess.run(["ffmpeg", "-v", "error", "-y", *inputs, "-filter_complex", graph, "-map", "0:v", "-map", "[a]",
                    "-c:v", "copy", "-c:a", "aac", "-b:a", "192k", "-movflags", "+faststart", a.out], check=True)
    print("done", a.out, f"{total:.1f}s")


if __name__ == "__main__":
    main()
