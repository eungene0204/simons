#!/bin/bash
# 렌더한 영상 검수 자료: review_sheet.png(1.5초 간격 접촉 시트) + review_<초>.png(원본 크기 확인 프레임) + 규격 출력.
# 사용: bash review_video.sh out.mp4
set -euo pipefail
V="$1"
ffprobe -v error -show_entries stream=width,height,r_frame_rate,codec_name -show_entries format=duration,size -of compact "$V"
ffmpeg -v error -y -i "$V" -vf "fps=2/3,scale=480:-1,tile=6x8" -frames:v 1 review_sheet.png
DUR=$(ffprobe -v error -show_entries format=duration -of csv=p=0 "$V")
for f in 0.12 0.35 0.75 0.85; do
  T=$(python3 -c "print(round($DUR*$f,1))"); ffmpeg -v error -y -ss "$T" -i "$V" -frames:v 1 "review_$T.png"
done
ls review_*.png
