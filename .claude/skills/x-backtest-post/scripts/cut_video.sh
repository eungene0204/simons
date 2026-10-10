#!/bin/bash
# 녹화 원본에서 구간을 잘라 배속을 바꿔 이어 붙이고, 마지막 장면을 2.5초 정지로 붙인다(X용 H.264 mp4).
# 사용: cut_video.sh <원본.mp4> <결과.mp4> <구간 파일: 한 줄에 "시작 끝 배속"(초)>
F=""; C=""; i=0
while read s e sp; do [ -z "$s" ] && continue; F="${F}[0:v]trim=${s}:${e},setpts=(PTS-STARTPTS)/${sp}[v${i}];"; C="${C}[v${i}]"; i=$((i+1)); done < "$3"
F="${F}${C}concat=n=${i}:v=1:a=0,tpad=stop_mode=clone:stop_duration=2.5,fps=30[out]"
ffmpeg -v error -y -i "$1" -filter_complex "$F" -map "[out]" -c:v libx264 -profile:v high -pix_fmt yuv420p -crf 20 -movflags +faststart "$2"
