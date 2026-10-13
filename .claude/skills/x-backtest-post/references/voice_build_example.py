"""문장 단위 목소리를 장면 이벤트(칩 클릭)에 맞춰 영상에 입힌다. 사용: python build_voice.py <gemini|yuna>"""
import json, subprocess, sys, shutil
from pathlib import Path

VOICE = sys.argv[1]
ROOT = Path('.'); OUT = ROOT / f'vox_{VOICE}'; OUT.mkdir(exist_ok=True)
H = '/Users/eugene/nullalgo/simons/.claude/skills/x-backtest-post/scripts'

def run(*a): subprocess.run(a, check=True)
def dur(p): return float(subprocess.run(['ffprobe','-v','error','-show_entries','format=duration','-of','csv=p=0',str(p)],capture_output=True,text=True).stdout)
EDGE = 'silenceremove=start_periods=1:start_threshold=-42dB:start_silence=0.03,areverse,silenceremove=start_periods=1:start_threshold=-42dB:start_silence=0.03,areverse'
FADE = 'afade=t=in:d=0.008,areverse,afade=t=in:d=0.02,areverse'
CLEAN = 'highpass=f=70,lowpass=f=10000,adeclick'   # 고역 잡음·클릭 정리(Gemini 후보)

def cut(src, a, b, dst, clean=True):
    af = f'{EDGE},{FADE}' + (f',{CLEAN}' if clean else '')
    args = ['ffmpeg','-v','error','-y','-i',str(src),'-ss',str(a)] + (['-to',str(b)] if b else []) + ['-af',af,'-ar','44100','-ac','2',str(dst)]
    run(*args)

def cutx(src, a, b, dst):   # 무음 탐지로 얻은 정확한 구간만 자른다(쉼 구간의 잡음 때문에 자동 무음 제거가 안 먹는다)
    af = 'afade=t=in:d=0.012,areverse,afade=t=in:d=0.025,areverse,' + CLEAN
    run('ffmpeg','-v','error','-y','-i',str(src),'-ss',str(a),'-to',str(b),'-af',af,'-ar','44100','-ac','2',str(dst))

ph = {}
if VOICE == 'gemini':
    V = ROOT / 'vo'
    for k in ('L1','L4','L5','L6','L7','L8'): cut(V/f'{k}.wav',0,None,OUT/f'{k}.wav')
    cutx(V/'L2.wav',0.15,1.95,OUT/'P1.wav'); cutx(V/'L2.wav',2.55,5.15,OUT/'P2.wav'); cutx(V/'L2.wav',5.58,7.50,OUT/'P3.wav')
    cutx(V/'L3.wav',3.40,4.15,OUT/'B1.wav'); cutx(V/'L3.wav',5.95,7.52,OUT/'B2.wav')
    run('ffmpeg','-v','error','-y','-f','lavfi','-t','0.12','-i','anullsrc=r=44100:cl=stereo',str(OUT/'gap.wav'))
    run('ffmpeg','-v','error','-y','-i',str(OUT/'B1.wav'),'-i',str(OUT/'gap.wav'),'-i',str(OUT/'B2.wav'),'-filter_complex','[0][1][2]concat=n=3:v=0:a=1','-ar','44100','-ac','2',str(OUT/'B.wav'))
    cutx(V/'L3.wav',7.97,9.62,OUT/'C.wav'); cutx(V/'L3.wav',10.25,11.20,OUT/'D.wav'); cutx(V/'L3.wav',11.72,13.15,OUT/'E.wav')
else:
    T = {'L1':'속설 검증 여덟 번째. 볼린저밴드 하단에 닿으면 반등한다는 말, 문장 하나로 확인해 봅니다.',
         'P1':'문장이 조건으로 풀립니다.','P2':'하단을 찍고 중심선을 넘으면 매수,','P3':'상단을 넘으면 매도입니다.',
         'B':'하단 터치 인정 기간은 십 거래일,','C':'리밸런싱과 익절은 없음,','D':'기간은 오 년,','E':'자본은 천만 원.',
         'L4':'조건이 채워지면 확정하고 백테스트를 시작합니다.','L5':'과거 오 년 데이터로 매수와 매도를 하나씩 모의 체결합니다.',
         'L6':'결과입니다. 수익률 마이너스 칠십육 점 육 삼 퍼센트, 최대 낙폭 마이너스 칠십팔 점 이 사 퍼센트.',
         'L7':'같은 기간 코덱스 코스닥 백오십은 마이너스 일 점 팔 퍼센트였습니다.','L8':'같은 문장은 본문 링크에서 직접 돌려 볼 수 있습니다.'}
    for k,t in T.items():
        run('say','-v','Yuna','-r','180','-o',str(OUT/f'{k}.aiff'),t)
        cut(OUT/f'{k}.aiff',0,None,OUT/f'{k}.wav',clean=False)
D = {k: dur(OUT/f'{k}.wav') for k in ['L1','P1','P2','P3','B','C','D','E','L4','L5','L6','L7','L8']}

