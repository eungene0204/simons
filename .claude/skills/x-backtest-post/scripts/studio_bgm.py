"""스튜디오 영상에 BGM을 입힌다(항상 — 소리 없는 영상은 내보내지 않는다, 2026-10-19 사용자 지시).
사용: uv run --with numpy python studio_bgm.py <plan.json> <silent.mp4> <out.mp4> [bright|calm]
plan.json 클립에서 곡의 구간 시작(본편·④ 칩·⑥ 실행·결과·끝 카드)을 읽어 cf/bgm_*.py에 넘기고, 2패스 loudnorm→alimiter→AAC로 믹스한다.
"""
import json, subprocess, sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
plan, silent, out = sys.argv[1], sys.argv[2], sys.argv[3]
kind = sys.argv[4] if len(sys.argv) > 4 else "bright"
LUFS = {"bright": -17, "calm": -18}[kind]
clips = json.loads(Path(plan).read_text())["clips"]

start, t = [], 0.0
for c in clips:
    start.append(t)
    t += c["dur"] if "card" in c else (c["to"] - c["from"]) / 1000 / c["speed"]
total = t

def first(prefix, default):
    return next((start[i] for i, c in enumerate(clips) if c.get("caption", "").startswith(prefix)), default)

main = start[1]   # 제목 카드가 끝나는 지점
chip = first("④", start[1])
run = first("⑥", chip)
result = first("⑦", run)
end = next(start[i] for i in range(len(clips) - 1, -1, -1) if "card" in clips[i])

wav = Path(silent).with_suffix(".bgm.wav")
subprocess.run([sys.executable, str(HERE / "cf" / f"bgm_{kind}.py"), str(wav), f"{total:.2f}", f"{main:.2f}", f"{chip:.2f}", f"{run:.2f}", f"{result:.2f}", f"{end:.2f}"], check=True)
r = subprocess.run(["ffmpeg", "-hide_banner", "-nostats", "-i", str(wav), "-af", f"loudnorm=I={LUFS}:TP=-3:LRA=11:print_format=json", "-f", "null", "-"], capture_output=True, text=True).stderr
j = json.loads(r[r.rindex("{"): r.rindex("}") + 1])
ln = (f"loudnorm=I={LUFS}:TP=-3:LRA=11:measured_I={j['input_i']}:measured_TP={j['input_tp']}:measured_LRA={j['input_lra']}"
      f":measured_thresh={j['input_thresh']}:offset={j['target_offset']}:linear=true,alimiter=limit=0.63:level=disabled,aresample=48000")
subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", silent, "-i", str(wav), "-filter_complex", f"[1:a]{ln}[a]", "-map", "0:v", "-map", "[a]",
                "-c:v", "copy", "-c:a", "aac", "-b:a", "192k", "-ar", "48000", "-t", f"{total:.3f}", "-movflags", "+faststart", out], check=True)
print(f"bgm done {out} total={total:.2f}s kind={kind}")
