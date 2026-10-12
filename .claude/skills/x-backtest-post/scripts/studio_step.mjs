// studio_server.mjs 브라우저에서 한 동작씩 실행한다(표준 흐름에서 벗어난 장면을 손으로 찍을 때).
// 표준 흐름 전체는 studio_record.mjs가 한 번에 돌린다.
//
// 사용: node studio_step.mjs <동작> [인자...]
//   type <문장> · click <보이는 글자> · label <aria-label> · card <이름> <글자A> <글자B>
//   waitfor <이름> <글자> [초] · wait <초> · hold <초> · text · shot
import fs from 'fs';
import { connect, typePrompt, press, visibleText, card, waitFor, hold } from './studio_lib.mjs';

const [, , action, ...args] = process.argv;
const { browser, page } = await connect();

if (action === 'type') await typePrompt(page, args.join(' '));
if (action === 'click') await press(page, visibleText(page, args.join(' ')), args.join(' '));
if (action === 'label') await press(page, page.locator(`[aria-label="${args.join(' ')}"]:visible`).first(), args.join(' '), 'label');
if (action === 'card') console.log(args[0], JSON.stringify(await card(page, ...args)));
if (action === 'waitfor') console.log(args[0], JSON.stringify(await waitFor(page, args[0], args[1], Number(args[2] || 300))));
if (action === 'wait') await page.waitForTimeout(Number(args[0]) * 1000);
if (action === 'hold') await hold(page, Number(args[0] || 3));
if (action === 'text') console.log(await page.innerText('body'));
if (['shot', 'type', 'click', 'label', 'wait', 'hold'].includes(action)) await page.screenshot({ path: 'cur.png' });
fs.writeFileSync('last_url.txt', page.url());
await browser.close();
