// 로그인은 녹화 밖에서 끝내고, 로그인 상태를 넘겨받은 새 컨텍스트만 녹화한다.
// 사용: GUEST_PW=<비밀번호> node record_server.mjs &   종료: kill -TERM <pid> → 영상 파일 확정, 경로 출력
import { chromium } from 'playwright';

const BASE = process.env.NULLSTOCK_BASE || 'http://localhost:3000';
const GUEST_ID = process.env.GUEST_ID || 'guest_5312';
const SIZE = { width: 1440, height: 900 };
if (!process.env.GUEST_PW) throw new Error('GUEST_PW 환경변수가 없다');

const browser = await chromium.launch({ args: ['--remote-debugging-port=9222'], handleSIGTERM: false });
const login = await browser.newContext({ viewport: SIZE });
const lp = await login.newPage();
await lp.goto(`${BASE}/guest`, { waitUntil: 'domcontentloaded', timeout: 60000 });
await lp.waitForTimeout(2500);
await lp.fill('input[placeholder="guest_1234"]', GUEST_ID);
await lp.fill('input[type="password"]', process.env.GUEST_PW);
await lp.click('button:has-text("입장")');
await lp.waitForSelector('text=널스탁 데모', { timeout: 30000 });
const state = await login.storageState();
await login.close();

const ctx = await browser.newContext({ viewport: SIZE, storageState: state, recordVideo: { dir: 'videos', size: SIZE } });
const page = await ctx.newPage();
await page.goto(`${BASE}/analytics/new`, { waitUntil: 'networkidle', timeout: 60000 });
console.log('ready', page.url(), Date.now());

process.on('SIGTERM', async () => {
  const video = page.video();
  await ctx.close();
  console.log('video', await video.path());
  await browser.close();
  process.exit(0);
});
await new Promise(() => {});
