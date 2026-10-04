// 임시 Playwright 브라우저를 CDP(9222)로 띄워 두고 데모 게스트로 로그인한 상태를 유지한다.
// 사용: GUEST_PW=<비밀번호> node browser_server.mjs &   (비밀번호는 출력·기록하지 않는다)
import { chromium } from 'playwright';

const BASE = process.env.NULLSTOCK_BASE || 'http://localhost:3000';
const GUEST_ID = process.env.GUEST_ID || 'guest_5312';
if (!process.env.GUEST_PW) throw new Error('GUEST_PW 환경변수가 없다');

const browser = await chromium.launch({ args: ['--remote-debugging-port=9222'] });
const ctx = await browser.newContext({ viewport: { width: 1440, height: 900 } });
const page = await ctx.newPage();
await page.goto(`${BASE}/guest`, { waitUntil: 'domcontentloaded', timeout: 60000 });
// 폼이 hydrate되기 전에 제출하면 클릭이 조용히 무시된다 — 잠시 기다린다(2026-10-04 실측)
await page.waitForTimeout(2500);
await page.fill('input[placeholder="guest_1234"]', GUEST_ID);
await page.fill('input[type="password"]', process.env.GUEST_PW);
await page.click('button:has-text("입장")');
// 로그인 완료 = 헤더에 계정 이름이 보일 때. 고정 대기는 세션이 설정되기 전에 넘어가 랜딩으로 튕긴다
await page.waitForSelector('text=널스탁 데모', { timeout: 30000 }).catch(() => {
  throw new Error('게스트 로그인 실패 — 아이디·비밀번호, 레이트리밋(아이디당 10회/15분), 만료 여부를 확인한다');
});
await page.goto(`${BASE}/analytics/new`, { waitUntil: 'domcontentloaded', timeout: 60000 });
console.log('ready', page.url());
await new Promise(() => {});
