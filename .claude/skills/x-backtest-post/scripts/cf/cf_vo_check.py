"""내레이션 녹음을 Gemini 받아쓰기로 대본과 대조한다(들을 수 없을 때의 검수 — 2026-10-12 도입).

줄들을 1.2초 무음으로 이어 한 파일로 만들어 한 번에 받아쓴다(요청 수 절약). 대본과 다른 줄은 사람이 고친다.
사용: python3 cf_vo_check.py <wav> [wav ...]
"""

from __future__ import annotations

import base64
import json
import subprocess
import sys
import tempfile
import time
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from cf_tts_gemini import load_key  # noqa: E402

wavs = [Path(p).resolve() for p in sys.argv[1:]]
with tempfile.TemporaryDirectory() as d:
    gap, lst, allw = Path(d) / "gap.wav", Path(d) / "list.txt", Path(d) / "all.mp3"
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-t", "1.2", "-i", "anullsrc=r=44100:cl=stereo", str(gap)], check=True)
    lst.write_text("".join(f"file '{w}'\nfile '{gap}'\n" for w in wavs))
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "concat", "-safe", "0", "-i", str(lst), "-ar", "44100", "-ac", "2", str(allw)], check=True)
    audio = base64.b64encode(allw.read_bytes()).decode()
body = {"contents": [{"parts": [
    {"text": f"이 한국어 음성에는 문장 {len(wavs)}개가 짧은 무음으로 나뉘어 있습니다. 들리는 그대로 받아써서 한 줄에 한 문장씩 번호를 붙여 출력하세요."},
    {"inlineData": {"mimeType": "audio/mp3", "data": audio}}]}]}
key = load_key()
for attempt in range(6):  # 503(일시 과부하)이 잦다 — 10-12 실측
    try:
        req = urllib.request.Request("https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent",
                                     data=json.dumps(body).encode(), headers={"Content-Type": "application/json", "x-goog-api-key": key})
        print(json.load(urllib.request.urlopen(req, timeout=180))["candidates"][0]["content"]["parts"][0]["text"])
        break
    except Exception as e:  # noqa: BLE001
        print("재시도:", e, file=sys.stderr)
        time.sleep(20)
