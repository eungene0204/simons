// 줌 연출 영상용 녹화 브라우저. 로그인은 녹화 밖에서 끝내고, 로그인 상태를 넘겨받은 새 화면을
// 2배 해상도(1440×810 CSS px → 2880×1620)로 띄운 뒤 CDP 스크린캐스트 프레임을 JPEG로 저장한다.
// Playwright recordVideo는 비트레이트가 1Mbps로 묶여 줌을 당기면 글자가 뭉개진다 — 그래서 프레임을 직접 받는다.
// 화면에는 가짜 커서와 클릭 물결을 심는다(헤드리스는 커서가 찍히지 않는다).
//
// 홍보 CF용 변형(studio_server.mjs 기반): START_PATH(시작 화면)와 DEMO_LIVE_QUOTES=1(시연용 시세 움직임)을 더했다.
// DEMO_LIVE_QUOTES=1이면 /api/stock/prices 응답(마지막 종가)에 작은 무작위 걸음을 얹어 장이 닫힌 날에도 시세가
// 움직이는 화면을 찍는다 — 실제 시세가 아니므로 영상의 그 장면에 반드시 '시연용 연출 화면'을 표기한다.
// 사용: GUEST_PW=<비밀번호> [START_PATH=/backtest] [DEMO_LIVE_QUOTES=1] node cf_server.mjs &
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
if (process.env.DEMO_LIVE_QUOTES === '1') {
  // 종목마다 결정적 난수(시드 고정)로 0.1% 안팎씩 걷는다. 호가 단위에 맞춰 반올림하고 거래량은 늘기만 한다.
  const state = {};
  let seed = 20261012;
  const rand = () => ((seed = (seed * 1103515245 + 12345) % 2147483648) / 2147483648);
  const gauss = () => Math.sqrt(-2 * Math.log(rand() + 1e-9)) * Math.cos(2 * Math.PI * rand());
  const tick = (p) => (p < 2000 ? 1 : p < 5000 ? 5 : p < 20000 ? 10 : p < 50000 ? 50 : p < 200000 ? 100 : p < 500000 ? 500 : 1000);
  await ctx.route('**/api/stock/prices', async (route) => {
    const res = await route.fetch();
    const data = await res.json().catch(() => null);
    if (!data || typeof data !== 'object') return route.fulfill({ response: res });
    for (const [sym, q] of Object.entries(data)) {
      if (!q || !(q.price > 0) || !/^\d{6}$/.test(sym)) continue;
      const s = (state[sym] ??= { price: q.price, prev: q.previousClose > 0 ? q.previousClose : q.price / (1 + (q.changePercent || 0) / 100), volume: q.volume || 0 });
      if (rand() < 0.75) {
        const next = s.price * (1 + gauss() * 0.0011);
        const t = tick(next);
        s.price = Math.max(t, Math.round(next / t) * t);
      }
      s.volume += Math.round(rand() * 4000 + 300);
      data[sym] = { ...q, price: s.price, changePercent: Math.round((s.price / s.prev - 1) * 10000) / 100, volume: s.volume, source: 'demo' };
    }
    await route.fulfill({ response: res, json: data });
  });
}

const page = await ctx.newPage();
await page.goto(`${BASE}${process.env.START_PATH || '/analytics/new'}`, { waitUntil: 'networkidle', timeout: 60000 });
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
