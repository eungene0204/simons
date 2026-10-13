"""설명 영상용 밝은 배경 음악(저작권 없는 자체 합성). 100BPM, C–G–Am–F 장조. 맑은 벨 플럭 + 따뜻한 패드 + 아주 가벼운 킥·셰이커.
사용: uv run --with numpy python bgm_bright.py out.wav <총길이초> <본편 시작> <플럭 시작> <촘촘해지는 시작> <결과 시작> <끝 카드 시작>
"""
import sys, wave
from pathlib import Path
import numpy as np
SR = 44100
BPM = 100; BEAT = 60 / BPM; BAR = BEAT * 4
CHORDS = [(48, [60, 64, 67, 72]), (43, [59, 62, 67, 71]), (45, [60, 64, 69, 72]), (41, [60, 65, 69, 72])]   # C G Am F
hz = lambda m: 440.0 * 2 ** ((m - 69) / 12)
def env(n, a, r):
    t = np.arange(n) / SR
    return np.clip(np.minimum(1, t / max(a, 1e-4)) * np.minimum(1, (n / SR - t) / max(r, 1e-4)), 0, 1)
def lowpass(x, c):
    a = np.exp(-2 * np.pi * c / SR); y = np.zeros_like(x); s = 0.0
    for i in range(len(x)): s = (1 - a) * x[i] + a * s; y[i] = s
    return y
def tri(f, n, det=0.0):
    t = np.arange(n) / SR; out = np.zeros(n)
    for d in (-det, 0, det): out += 2 * np.abs(2 * ((f * (1 + d) * t) % 1.0) - 1) - 1
    return out / 3

def build(total, main, arp, busy, result, end):
    n = int(total * SR); L = np.zeros(n); R = np.zeros(n); echo = np.zeros((2, n)); rng = np.random.default_rng(11)
    def add(sig, at, pan=0.0, gain=1.0, send=0.0):
        i = int(at * SR)
        if i >= n: return
        sig = sig[: n - i] * gain
        l, r = sig * (1 - pan) / 2 * 2 ** 0.5, sig * (1 + pan) / 2 * 2 ** 0.5
        L[i:i + len(sig)] += l; R[i:i + len(sig)] += r
        if send: echo[0, i:i + len(sig)] += l * send; echo[1, i:i + len(sig)] += r * send
    t = 0.0; k = 0
    while t < end:
        root, notes = CHORDS[k % 4]
        m = int((BAR + 0.5) * SR)
        pad = sum(tri(hz(x), m, 0.004) for x in notes) / len(notes)
        pad = lowpass(pad, 2400 if t < main else 3800) * env(m, 0.25, 0.7)
        add(pad, t, -0.3, 0.17); add(pad, t + 0.012, 0.3, 0.17)
        if t >= main - 1e-6:   # 베이스: 1박, 2박 뒷박, 3박
            for b, g, ln in ((0, 0.17, 0.9), (1.5, 0.09, 0.4), (2, 0.13, 0.9)):
                bn = int(BEAT * ln * SR)
                sub = (np.sin(2 * np.pi * hz(root) * np.arange(bn) / SR) + 0.25 * np.sin(2 * np.pi * 2 * hz(root) * np.arange(bn) / SR)) * env(bn, 0.01, 0.5)
                add(sub, t + b * BEAT, 0, g)
        t += BAR; k += 1
    # 벨 플럭 아르페지오(8분음표, 촘촘한 구간은 16분음표)
    tt = arp; i = 0
    while tt < end - 0.3:
        dense = busy <= tt < result
        s = BEAT / 4 if dense else BEAT / 2
        root, notes = CHORDS[int((tt - main) // BAR) % 4]
        seq = [0, 1, 2, 3, 2, 1] if not dense else [0, 2, 1, 3, 2, 3, 1, 3]
        note = notes[seq[i % len(seq)]] + 12
        pn = int(0.8 * SR); x = np.arange(pn) / SR; f = hz(note)
        bell = (np.sin(2 * np.pi * f * x) + 0.5 * np.sin(2 * np.pi * 2 * f * x) * np.exp(-x * 14) + 0.22 * np.sin(2 * np.pi * 3.01 * f * x) * np.exp(-x * 20)) * np.exp(-x * 9)
        add(bell, tt, 0.5 if i % 2 else -0.5, 0.12 if not dense else 0.095, send=0.5)
        tt += s; i += 1
    # 가벼운 리듬: 셰이커(뒷박) + 아주 약한 킥(1·3박) + 약한 클랩(2·4박) — 칩 구간부터
    b0 = arp; j = 0
    while b0 < end - 0.2:
        beat = b0
        hn = int(0.06 * SR); sh = rng.standard_normal(hn) * np.exp(-np.arange(hn) / SR * 55); sh = sh - lowpass(sh, 5500)
        add(sh, beat + BEAT / 2, 0.3, 0.22)
        if j % 2 == 0:
            kn = int(0.30 * SR); tk = np.arange(kn) / SR
            add(np.sin(2 * np.pi * (50 + 80 * np.exp(-tk * 28)) * tk) * np.exp(-tk * 10), beat, 0, 0.30)
        else:
            cn = int(0.14 * SR); cl = rng.standard_normal(cn) * np.exp(-np.arange(cn) / SR * 28)
            add(cl - lowpass(cl, 1500), beat, -0.15, 0.07)
        b0 += BEAT; j += 1
    # 결과 장면: 밝게 열리는 스웰
    sn = int(2.0 * SR)
    sw = sum(tri(hz(v), sn, 0.004) for v in (72, 76, 79, 84)) / 4
    add(lowpass(sw, 3500) * env(sn, 1.4, 0.6), result - 0.3, 0, 0.14)
    # 끝 카드: C 장조 화음을 길게
    m = int((total - end) * SR)
    pad = sum(tri(hz(v), m, 0.004) for v in (60, 64, 67, 72, 79)) / 5
    add(lowpass(pad, 2200) * env(m, 0.2, (total - end) * 0.85), end, 0, 0.30)
    add(np.sin(2 * np.pi * hz(36) * np.arange(m) / SR) * env(m, 0.03, (total - end) * 0.8), end, 0, 0.28)
    for d, g in ((0.30, 0.30), (0.60, 0.16)):
        o = int(d * SR); L[o:] += echo[0, :n - o] * g; R[o:] += echo[1, :n - o] * g
    out = np.stack([L, R], 1); out /= max(1e-9, np.abs(out).max()) / 0.85
    f = int(1.2 * SR); out[:f] *= np.linspace(0, 1, f)[:, None]
    f2 = int(2.5 * SR); out[-f2:] *= np.linspace(1, 0, f2)[:, None]
    return out

if __name__ == '__main__':
    path = sys.argv[1]; total, main, arp, busy, result, end = map(float, sys.argv[2:8])
    pcm = (build(total, main, arp, busy, result, end) * 32767).astype('<i2')
    with wave.open(path, 'wb') as w:
        w.setnchannels(2); w.setsampwidth(2); w.setframerate(SR); w.writeframes(pcm.tobytes())
    print(path, f'{total:.1f}s')
