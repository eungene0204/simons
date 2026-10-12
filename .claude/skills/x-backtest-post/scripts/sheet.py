# 스튜디오 녹화 폴더(frames/index.tsv)에서 녹화 시작 기준 시각들의 프레임을 모아 한 장으로 — 편집점 찾기용
# 사용: python sheet.py out.png 열수 <상대초...> — 녹화 시작 기준 시각의 프레임을 모아 한 장으로
import sys, bisect
from PIL import Image, ImageDraw
rows=[l.split('\t') for l in open('frames/index.tsv').read().splitlines() if l]
names=[r[0] for r in rows]; times=[int(r[1]) for r in rows]; t0=times[0]
out, cols, secs = sys.argv[1], int(sys.argv[2]), [float(x) for x in sys.argv[3:]]
W,H=480,270; n=len(secs); r=(n+cols-1)//cols
sheet=Image.new('RGB',(W*cols,H*r))
for i,s in enumerate(secs):
    j=max(bisect.bisect_right(times,t0+s*1000)-1,0)
    im=Image.open(f'frames/{names[j]}.jpg').resize((W,H))
    ImageDraw.Draw(im).text((8,8),f'{s:.1f}s',fill=(255,255,0))
    sheet.paste(im,((i%cols)*W,(i//cols)*H))
sheet.save(out)
