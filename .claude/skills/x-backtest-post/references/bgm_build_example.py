import json, subprocess
H='/Users/eugene/nullalgo/simons/.claude/skills/x-backtest-post/scripts'
p=json.load(open('plan.json')); cl=p['clips']; real=lambda c:(c['to']-c['from'])/1000
cl[2]['speed']=1.2; cl[2]['badge']='빨리 감기 ×1.2'; cl[2]['caption']='② 널스탁이 문장을 읽고 매수·매도 조건으로 해석합니다'
cl[3]['caption']='③ 널스탁이 해석한 전략을 항목별로 정리해 줍니다 — 유니버스·매수·매도·종목 수·손절'
vals=['하단 터치 인정 기간 10거래일','익절 안 함','리밸런싱 안 함','백테스트 기간 최근 5년','초기 자본 1,000만원']
for i,v in zip(range(4,9),vals): cl[i]['speed']=1.0; cl[i]['caption']=f'④ 문장에 없던 값은 버튼으로 답합니다 · {v}'
cl[9]['caption']=cl[10]['caption']='⑤ 조건이 모두 채워지면 요약을 확인하고 확정합니다'
cl[11]['caption']=cl[12]['caption']='⑥ 과거 5년 일별 데이터로 매수·매도를 하나씩 모의 체결합니다'
cl[12]['speed']=6.0; cl[12]['badge']='빨리 감기 ×6'; cl[13]['caption']='⑦ 백테스트 결과'
json.dump(p,open('plan_bgm.json','w'),ensure_ascii=False)
S={}; t=0
for i,c in enumerate(cl): S[i]=t; t+=(c['dur'] if 'card' in c else real(c)/c['speed'])
total=t; print('총 %.2f'%total)
subprocess.run(['uv','run','--project','/Users/eugene/nullalgo/simons','python',f'{H}/render_studio.py','plan_bgm.json','silent_bgm.mp4'],check=True)
def mux(script, wav, out, lufs):
    subprocess.run(['uv','run','--project','/Users/eugene/nullalgo/simons','--with','numpy','python',script,wav,f'{total:.2f}','2.6',f'{S[4]:.2f}',f'{S[11]:.2f}',f'{S[13]:.2f}',f'{S[17]:.2f}'],check=True)
    r=subprocess.run(['ffmpeg','-hide_banner','-nostats','-i',wav,'-af',f'loudnorm=I={lufs}:TP=-3:LRA=11:print_format=json','-f','null','-'],capture_output=True,text=True).stderr
    j=json.loads(r[r.rindex('{'):r.rindex('}')+1])
    ln=f"loudnorm=I={lufs}:TP=-3:LRA=11:measured_I={j['input_i']}:measured_TP={j['input_tp']}:measured_LRA={j['input_lra']}:measured_thresh={j['input_thresh']}:offset={j['target_offset']}:linear=true,alimiter=limit=0.63:level=disabled,aresample=48000"
    subprocess.run(['ffmpeg','-v','error','-y','-i','silent_bgm.mp4','-i',wav,'-filter_complex',f'[1:a]{ln}[a]','-map','0:v','-map','[a]','-c:v','copy','-c:a','aac','-b:a','192k','-ar','48000','-t',f'{total:.3f}','-movflags','+faststart',out],check=True)
mux('bgm_bright.py','bgm_bright.wav','final_bright.mp4',-17)
mux('bgm_calm.py','bgm_calm.wav','final_calm.mp4',-18)
json.dump({'S':S,'total':total},open('timeline_bgm.json','w')); print('done')