t0 = int(open('frames/index.tsv').readline().split('\t')[1])
plan = json.load(open('plan.json')); cl = plan['clips']
def real(c): return (c['to']-c['from'])/1000
def base(c): return c['dur'] if 'card' in c else real(c)/c['speed']
press = {4:31.53,5:34.95,6:39.95,7:43.35,8:46.78}   # 칩 누른 시각(녹화 시계, 초)
src0 = lambda i: (cl[i]['from']-t0)/1000
D_ = {i: base(cl[i]) for i in range(len(cl))}
g = 0.25; starts = {}; S = {}

# ③ 해석 카드: 칩 클릭 전까지의 구간만 쓰고(반복 방지) 문구 길이만큼 늘린다
cl[3]['to'] = cl[4]['from']
d1_need = D['L1'] + 0.4 + 0.3 - (2.6 + 0)           # 제목 2.6 이후 ①~② 안에 L1이 끝나야 한다
D_[1] = max(D_[1], d1_need - D_[2])
D_[3] = 0.3 + D['P1'] + g + D['P2'] + g + D['P3'] + 0.4
# 칩: 문구가 '누르는 순간'에 끝나도록
chip_ph = {4:'B',5:'C',6:None,7:'D',8:'E'}
offs = {}
for i,k in chip_ph.items():
    if not k: continue
    po = press[i] - src0(i)                           # 클립 안에서 누르는 시각(1배속 기준)
    off = max(0.2, po + 0.3 - D[k]); offs[i] = off
    D_[i] = max(D_[i], off + D[k] + 0.25)
# ⑤ 확정, ⑥ 실행, ⑦ 결과
D_[9] = D_[9] + 0.0; need5 = 0.2 + D['L4'] + 0.2
if D_[9]+D_[10] < need5: k=need5/(D_[9]+D_[10]); D_[9]*=k; D_[10]*=k
need6 = 0.2 + D['L5'] + 0.2
if D_[11]+D_[12] < need6: k=need6/(D_[11]+D_[12]); D_[11]*=k; D_[12]*=k
D_[14] = max(D_[14], 0.3 + D['L6'] + 0.3 - D_[13])
D_[15] = max(D_[15], 0.3 + D['L7'] + 0.3)
# 시각 계산
t = 0
for i in range(len(cl)): S[i] = t; t += D_[i]
end_need = S[16] + 0.4 + D['L8'] + 0.6
D_[17] = max(D_[17], end_need - S[17])
# 적용
for i,c in enumerate(cl):
    if 'card' in c: c['dur'] = round(D_[i],3)
    else: c['speed'] = round(real(c)/D_[i], 4)
cl[12]['badge'] = '빨리 감기 ×%d' % round(cl[12]['speed'])
json.dump(plan, open(f'plan_{VOICE}.json','w'), ensure_ascii=False)
t = 0
for i in range(len(cl)): S[i] = t; t += D_[i]
total = t
# 줄 시작 시각
starts['L1']=0.4; a=S[3]+0.3
for k in ('P1','P2','P3'): starts[k]=a; a+=D[k]+g
for i,k in chip_ph.items():
    if k: starts[k]=S[i]+offs[i]
starts['L4']=S[9]+0.2; starts['L5']=S[11]+0.2; starts['L6']=S[13]+0.3; starts['L7']=S[15]+0.3; starts['L8']=S[16]+0.4
order=['L1','P1','P2','P3','B','C','D','E','L4','L5','L6','L7','L8']
prev=0; ok=True
for k in order:
    e=starts[k]+D[k]; gap=starts[k]-prev
    if gap < 0.05 or e > total: ok=False
    print(f'{k:3s} {starts[k]:6.2f} → {e:6.2f} ({D[k]:.2f}s) 간격 {gap:5.2f}'+('  ← 문제' if gap<0.05 else '')); prev=e
print('총 길이 %.2f'%total, 'OK' if ok else '문제 있음')
run('uv','run','--project','/Users/eugene/nullalgo/simons','python',f'{H}/render_studio.py',f'plan_{VOICE}.json',f'silent_{VOICE}.mp4')
inputs=['-i',f'silent_{VOICE}.mp4']+sum([['-i',str(OUT/f'{k}.wav')] for k in order],[])
fc=''.join(f'[{n+1}:a]adelay={int(starts[k]*1000)}|{int(starts[k]*1000)}[a{n}];' for n,k in enumerate(order))
fc+=''.join(f'[a{n}]' for n in range(len(order)))+f'amix=inputs={len(order)}:normalize=0:duration=longest,loudnorm=I=-17:TP=-3:LRA=11,aresample=48000,apad=whole_dur={total}[aout]'
run('ffmpeg','-v','error','-y',*inputs,'-filter_complex',fc,'-map','0:v','-map','[aout]','-c:v','copy','-c:a','aac','-b:a','192k','-ar','48000','-t',str(total),'-movflags','+faststart',f'final_{VOICE}.mp4')
json.dump({'starts':starts,'dur':D,'S':S,'total':total},open(f'timing_{VOICE}.json','w'))
print('done',f'final_{VOICE}.mp4')
