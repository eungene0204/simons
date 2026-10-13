"""설명 영상용 차분한 배경 음악(저작권 없는 자체 합성). 84BPM, Am–F–C–G. 드럼·충격음 없이 패드+베이스+잔잔한 플럭.
사용: uv run --with numpy python bgm_calm.py out.wav <총길이초> <장면 시작초 ...>
  장면 시작초 = [본편 시작, 아르페지오 시작, 촘촘해지는 시작, 결과 시작, 끝 카드 시작]
"""
import sys, wave
from pathlib import Path
import numpy as np
sys.path.insert(0, str(Path(__file__).resolve().parent))
SR = 44100
BPM = 84; BEAT = 60 / BPM; BAR = BEAT * 4
CHORDS = [(45, [57, 60, 64, 69]), (41, [53, 57, 60, 65]), (48, [55, 60, 64, 67]), (43, [55, 59, 62, 67])]
hz = lambda m: 440.0 * 2 ** ((m - 69) / 12)
def env(n, a, r):
    t = np.arange(n) / SR
    return np.clip(np.minimum(1, t / max(a, 1e-4)) * np.minimum(1, (n / SR - t) / max(r, 1e-4)), 0, 1)
def lowpass(x, c):
    a = np.exp(-2 * np.pi * c / SR); y = np.zeros_like(x); s = 0.0
    for i in range(len(x)): s = (1 - a) * x[i] + a * s; y[i] = s
    return y
def saw(f, n, det=0.0):
    t = np.arange(n) / SR; out = np.zeros(n)
    for d in (-det, 0, det): out += 2 * ((f * (1 + d) * t) % 1.0) - 1
    return out / 3

def build(total, main, arp, busy, result, end):
    n = int(total * SR); L = np.zeros(n); R = np.zeros(n); echo = np.zeros((2, n))
    def add(sig, at, pan=0.0, gain=1.0, send=0.0):
        i = int(at * SR)
        if i >= n: return
        sig = sig[: n - i] * gain
        l, r = sig * (1 - pan) / 2 * 2 ** 0.5, sig * (1 + pan) / 2 * 2 ** 0.5
        L[i:i + len(sig)] += l; R[i:i + len(sig)] += r
        if send:
            echo[0, i:i + len(sig)] += l * send; echo[1, i:i + len(sig)] += r * send
    t = 0.0; k = 0
    while t < end:
        root, notes = CHORDS[k % 4]
        m = int((BAR + 0.8) * SR)
        pad = sum(saw(hz(x), m, 0.003) for x in notes) / len(notes)
        pad = lowpass(pad, 700 if t < main else 1100) * env(m, 0.7, 1.0)
        add(pad, t, -0.3, 0.17); add(pad, t + 0.015, 0.3, 0.17)
        if t >= main - 1e-6:   # 베이스: 마디 첫 박과 셋째 박
            for b in (0, 2):
                bn = int(BEAT * 1.8 * SR)
                sub = np.sin(2 * np.pi * hz(root) * np.arange(bn) / SR) * env(bn, 0.02, 0.9)
                add(sub, t + b * BEAT, 0, 0.26 if b == 0 else 0.17)
        t += BAR; k += 1
    # 플럭 아르페지오(8분음표, 촘촘한 구간은 16분음표)
    step = BEAT / 2; tt = arp; i = 0
    while tt < end - 0.3:
        dense = busy <= tt < result
        s = step / 2 if dense else step
        root, notes = CHORDS[int((tt - main) // BAR) % 4]
        note = notes[i % 4] + (12 if not dense else 12 + (7 if i % 8 == 5 else 0))
        pn = int(0.9 * SR); x = np.arange(pn) / SR
        pl = (np.sin(2 * np.pi * hz(note) * x) + 0.35 * np.sin(2 * np.pi * 2 * hz(note) * x)) * np.exp(-x * 7)
        add(pl, tt, 0.45 if i % 2 else -0.45, 0.05 if not dense else 0.04, send=0.55)
        tt += s; i += 1
    # 결과 장면: 부드럽게 열리는 스웰
    sn = int(2.2 * SR); x = np.arange(sn) / SR
    sw = sum(saw(hz(v), sn, 0.003) for v in (69, 72, 76, 81)) / 4
    add(lowpass(sw, 1800) * env(sn, 1.6, 0.6), result - 0.4, 0, 0.10)
    # 끝 카드: 마지막 Am을 길게
    m = int((total - end) * SR)
    pad = sum(saw(hz(v), m, 0.003) for v in (57, 60, 64, 69, 76)) / 5
    add(lowpass(pad, 900) * env(m, 0.3, (total - end) * 0.85), end, 0, 0.26)
    sub = np.sin(2 * np.pi * hz(33) * np.arange(m) / SR) * env(m, 0.05, (total - end) * 0.8)
    add(sub, end, 0, 0.30)
    # 반향(2탭)
    for d, g in ((0.43, 0.30), (0.86, 0.14)):
        o = int(d * SR)
        L[o:] += echo[0, :n - o] * g; R[o:] += echo[1, :n - o] * g
    out = np.stack([L, R], 1); out /= max(1e-9, np.abs(out).max()) / 0.85
    f = int(1.5 * SR); out[:f] *= np.linspace(0, 1, f)[:, None]
    f2 = int(2.5 * SR); out[-f2:] *= np.linspace(1, 0, f2)[:, None]
    return out

if __name__ == '__main__':
    path = sys.argv[1]; total, main, arp, busy, result, end = map(float, sys.argv[2:8])
    pcm = (build(total, main, arp, busy, result, end) * 32767).astype('<i2')
    with wave.open(path, 'wb') as w:
        w.setnchannels(2); w.setsampwidth(2); w.setframerate(SR); w.writeframes(pcm.tobytes())
    print(path, f'{total:.1f}s')
