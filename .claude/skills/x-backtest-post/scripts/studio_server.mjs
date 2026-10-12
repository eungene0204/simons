// 줌 연출 영상용 녹화 브라우저. 로그인은 녹화 밖에서 끝내고, 로그인 상태를 넘겨받은 새 화면을
// 2배 해상도(1440×810 CSS px → 2880×1620)로 띄운 뒤 CDP 스크린캐스트 프레임을 JPEG로 저장한다.
// Playwright recordVideo는 비트레이트가 1Mbps로 묶여 줌을 당기면 글자가 뭉개진다 — 그래서 프레임을 직접 받는다.
// 화면에는 가짜 커서와 클릭 물결을 심는다(헤드리스는 커서가 찍히지 않는다).
//
// 사용: GUEST_PW=<비밀번호> node studio_server.mjs &   → frames/<번호>.jpg + frames/index.tsv(번호\t시각ms)
// 종료: kill -TERM <pid> (스크린캐스트를 멈추고 닫는다)
import { chromium } from 'playwright';
import fs from 'fs';

const BASE = process.env.NULLSTOCK_BASE || 'http://localhost:3000';
const GUEST_ID = process.env.GUEST_ID || 'guest_5312';
const VIEWPORT = { width: 1440, height: 810 };
if (!process.env.GUEST_PW) throw new Error('GUEST_PW 환경변수가 없다');

const CURSOR_SCRIPT = `(() => {
  const install = () => {
    if (document.getElementById('__studio_cursor')) return;
    const c = document.createElement('div');
    c.id = '__studio_cursor';
    c.innerHTML = '<svg width="30" height="30" viewBox="0 0 24 24"><path d="M5 2.5l13.5 8.2-6 1.3-3.1 5.8z" fill="#fff" stroke="#111" stroke-width="1.4" stroke-linejoin="round"/></svg>';
    Object.assign(c.style, { position: 'fixed', left: '0', top: '0', zIndex: '2147483647', pointerEvents: 'none',
      transform: 'translate(-200px,-200px)', filter: 'drop-shadow(0 2px 3px rgba(0,0,0,.45))' });
    document.documentElement.appendChild(c);
    document.addEventListener('mousemove', (e) => { c.style.transform = 'translate(' + (e.clientX - 5) + 'px,' + (e.clientY - 3) + 'px)'; }, true);
    document.addEventListener('mousedown', (e) => {
      const r = document.createElement('div');
      Object.assign(r.style, { position: 'fixed', left: (e.clientX - 22) + 'px', top: (e.clientY - 22) + 'px', width: '44px', height: '44px',
        borderRadius: '50%', border: '3px solid #f07a4a', background: 'rgba(240,122,74,.18)', zIndex: '2147483646', pointerEvents: 'none',
        transition: 'transform .5s ease-out, opacity .5s ease-out', transform: 'scale(.35)', opacity: '1' });
      document.documentElement.appendChild(r);
      requestAnimationFrame(() => requestAnimationFrame(() => { r.style.transform = 'scale(1.7)'; r.style.opacity = '0'; }));
      setTimeout(() => r.remove(), 700);
    }, true);
  };
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', install); else install();
})();`;

const browser = await chromium.launch({ args: ['--remote-debugging-port=9222', '--force-device-scale-factor=2'], handleSIGTERM: false });
const login = await browser.newContext({ viewport: VIEWPORT });
const lp = await login.newPage();
await lp.goto(`${BASE}/guest`, { waitUntil: 'domcontentloaded', timeout: 60000 });
await lp.waitForTimeout(2500); // 폼이 hydrate되기 전에 제출하면 클릭이 조용히 무시된다
await lp.fill('input[placeholder="guest_1234"]', GUEST_ID);
await lp.fill('input[type="password"]', process.env.GUEST_PW);
await lp.click('button:has-text("입장")');
await lp.waitForSelector('text=널스탁 데모', { timeout: 30000 });
const state = await login.storageState();
await login.close();

const ctx = await browser.newContext({ viewport: VIEWPORT, deviceScaleFactor: 2, storageState: state });
await ctx.addInitScript(CURSOR_SCRIPT);
const page = await ctx.newPage();
await page.goto(`${BASE}/analytics/new`, { waitUntil: 'networkidle', timeout: 60000 });
await page.mouse.move(1300, 700);

fs.mkdirSync('frames', { recursive: true });
const index = fs.createWriteStream('frames/index.tsv');
const cdp = await ctx.newCDPSession(page);
let seq = 0;
cdp.on('Page.screencastFrame', async ({ data, metadata, sessionId }) => {
  const name = String(seq++).padStart(6, '0');
  fs.writeFileSync(`frames/${name}.jpg`, Buffer.from(data, 'base64'));
  index.write(`${name}\t${Math.round(metadata.timestamp * 1000)}\n`); // 동작 기록(marks.jsonl)과 같은 시계(ms)
  await cdp.send('Page.screencastFrameAck', { sessionId }).catch(() => {});
});
await cdp.send('Page.startScreencast', { format: 'jpeg', quality: 90, maxWidth: 2880, maxHeight: 1620, everyNthFrame: 2 });
console.log('ready', page.url(), Date.now());

process.on('SIGTERM', async () => {
  await cdp.send('Page.stopScreencast').catch(() => {});
  index.end();
  console.log('frames', seq);
  await browser.close();
  process.exit(0);
});
await new Promise(() => {});
