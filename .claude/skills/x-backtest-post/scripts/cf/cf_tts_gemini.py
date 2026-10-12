"""홍보 CF 내레이션을 Gemini TTS로 합성한다(edge-tts가 2026-10-12부터 403으로 막혀 대체).

사용: uv run python cf_tts_gemini.py <out_dir> <voice> <key=문장> [key=문장 ...]
  키는 .env의 GOOGLE_API_KEY(값은 출력하지 않는다). 대본 문구만 Google로 전송된다.
  출력: <out_dir>/<key>.wav(44.1kHz 스테레오, 앞뒤 무음 제거)
"""

from __future__ import annotations

import base64
import time
import urllib.error
import json
import os
import subprocess
import sys
import urllib.request
from pathlib import Path

MODEL = os.environ.get("CF_TTS_MODEL", "gemini-3.8-flash-tts")
STYLE = os.environ.get("CF_TTS_STYLE", "")  # 말투 지시문은 넣지 않는다 — 한국어·영어 모두 지시문까지 소리 내어 읽었다(10-12 실측: 5초 문장이 11~13초)


def load_key() -> str:
    key = os.environ.get("GOOGLE_API_KEY")
    if not key:
        for line in Path(__file__).resolve().parents[5].joinpath(".env").read_text().splitlines():
            if line.startswith("GOOGLE_API_KEY="):
                key = line.split("=", 1)[1].strip().strip('"')
    if not key:
        raise SystemExit("[중단] GOOGLE_API_KEY가 없다")
    return key


def synth(text: str, voice: str, key: str) -> bytes:
    body = {"contents": [{"parts": [{"text": STYLE + text}]}],
            "generationConfig": {"responseModalities": ["AUDIO"],
                                 "speechConfig": {"voiceConfig": {"prebuiltVoiceConfig": {"voiceName": voice}}}}}
    req = urllib.request.Request(f"https://generativelanguage.googleapis.com/v1beta/models/{MODEL}:generateContent",
                                 data=json.dumps(body).encode(), headers={"Content-Type": "application/json", "x-goog-api-key": key})
    for attempt in range(8):  # 분당 요청 한도(429)에 걸리면 기다렸다 다시 — 10-12 실측: 5건 연속에서 429
        try:
            with urllib.request.urlopen(req, timeout=120) as r:
                d = json.load(r)
            break
        except urllib.error.HTTPError as e:
            if e.code != 429 or attempt == 7:
                raise
            time.sleep(20 + attempt * 10)
    part = d["candidates"][0]["content"]["parts"][0]["inlineData"]
    return base64.b64decode(part["data"])  # 24kHz 16비트 모노 PCM


def main():
    out, voice, *pairs = sys.argv[1:]
    out_dir = Path(out)
    out_dir.mkdir(parents=True, exist_ok=True)
    key = load_key()
    for pair in pairs:
        k, text = pair.split("=", 1)
        pcm = synth(text, voice, key)
        raw = out_dir / f"{k}.pcm"
        raw.write_bytes(pcm)
        subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "s16le", "-ar", "24000", "-ac", "1", "-i", str(raw), "-af",
                        "silenceremove=start_periods=1:start_threshold=-45dB,areverse,silenceremove=start_periods=1:start_threshold=-45dB,areverse",
                        "-ar", "44100", "-ac", "2", str(out_dir / f"{k}.wav")], check=True)
        raw.unlink()
        dur = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(out_dir / f"{k}.wav")],
                             capture_output=True, text=True).stdout.strip()
        print(k, dur, flush=True)


if __name__ == "__main__":
    main()
