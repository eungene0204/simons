// 켜 둔 브라우저에 붙어 한 동작씩 실행한다.
// 사용: node step.mjs <goto|type|click|wait|shot|text> [인자]
//   type  : 현재 보이는 입력창(textarea 또는 '입력/적어' placeholder input)에 채우고 Enter
//   click : 보이는 텍스트로 클릭(부분 일치)   wait: 초   shot: cur.png 저장   text: 본문 텍스트 출력
import { chromium } from 'playwright';

const [, , action, arg] = process.argv;
const browser = await chromium.connectOverCDP('http://localhost:9222');
const page = browser.contexts()[0].pages()[0];
if (action === 'goto') await page.goto(arg, { waitUntil: 'domcontentloaded', timeout: 60000 });
if (action === 'type') {
  await page.locator('textarea, input[placeholder*="입력"], input[placeholder*="적어"]').last().fill(arg);
  await page.keyboard.press('Enter');
}
if (action === 'click') await page.getByText(arg, { exact: false }).first().click();
if (action === 'wait') await page.waitForTimeout(Number(arg) * 1000);
if (['shot', 'type', 'click', 'wait'].includes(action)) await page.screenshot({ path: 'cur.png' });
if (action === 'text') console.log(await page.innerText('body'));
console.log('url:', page.url());
await browser.close();
