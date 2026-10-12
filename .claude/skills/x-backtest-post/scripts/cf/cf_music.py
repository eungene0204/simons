"""홍보 CF 배경 음악을 합성한다(저작권 없는 자체 합성, 44.1kHz 스테레오 WAV).

110BPM, A단조 Am–F–C–G 진행. 패드는 처음부터, 킥·하이햇·아르페지오는 본편 장면이 시작되는 순간 들어오고,
장면 전환 시각(hits)마다 상승음(riser)과 임팩트를 넣는다. 끝 카드에서는 마지막 화음을 길게 끌며 사라진다.

사용: uv run --with numpy python cf_music.py out.wav <길이초> <본편시작초> <끝카드초> [전환초 ...]
"""

from __future__ import annotations

import sys
import wave

import numpy as np

SR = 44100
BPM = 110
BEAT = 60 / BPM
CHORDS = [  # (근음 MIDI, 화음 구성음 MIDI) — Am, F, C, G
    (45, [57, 60, 64, 69]),
    (41, [53, 57, 60, 65]),
    (48, [55, 60, 64, 67]),
    (43, [55, 59, 62, 67]),
]


def hz(m: float) -> float:
    return 440.0 * 2 ** ((m - 69) / 12)


def env_adsr(n: int, a: float, r: float) -> np.ndarray:
    t = np.arange(n) / SR
    e = np.minimum(1, t / max(a, 1e-4)) * np.minimum(1, (n / SR - t) / max(r, 1e-4))
    return np.clip(e, 0, 1)


def saw(f: float, n: int, detune: float = 0.0) -> np.ndarray:
    t = np.arange(n) / SR
    out = np.zeros(n)
    for d in (-detune, 0, detune):
        ph = (t * f * (1 + d)) % 1
        out += 2 * ph - 1
    return out / 3


def lowpass(x: np.ndarray, cutoff: float) -> np.ndarray:
    a = np.exp(-2 * np.pi * cutoff / SR)
    y = np.empty_like(x)
    acc = 0.0
    for i, v in enumerate(x):  # 한 극 저역 통과 — 길이가 짧아 파이썬 루프로 충분하다
        acc = (1 - a) * v + a * acc
        y[i] = acc
    return y


def build(total: float, main_start: float, end_start: float, hits: list[float]) -> np.ndarray:
    n = int(total * SR)
    L = np.zeros(n)
    R = np.zeros(n)
    bar = BEAT * 4
    rng = np.random.default_rng(7)

    def add(sig: np.ndarray, at: float, pan: float = 0.0, gain: float = 1.0) -> None:
        i = int(at * SR)
        if i >= n:
            return
        sig = sig[: n - i] * gain
        L[i : i + len(sig)] += sig * (1 - pan) / 2 * 2 ** 0.5
        R[i : i + len(sig)] += sig * (1 + pan) / 2 * 2 ** 0.5

    # 패드 — 마디마다 화음, 끝 카드에서는 마지막 Am을 길게
    t = 0.0
    k = 0
    while t < end_start:
        root, notes = CHORDS[k % 4]
        m = int(bar * SR) + int(0.4 * SR)
        pad = sum(saw(hz(x), m, 0.004) for x in notes) / len(notes)
        pad = lowpass(pad, 1400 if t >= main_start else 700) * env_adsr(m, 0.35, 0.5)
        add(pad, t, -0.3, 0.16)
        add(pad, t + 0.012, 0.3, 0.16)
        # 베이스 — 본편부터 8분음표
        if t >= main_start - 1e-6:
            for b in range(8):
                bn = int(BEAT / 2 * SR)
                sub = np.sin(2 * np.pi * hz(root) * np.arange(bn) / SR) * env_adsr(bn, 0.005, 0.12)
                add(sub, t + b * BEAT / 2, 0, 0.30 if b % 2 == 0 else 0.18)
        t += bar
        k += 1
    m = int((total - end_start) * SR)
    pad = sum(saw(hz(x), m, 0.004) for x in CHORDS[0][1] + [76]) / 5
    add(lowpass(pad, 1100) * env_adsr(m, 0.05, (total - end_start) * 0.8), end_start, 0, 0.30)
    sub = np.sin(2 * np.pi * hz(33) * np.arange(m) / SR) * env_adsr(m, 0.01, (total - end_start) * 0.7)
    add(sub, end_start, 0, 0.35)

    # 드럼·아르페지오 — 본편 ~ 끝 카드 직전
    beat = main_start
    i = 0
    while beat < end_start - 0.05:
        kn = int(0.35 * SR)
        tt = np.arange(kn) / SR
        kick = np.sin(2 * np.pi * (45 + 90 * np.exp(-tt * 30)) * tt) * np.exp(-tt * 9)
        add(kick, beat, 0, 0.55)
        hn = int(0.05 * SR)
        hat = rng.standard_normal(hn) * np.exp(-np.arange(hn) / SR * 90)
        hat = hat - lowpass(hat, 6000)
        add(hat, beat + BEAT / 2, 0.25, 0.10)
        if i % 4 == 2:  # 클랩(2·4박)
            cn = int(0.18 * SR)
            clap = rng.standard_normal(cn) * np.exp(-np.arange(cn) / SR * 22)
            add(clap - lowpass(clap, 1200), beat - BEAT, -0.1, 0.09)
        # 아르페지오 16분음표
        root, notes = CHORDS[int((beat - main_start) / bar + 0) % 4]
        for s in range(4):
            an = int(BEAT / 4 * SR)
            note = notes[(i * 4 + s) % 4] + 12
            pl = np.sign(np.sin(2 * np.pi * hz(note) * np.arange(an) / SR)) * np.exp(-np.arange(an) / SR * 18)
            add(lowpass(pl, 2500), beat + s * BEAT / 4, 0.4 if s % 2 else -0.4, 0.045)
        beat += BEAT
        i += 1

    # 전환 — 1.6초 상승음(노이즈 스윕) + 임팩트
    for h in hits:
        rn = int(1.6 * SR)
        noise = rng.standard_normal(rn)
        sweep = np.zeros(rn)
        for j, c in enumerate(np.linspace(400, 7000, 16)):  # 구간별로 차단 주파수를 올린다
            a, b = j * rn // 16, (j + 1) * rn // 16
            sweep[a:b] = (noise[a:b] - lowpass(noise[a:b], c))
        sweep *= np.linspace(0, 1, rn) ** 2
        add(sweep, h - 1.6, 0, 0.05)
        im = int(1.2 * SR)
        tt = np.arange(im) / SR
        boom = np.sin(2 * np.pi * (38 + 60 * np.exp(-tt * 12)) * tt) * np.exp(-tt * 3.5)
        add(boom, h, 0, 0.55)

    out = np.stack([L, R], 1)
    out /= max(1e-9, np.abs(out).max()) / 0.89
    fade = int(0.02 * SR)
    out[:fade] *= np.linspace(0, 1, fade)[:, None]
    return out


if __name__ == "__main__":
    path, total, main_start, end_start = sys.argv[1], *map(float, sys.argv[2:5])
    hits = [float(x) for x in sys.argv[5:]]
    pcm = (build(total, main_start, end_start, hits) * 32767).astype("<i2")
    with wave.open(path, "wb") as w:
        w.setnchannels(2)
        w.setsampwidth(2)
        w.setframerate(SR)
        w.writeframes(pcm.tobytes())
    print(path, f"{total:.1f}s")
