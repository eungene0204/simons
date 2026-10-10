// 녹화 브라우저에 붙어 한 동작씩 실행한다. step.mjs와 같되 type은 사람처럼 한 글자씩 친다.
// 사용: node rstep.mjs <goto|type|click|wait|shot|text|scroll|hold> [인자]   hold <초>: 마우스를 화면 구석으로 치우고 정지(결과 장면용)   — 동작 시각(ms)을 marks.log에 남긴다
import { chromium } from 'playwright';
import fs from 'fs';

const [, , action, arg] = process.argv;
const browser = await chromium.connectOverCDP('http://localhost:9222');
const page = browser.contexts().flatMap((c) => c.pages()).find((p) => p.url().startsWith('http://localhost'));
fs.appendFileSync('marks.log', `${Date.now()} ${action} ${arg ?? ''}\n`);
if (action === 'goto') await page.goto(arg, { waitUntil: 'domcontentloaded', timeout: 60000 });
if (action === 'type') {
  const box = page.locator('textarea, input[placeholder*="입력"], input[placeholder*="적어"]').last();
  await box.click();
  await box.pressSequentially(arg, { delay: 35 });
  await page.waitForTimeout(600);
  await page.keyboard.press('Enter');
}
if (action === 'click') await page.getByText(arg, { exact: false }).first().click();
if (action === 'wait') await page.waitForTimeout(Number(arg) * 1000);
if (action === 'hold') { await page.mouse.move(1430, 120, { steps: 10 }); await page.waitForTimeout(Number(arg || 5) * 1000); }
if (action === 'scroll') await page.mouse.wheel(0, Number(arg));
if (['shot', 'type', 'click', 'wait', 'scroll'].includes(action)) await page.screenshot({ path: 'cur.png' });
if (action === 'text') console.log(await page.innerText('body'));
console.log('url:', page.url());
await browser.close();
