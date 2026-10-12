// 영상 앞뒤에 붙이는 1920×1080 카드를 그린다(널스탁 다크 팔레트).
// 사용: node card.mjs <spec.json> <out.png>
//   spec: { "eyebrow": "속설 검증 #1", "title": "…", "subtitle": "…",
//           "stats": [["투자 수익률", "-12.3%"], …],   // 있으면 수치 격자(끝 카드)
//           "footer": "…" }
// 평가 어휘(좋다·나쁘다·통한다)는 넣지 않는다 — 수치와 정의만.
import { chromium } from 'playwright';
import fs from 'fs';

const [, , specPath, out] = process.argv;
const s = JSON.parse(fs.readFileSync(specPath, 'utf8'));
const esc = (t) => String(t ?? '').replace(/[&<>]/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;' })[c]);
const tone = (v) => (/^-/.test(v) ? '#6ea8ff' : /^\+/.test(v) ? '#ff6b6b' : '#f3f1ec'); // 앱과 같은 손익 색(손실=파랑, 이익=빨강)

const stats = (s.stats || []).map(([k, v]) => `<div class="stat"><div class="k">${esc(k)}</div><div class="v" style="color:${tone(v)}">${esc(v)}</div></div>`).join('');
const html = `<!doctype html><html><head><meta charset="utf-8"><style>
  * { margin: 0; box-sizing: border-box; }
  body { width: 1920px; height: 1080px; background: radial-gradient(1200px 700px at 30% 20%, #26211d 0%, #141312 60%); color: #f3f1ec;
         font-family: 'Apple SD Gothic Neo', sans-serif; display: flex; flex-direction: column; justify-content: center; padding: 0 160px; }
  .brand { position: absolute; top: 72px; left: 160px; font-size: 34px; font-weight: 800; letter-spacing: -0.5px; }
  .brand b { color: #f07a4a; margin-right: 14px; font-weight: 800; }
  .eyebrow { display: inline-block; align-self: flex-start; background: #f07a4a; color: #fff; font-size: 34px; font-weight: 800;
             padding: 12px 28px; border-radius: 999px; margin-bottom: 44px; }
  .title { font-size: ${s.stats ? 72 : 108}px; font-weight: 800; line-height: 1.22; letter-spacing: -2px; }
  .subtitle { margin-top: 36px; font-size: 40px; color: #b9b3aa; font-weight: 600; line-height: 1.45; }
  .grid { margin-top: 56px; display: grid; grid-template-columns: repeat(${Math.min((s.stats || []).length, 4)}, 1fr); gap: 28px; }
  .stat { background: #1e1c1a; border: 1px solid #34302b; border-radius: 28px; padding: 34px 38px; }
  .k { font-size: 30px; color: #b9b3aa; font-weight: 600; } .v { margin-top: 14px; font-size: 64px; font-weight: 800; letter-spacing: -1px; }
  .footer { position: absolute; bottom: 72px; left: 160px; right: 160px; font-size: 32px; color: #8f897f; font-weight: 600; }
</style></head><body>
  <div class="brand"><b>NS</b>널스탁</div>
  ${s.eyebrow ? `<div class="eyebrow">${esc(s.eyebrow)}</div>` : ''}
  <div class="title">${esc(s.title).replace(/\n/g, '<br>')}</div>
  ${s.subtitle ? `<div class="subtitle">${esc(s.subtitle).replace(/\n/g, '<br>')}</div>` : ''}
  ${stats ? `<div class="grid">${stats}</div>` : ''}
  ${s.footer ? `<div class="footer">${esc(s.footer)}</div>` : ''}
</body></html>`;

const browser = await chromium.launch();
const page = await browser.newPage({ viewport: { width: 1920, height: 1080 } });
await page.setContent(html);
await page.screenshot({ path: out });
await browser.close();
console.log(out);
